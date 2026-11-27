"""Durum makinesi ve konuşma akışı (sahte Gemini Live ile)."""

import asyncio
import json

from conftest import arac, icerik, operator, ses
from google.genai import types


def tanitim(metin="Selam, ben Nimbus. Adın ne?"):
    return [ses(), icerik(output_transcription=types.Transcription(text=metin)), icerik(turn_complete=True)]


def test_uyandir_karsila_vedalas(ortam):
    o, istemci, govde, _ = ortam([[tanitim(), tanitim("Hadi bay.")]])
    asyncio.run(operator(o, ["", "v", "q"]))
    assert govde.durumlar() == ["uyku", "karsilama", "sohbet", "veda", "uyku"]
    live = istemci.liveler[0]
    assert "[Sahne yönetimi]" in live.gonderilen_metinler[0] and "geldi" in live.gonderilen_metinler[0]
    assert len(live.gonderilen_metinler) == 2  # karşılama + veda


def test_model_kendi_vedalasir(ortam):
    tur = [ses(), icerik(output_transcription=types.Transcription(text="Görüşürüz!")),
           arac(("uykuya_don", {})), icerik(turn_complete=True)]
    o, istemci, govde, _ = ortam([[tur]])
    asyncio.run(operator(o, ["", "q"], bekle=0.4))
    assert govde.durumlar()[-2:] == ["veda", "uyku"]
    assert istemci.liveler[0].arac_yanitlari[0].scheduling == types.FunctionResponseScheduling.SILENT


def test_model_konusmadan_vedalasirsa_veda_soyletilir(ortam):
    sessiz_veda = [arac(("uykuya_don", {})), icerik(turn_complete=True)]
    o, istemci, govde, _ = ortam([[sessiz_veda, tanitim("Hadi bay, bulutlara dönüyorum.")]])
    asyncio.run(operator(o, ["", "q"], bekle=0.5))
    live = istemci.liveler[0]
    assert len(live.gonderilen_metinler) == 2 and o.persona.veda in live.gonderilen_metinler[1]
    assert govde.durumlar()[-2:] == ["veda", "uyku"]
    assert ("nimbus", "Hadi bay, bulutlara dönüyorum.") in o.konusma_metni


def test_sifirla_hemen_uyutur(ortam):
    o, _, govde, _ = ortam([[tanitim()]])
    asyncio.run(operator(o, ["", "s", "q"]))
    assert govde.durumlar()[-1] == "uyku" and "veda" not in govde.durumlar()


def test_her_kisi_icin_yeni_baglanti(ortam):
    o, istemci, _, _ = ortam([[tanitim()], [tanitim()]])
    asyncio.run(operator(o, ["", "s", "", "s", "q"]))
    assert len(istemci.liveler) == 2


def test_talimat_icerigi(ortam):
    o, istemci, _, _ = ortam([[tanitim()]])
    asyncio.run(operator(o, ["", "s", "q"]))
    c = istemci.configler[0]
    for parca in ("Senin adın Nimbus", "[Sahne yönetimi]", "kisiyi_tani", "Şu an"):
        assert parca in c.system_instruction
    adlar = [fd.name for t in c.tools if t.function_declarations for fd in t.function_declarations]
    assert {"kisiyi_tani", "uykuya_don"} <= set(adlar)
    assert any(t.google_search for t in c.tools)


def test_arama_desteklenmezse_aramasiz_baglanir(ortam):
    hata = lambda c: RuntimeError("1007 google_search yok") if any(t.google_search for t in c.tools) else None
    o, istemci, govde, _ = ortam([[tanitim()]], baglanti_hatasi=hata)
    asyncio.run(operator(o, ["", "s", "q"]))
    assert len(istemci.configler) == 2 and not any(t.google_search for t in istemci.configler[1].tools)
    assert "sohbet" in govde.durumlar()


def test_soz_kesilince_metin_duyulan_kisma_kadar(ortam):
    uzun = "Bir iki üç dört beş altı yedi sekiz dokuz on on bir on iki on üç on dört on beş."
    tur = [icerik(output_transcription=types.Transcription(text=uzun)), ses(2.0), icerik(interrupted=True),
           icerik(turn_complete=True)]
    o, _, _, _ = ortam([[tur]])
    asyncio.run(operator(o, ["", "s", "q"], bekle=0.05))
    yazilan = [m for k, m in o.konusma_metni if k == "nimbus"]
    assert yazilan and yazilan[0].endswith("…") and len(yazilan[0]) < len(uzun)


def test_hafiza_tanisma_ve_tekrar_gelis(ortam):
    tanisma = [icerik(input_transcription=types.Transcription(text="Ben Eyüp, Konyalıyım.")), ses(),
               arac(("kisiyi_tani", {"ad": "Eyüp"})),
               icerik(output_transcription=types.Transcription(text="Memnun oldum Eyüp.")), icerik(turn_complete=True)]
    o, istemci, _, dosya = ortam([[tanisma, tanitim("Bay.")], [tanisma, tanitim("Bay.")]],
                                not_cevabi=["Konyalı."])
    asyncio.run(operator(o, ["", "v", "", "v", "q"], bekle=0.4, zaman_asimi=20))
    ilk = istemci.liveler[0].arac_yanitlari[0]
    ikinci = istemci.liveler[1].arac_yanitlari[0]
    assert ilk.scheduling is None  # BLOCKING: model sonucu bekleyip tek seferde konuşur
    assert ilk.response["taniyor_musun"] is False
    assert ikinci.response["taniyor_musun"] is True and "Konyalı." in ikinci.response["bildiklerin"]
    kayit = json.loads(dosya.read_text(encoding="utf-8"))["kisiler"]["eyüp"]
    assert kayit["gorusme_sayisi"] == 2
