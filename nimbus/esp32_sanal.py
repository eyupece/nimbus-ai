"""Sanal ESP32: donanım gelmeden ESP32 yolunu uçtan uca dener.

Bu bilgisayarın mikrofonu ve hoparlörü, gerçek ESP32 gibi WebSocket üzerinden Nimbus'a bağlanır:
    ./n --esp32-sanal
Ses, protokol, tampon ve söz kesme gerçek donanımdaki gibi çalışır; sadece servo/LED yerine
terminale yazılır.
"""

import asyncio
import json
import queue
import threading

import pyaudio
from websockets.asyncio.client import connect

from .ses import CIKIS_HIZI, FORMAT, GIRIS_HIZI, KANAL, mikrofon_sec

PARCA = 512  # ESP32 yazılımıyla aynı: 32 ms


class _Calici:
    """Gelen sesi kendi iş parçacığında çalar (ESP32'deki hoparlör görevi gibi)."""

    def __init__(self, pya):
        self.kuyruk: queue.Queue[bytes] = queue.Queue()
        self.akis = pya.open(format=FORMAT, channels=KANAL, rate=CIKIS_HIZI, output=True, frames_per_buffer=480)
        threading.Thread(target=self._dongu, daemon=True).start()

    def _dongu(self):
        while True:
            self.akis.write(self.kuyruk.get())

    def temizle(self):
        while not self.kuyruk.empty():
            try:
                self.kuyruk.get_nowait()
            except queue.Empty:
                break


async def sanal_esp32(port: int, anahtar: str, mikrofon_secimi: str | None) -> None:
    pya = pyaudio.PyAudio()
    giris = mikrofon_sec(pya, mikrofon_secimi)
    mikrofon = pya.open(format=FORMAT, channels=KANAL, rate=GIRIS_HIZI, input=True,
                        input_device_index=giris["index"], frames_per_buffer=PARCA)
    calici = _Calici(pya)
    adres = f"ws://127.0.0.1:{port}/esp32?anahtar={anahtar}"
    while True:
        try:
            async with connect(adres, max_size=2**20, compression=None) as ws:
                await ws.send(json.dumps({"tip": "merhaba", "surum": "sanal"}))

                async def gonder():
                    while True:
                        veri = await asyncio.to_thread(mikrofon.read, PARCA, exception_on_overflow=False)
                        await ws.send(veri)

                gorev = asyncio.create_task(gonder())
                try:
                    async for mesaj in ws:
                        if isinstance(mesaj, bytes):
                            calici.kuyruk.put(mesaj)
                            continue
                        olay = json.loads(mesaj)
                        if olay.get("tip") == "sustur":
                            calici.temizle()
                        elif olay.get("tip") in ("durum", "jest"):
                            print(f"\033[90m🤖 sanal ESP32 ← {olay['tip']}: {olay.get('ad')}\033[0m", flush=True)
                finally:
                    gorev.cancel()
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(1)  # sunucu henüz hazır değil


def sanal_esp32_baslat(kopru, mikrofon_secimi: str | None) -> None:
    """Köprünün sunucusu başlayınca sanal ESP32'yi de başlatır."""
    eski_baslat = kopru.baslat

    async def baslat():
        await eski_baslat()
        kopru._gorevler.append(asyncio.create_task(sanal_esp32(kopru.port, kopru.anahtar, mikrofon_secimi)))
        print("🧪 Sanal ESP32: bu bilgisayarın mikrofonu ve hoparlörü ağ üzerinden bağlanıyor.", flush=True)

    kopru.baslat = baslat
