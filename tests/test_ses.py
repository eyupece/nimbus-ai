"""Mikrofon seçimi ve ağız senkronu."""

import array
import math
import time

from conftest import SahtePyAudio
from nimbus import ses


def test_stereo_mix_atlanir():
    d = ses.mikrofon_sec(SahtePyAudio(), None)
    assert "Stereo Mix" not in d["name"] and "Sound Mapper" not in d["name"]


def test_isimle_ve_bozuk_turkce_karakterle_secim():
    assert ses.cihaz_adi(ses.mikrofon_sec(SahtePyAudio(), "kulaklık")).startswith("Kulaklık")
    assert ses.mikrofon_sec(SahtePyAudio(), "1")["index"] == 1


def test_agiz_yumusatici_acilir_ve_kapanir():
    y = ses.AgizYumusatici()
    acik = [y(5000) for _ in range(5)][-1]
    kapali = [y(0) for _ in range(15)][-1]
    assert acik > 0.9 and kapali < 0.05


def test_agiz_ses_karti_gecikmesi_kadar_gecikir():
    olaylar = []

    class G:
        def agiz(self, a):
            olaylar.append(time.monotonic())

    h = ses.Hoparlor(SahtePyAudio(), G(), kaydir_ms=100)  # 50 ms kart + 100 ms ince ayar
    baslangic = time.monotonic()
    h.cal(array.array("h", [int(6000 * math.sin(i / 4)) for i in range(4800)]).tobytes())
    time.sleep(0.5)
    h.kapat()
    assert olaylar and 0.13 <= olaylar[0] - baslangic <= 0.3
