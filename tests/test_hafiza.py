"""Hafıza: Türkçe isim, benzer isim ipucu, kalıcılık, unutma."""

from nimbus.hafiza import Hafiza, anahtar


def test_turkce_anahtar():
    assert anahtar("İREM") == "irem"
    assert anahtar("IŞIK") == "ışık"
    assert anahtar("  Eyüp   Ece ") == "eyüp ece"


def test_tanisma_ve_hatirlama(tmp_path):
    h = Hafiza(tmp_path / "h.json")
    assert h.tani("Eyüp")["taniyor_musun"] is False
    h.gorusmeyi_kaydet("Eyüp", ["Konyalı", "Yazılımcı"])
    h2 = Hafiza(tmp_path / "h.json")  # diskten tekrar oku
    b = h2.tani("EYÜP")
    assert b["taniyor_musun"] and b["kacinci_gorusme"] == 2 and "Konyalı" in b["bildiklerin"]


def test_benzer_isim_ipucu(tmp_path):
    h = Hafiza(tmp_path / "h.json")
    h.gorusmeyi_kaydet("Eyüp", [])
    assert h.tani("Eyup")["benzer_isimler"] == ["Eyüp"]


def test_not_siniri_ve_unutma(tmp_path):
    h = Hafiza(tmp_path / "h.json")
    h.gorusmeyi_kaydet("Deniz", [f"not {i}" for i in range(20)])
    assert len(h.kisiler["deniz"]["notlar"]) == 8
    assert h.unut("deniz") and not Hafiza(tmp_path / "h.json").kisiler


def test_bozuk_dosya_cokmez(tmp_path):
    (tmp_path / "h.json").write_text("{bozuk", encoding="utf-8")
    assert Hafiza(tmp_path / "h.json").kisiler == {}
