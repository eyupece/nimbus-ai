"""Eylem: ekranda bilgi kartı, sunum modunda slayt kontrolü, isim teyidi ipucu."""

import asyncio

from google.genai import types

from conftest import arac, icerik, operator, ses
from nimbus import oturum as O


def arac_adlari(config):
    return {f.name for t in config.tools if t.function_declarations for f in t.function_declarations}


def tur(*araclar, metin="Tamam."):
    m = [arac(*araclar)] if araclar else []
    return m + [ses(), icerik(output_transcription=types.Transcription(text=metin)), icerik(turn_complete=True)]


def test_ekranda_goster(ortam):
    o, istemci, govde, _ = ortam([[tur(("ekranda_goster", {"baslik": "Konya", "metin": "4°C\\nParçalı bulutlu"}))]])
    asyncio.run(operator(o, ["", "s", "q"], bekle=0.4))
    assert "ekranda_goster" in arac_adlari(istemci.configler[0])
    assert ("kart", "Konya", "4°C\\nParçalı bulutlu") in govde.olaylar
    yanit = istemci.liveler[0].arac_yanitlari[0]
    assert yanit.response == {"tamam": True} and yanit.scheduling is None  # BLOCKING


def test_sunum_modu_kapaliyken_slayt_yok(ortam):
    o, istemci, _, _ = ortam([[tur()]])
    asyncio.run(operator(o, ["", "s", "q"]))
    assert "slayt" not in arac_adlari(istemci.configler[0])
    assert "sunum modundasın" not in istemci.configler[0].system_instruction


def test_sunum_modunda_slayt(ortam, monkeypatch):
    basilan = []
    monkeypatch.setattr(O, "slayt_tusu", lambda yon: basilan.append(yon) or True)
    o, istemci, _, _ = ortam([[tur(("slayt", {"yon": "ileri"}), metin="Sıradaki slayt geliyor.")]], sunum=True)
    asyncio.run(operator(o, ["", "s", "q"], bekle=0.4))
    assert "slayt" in arac_adlari(istemci.configler[0])
    assert "sunum modundasın" in istemci.configler[0].system_instruction
    assert basilan == ["ileri"]
    assert istemci.liveler[0].arac_yanitlari[0].response == {"tamam": True}


def test_slayt_basarisizsa_hata_doner(ortam, monkeypatch):
    monkeypatch.setattr(O, "slayt_tusu", lambda yon: False)
    o, istemci, _, _ = ortam([[tur(("slayt", {"yon": "geri"}))]], sunum=True)
    asyncio.run(operator(o, ["", "s", "q"], bekle=0.4))
    assert "hata" in istemci.liveler[0].arac_yanitlari[0].response


def test_yeni_isim_teyit_ipucu(tmp_path):
    from nimbus.hafiza import Hafiza
    h = Hafiza(tmp_path / "h.json")
    assert "Memnun oldum Efe" in h.tani("Efe")["ipucu"] and "tekrar çağır" in h.tani("Efe")["ipucu"]
    h.gorusmeyi_kaydet("Eyüp", [])
    assert "Sen Eyüp değil misin" in h.tani("Eyup")["ipucu"]


def test_arac_hatasi_modeli_dondurmaz(ortam, monkeypatch):
    def patla(yon):
        raise OSError("tuş gönderilemedi")
    monkeypatch.setattr(O, "slayt_tusu", patla)
    o, istemci, _, _ = ortam([[tur(("slayt", {"yon": "ileri"}))]], sunum=True)
    asyncio.run(operator(o, ["", "s", "q"], bekle=0.4))
    yanitlar = istemci.liveler[0].arac_yanitlari
    assert yanitlar and "hata" in yanitlar[0].response  # hata olsa da model yanıtsız kalmadı
