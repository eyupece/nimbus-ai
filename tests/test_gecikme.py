"""Gecikme ölçüm aracının yardımcıları ve ayar seçenekleri (ağsız)."""

import numpy as np
from google.genai import types

from nimbus import gecikme as G
from nimbus.govde import SessizGovde


def test_yeniden_ornekleme_ve_kirpma():
    x = (np.sin(np.arange(24000) / 10) * 8000).astype(np.int16).tobytes()
    y = G.yeniden_ornekle(x, 24000, 16000)
    assert len(y) == 16000 * 2
    sesli = np.zeros(16000, dtype=np.int16)
    sesli[4000:6000] = 3000
    k = G.kirp(sesli.tobytes())
    assert 2000 * 2 <= len(k) <= (2000 + 16000 * 40 // 1000) * 2


def test_sessizlik_hafif_gurultulu():
    s = np.frombuffer(G.sessizlik(100), dtype=np.int16)
    assert len(s) == 1600 and 0 < np.abs(s).max() < 40


def test_ozet():
    assert G.ozet([900, 1100, 1000]) == {"n": 3, "ortanca": 1000, "en_iyi": 900, "en_kotu": 1100}
    assert G.ozet([]) == {"n": 0}


def test_varyant_ayarlari(ortam):
    o, _, _, _ = ortam([])
    o.govde = SessizGovde()
    assert G.live_ayari(o, {}).realtime_input_config.automatic_activity_detection.silence_duration_ms == o.a.sessizlik_ms
    a = G.live_ayari(o, {"sessizlik_ms": 200, "dusunme": "minimal", "arama": False})
    assert a.realtime_input_config.automatic_activity_detection.silence_duration_ms == 200
    assert a.thinking_config.thinking_level == types.ThinkingLevel.MINIMAL
    assert not any(t.google_search for t in a.tools)


def test_rapor():
    sonuc = [{"ad": "mevcut", "gecikmeler": [1000, 1200], "vad_ms": [], "erken": 1, "zaman_asimi": 0, "hata": None,
              "cumleler": [{"cumle": "a", "ms": 1000}, {"cumle": "b", "ms": None, "erken": True}]}]
    r = G.rapor_yaz(sonuc, 1)
    assert "| mevcut | **1200 ms** |" in r and "ERKEN" in r


class _VadLive:
    """Sahte Live: sesli parçadan sonra 0.15 sn sessizlik gelince cevap verir (sunucu VAD gibi)."""

    def __init__(self):
        import asyncio

        self.kuyruk = asyncio.Queue()
        self.son_sesli = None

    async def send_client_content(self, turns, turn_complete=True):
        from conftest import icerik, ses

        await self.kuyruk.put(ses(0.1))
        await self.kuyruk.put(icerik(turn_complete=True))

    async def send_tool_response(self, function_responses):
        pass

    async def send_realtime_input(self, audio=None, **k):
        import time

        from conftest import icerik, ses

        x = np.frombuffer(audio.data, dtype=np.int16)
        simdi = time.monotonic()
        if np.abs(x).max() > 500:
            self.son_sesli = simdi
        elif self.son_sesli and simdi - self.son_sesli > 0.15:
            self.son_sesli = None
            await self.kuyruk.put(ses(0.1))
            await self.kuyruk.put(icerik(turn_complete=True))

    async def receive(self):
        while True:
            m = await self.kuyruk.get()
            yield m
            if m.server_content and m.server_content.turn_complete:
                return


def test_varyant_olcumu_uctan_uca(ortam, monkeypatch):
    import asyncio

    o, _, _, _ = ortam([])
    live = _VadLive()

    class _Ctx:
        async def __aenter__(s):
            return live

        async def __aexit__(s, *a):
            pass

    istemci = type("I", (), {})()
    istemci.aio = type("A", (), {})()
    istemci.aio.live = type("L", (), {"connect": staticmethod(lambda model, config: _Ctx())})()
    monkeypatch.setattr(G, "CUMLELER", ["a", ["b", 300, "c"]])
    sesli = (np.ones(3200, dtype=np.int16) * 3000).tobytes()  # 0.2 sn
    sesler = [sesli, sesli + G.sessizlik(300) + sesli]
    sonuc = asyncio.run(G.varyant_olc(istemci, o, "test", {"parca_ms": 20}, sesler, 1))
    assert sonuc["hata"] is None, sonuc["hata"]
    assert len(sonuc["gecikmeler"]) == 1 and 100 < sonuc["gecikmeler"][0] < 600
    assert sonuc["erken"] == 1  # 300 ms duraklamada "cevap verdi"


def test_el_vad_konusma_basi_ve_sonu_sinyali(ortam, monkeypatch):
    import asyncio

    o, _, _, _ = ortam([])
    live = _VadLive()
    sinyaller = []

    async def kayitli(audio=None, activity_start=None, activity_end=None, **k):
        from conftest import icerik, ses

        if activity_start:
            sinyaller.append("bas")
        elif activity_end:
            sinyaller.append("son")
            await live.kuyruk.put(ses(0.1))
            await live.kuyruk.put(icerik(turn_complete=True))
        # el VAD'ında sunucu kendi kararını vermez
    live.send_realtime_input = kayitli

    class _Ctx:
        async def __aenter__(s):
            return live

        async def __aexit__(s, *a):
            pass

    istemci = type("I", (), {})()
    istemci.aio = type("A", (), {})()
    istemci.aio.live = type("L", (), {"connect": staticmethod(lambda model, config: _Ctx())})()
    sesli = (np.ones(3200, dtype=np.int16) * 3000).tobytes()
    monkeypatch.setattr(G, "CUMLELER", ["a"])
    sonuc = asyncio.run(G.varyant_olc(istemci, o, "el", {"el_vad_ms": 200, "parca_ms": 20}, [sesli], 1))
    assert sinyaller[:2] == ["bas", "son"]
    assert sonuc["hata"] is None and len(sonuc["gecikmeler"]) == 1 and 150 < sonuc["gecikmeler"][0] < 500
    assert G.live_ayari(o, {"el_vad_ms": 200}).realtime_input_config.automatic_activity_detection.disabled
