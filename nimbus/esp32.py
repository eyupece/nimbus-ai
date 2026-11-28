"""ESP32 gövdesi: Nimbus'un fiziksel bedeni (mikrofon, hoparlör, servolar, LED) Wi-Fi üzerinden.

Beyin dizüstünde kalır, ESP32 sadece kulak, ağız ve kas olur. ESP32 bir WebSocket istemcisi olarak bağlanır:

    ws://<dizüstü>:8766/esp32?anahtar=<NIMBUS_ESP32_ANAHTAR>

ESP32 -> dizüstü   ikili: mikrofon sesi (16 kHz, 16-bit mono PCM)
                   metin: {"tip": "merhaba", "surum": ...} | {"tip": "dokunma", "uzun": bool}
dizüstü -> ESP32   ikili: hoparlör sesi (24 kHz, 16-bit mono PCM)
                   metin: {"tip": "durum" | "jest" | "sustur", ...}

Ağız servosu ESP32'de, çalınan sesten hesaplanır (ağ gecikmesinden bağımsız, tam senkron).
Dizüstü kendini UDP yayınıyla duyurur (port 8767); ESP32 IP adresi yazmadan bulur.
"""

import asyncio
import hmac
import json
import socket
import time
from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

from websockets.asyncio.server import ServerConnection, serve

from .ses import CIKIS_HIZI, GIRIS_HIZI

PORT = 8766
DUYURU_PORTU = 8767
ONDEN_SN = 0.15  # ESP32 tamponunda önden tutulan ses: Wi-Fi titremesine karşı
DMA_SN = 0.04  # ESP32'nin I2S tamponu
SESSIZLIK = b"\0\0" * (GIRIS_HIZI // 10)  # ESP32 yokken 100 ms sessizlik


def yerel_ipler() -> list[str]:
    """Bu bilgisayarın yerel ağ IPv4 adresleri (ESP32'ye elle yazmak gerekirse)."""
    ipler: set[str] = set()
    try:
        for bilgi in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ipler.add(bilgi[4][0])
    except OSError:
        pass
    try:  # varsayılan ağ arayüzü (paket gönderilmez)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ipler.add(s.getsockname()[0])
    except OSError:
        pass
    return sorted(ip for ip in ipler if not ip.startswith(("127.", "169.254.")))


class Esp32Mikrofon:
    """Oturumun beklediği mikrofon arayüzü; ses ESP32'den gelir."""

    def __init__(self, kopru: "Esp32Kopru"):
        self.kopru = kopru
        self.ad = "ESP32 (INMP441)"

    async def oku(self) -> bytes:
        kuyruk = self.kopru._mikrofon
        if kuyruk is None:
            await asyncio.sleep(0.1)
            return SESSIZLIK
        try:
            return await asyncio.wait_for(kuyruk.get(), timeout=0.2)
        except asyncio.TimeoutError:
            return SESSIZLIK  # ESP32 bağlı değil ya da kopuk: gürültü tabanı bozulmasın

    def kapat(self) -> None:
        pass


class Esp32Akis:
    """Hoparlor'ün ses kartı yerine kullandığı akış: sesi gerçek zamanlı hızda ESP32'ye yollar.

    ESP32'de her an en fazla ONDEN_SN kadar ses birikir; böylece söz kesilince hemen susar
    ve `calinan_bayt` gerçekten duyulan sese yakın kalır.
    """

    def __init__(self, kopru: "Esp32Kopru"):
        self.kopru = kopru
        self._bitis = 0.0  # ESP32'ye gönderilmiş sesin çalınıp biteceği an

    def write(self, dilim: bytes) -> None:  # hoparlör iş parçacığından çağrılır
        simdi = time.monotonic()
        if self._bitis < simdi:
            self._bitis = simdi  # tampon boşalmış
        self.kopru._koy(bytes(dilim))
        self._bitis += len(dilim) / 2 / CIKIS_HIZI
        fazla = self._bitis - simdi - ONDEN_SN
        if fazla > 0:
            time.sleep(fazla)

    def get_output_latency(self) -> float:
        return ONDEN_SN + DMA_SN

    def temizle(self) -> None:
        """Söz kesildi: ESP32 tamponundaki sesi de at."""
        self._bitis = 0.0
        self.kopru._koy(json.dumps({"tip": "sustur"}))

    def close(self) -> None:
        pass


class Esp32Kopru:
    """WebSocket sunucusu + gövde arayüzü. Aynı anda tek ESP32 bağlı olur (yenisi eskisini düşürür)."""

    ekran_var = False

    def __init__(self, anahtar: str, port: int = PORT, duyuru: bool = True, dokunma=None):
        self.anahtar = anahtar
        self.port = port
        self.duyuru = duyuru
        self.dokunma = dokunma  # fn(uzun: bool); olay döngüsünde çağrılır
        self.baglanti: ServerConnection | None = None
        self.bilgi: dict = {}
        self._dongu: asyncio.AbstractEventLoop | None = None
        self._giden: asyncio.Queue | None = None
        self._mikrofon: asyncio.Queue | None = None
        self._sunucu = None
        self._gorevler: list[asyncio.Task] = []
        self._son_durum = "uyku"

    def mikrofon(self) -> Esp32Mikrofon:
        return Esp32Mikrofon(self)

    def akis(self) -> Esp32Akis:
        return Esp32Akis(self)

    # ---------- Sunucu ----------
    def _kontrol(self, baglanti: ServerConnection, istek):
        adres = urlparse(istek.path)
        if adres.path != "/esp32":
            return baglanti.respond(HTTPStatus.NOT_FOUND, "Bulunamadı\n")
        gelen = parse_qs(adres.query).get("anahtar", [""])[0]
        if not hmac.compare_digest(gelen.encode(), self.anahtar.encode()):
            print("⚠️  ESP32 bağlantısı reddedildi: anahtar yanlış (ESP32'yi ./n esp32-yukle ile yeniden yükle)",
                  flush=True)
            return baglanti.respond(HTTPStatus.FORBIDDEN, "Anahtar yanlış\n")
        return None

    async def _baglanti(self, baglanti: ServerConnection) -> None:
        eski, self.baglanti = self.baglanti, baglanti
        if eski:
            await eski.close()
        ip = baglanti.remote_address[0] if baglanti.remote_address else "?"
        try:
            await baglanti.send(json.dumps({"tip": "durum", "ad": self._son_durum}))
            async for mesaj in baglanti:
                if isinstance(mesaj, bytes):
                    if self._mikrofon.full():
                        self._mikrofon.get_nowait()  # gecikme birikmesin: en eskiyi at
                    self._mikrofon.put_nowait(mesaj)
                    continue
                try:
                    olay = json.loads(mesaj)
                except ValueError:
                    continue
                if olay.get("tip") == "merhaba":
                    self.bilgi = olay
                    print(f"🔌 ESP32 bağlandı ({ip}, yazılım {olay.get('surum', '?')})", flush=True)
                elif olay.get("tip") == "dokunma" and self.dokunma:
                    self.dokunma(bool(olay.get("uzun")))
        except Exception:
            pass
        finally:
            if self.baglanti is baglanti:
                self.baglanti = None
                print("🔌 ESP32 bağlantısı koptu, yeniden bağlanması bekleniyor.", flush=True)

    async def baslat(self) -> None:
        self._dongu = asyncio.get_running_loop()
        self._giden = asyncio.Queue()
        self._mikrofon = asyncio.Queue(maxsize=50)
        self._sunucu = await serve(self._baglanti, "0.0.0.0", self.port, process_request=self._kontrol,
                                   max_size=2**20, compression=None)
        self.port = self._sunucu.sockets[0].getsockname()[1]
        self._gorevler.append(asyncio.create_task(self._gonderici()))
        if self.duyuru:
            self._gorevler.append(asyncio.create_task(self._duyur()))
        ipler = ", ".join(yerel_ipler()) or "?"
        print(f"🔌 ESP32 bekleniyor: port {self.port} (bu bilgisayar: {ipler})", flush=True)

    async def kapat(self) -> None:
        for g in self._gorevler:
            g.cancel()
        if self._sunucu:
            self._sunucu.close()

    async def _gonderici(self) -> None:
        """Tek gönderici: ses ve olaylar sırasıyla gider."""
        while True:
            veri = await self._giden.get()
            baglanti = self.baglanti
            if baglanti is None:
                continue
            try:
                await baglanti.send(veri)
            except Exception:
                pass

    async def _duyur(self) -> None:
        """ESP32 bağlı değilken her 2 saniyede bir yerel ağa 'buradayım' der."""
        mesaj = f"NIMBUS {self.port}".encode()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            while True:
                if self.baglanti is None:
                    hedefler = {"255.255.255.255"} | {ip.rsplit(".", 1)[0] + ".255" for ip in yerel_ipler()}
                    for hedef in hedefler:
                        try:
                            s.sendto(mesaj, (hedef, DUYURU_PORTU))
                        except OSError:
                            pass
                await asyncio.sleep(2)
        finally:
            s.close()

    def _koy(self, veri) -> None:
        """İş parçacığı güvenli gönderim."""
        if self._dongu is None or self.baglanti is None:
            return
        self._dongu.call_soon_threadsafe(self._giden.put_nowait, veri)

    # ---------- Gövde arayüzü ----------
    def agiz(self, aciklik: float) -> None:
        pass  # ESP32 ağzı çaldığı sesten kendisi hesaplıyor

    def jest(self, ad: str) -> None:
        self._koy(json.dumps({"tip": "jest", "ad": ad}))

    def durum(self, ad: str) -> None:
        self._son_durum = ad
        self._koy(json.dumps({"tip": "durum", "ad": ad}))

    def altyazi(self, kim: str, metin: str, ad: str = "Nimbus") -> None:
        pass

    def kart(self, baslik: str, metin: str) -> None:
        pass
