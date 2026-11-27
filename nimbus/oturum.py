"""Nimbus oturumu: durum makinesi + Gemini Live bağlantısı + ses + gövde + kayıt.

Akış: UYKU ─(operatör: Enter/u)─► KARŞILAMA ─► SOHBET ─(operatör: v / model: uykuya_don)─► VEDA ─► UYKU
Her yeni kişi için ayrı bir Live bağlantısı açılır; böylece bağlam temiz kalır ve oturum süre sınırına takılmaz.
"""

import asyncio
import json
import sys
import time
from datetime import datetime

import pyaudio
from google import genai
from google.genai import types

from .araclar import ARACLAR, SAHNE_ONEKI, SAHNE_TALIMATI, sessiz_yanit, yanit
from .ayarlar import Ayarlar
from .durum import Durum, komut_yardimi, operator_dinle
from .govde import JESTLER, Govde
from .persona import Persona
from .ses import GIRIS_HIZI, Hoparlor, Mikrofon, rms

KONUSMA_ESIGI = 700  # mikrofonda bu RMS'in üstü "konuşuyor" sayılır (gecikme ölçümü için)

MAVI, SARI, GRI, MOR, SIFIRLA = "\033[94m", "\033[93m", "\033[90m", "\033[95m", "\033[0m"


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


def birlestir(onceki: str, parca: str) -> str:
    """Yazıya döküm parçalarını birleştirir; cümle sonu ile yeni cümle arasına boşluk koyar."""
    if onceki and onceki[-1] in ".?!," and parca and not parca[0].isspace():
        return onceki + " " + parca
    return onceki + parca


def duyulan_kisim(metin: str, oran: float) -> str:
    """Söz kesildiğinde metnin yaklaşık olarak gerçekten seslendirilen kısmı (kelime sınırında)."""
    metin = metin.strip()
    if oran >= 0.97 or not metin:
        return metin
    sinir = int(len(metin) * max(oran, 0.0))
    kesik = metin[:sinir]
    if sinir < len(metin) and " " in kesik:
        kesik = kesik.rsplit(" ", 1)[0]  # yarım kelime bırakma
    return kesik.rstrip(" ,.;:") + "…"


class Oturum:
    def __init__(self, ayarlar: Ayarlar, persona: Persona, govde: Govde,
                 yarim_dubleks: bool = False, dil_ipucu: bool = False):
        self.a = ayarlar
        self.persona = persona
        self.govde = govde
        self.yarim_dubleks = yarim_dubleks
        self.dil_ipucu = dil_ipucu

        self.pya = pyaudio.PyAudio()
        self.istemci: genai.Client | None = None
        self.mikrofon: Mikrofon | None = None
        self.hoparlor: Hoparlor | None = None

        self.durum = Durum.UYKU
        self.live = None  # aktif Live bağlantısı (UYKU'da None)
        self.bitti: asyncio.Event | None = None  # aktif konuşmanın bitiş sinyali
        self.cikis = False
        self.veda_sesi_geldi = False  # veda turunun sesi gelmeden bağlantıyı kapatma
        self.komutlar: asyncio.Queue[str] = asyncio.Queue()

        # Gecikme: mikrofonda son konuşma sesi -> Nimbus'un ilk ses parçası
        self.son_konusma_ani: float | None = None
        self.yanit_basladi = False
        self.gecikmeler: list[float] = []

        # Yazıya dökümler parça parça gelir; tur bitince tek satır
        self.sen_tampon = ""
        self.nimbus_tampon = ""
        self.kayit = None

        # Söz kesilince metni de kesmek için: bu turda gelen ses ve tur başında çalınmış miktar
        self.tur_alinan_bayt = 0
        self.tur_baslangic_calinan = 0

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
            system_instruction=self.persona.sistem_talimati() + "\n\n" + SAHNE_TALIMATI,
            speech_config=konusma,
            tools=ARACLAR,
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                    silence_duration_ms=self.a.sessizlik_ms,
                )
            ),
        )

    # ---------- Durum ----------
    def durum_degistir(self, yeni: Durum) -> None:
        if yeni != self.durum:
            self.durum = yeni
            self.govde.durum(yeni.value)
            self._kaydet("sistem", f"durum: {yeni.value}")
            if yeni == Durum.UYKU:
                print(f"{GRI}💤 Uykuda. {komut_yardimi()}{SIFIRLA}", flush=True)

    async def sahne_mesaji(self, metin: str) -> None:
        """Operatör yönlendirmesini modele metin olarak iletir; model sesle cevap verir."""
        if self.live:
            await self.live.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=f"{SAHNE_ONEKI} {metin}")]),
                turn_complete=True,
            )

    async def veda_baslat(self, operatorden: bool) -> None:
        if self.durum in (Durum.KARSILAMA, Durum.SOHBET):
            self.durum_degistir(Durum.VEDA)
            # Model kendisi vedalaştıysa sesi zaten geldi; operatör istediyse yeni veda cümlesini bekle.
            # (turn_complete=True ile giden mesaj, sürmekte olan cevabı keser.)
            self.veda_sesi_geldi = not operatorden
            if operatorden:
                await self.sahne_mesaji(self.persona.veda)

    async def konusmayi_bitir(self) -> None:
        """Veda sesi çalınıp bitince bağlantıyı kapat."""
        while time.monotonic() < self.hoparlor.konusuyor_bitis + 0.2:
            await asyncio.sleep(0.05)
        if self.bitti:
            self.bitti.set()

    # ---------- Döngüler ----------
    async def dinle(self) -> None:
        """Mikrofon her zaman okunur; sadece aktif bir konuşma varken modele gönderilir."""
        while True:
            veri = await self.mikrofon.oku()
            if not self.live or self.durum == Durum.UYKU:
                continue
            if self.yarim_dubleks and time.monotonic() < self.hoparlor.konusuyor_bitis + 0.3:
                continue
            if rms(veri) > KONUSMA_ESIGI:
                self.son_konusma_ani = time.monotonic()
            try:
                await self.live.send_realtime_input(
                    audio=types.Blob(data=veri, mime_type=f"audio/pcm;rate={GIRIS_HIZI}")
                )
            except Exception:
                pass  # bağlantı kapanırken gelen son parçalar

    async def al(self, live) -> None:
        try:
            await self._al(live)
        except Exception as hata:
            # 1000 = bağlantı normal kapandı (veda, sıfırla, çıkış); hata değil
            if "1000" not in str(hata):
                raise

    async def _al(self, live) -> None:
        while True:
            async for yanit in live.receive():
                if yanit.tool_call:
                    await self.arac_cagrilari(live, yanit.tool_call)

                icerik = yanit.server_content
                if icerik is None:
                    continue

                if icerik.input_transcription and icerik.input_transcription.text:
                    self.sen_tampon = birlestir(self.sen_tampon, icerik.input_transcription.text)

                # Bir olayda birden fazla parça olabilir, hepsini işle
                if icerik.model_turn:
                    for parca in icerik.model_turn.parts or []:
                        if parca.inline_data and parca.inline_data.data:
                            if not self.yanit_basladi:
                                self.yanit_basladi = True
                                self.tur_alinan_bayt = 0
                                self.tur_baslangic_calinan = self.hoparlor.calinan_bayt
                                self._sen_yaz()
                                self._gecikme_yaz()
                            self.tur_alinan_bayt += len(parca.inline_data.data)
                            self.hoparlor.cal(parca.inline_data.data)
                            if self.durum == Durum.VEDA:
                                self.veda_sesi_geldi = True

                if icerik.output_transcription and icerik.output_transcription.text:
                    self.nimbus_tampon = birlestir(self.nimbus_tampon, icerik.output_transcription.text)

                if icerik.interrupted:
                    calinan = self.hoparlor.calinan_bayt - self.tur_baslangic_calinan
                    self.hoparlor.sustur()
                    if self.tur_alinan_bayt:
                        self.nimbus_tampon = duyulan_kisim(self.nimbus_tampon, calinan / self.tur_alinan_bayt)
                    self._nimbus_yaz(kesildi=True)

                if icerik.turn_complete:
                    self._nimbus_yaz()
                    if self.durum == Durum.KARSILAMA:
                        self.durum_degistir(Durum.SOHBET)
                    elif self.durum == Durum.VEDA and self.veda_sesi_geldi:
                        asyncio.create_task(self.konusmayi_bitir())

    async def arac_cagrilari(self, live, arac: types.LiveServerToolCall) -> None:
        yanitlar = []
        for cagri in arac.function_calls or []:
            argumanlar = cagri.args or {}
            if cagri.name == "jest":
                if argumanlar.get("ad") in JESTLER:
                    self.govde.jest(argumanlar["ad"])
                    self._kaydet("jest", argumanlar["ad"])
                yanitlar.append(yanit(cagri))  # BLOCKING: model konuşmaya devam etsin
            elif cagri.name == "uykuya_don":
                await self.veda_baslat(operatorden=False)
                yanitlar.append(sessiz_yanit(cagri))
            else:
                yanitlar.append(yanit(cagri, {"hata": "bilinmeyen fonksiyon"}))
        if yanitlar:
            await live.send_tool_response(function_responses=yanitlar)

    async def konusma_komutlari(self) -> None:
        """Konuşma sürerken operatör komutları."""
        while True:
            komut = await self.komutlar.get()
            if komut == "v":
                await self.veda_baslat(operatorden=True)
            elif komut == "s":
                self.hoparlor.sustur()
                self.bitti.set()
            elif komut == "q":
                self.cikis = True
                self.hoparlor.sustur()
                self.bitti.set()

    async def konusma(self) -> None:
        """Bir kişiyle baştan sona bir konuşma: bağlan, karşıla, sohbet et, vedalaş."""
        self.bitti = asyncio.Event()
        self.durum_degistir(Durum.KARSILAMA)
        try:
            async with self.istemci.aio.live.connect(model=self.a.model, config=self.live_ayari()) as live:
                self.live = live
                await self.sahne_mesaji(f"Karşına biri geldi. {self.persona.karsilama}")
                gorevler = [asyncio.create_task(self.al(live)), asyncio.create_task(self.konusma_komutlari())]
                bitis = asyncio.create_task(self.bitti.wait())
                await asyncio.wait([bitis, *gorevler], return_when=asyncio.FIRST_COMPLETED)
                for g in [bitis, *gorevler]:
                    g.cancel()
                sonuclar = await asyncio.gather(*gorevler, return_exceptions=True)
                for sonuc in sonuclar:  # bir görev gerçek bir hatayla bittiyse göster
                    if isinstance(sonuc, Exception) and not isinstance(sonuc, asyncio.CancelledError):
                        print(f"⚠️  Bağlantı hatası: {sonuc}", flush=True)
        except Exception as hata:
            print(f"⚠️  Bağlantı kurulamadı: {hata}", flush=True)
        finally:
            self.live = None
            self.hoparlor.sustur()
            self._nimbus_yaz()
            self.durum_degistir(Durum.UYKU)

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
        self.istemci, arka_uc = istemci_olustur(self.a)
        self.mikrofon = Mikrofon(self.pya, self.a.mikrofon)
        self.hoparlor = Hoparlor(self.pya, self.govde)

        self.a.kayit_klasoru.mkdir(exist_ok=True)
        dosya = self.a.kayit_klasoru / f"konusma-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
        self.kayit = open(dosya, "a", encoding="utf-8")

        print(f"☁️  {arka_uc} | Model: {self.a.model} | Persona: {self.persona.ad} ({self.persona.ses})")
        print(f"🎙  Mikrofon: {self.mikrofon.ad}")
        operator_dinle(self.komutlar, asyncio.get_running_loop())
        self.govde.durum(Durum.UYKU.value)
        print(f"{GRI}💤 Uykuda. {komut_yardimi()}{SIFIRLA}", flush=True)

        mikrofon_gorevi = asyncio.create_task(self.dinle())
        try:
            while not self.cikis:
                komut = await self.komutlar.get()
                if komut in ("", "u"):
                    await self.konusma()
                elif komut == "q":
                    break
        finally:
            mikrofon_gorevi.cancel()

    def kapat(self) -> None:
        if self.hoparlor:
            self.hoparlor.kapat()
        if self.mikrofon:
            self.mikrofon.kapat()
        if self.kayit:
            self.kayit.close()
        self.pya.terminate()
