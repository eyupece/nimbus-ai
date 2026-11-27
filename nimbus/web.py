"""Tarayıcıdaki bulut yüz: küçük bir HTTP + WebSocket sunucusu ve ona bağlı gövde.

http://localhost:8765        -> web/index.html (bulut yüz)
ws://localhost:8765/canli     -> ağız / jest / durum / altyazı olayları
"""

import asyncio
import json
import webbrowser
from http import HTTPStatus

from websockets.asyncio.server import ServerConnection, serve
from websockets.datastructures import Headers
from websockets.http11 import Request, Response

from .ayarlar import KOK

SAYFA = KOK / "web" / "index.html"


class WebGovde:
    """Gövde olaylarını bağlı tüm tarayıcılara yayınlar.

    `agiz` hoparlör iş parçacığından çağrılır; olaylar olay döngüsüne güvenli şekilde aktarılır.
    """

    def __init__(self, port: int = 8765, tarayici_ac: bool = True, konsol=None):
        self.port = port
        self.tarayici_ac = tarayici_ac
        self.konsol = konsol  # jest/durumları terminale de yazmak için (opsiyonel)
        self._istemciler: set[ServerConnection] = set()
        self._dongu: asyncio.AbstractEventLoop | None = None
        self._son_agiz = -1.0
        self._son_durum = "uyku"

    # ---------- Sunucu ----------
    def _http(self, baglanti: ServerConnection, istek: Request) -> Response | None:
        if istek.path.startswith("/canli"):
            return None  # WebSocket el sıkışmasına devam
        if istek.path in ("/", "/index.html") or istek.path.startswith("/?"):
            govde = SAYFA.read_bytes()  # her istekte oku: tasarım değişince yenilemek yeter
            basliklar = Headers({"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"})
            return Response(200, "OK", basliklar, govde)
        return baglanti.respond(HTTPStatus.NOT_FOUND, "Bulunamadı\n")

    async def _baglanti(self, baglanti: ServerConnection) -> None:
        self._istemciler.add(baglanti)
        try:
            # Yeni açılan sayfa mevcut durumu bilsin
            await baglanti.send(json.dumps({"tip": "durum", "ad": self._son_durum}))
            await baglanti.wait_closed()
        finally:
            self._istemciler.discard(baglanti)

    async def baslat(self) -> None:
        self._dongu = asyncio.get_running_loop()
        await serve(self._baglanti, "localhost", self.port, process_request=self._http)
        adres = f"http://localhost:{self.port}"
        print(f"🌥  Bulut yüz: {adres}")
        if self.tarayici_ac:
            webbrowser.open(adres)

    # ---------- Yayın ----------
    def _gonder(self, mesaj: dict) -> None:
        if not self._dongu or not self._istemciler:
            return
        veri = json.dumps(mesaj, ensure_ascii=False)

        def yay():
            for istemci in list(self._istemciler):
                asyncio.ensure_future(self._guvenli_gonder(istemci, veri))

        self._dongu.call_soon_threadsafe(yay)

    @staticmethod
    async def _guvenli_gonder(istemci: ServerConnection, veri: str) -> None:
        try:
            await istemci.send(veri)
        except Exception:
            pass  # sekme kapandıysa önemli değil

    # ---------- Gövde arayüzü ----------
    def agiz(self, aciklik: float) -> None:
        aciklik = round(aciklik, 2)
        # Gözle fark edilmeyecek küçük değişimleri gönderme; kapanışı her zaman gönder
        if abs(aciklik - self._son_agiz) >= 0.03 or (aciklik == 0 and self._son_agiz != 0):
            self._son_agiz = aciklik
            self._gonder({"tip": "agiz", "aciklik": aciklik})

    def jest(self, ad: str) -> None:
        self._gonder({"tip": "jest", "ad": ad})
        if self.konsol:
            self.konsol.jest(ad)

    def durum(self, ad: str) -> None:
        self._son_durum = ad
        self._gonder({"tip": "durum", "ad": ad})
        if self.konsol:
            self.konsol.durum(ad)

    def altyazi(self, kim: str, metin: str, ad: str = "Nimbus") -> None:
        self._gonder({"tip": "altyazi", "kim": kim, "metin": metin, "ad": ad})
