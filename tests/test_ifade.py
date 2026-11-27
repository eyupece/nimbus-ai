"""Söylenen metinden yüz ifadesi."""

import pytest

from nimbus import ifade


def kelime_kelime(cumle):
    ifade.ARALIK_SN = 0
    o = ifade.IfadeOkuyucu()
    k = cumle.split()
    return [j for i in range(1, len(k) + 1) if (j := o.oku(" ".join(k[:i]) + (" " if i == len(k) else "")))]


@pytest.mark.parametrize("cumle,beklenen", [
    ("Vay, neye şaşırdın böyle?", "saskin"),
    ("Haha, efsane bir soru bu.", "gul"),
    ("Ben zaten demiştim, herkes bilir.", "goz_kirp"),
    ("Emin misin? Pek inandırıcı gelmedi.", "gozleri_kis"),
    ("Hımm, ilginç bir durum.", "dusun"),
    ("Senin günün nasıl geçti?", "kas_kaldir"),
])
def test_ifade_kurallari(cumle, beklenen):
    assert beklenen in kelime_kelime(cumle)


def test_ayni_kelime_iki_kez_tetiklemez():
    ifade.ARALIK_SN = 0
    o = ifade.IfadeOkuyucu()
    assert o.oku("Haha güzel ") == "gul"
    assert o.oku("Haha güzel ") is None


def test_aralik_siniri():
    ifade.ARALIK_SN = 10
    o = ifade.IfadeOkuyucu()
    assert o.oku("Vay be ") == "saskin"
    assert o.oku("Vay be haha ") is None
