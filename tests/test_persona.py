"""Persona dosyaları: biçim bozulmasın, talimat düzgün üretilsin (bir kez bozuk YAML klasöre gitmişti)."""

import pytest
import yaml

from conftest import KOK
from nimbus.persona import Persona

PERSONALAR = sorted((KOK / "personas").glob("*.yaml"))


@pytest.mark.parametrize("dosya", PERSONALAR, ids=lambda p: p.name)
def test_persona_gecerli(dosya):
    veri = yaml.safe_load(dosya.read_text(encoding="utf-8"))
    for alan in ("ad", "ses", "hikaye", "kurallar", "karsilama", "veda"):
        assert veri.get(alan), f"{dosya.name}: '{alan}' eksik"
    assert all(isinstance(k, str) for k in veri["kurallar"])
    for o in veri.get("ornekler", []):
        assert o.get("kisi") and o.get("nimbus"), "örnek diyalogda kisi/nimbus eksik"
    for ad, deger in veri.get("ozellikler", {}).items():
        assert 0 <= deger <= 100, f"{ad} 0-100 arası olmalı"


@pytest.mark.parametrize("dosya", PERSONALAR, ids=lambda p: p.name)
def test_sistem_talimati(dosya):
    p = Persona.yukle(dosya)
    t = p.sistem_talimati()
    assert f"Senin adın {p.ad}" in t
    assert all(k.split()[0] in t for k in p.kurallar)
    assert 300 < len(t) < 6000


def test_gdg_personasi_bilgiyi_icerir():
    p = Persona.yukle(KOK / "personas" / "gdg-konya.yaml")
    t = p.sistem_talimati()
    assert "GDG Cloud Konya" in t and "21 Kasım 2026" in t and "uydurma" in t
    assert (KOK / p.bilgi_dosyasi).exists()
