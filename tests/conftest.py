"""Ortak test altyapısı: sahte ses kartı ve sahte Gemini Live bağlantısı.

Testler mikrofon, hoparlör ya da internet gerektirmez:
    pip install -r requirements-dev.txt
    pytest
"""

import asyncio
import json
import sys
import time
import types as pytypes
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))


# ---------- Sahte PyAudio (her makinede çalışsın) ----------
class SahteAkis:
    def __init__(self, hiz_bolen=50):
        self.hiz_bolen = hiz_bolen  # sesi gerçek süresinin 1/50'sinde "çal"

    def write(self, b):
        time.sleep(len(b) / 2 / 24000 / self.hiz_bolen)

    def read(self, n, exception_on_overflow=False):
        time.sleep(0.002)
        return b"\0\0" * n

    def get_output_latency(self):
        return 0.05

    def close(self):
        pass


class SahtePyAudio:
    cihazlar = [
        dict(index=0, name="Microsoft Sound Mapper - Input", maxInputChannels=2, hostApi=0),
        dict(index=1, name="Mikrofon (Realtek(R) Audio)", maxInputChannels=2, hostApi=0),
        dict(index=2, name="Stereo Mix (Realtek(R) Audio)", maxInputChannels=2, hostApi=0),
        dict(index=3, name="KulaklÄ±k (Poly V4320 Series)", maxInputChannels=1, hostApi=0),
    ]
    varsayilan = 2

    def open(self, **k):
        return SahteAkis()

    def terminate(self):
        pass

    def get_default_host_api_info(self):
        return {"index": 0}

    def get_device_count(self):
        return len(self.cihazlar)

    def get_device_info_by_index(self, i):
        return self.cihazlar[i]

    def get_default_input_device_info(self):
        return self.cihazlar[self.varsayilan]


_pa = pytypes.ModuleType("pyaudio")
_pa.paInt16 = 8
_pa.PyAudio = SahtePyAudio
sys.modules.setdefault("pyaudio", _pa)

from google.genai import types  # noqa: E402


# ---------- Sahte Gemini Live ----------
def icerik(**kw):
    return types.LiveServerMessage(server_content=types.LiveServerContent(**kw))


def ses(saniye=0.3):
    veri = b"\x10\x27" * int(24000 * saniye)
    return icerik(model_turn=types.Content(parts=[types.Part(inline_data=types.Blob(data=veri, mime_type="audio/pcm"))]))


def arac(*cagrilar):
    return types.LiveServerMessage(tool_call=types.LiveServerToolCall(
        function_calls=[types.FunctionCall(id=str(i), name=ad, args=args) for i, (ad, args) in enumerate(cagrilar)]))


class SahteLive:
    """Senaryo: gelen her metin mesajına (send_client_content) sıradaki yanıt listesini gönderir."""

    def __init__(self, yanitlar):
        self.yanitlar = list(yanitlar)
        self.kuyruk = asyncio.Queue()
        self.gonderilen_metinler = []
        self.arac_yanitlari = []
        self.gonderilen_goruntuler = []

    async def send_client_content(self, turns, turn_complete=True):
        self.gonderilen_metinler.append(turns.parts[0].text)
        for m in (self.yanitlar.pop(0) if self.yanitlar else [ses(), icerik(turn_complete=True)]):
            await self.kuyruk.put(m)

    async def send_tool_response(self, function_responses):
        self.arac_yanitlari.extend(function_responses)

    async def send_realtime_input(self, **k):
        if k.get("video"):
            self.gonderilen_goruntuler.append(k["video"])

    async def receive(self):
        while True:
            m = await self.kuyruk.get()
            yield m
            if m.server_content and m.server_content.turn_complete:
                return


class SahteIstemci:
    def __init__(self, oturum_senaryolari, baglanti_hatasi=None, not_cevabi=None):
        self.senaryolar = list(oturum_senaryolari)
        self.baglanti_hatasi = baglanti_hatasi  # fn(config) -> Exception | None
        self.liveler = []
        self.configler = []
        self.not_cevabi = not_cevabi or ["Test notu."]
        istemci = self

        class _Ctx:
            async def __aenter__(s):
                live = SahteLive(istemci.senaryolar.pop(0) if istemci.senaryolar else [])
                istemci.liveler.append(live)
                return live

            async def __aexit__(s, *a):
                pass

        class _Live:
            @staticmethod
            def connect(model, config):
                istemci.configler.append(config)
                if istemci.baglanti_hatasi:
                    hata = istemci.baglanti_hatasi(config)
                    if hata:
                        raise hata
                return _Ctx()

        class _Models:
            async def generate_content(s, model, contents, config=None):
                if "Değerlendir" in contents:  # senaryo değerlendiricisi
                    cevap = {"puan": 4, "gecti": True, "yorum": "İyi.", "sorunlar": []}
                else:  # hafıza not çıkarma
                    cevap = istemci.not_cevabi
                return pytypes.SimpleNamespace(text=json.dumps(cevap, ensure_ascii=False))

        self.aio = pytypes.SimpleNamespace(live=_Live(), models=_Models())


class KayitGovde:
    def __init__(self):
        self.olaylar = []

    def agiz(self, a):
        pass

    def jest(self, ad):
        self.olaylar.append(("jest", ad))

    def durum(self, ad):
        self.olaylar.append(("durum", ad))

    def altyazi(self, kim, metin, ad="Nimbus"):
        self.olaylar.append(("altyazi", kim, metin))

    def durumlar(self):
        return [o[1] for o in self.olaylar if o[0] == "durum"]


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    """Oturum kurucu: sahte istemci + geçici hafıza + geçici kayıt klasörü."""
    from nimbus import hafiza as H
    from nimbus import oturum as O
    from nimbus.ayarlar import Ayarlar
    from nimbus.persona import Persona

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test")
    monkeypatch.setattr(O, "operator_dinle", lambda q, l: None)
    hafiza_dosyasi = tmp_path / "hafiza.json"
    monkeypatch.setattr(O, "Hafiza", lambda: H.Hafiza(hafiza_dosyasi))

    def kur(senaryolar, kamera=None, **istemci_ayar):
        istemci = SahteIstemci(senaryolar, **istemci_ayar)
        monkeypatch.setattr(O, "istemci_olustur", lambda a: (istemci, "sahte"))
        a = Ayarlar.yukle()
        a.kayit_klasoru = tmp_path / "logs"
        govde = KayitGovde()
        o = O.Oturum(a, Persona.yukle(KOK / "personas" / "nimbus.yaml"), govde, kamera=kamera)
        return o, istemci, govde, hafiza_dosyasi

    return kur


async def operator(o, komutlar, bekle=0.25, zaman_asimi=10):
    """Oturumu çalıştırıp sırayla operatör komutları gönderir."""
    gorev = asyncio.create_task(o.calistir())
    for k in komutlar:
        await asyncio.sleep(bekle)
        o.komutlar.put_nowait(k)
    await asyncio.wait_for(gorev, zaman_asimi)
