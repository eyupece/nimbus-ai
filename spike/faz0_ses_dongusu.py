"""
Nimbus - Faz 0: Ses döngüsü keşfi (arşiv; güncel kod: python -m nimbus)
=================================
Mikrofon -> Gemini Live -> Hoparlör. Amaç:
  1) Türkçe ses kalitesini kulakla test etmek
  2) Gecikmeyi ölçmek (konuşman bittikten sonra ilk sesin gelme süresi)
  3) Söz kesmeyi (barge-in) ve yankıyı denemek

Çalıştırma:
  python spike/faz0_ses_dongusu.py                 # varsayılan ses
  python spike/faz0_ses_dongusu.py --ses Charon    # başka bir ses
  python spike/faz0_ses_dongusu.py --yarim-dubleks # hoparlörle test (yankıyı önler)
  python spike/faz0_ses_dongusu.py --cihazlar      # mikrofonları listele
  python spike/faz0_ses_dongusu.py --mikrofon-testi --mikrofon 1   # API'siz mikrofon testi

Çıkmak için Ctrl+C.
"""

import argparse
import array
import asyncio
import math
import os
import sys
import time
from pathlib import Path

import pyaudio
import yaml
from dotenv import load_dotenv
from google import genai
from google.genai import types

KOK = Path(__file__).resolve().parent.parent
load_dotenv(KOK / ".env")

# Live API ses formatları: giriş 16 kHz, çıkış 24 kHz, 16-bit mono PCM
FORMAT = pyaudio.paInt16
KANAL = 1
GIRIS_HIZI = 16000
CIKIS_HIZI = 24000
PARCA = 1024

# Denemek için bazı hazır sesler (Chirp 3 HD ailesi)
ORNEK_SESLER = ["Charon", "Puck", "Kore", "Fenrir", "Aoede", "Leda", "Orus", "Zephyr"]


# Gerçek mikrofon olmayan "geri döngü" cihazları (sistem sesini kaydeder)
GERI_DONGU = ("stereo mix", "stereo karışımı", "loopback", "what u hear", "wave out")
# Windows'un "varsayılana yönlendir" sanal cihazları; varsayılan Stereo Mix ise onu kaydeder
YONLENDIRICI = ("sound mapper", "ses eşleyici", "primary sound capture", "birincil ses yakalama")


KONUSMA_ESIGI = 700  # bu RMS seviyesinin üstü "konuşuyor" sayılır (mikrofon testine göre ayarlanabilir)


def rms(veri: bytes) -> float:
    ornekler = array.array("h", veri)
    return math.sqrt(sum(x * x for x in ornekler) / len(ornekler)) if ornekler else 0.0


def cihaz_adi(d: dict) -> str:
    """Windows (MME) Türkçe cihaz adlarını bozuk gösterebiliyor: 'KulaklÄ±k' -> 'Kulaklık'."""
    try:
        return d["name"].encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return d["name"]


def persona_yukle(yol: Path) -> dict:
    with open(yol, encoding="utf-8") as f:
        return yaml.safe_load(f)


def giris_cihazlari(pya: "pyaudio.PyAudio") -> list[dict]:
    """Varsayılan ses API'sindeki (Windows'ta MME) giriş cihazları."""
    api = pya.get_default_host_api_info()["index"]
    return [
        d
        for i in range(pya.get_device_count())
        if (d := pya.get_device_info_by_index(i))["maxInputChannels"] > 0 and d["hostApi"] == api
    ]


def mikrofon_sec(pya: "pyaudio.PyAudio", secim: str | None) -> dict:
    """--mikrofon ile numara ya da isim parçası verilebilir; verilmezse geri döngü olmayan ilk uygun cihaz."""
    cihazlar = giris_cihazlari(pya)
    if secim is not None:
        if secim.isdigit():
            return pya.get_device_info_by_index(int(secim))
        for d in cihazlar:
            if secim.lower() in cihaz_adi(d).lower():
                return d
        sys.exit(f"❌ '{secim}' adında mikrofon yok. Liste için: --cihazlar")

    varsayilan = pya.get_default_input_device_info()
    if not any(k in cihaz_adi(varsayilan).lower() for k in GERI_DONGU):
        return varsayilan
    for d in cihazlar:
        if not any(k in cihaz_adi(d).lower() for k in GERI_DONGU + YONLENDIRICI):
            print(f"⚠️  Varsayılan giriş '{cihaz_adi(varsayilan)}' bir geri döngü cihazı, atlandı.")
            return d
    sys.exit("❌ Gerçek bir mikrofon bulunamadı. Liste için: --cihazlar")


class SesDongusu:
    def __init__(self, model: str, ses: str, talimat: str, yarim_dubleks: bool, mikrofon: str | None = None):
        self.model = model
        self.ses = ses
        self.talimat = talimat
        self.yarim_dubleks = yarim_dubleks
        self.mikrofon = mikrofon

        self.pya = pyaudio.PyAudio()
        self.calinacak: asyncio.Queue[bytes] = asyncio.Queue()
        self.konusuyor_bitis = 0.0  # Nimbus'un sesi en son ne zaman çaldı

        # Gecikme ölçümü: mikrofonda son konuşma sesi duyulan an -> Nimbus'un ilk ses parçası
        self.son_konusma_ani: float | None = None
        self.yanit_basladi = False
        self.gecikmeler: list[float] = []

        # Yazıya dökümler parça parça gelir; tur bitince tek satır basıyoruz
        self.sen_tampon = ""
        self.nimbus_tampon = ""

    def ayar(self) -> types.LiveConnectConfig:
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=self.talimat,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.ses)
                )
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            # Sunucu tarafı konuşma algılama: sustuğunu ne kadar hızlı anlasın?
            # Düşük sessizlik süresi = daha hızlı cevap, ama düşünürken araya girebilir.
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                    silence_duration_ms=int(os.getenv("NIMBUS_SESSIZLIK_MS", "400")),
                )
            ),
        )

    async def dinle(self, oturum):
        """Mikrofonu okuyup Live'a gönderir."""
        giris = mikrofon_sec(self.pya, self.mikrofon)
        akis = await asyncio.to_thread(
            self.pya.open,
            format=FORMAT,
            channels=KANAL,
            rate=GIRIS_HIZI,
            input=True,
            input_device_index=giris["index"],
            frames_per_buffer=PARCA,
        )
        print(f"🎙  Mikrofon: {cihaz_adi(giris)}")
        while True:
            veri = await asyncio.to_thread(akis.read, PARCA, exception_on_overflow=False)
            # Yarım dubleks: Nimbus konuşurken (ve 300 ms sonrasına kadar) mikrofonu sustur
            if self.yarim_dubleks and time.monotonic() < self.konusuyor_bitis + 0.3:
                continue
            if rms(veri) > KONUSMA_ESIGI:
                self.son_konusma_ani = time.monotonic()
            await oturum.send_realtime_input(
                audio=types.Blob(data=veri, mime_type=f"audio/pcm;rate={GIRIS_HIZI}")
            )

    async def al(self, oturum):
        """Live'dan gelen sesi ve yazıya dökümleri işler."""
        while True:
            async for yanit in oturum.receive():
                icerik = yanit.server_content
                if icerik is None:
                    continue

                if icerik.input_transcription and icerik.input_transcription.text:
                    self.sen_tampon += icerik.input_transcription.text

                # Nimbus'un sesi: bir olayda birden fazla parça olabilir, hepsini işle
                if icerik.model_turn:
                    for parca in icerik.model_turn.parts or []:
                        if parca.inline_data and parca.inline_data.data:
                            if not self.yanit_basladi:
                                self.yanit_basladi = True
                                self.sen_yaz()
                                self.gecikme_yaz()
                            self.calinacak.put_nowait(parca.inline_data.data)

                if icerik.output_transcription and icerik.output_transcription.text:
                    self.nimbus_tampon += icerik.output_transcription.text

                # Söz kesildi: çalma kuyruğunu boşalt
                if icerik.interrupted:
                    while not self.calinacak.empty():
                        self.calinacak.get_nowait()
                    self.nimbus_yaz(kesildi=True)

                if icerik.turn_complete:
                    self.nimbus_yaz()

    def sen_yaz(self):
        if self.sen_tampon.strip():
            print(f"\033[94mSen:\033[0m {self.sen_tampon.strip()}", flush=True)
        self.sen_tampon = ""

    def gecikme_yaz(self):
        if self.son_konusma_ani is None:
            return
        ms = (time.monotonic() - self.son_konusma_ani) * 1000
        self.gecikmeler.append(ms)
        print(f"\033[90m⏱  sen sustuktan sonra ilk ses: {ms:.0f} ms\033[0m", flush=True)
        self.son_konusma_ani = None

    def nimbus_yaz(self, kesildi: bool = False):
        if self.nimbus_tampon.strip():
            ek = " \033[90m✋ (sözü kesildi)\033[0m" if kesildi else ""
            print(f"\033[93mNimbus:\033[0m {self.nimbus_tampon.strip()}{ek}\n", flush=True)
        self.nimbus_tampon = ""
        self.yanit_basladi = False

    def ozet_yaz(self):
        if not self.gecikmeler:
            return
        g = sorted(self.gecikmeler)
        print(f"\n📊 {len(g)} cevap | ortanca {g[len(g) // 2]:.0f} ms | en iyi {g[0]:.0f} ms | en kötü {g[-1]:.0f} ms")

    async def cal(self):
        """Gelen sesi hoparlörden çalar."""
        akis = await asyncio.to_thread(
            self.pya.open, format=FORMAT, channels=KANAL, rate=CIKIS_HIZI, output=True
        )
        while True:
            veri = await self.calinacak.get()
            sure = len(veri) / 2 / CIKIS_HIZI  # 16-bit mono
            self.konusuyor_bitis = time.monotonic() + sure
            await asyncio.to_thread(akis.write, veri)

    @staticmethod
    def istemci_olustur() -> tuple[genai.Client, str]:
        """NIMBUS_BACKEND=gemini (AI Studio anahtarı) ya da vertex (Google Cloud projesi)."""
        arka_uc = os.getenv("NIMBUS_BACKEND", "gemini").lower()
        if arka_uc == "vertex":
            proje = os.getenv("GOOGLE_CLOUD_PROJECT")
            bolge = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
            if not proje:
                sys.exit("❌ Vertex için .env'de GOOGLE_CLOUD_PROJECT gerekli.")
            # Kimlik: `gcloud auth application-default login` ile alınan kullanıcı bilgisi
            return genai.Client(vertexai=True, project=proje, location=bolge), f"vertex:{proje}/{bolge}"

        anahtar = os.getenv("GEMINI_API_KEY")
        if not anahtar or anahtar == "buraya_yapistir":
            sys.exit("❌ GEMINI_API_KEY bulunamadı. .env dosyasına anahtarını yapıştır.")
        # Live API, Gemini Developer API'de v1beta altında; SDK varsayılanı v1 olduğu için açıkça belirtiyoruz
        return (
            genai.Client(api_key=anahtar, http_options=types.HttpOptions(api_version="v1beta")),
            "gemini-api",
        )

    async def calistir(self):
        istemci, arka_uc = self.istemci_olustur()
        print(f"☁️  {arka_uc} | Model: {self.model} | Ses: {self.ses} | Yarım dubleks: {self.yarim_dubleks}")
        print("Konuşmaya başla. Çıkmak için Ctrl+C.\n")

        async with istemci.aio.live.connect(model=self.model, config=self.ayar()) as oturum:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self.dinle(oturum))
                tg.create_task(self.al(oturum))
                tg.create_task(self.cal())


def cihazlari_listele():
    pya = pyaudio.PyAudio()
    varsayilan = pya.get_default_input_device_info()["index"]
    print("Giriş cihazları (--mikrofon NUMARA ya da isim parçası ile seç):\n")
    for d in giris_cihazlari(pya):
        isaret = "  ← varsayılan" if d["index"] == varsayilan else ""
        uyari = "  (geri döngü, mikrofon değil)" if any(k in cihaz_adi(d).lower() for k in GERI_DONGU) else ""
        print(f"  [{d['index']:>2}] {cihaz_adi(d)}{isaret}{uyari}")
    pya.terminate()


def mikrofon_testi(secim: str | None, saniye: int = 8):
    """API'ye bağlanmadan mikrofonun ses alıp almadığını gösterir."""
    pya = pyaudio.PyAudio()
    giris = mikrofon_sec(pya, secim)
    akis = pya.open(format=FORMAT, channels=KANAL, rate=GIRIS_HIZI, input=True,
                    input_device_index=giris["index"], frames_per_buffer=PARCA)
    print(f"🎙  {cihaz_adi(giris)} - {saniye} saniye konuş, çubuk hareket etmeli:\n")
    bitis = time.monotonic() + saniye
    en_yuksek = 0
    while time.monotonic() < bitis:
        ornekler = array.array("h", akis.read(PARCA, exception_on_overflow=False))
        rms = math.sqrt(sum(x * x for x in ornekler) / len(ornekler))
        en_yuksek = max(en_yuksek, rms)
        cubuk = "█" * min(40, int(rms / 150))
        print(f"\r  {cubuk:<40} {rms:6.0f}", end="", flush=True)
    akis.close()
    pya.terminate()
    durum = "✅ ses alınıyor" if en_yuksek > 500 else "⚠️  neredeyse hiç ses yok, başka mikrofon dene"
    print(f"\n\n{durum} (en yüksek seviye: {en_yuksek:.0f})")


def main():
    p = argparse.ArgumentParser(description="Nimbus Faz 0 ses döngüsü")
    p.add_argument("--ses", default=None, help=f"Ses adı. Örnekler: {', '.join(ORNEK_SESLER)}")
    p.add_argument("--persona", default=str(KOK / "personas" / "nimbus.yaml"))
    p.add_argument("--yarim-dubleks", action="store_true", help="Nimbus konuşurken mikrofonu sustur (hoparlörle test için)")
    p.add_argument("--mikrofon", default=os.getenv("NIMBUS_MIKROFON"), help="Mikrofon numarası ya da isim parçası")
    p.add_argument("--cihazlar", action="store_true", help="Giriş cihazlarını listele ve çık")
    p.add_argument("--mikrofon-testi", action="store_true", help="API'ye bağlanmadan mikrofon seviyesini göster")
    a = p.parse_args()

    if a.cihazlar:
        return cihazlari_listele()
    if a.mikrofon_testi:
        return mikrofon_testi(a.mikrofon)

    persona = persona_yukle(Path(a.persona))
    model = os.getenv("NIMBUS_MODEL", "gemini-3.8-live")
    ses = a.ses or persona.get("ses", "Charon")

    talimat = persona.get("talimat")
    if not talimat:  # persona v2 (Faz 1) biçimi
        sys.path.insert(0, str(KOK))
        from nimbus.persona import Persona
        talimat = Persona.yukle(Path(a.persona)).sistem_talimati()
    dongu = SesDongusu(model, ses, talimat, a.yarim_dubleks, a.mikrofon)
    try:
        asyncio.run(dongu.calistir())
    except KeyboardInterrupt:
        dongu.ozet_yaz()
        print("\n👋 Görüşürüz.")
    finally:
        dongu.pya.terminate()


if __name__ == "__main__":
    main()
