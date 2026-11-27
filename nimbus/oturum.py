"""Gemini Live oturumu: mikrofon -> model -> hoparlör + gövde, yazıya döküm ve kayıt."""

import asyncio
import json
import sys
import time
from datetime import datetime

import pyaudio
from google import genai
from google.genai import types

from .ayarlar import Ayarlar
from .govde import Govde
from .persona import Persona
from .ses import GIRIS_HIZI, Hoparlor, Mikrofon, rms

KONUSMA_ESIGI = 700  # mikrofonda bu RMS'in üstü "konuşuyor" sayılır (gecikme ölçümü için)

MAVI, SARI, GRI, SIFIRLA = "\033[94m", "\033[93m", "\033[90m", "\033[0m"


def istemci_olustur(a: Ayarlar) -> tuple[genai.Client, str]:
    if a.arka_uc == "vertex":
        if not a.proje:
            sys.exit("❌ Vertex için .env'de GOOGLE_CLOUD_PROJECT gerekli.")
        # Kimlik: `gcloud auth application-default login`
        return genai.Client(vertexai=True, project=a.proje, location=a.bolge), f"vertex:{a.proje}/{a.bolge}"

    if not a.gemini_anahtar or a.gemini_anahtar == "buraya_yapistir":
        sys.exit("❌ GEMINI_API_KEY bulunamadı.")
    # Live API, Gemini Developer API'de v1beta altında; SDK varsayılanı v1
    istemci = genai.Client(api_key=a.gemini_anahtar, http_options=types.HttpOptions(api_version="v1beta"))
    return istemci, "gemini-api"


class Oturum:
    def __init__(self, ayarlar: Ayarlar, persona: Persona, govde: Govde,
                 yarim_dubleks: bool = False, dil_ipucu: bool = False):
        self.a = ayarlar
        self.persona = persona
        self.govde = govde
        self.yarim_dubleks = yarim_dubleks
        self.dil_ipucu = dil_ipucu

        self.pya = pyaudio.PyAudio()
        self.mikrofon: Mikrofon | None = None
        self.hoparlor: Hoparlor | None = None

        # Gecikme: mikrofonda son konuşma sesi -> Nimbus'un ilk ses parçası
        self.son_konusma_ani: float | None = None
        self.yanit_basladi = False
        self.gecikmeler: list[float] = []

        # Yazıya dökümler parça parça gelir; tur bitince tek satır
        self.sen_tampon = ""
        self.nimbus_tampon = ""
        self.kayit = None

    # ---------- Live ayarları ----------
    def live_ayari(self) -> types.LiveConnectConfig:
        konusma = types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.persona.ses)
            ),
            language_code=self.persona.dil if self.dil_ipucu else None,
        )
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=self.persona.sistem_talimati(),
            speech_config=konusma,
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                    silence_duration_ms=self.a.sessizlik_ms,
                )
            ),
        )

    # ---------- Döngüler ----------
    async def dinle(self, oturum) -> None:
        while True:
            veri = await self.mikrofon.oku()
            if self.yarim_dubleks and time.monotonic() < self.hoparlor.konusuyor_bitis + 0.3:
                continue
            if rms(veri) > KONUSMA_ESIGI:
                self.son_konusma_ani = time.monotonic()
            await oturum.send_realtime_input(
                audio=types.Blob(data=veri, mime_type=f"audio/pcm;rate={GIRIS_HIZI}")
            )

    async def al(self, oturum) -> None:
        while True:
            async for yanit in oturum.receive():
                icerik = yanit.server_content
                if icerik is None:
                    continue

                if icerik.input_transcription and icerik.input_transcription.text:
                    self.sen_tampon += icerik.input_transcription.text

                # Bir olayda birden fazla parça olabilir, hepsini işle
                if icerik.model_turn:
                    for parca in icerik.model_turn.parts or []:
                        if parca.inline_data and parca.inline_data.data:
                            if not self.yanit_basladi:
                                self.yanit_basladi = True
                                self._sen_yaz()
                                self._gecikme_yaz()
                            self.hoparlor.cal(parca.inline_data.data)

                if icerik.output_transcription and icerik.output_transcription.text:
                    self.nimbus_tampon += icerik.output_transcription.text

                if icerik.interrupted:
                    self.hoparlor.sustur()
                    self._nimbus_yaz(kesildi=True)

                if icerik.turn_complete:
                    self._nimbus_yaz()

    # ---------- Çıktı ve kayıt ----------
    def _kaydet(self, kim: str, metin: str, **ek) -> None:
        if self.kayit:
            satir = {"zaman": datetime.now().isoformat(timespec="seconds"), "kim": kim, "metin": metin, **ek}
            self.kayit.write(json.dumps(satir, ensure_ascii=False) + "\n")
            self.kayit.flush()

    def _sen_yaz(self) -> None:
        metin = self.sen_tampon.strip()
        if metin:
            print(f"{MAVI}Sen:{SIFIRLA} {metin}", flush=True)
            self._kaydet("sen", metin)
        self.sen_tampon = ""

    def _gecikme_yaz(self) -> None:
        if self.son_konusma_ani is None:
            return
        ms = (time.monotonic() - self.son_konusma_ani) * 1000
        self.gecikmeler.append(ms)
        print(f"{GRI}⏱  sen sustuktan sonra ilk ses: {ms:.0f} ms{SIFIRLA}", flush=True)
        self.son_konusma_ani = None

    def _nimbus_yaz(self, kesildi: bool = False) -> None:
        metin = self.nimbus_tampon.strip()
        if metin:
            ek = f" {GRI}✋ (sözü kesildi){SIFIRLA}" if kesildi else ""
            print(f"{SARI}{self.persona.ad}:{SIFIRLA} {metin}{ek}\n", flush=True)
            self._kaydet("nimbus", metin, kesildi=kesildi,
                         gecikme_ms=round(self.gecikmeler[-1]) if self.gecikmeler else None)
        self.nimbus_tampon = ""
        self.yanit_basladi = False

    def ozet_yaz(self) -> None:
        if self.gecikmeler:
            g = sorted(self.gecikmeler)
            print(f"\n📊 {len(g)} cevap | ortanca {g[len(g) // 2]:.0f} ms | "
                  f"en iyi {g[0]:.0f} ms | en kötü {g[-1]:.0f} ms")
        if self.kayit:
            print(f"📝 Konuşma kaydı: {self.kayit.name}")

    # ---------- Çalıştır ----------
    async def calistir(self) -> None:
        istemci, arka_uc = istemci_olustur(self.a)
        self.mikrofon = Mikrofon(self.pya, self.a.mikrofon)
        self.hoparlor = Hoparlor(self.pya, self.govde)

        self.a.kayit_klasoru.mkdir(exist_ok=True)
        dosya = self.a.kayit_klasoru / f"konusma-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
        self.kayit = open(dosya, "a", encoding="utf-8")

        print(f"☁️  {arka_uc} | Model: {self.a.model} | Persona: {self.persona.ad} ({self.persona.ses})")
        print(f"🎙  Mikrofon: {self.mikrofon.ad}")
        print("Konuşmaya başla. Çıkmak için Ctrl+C.\n")

        async with istemci.aio.live.connect(model=self.a.model, config=self.live_ayari()) as oturum:
            self.govde.durum("sohbet")
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self.dinle(oturum))
                tg.create_task(self.al(oturum))

    def kapat(self) -> None:
        if self.hoparlor:
            self.hoparlor.kapat()
        if self.mikrofon:
            self.mikrofon.kapat()
        if self.kayit:
            self.kayit.close()
        self.pya.terminate()
