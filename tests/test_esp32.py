"""ESP32 köprüsü: protokol, anahtar, ses temposu, dokunma ve söz kesme (donanımsız)."""

import asyncio
import json
import time
import types as pytypes

import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from nimbus import ayarlar as A
from nimbus.durum import Durum
from nimbus.esp32 import ONDEN_SN, Esp32Kopru
from nimbus.govde import CokluGovde, SessizGovde
from nimbus.ses import Hoparlor


async def _kopru(**k):
    kopru = Esp32Kopru("gizli", port=0, duyuru=False, **k)
    await kopru.baslat()
    return kopru


def test_ses_ve_olaylar_iki_yonlu():
    async def senaryo():
        dokunmalar = []
        kopru = await _kopru(dokunma=dokunmalar.append)
        try:
            async with connect(f"ws://127.0.0.1:{kopru.port}/esp32?anahtar=gizli") as ws:
                assert json.loads(await ws.recv()) == {"tip": "durum", "ad": "uyku"}
                await ws.send(json.dumps({"tip": "merhaba", "surum": "test"}))
                mikrofon_sesi = b"\x01\x02" * 512
                await ws.send(mikrofon_sesi)
                assert await kopru.mikrofon().oku() == mikrofon_sesi

                kopru.durum("sohbet")
                kopru.jest("gul")
                akis = kopru.akis()
                await asyncio.to_thread(akis.write, b"\x05\x00" * 480)
                akis.temizle()
                gelen = [await asyncio.wait_for(ws.recv(), 2) for _ in range(4)]
                assert json.loads(gelen[0]) == {"tip": "durum", "ad": "sohbet"}
                assert json.loads(gelen[1]) == {"tip": "jest", "ad": "gul"}
                assert gelen[2] == b"\x05\x00" * 480
                assert json.loads(gelen[3]) == {"tip": "sustur"}

                await ws.send(json.dumps({"tip": "dokunma", "uzun": True}))
                await asyncio.sleep(0.1)
                assert dokunmalar == [True]
                assert kopru.bilgi["surum"] == "test"
        finally:
            await kopru.kapat()

    asyncio.run(senaryo())


def test_yanlis_anahtar_reddedilir():
    async def senaryo():
        kopru = await _kopru()
        try:
            with pytest.raises(InvalidStatus):
                async with connect(f"ws://127.0.0.1:{kopru.port}/esp32?anahtar=yanlis"):
                    pass
            with pytest.raises(InvalidStatus):
                async with connect(f"ws://127.0.0.1:{kopru.port}/baska"):
                    pass
        finally:
            await kopru.kapat()

    asyncio.run(senaryo())


def test_esp32_yokken_mikrofon_sessizlik_dondurur():
    async def senaryo():
        kopru = await _kopru()
        try:
            veri = await kopru.mikrofon().oku()
            assert veri and set(veri) == {0}
        finally:
            await kopru.kapat()

    asyncio.run(senaryo())


def test_ses_gercek_zaman_hizinda_gider():
    """0.5 sn ses önden en fazla ONDEN_SN kadar gider: gönderim ~0.35 sn sürmeli."""
    akis = Esp32Kopru("x").akis()
    dilim = b"\0\0" * 480  # 20 ms
    bas = time.monotonic()
    for _ in range(25):
        akis.write(dilim)
    gecen = time.monotonic() - bas
    assert 0.5 - ONDEN_SN - 0.08 < gecen < 0.5


def test_hoparlor_susunca_esp32_tamponu_da_temizlenir():
    from conftest import SahtePyAudio

    temizlendi = []
    akis = pytypes.SimpleNamespace(write=lambda b: None, get_output_latency=lambda: 0.2,
                                   temizle=lambda: temizlendi.append(1), close=lambda: None)
    h = Hoparlor(SahtePyAudio(), SessizGovde(), akis=akis)
    try:
        h.konusuyor_bitis = time.monotonic() + 5
        h.sustur()
        assert temizlendi == [1] and h.konusuyor_bitis <= time.monotonic()
        assert abs(h.cikis_gecikmesi - 0.2) < 1e-9
    finally:
        h.kapat()


def test_coklu_govde_hepsine_iletir():
    kayit = []

    class G(SessizGovde):
        def jest(self, ad):
            kayit.append(ad)

    c = CokluGovde(G(), G())
    c.jest("gul")
    assert kayit == ["gul", "gul"] and c.ekran_var is False


def test_dokunma_uyandirir_susturur_vedalastirir(ortam):
    o, _, _, _ = ortam([])
    o.dokunuldu()
    assert o.komutlar.get_nowait() == "u"

    o.durum = Durum.SOHBET
    o.hoparlor = pytypes.SimpleNamespace(konusuyor_bitis=time.monotonic() + 3)
    o.dokunuldu()
    assert o.komutlar.get_nowait() == "k"
    o.dokunuldu(uzun=True)
    assert o.komutlar.get_nowait() == "v"

    o.hoparlor.konusuyor_bitis = 0  # Nimbus susmuşken dokunmak bir şey yapmaz
    o.dokunuldu()
    assert o.komutlar.empty()


def test_soz_kesince_duyulan_kisim_yazilir(ortam):
    o, _, _, _ = ortam([])
    susturuldu = []
    o.hoparlor = pytypes.SimpleNamespace(calinan_bayt=1500, sustur=lambda: susturuldu.append(1))
    o.yanit_basladi = True
    o.tur_baslangic_calinan = 1000
    o.tur_alinan_bayt = 2000
    o.nimbus_tampon = "Bir iki üç dört beş altı yedi sekiz"
    o.sozu_kes()
    assert susturuldu == [1] and o.tur_susturuldu
    kim, metin = o.konusma_metni[-1]
    assert kim == "nimbus" and metin.startswith("Bir") and "sekiz" not in metin
    o.sozu_kes()  # ikinci kez bir şey yapmaz
    assert susturuldu == [1]


def test_esp32_anahtari_bir_kez_uretilir(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "KOK", tmp_path)
    monkeypatch.delenv("NIMBUS_ESP32_ANAHTAR", raising=False)
    (tmp_path / ".env").write_text("NIMBUS_KONUM=Konya\n", encoding="utf-8")
    k1 = A.esp32_anahtari()
    k2 = A.esp32_anahtari()
    icerik = (tmp_path / ".env").read_text(encoding="utf-8")
    assert k1 == k2 and len(k1) >= 20
    assert "NIMBUS_KONUM=Konya" in icerik and icerik.count("NIMBUS_ESP32_ANAHTAR=") == 1


def test_sanal_esp32_baglanir_ve_ses_akitir():
    from nimbus.esp32_sanal import sanal_esp32_baslat

    async def senaryo():
        kopru = Esp32Kopru("gizli", port=0, duyuru=False)
        sanal_esp32_baslat(kopru, None)
        await kopru.baslat()
        try:
            for _ in range(50):
                if kopru.bilgi:
                    break
                await asyncio.sleep(0.05)
            assert kopru.bilgi.get("surum") == "sanal"
            assert len(await kopru.mikrofon().oku()) == 1024
        finally:
            await kopru.kapat()

    asyncio.run(senaryo())


def test_esp32_ayar_dosyasi_ozel_karakterleri_kacirir(tmp_path, monkeypatch):
    from nimbus import esp32_yukle as Y

    monkeypatch.setattr(Y, "AYAR_DOSYASI", tmp_path / "ayarlar.h")
    monkeypatch.setenv("NIMBUS_ESP32_SES", "55")
    monkeypatch.setenv("NIMBUS_ESP32_AGIZ_ACIK", "abc")  # sayı değilse yok sayılır
    Y.ayar_dosyasi_yaz('Ev "Ağı"', "şi\\fre", "anahtar123", "")
    h = (tmp_path / "ayarlar.h").read_text(encoding="utf-8")
    assert '#define WIFI_AD "Ev \\"Ağı\\""' in h
    assert '#define WIFI_SIFRE "şi\\\\fre"' in h
    assert '#define SUNUCU_IP ""' in h and "#define SES_SEVIYESI 55" in h and "AGIZ_ACIK" not in h


def test_esp32_yazilimi_ile_python_ayni_portlari_kullanir():
    from nimbus.esp32 import DUYURU_PORTU, PORT
    from nimbus.ayarlar import KOK

    kod = (KOK / "donanim" / "esp32" / "src" / "main.cpp").read_text(encoding="utf-8")
    assert f"#define SUNUCU_PORT {PORT}" in kod and f"#define DUYURU_PORTU {DUYURU_PORTU}" in kod
    assert '"/esp32?anahtar="' in kod and '\\"tip\\":\\"dokunma\\"' in kod


def test_oturum_esp32_ile_uctan_uca(ortam):
    """Uyan -> karşılama sesi ESP32'ye akar, durumlar ESP32'ye gider, ESP32 mikrofonu dinlenir."""
    from conftest import ses

    tanitim = [ses(0.5), icerik_metni("Selam, ben Nimbus."), turn_bitti()]
    o, _, kayit, _ = ortam([[tanitim]])
    kopru = Esp32Kopru("gizli", port=0, duyuru=False)
    o.esp32 = kopru
    o.govde = CokluGovde(kayit, kopru)

    async def senaryo():
        gelen_ses, olaylar = [], []

        async def esp32_istemci():
            while not kopru.port:
                await asyncio.sleep(0.02)
            async with connect(f"ws://127.0.0.1:{kopru.port}/esp32?anahtar=gizli") as ws:
                await ws.send(json.dumps({"tip": "merhaba", "surum": "test"}))
                async for m in ws:
                    if isinstance(m, bytes):
                        gelen_ses.append(len(m))
                    else:
                        olaylar.append(json.loads(m))

        kopru.port = 0
        istemci = asyncio.create_task(esp32_istemci())
        # Köprü kalksın, ESP32 bağlansın, sonra uyandır
        gorev = asyncio.create_task(o.calistir())
        for _ in range(100):
            if kopru.baglanti:
                break
            await asyncio.sleep(0.02)
        assert kopru.baglanti, "ESP32 bağlanamadı"
        for k in ["", "s", "q"]:
            await asyncio.sleep(0.8)
            o.komutlar.put_nowait(k)
        await asyncio.wait_for(gorev, 10)
        istemci.cancel()
        return gelen_ses, olaylar

    gelen_ses, olaylar = asyncio.run(senaryo())
    assert sum(gelen_ses) == 24000  # 0.5 sn ses (24 kHz, 16-bit) eksiksiz gitti
    durumlar = [e["ad"] for e in olaylar if e.get("tip") == "durum"]
    assert "karsilama" in durumlar and durumlar[-1] == "uyku"
    o.kapat()


def icerik_metni(metin):
    from conftest import icerik
    from google.genai import types  # noqa: F401

    return icerik(output_transcription=types.Transcription(text=metin))


def turn_bitti():
    from conftest import icerik

    return icerik(turn_complete=True)
