"""Görme: bak() kameradan kare gönderir, ilk bakış, kamera yoksa araç yok, uyuyunca kamera kapanır."""

import asyncio

from google.genai import types

from conftest import KOK, arac, icerik, operator, ses
from nimbus.kamera import SabitGorsel

RESIM = KOK / "senaryolar" / "gorseller" / "masa.jpg"


def tanitim(metin="Selam."):
    return [ses(), icerik(output_transcription=types.Transcription(text=metin)), icerik(turn_complete=True)]


class SayacliGorsel(SabitGorsel):
    def __init__(self):
        super().__init__(RESIM)
        self.kapatildi = 0

    def kapat(self):
        super().kapat()
        self.kapatildi += 1


def test_kamera_yokken_bak_araci_yok(ortam):
    o, istemci, _, _ = ortam([[tanitim()]])
    asyncio.run(operator(o, ["", "s", "q"]))
    c = istemci.configler[0]
    assert not any(t.function_declarations and any(f.name == "bak" for f in t.function_declarations) for t in c.tools)
    assert "kameran" not in c.system_instruction


def test_ilk_bakis_ve_bak(ortam):
    bak_turu = [arac(("bak", {})), ses(), icerik(output_transcription=types.Transcription(text="Kırmızı kupa!")),
                icerik(turn_complete=True)]
    kamera = SayacliGorsel()
    o, istemci, govde, _ = ortam([[tanitim("O kapüşon ne öyle?"), bak_turu]], kamera=kamera)

    async def senaryo():
        gorev = asyncio.create_task(o.calistir())
        await asyncio.sleep(0.25); o.komutlar.put_nowait("")
        await asyncio.sleep(0.4)
        # kişi "elimde ne var" demiş gibi: modele bir tur daha tetikle
        await o.sahne_mesaji("Kişi: Elimde ne var?")
        await asyncio.sleep(0.5); o.komutlar.put_nowait("s")
        await asyncio.sleep(0.25); o.komutlar.put_nowait("q")
        await asyncio.wait_for(gorev, 10)

    asyncio.run(senaryo())
    live = istemci.liveler[0]
    c = istemci.configler[0]
    assert any(t.function_declarations and any(f.name == "bak" for f in t.function_declarations) for t in c.tools)
    assert "asla yorum yapma" in c.system_instruction  # kişisel özellik yasağı
    assert len(live.gonderilen_goruntuler) == 2  # ilk bakış + bak()
    assert live.gonderilen_goruntuler[0].mime_type == "image/jpeg"
    assert "Kameradan onu görüyorsun" in live.gonderilen_metinler[0]
    bak_yaniti = [y for y in live.arac_yanitlari if y.name == "bak"][0]
    assert bak_yaniti.response["tamam"] and bak_yaniti.scheduling is None  # BLOCKING
    assert ("jest", "bak") in govde.olaylar
    assert kamera.kapatildi >= 1 and not kamera.acik  # uyuyunca kapandı


def test_ilk_bakis_kapatilabilir(ortam, monkeypatch):
    monkeypatch.setenv("NIMBUS_ILK_BAKIS", "0")
    o, istemci, _, _ = ortam([[tanitim()]], kamera=SabitGorsel(RESIM))
    asyncio.run(operator(o, ["", "s", "q"]))
    assert not istemci.liveler[0].gonderilen_goruntuler
    assert "Kameradan onu görüyorsun" not in istemci.liveler[0].gonderilen_metinler[0]


def test_kamera_hatasi_cokertmez(ortam):
    class Bozuk(SabitGorsel):
        def kare_al(self, zaman_asimi=3.0):
            raise RuntimeError("kamera meşgul")

    o, istemci, govde, _ = ortam([[tanitim()]], kamera=Bozuk(RESIM))
    asyncio.run(operator(o, ["", "s", "q"]))
    assert "sohbet" in govde.durumlar() and not istemci.liveler[0].gonderilen_goruntuler


def test_jpeg_kucultme():
    import pytest
    cv2 = pytest.importorskip("cv2")
    import numpy as np
    from nimbus.kamera import _jpeg
    veri = _jpeg(np.zeros((1080, 1920, 3), np.uint8))
    kare = cv2.imdecode(np.frombuffer(veri, np.uint8), cv2.IMREAD_COLOR)
    assert max(kare.shape[:2]) == 768
