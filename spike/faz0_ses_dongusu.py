"""
Nimbus - Faz 0: Ses döngüsü keşfi
=================================
Mikrofon -> Gemini Live -> Hoparlör. Amaç:
  1) Türkçe ses kalitesini kulakla test etmek
  2) Gecikmeyi ölçmek (konuşman bittikten sonra ilk sesin gelme süresi)
  3) Söz kesmeyi (barge-in) ve yankıyı denemek

Çalıştırma:
  python spike/faz0_ses_dongusu.py                 # varsayılan ses
  python spike/faz0_ses_dongusu.py --ses Charon    # başka bir ses
  python spike/faz0_ses_dongusu.py --yarim-dubleks # hoparlörle test (yankıyı önler)

Çıkmak için Ctrl+C.
"""

import argparse
import asyncio
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


def persona_yukle(yol: Path) -> dict:
    with open(yol, encoding="utf-8") as f:
        return yaml.safe_load(f)


class SesDongusu:
    def __init__(self, model: str, ses: str, talimat: str, yarim_dubleks: bool):
        self.model = model
        self.ses = ses
        self.talimat = talimat
        self.yarim_dubleks = yarim_dubleks

        self.pya = pyaudio.PyAudio()
        self.calinacak: asyncio.Queue[bytes] = asyncio.Queue()
        self.konusuyor_bitis = 0.0  # Nimbus'un sesi en son ne zaman çaldı
        self.son_kullanici_sesi = None  # gecikme ölçümü için
        self.ilk_ses_olculdu = True

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
        )

    async def dinle(self, oturum):
        """Mikrofonu okuyup Live'a gönderir."""
        giris = self.pya.get_default_input_device_info()
        akis = await asyncio.to_thread(
            self.pya.open,
            format=FORMAT,
            channels=KANAL,
            rate=GIRIS_HIZI,
            input=True,
            input_device_index=giris["index"],
            frames_per_buffer=PARCA,
        )
        print(f"🎙  Mikrofon: {giris['name']}")
        while True:
            veri = await asyncio.to_thread(akis.read, PARCA, exception_on_overflow=False)
            # Yarım dubleks: Nimbus konuşurken (ve 300 ms sonrasına kadar) mikrofonu sustur
            if self.yarim_dubleks and time.monotonic() < self.konusuyor_bitis + 0.3:
                continue
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

                # Kullanıcının konuşması (yazıya döküm)
                if icerik.input_transcription and icerik.input_transcription.text:
                    print(f"\033[94mSen:\033[0m {icerik.input_transcription.text}", flush=True)
                    self.son_kullanici_sesi = time.monotonic()
                    self.ilk_ses_olculdu = False

                # Nimbus'un sesi: bir olayda birden fazla parça olabilir, hepsini işle
                if icerik.model_turn:
                    for parca in icerik.model_turn.parts or []:
                        if parca.inline_data and parca.inline_data.data:
                            if not self.ilk_ses_olculdu and self.son_kullanici_sesi:
                                ms = (time.monotonic() - self.son_kullanici_sesi) * 1000
                                print(f"\033[90m⏱  ilk ses ~{ms:.0f} ms\033[0m", flush=True)
                                self.ilk_ses_olculdu = True
                            self.calinacak.put_nowait(parca.inline_data.data)

                if icerik.output_transcription and icerik.output_transcription.text:
                    print(f"\033[93mNimbus:\033[0m {icerik.output_transcription.text}", flush=True)

                # Söz kesildi: çalma kuyruğunu boşalt
                if icerik.interrupted:
                    while not self.calinacak.empty():
                        self.calinacak.get_nowait()
                    print("\033[90m✋ (sözü kesildi)\033[0m", flush=True)

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

    async def calistir(self):
        anahtar = os.getenv("GEMINI_API_KEY")
        if not anahtar:
            sys.exit("❌ GEMINI_API_KEY bulunamadı. .env.example dosyasını .env olarak kopyalayıp anahtarını yapıştır.")

        istemci = genai.Client(api_key=anahtar)
        print(f"☁️  Model: {self.model} | Ses: {self.ses} | Yarım dubleks: {self.yarim_dubleks}")
        print("Konuşmaya başla. Çıkmak için Ctrl+C.\n")

        async with istemci.aio.live.connect(model=self.model, config=self.ayar()) as oturum:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self.dinle(oturum))
                tg.create_task(self.al(oturum))
                tg.create_task(self.cal())


def main():
    p = argparse.ArgumentParser(description="Nimbus Faz 0 ses döngüsü")
    p.add_argument("--ses", default=None, help=f"Ses adı. Örnekler: {', '.join(ORNEK_SESLER)}")
    p.add_argument("--persona", default=str(KOK / "personas" / "nimbus.yaml"))
    p.add_argument("--yarim-dubleks", action="store_true", help="Nimbus konuşurken mikrofonu sustur (hoparlörle test için)")
    a = p.parse_args()

    persona = persona_yukle(Path(a.persona))
    model = os.getenv("NIMBUS_MODEL", "gemini-3.8-live")
    ses = a.ses or persona.get("ses", "Charon")

    dongu = SesDongusu(model, ses, persona["talimat"], a.yarim_dubleks)
    try:
        asyncio.run(dongu.calistir())
    except KeyboardInterrupt:
        print("\n👋 Görüşürüz.")
    finally:
        dongu.pya.terminate()


if __name__ == "__main__":
    main()
