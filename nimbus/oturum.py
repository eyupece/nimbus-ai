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

from .araclar import ARACLAR, ARAMA, BAK, GORME_TALIMATI, SAHNE_ONEKI, SAHNE_TALIMATI, sessiz_yanit, yanit
from .hafiza import Hafiza, anahtar, notlari_cikar
from .ayarlar import Ayarlar
from .eylem import EKRAN, SLAYT, SUNUM_TALIMATI, slayt_tusu
from .durum import Durum, komut_yardimi, operator_dinle
from .govde import JESTLER, Govde
from .ifade import IfadeOkuyucu
from .persona import Persona
from .ses import GIRIS_HIZI, Hoparlor, Mikrofon, rms

class KonusmaAlgilayici:
    """Mikrofonun gürültü tabanını öğrenir; konuşmayı ona göre ayırır (kısık/yüksek her mikrofonda çalışır).

    Sadece gecikme ölçümü için kullanılır; asıl konuşma algılamayı Gemini sunucusu yapar.
    """

    def __init__(self):
        self.taban = 200.0

    def konusuyor_mu(self, siddet: float) -> bool:
        # Taban yavaşça yükselir, hızlıca düşer: sessiz anları izler
        self.taban += (siddet - self.taban) * (0.002 if siddet > self.taban else 0.05)
        return siddet > max(250.0, self.taban * 3)

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


HAFIZA_TALIMATI = (
    "Hafızan var: karşındaki adını söylediği anda, cevap vermeden önce kisiyi_tani fonksiyonunu çağır. "
    "Sonuç geldiğinde onu tanıyorsan bunu doğal, esprili ve kısa şekilde belli et (bildiklerinden birine değin); "
    "tanımıyorsan yeni tanıştığınızı bil. Hafızanı bir kayıt sistemi gibi anlatma, sadece hatırla."
)

AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def zaman_bilgisi(konum: str | None) -> str:
    """Modelin bugünü ve saati bilmesi için (Jarvis hissi)."""
    simdi = datetime.now()
    metin = (f"Şu an {simdi.day} {AYLAR[simdi.month - 1]} {simdi.year}, {GUNLER[simdi.weekday()]}, "
             f"saat {simdi:%H:%M}.")
    if konum:
        metin += f" Bulunduğun yer: {konum}."
    return metin


def birlestir(onceki: str, parca: str) -> str:
    """Yazıya döküm parçalarını birleştirir; cümle sonu ile yeni cümle arasına boşluk koyar."""
    if onceki and onceki[-1] in ".?!," and parca and not parca[0].isspace():
        return onceki + " " + parca
    return onceki + parca


def duyulan_kisim(metin: str, oran: float, uc: str = "…") -> str:
    """Söz kesildiğinde metnin yaklaşık olarak gerçekten seslendirilen kısmı (kelime sınırında)."""
    metin = metin.strip()
    if oran >= 0.97 or not metin:
        return metin
    sinir = int(len(metin) * max(oran, 0.0))
    kesik = metin[:sinir]
    if sinir < len(metin) and " " in kesik:
        kesik = kesik.rsplit(" ", 1)[0]  # yarım kelime bırakma
    return kesik.rstrip(" ,.;:") + uc


class Oturum:
    def __init__(self, ayarlar: Ayarlar, persona: Persona, govde: Govde,
                 yarim_dubleks: bool = False, dil_ipucu: bool = False, kamera=None, sunum: bool = False):
        self.a = ayarlar
        self.persona = persona
        self.govde = govde
        self.yarim_dubleks = yarim_dubleks
        self.dil_ipucu = dil_ipucu
        self.arama_acik = ayarlar.arama  # Google araması (desteklenmezse otomatik kapanır)
        self.hafiza = Hafiza()
        self.kamera = kamera  # Kamera ya da SabitGorsel; None = görme yok
        self.sunum = sunum  # slayt kontrolü
        self.ekran = getattr(govde, "ekran_var", False)  # bilgi kartı gösterebilir mi
        self.aktif_kisi: str | None = None  # bu konuşmada kendini tanıtan kişi
        self.konusma_metni: list[tuple[str, str]] = []  # not çıkarmak için
        self.arka_plan: set[asyncio.Task] = set()  # konuşma sonrası not çıkarma görevleri

        self.pya = pyaudio.PyAudio()
        self.istemci: genai.Client | None = None
        self.mikrofon: Mikrofon | None = None
        self.hoparlor: Hoparlor | None = None

        self.durum = Durum.UYKU
        self.live = None  # aktif Live bağlantısı (UYKU'da None)
        self.bitti: asyncio.Event | None = None  # aktif konuşmanın bitiş sinyali
        self.cikis = False
        self.veda_sesi_geldi = False  # veda turunun sesi gelmeden bağlantıyı kapatma
        self.veda_istendi = False  # modele veda cümlesi söylemesi için sahne mesajı gitti mi
        self.komutlar: asyncio.Queue[str] = asyncio.Queue()

        # Gecikme: mikrofonda son konuşma sesi -> Nimbus'un ilk ses parçası
        self.son_konusma_ani: float | None = None
        self.konusma_algilayici = KonusmaAlgilayici()
        self.yanit_basladi = False
        self.gecikmeler: list[float] = []

        # Yazıya dökümler parça parça gelir; tur bitince tek satır
        self.sen_tampon = ""
        self.nimbus_tampon = ""
        self.kayit = None

        # Söz kesilince metni de kesmek için: bu turda gelen ses ve tur başında çalınmış miktar
        self.tur_alinan_bayt = 0
        self.tur_baslangic_calinan = 0
        # Canlı altyazının takip ettiği tur: metin, gelen ses, başlangıç, kesildi mi
        self.altyazi_turu: dict | None = None
        self.ifade = IfadeOkuyucu()  # söylenen metinden gecikmesiz jest

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
            system_instruction="\n\n".join([
                self.persona.sistem_talimati(), SAHNE_TALIMATI, HAFIZA_TALIMATI,
                *([GORME_TALIMATI] if self.kamera else []), *([SUNUM_TALIMATI] if self.sunum else []),
                zaman_bilgisi(self.a.konum),
            ]),
            speech_config=konusma,
            tools=(ARACLAR + ([ARAMA] if self.arama_acik else []) + ([BAK] if self.kamera else [])
                   + ([EKRAN] if self.ekran else []) + ([SLAYT] if self.sunum else [])),
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

    async def goruntu_gonder(self, live) -> bool:
        """Kameradan tek kare alıp modele gönderir."""
        if not self.kamera:
            return False
        try:
            jpeg = await asyncio.to_thread(self.kamera.kare_al)
        except Exception as hata:
            print(f"{GRI}⚠️  Kamera: {hata}{SIFIRLA}", flush=True)
            return False
        self.govde.jest("bak")
        self._kaydet("gorme", f"kare gönderildi ({len(jpeg) // 1024} KB)")
        await live.send_realtime_input(video=types.Blob(data=jpeg, mime_type="image/jpeg"))
        return True

    def karsilama_mesaji(self, goruntu_var: bool) -> str:
        metin = f"Karşına biri geldi. {self.persona.karsilama}"
        if goruntu_var:
            metin += (" Az önce kameradan baktın. Görüntüde gerçekten gördüğün bir şeye kısaca değin: karşında biri "
                      "varsa kıyafeti, aksesuarı ya da elindeki eşya; kimse görünmüyorsa ortam ya da masadaki bir şey. "
                      "Görüntüde olmayan hiçbir şeyi söyleme; emin değilsen görüntüye hiç değinme.")
        return metin

    async def veda_baslat(self, operatorden: bool) -> None:
        if self.durum in (Durum.KARSILAMA, Durum.SOHBET):
            self.durum_degistir(Durum.VEDA)
            # Model kendisi vedalaştıysa ve bu turda konuştuysa veda sesi gelmiştir; konuşmadan çağırdıysa
            # tur bitince ona veda cümlesi söyletilir. Operatör istediyse yeni veda cümlesi beklenir.
            # (turn_complete=True ile giden mesaj, sürmekte olan cevabı keser.)
            self.veda_sesi_geldi = (not operatorden) and self.yanit_basladi
            self.veda_istendi = operatorden
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
            if self.konusma_algilayici.konusuyor_mu(rms(veri)):
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
            async for mesaj in live.receive():
                if mesaj.tool_call:
                    await self.arac_cagrilari(live, mesaj.tool_call)

                icerik = mesaj.server_content
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
                                self.altyazi_turu = {"metin": "", "alinan": 0, "kesildi": False,
                                                     "baslangic": self.tur_baslangic_calinan}
                                self.ifade.yeni_tur()
                                self._sen_yaz()
                                self._gecikme_yaz()
                            self.tur_alinan_bayt += len(parca.inline_data.data)
                            if self.altyazi_turu:
                                self.altyazi_turu["alinan"] = self.tur_alinan_bayt
                            self.hoparlor.cal(parca.inline_data.data)
                            if self.durum == Durum.VEDA:
                                self.veda_sesi_geldi = True

                if icerik.output_transcription and icerik.output_transcription.text:
                    self.nimbus_tampon = birlestir(self.nimbus_tampon, icerik.output_transcription.text)
                    if self.altyazi_turu and not self.altyazi_turu["kesildi"]:
                        self.altyazi_turu["metin"] = self.nimbus_tampon

                if icerik.interrupted:
                    calinan = self.hoparlor.calinan_bayt - self.tur_baslangic_calinan
                    self.hoparlor.sustur()
                    if self.tur_alinan_bayt:
                        self.nimbus_tampon = duyulan_kisim(self.nimbus_tampon, calinan / self.tur_alinan_bayt)
                    if self.altyazi_turu:
                        self.altyazi_turu.update(metin=self.nimbus_tampon, kesildi=True)
                    self._nimbus_yaz(kesildi=True)

                if icerik.turn_complete:
                    self._nimbus_yaz()
                    if self.durum == Durum.KARSILAMA:
                        self.durum_degistir(Durum.SOHBET)
                    elif self.durum == Durum.VEDA and self.veda_sesi_geldi:
                        asyncio.create_task(self.konusmayi_bitir())
                    elif self.durum == Durum.VEDA and not self.veda_istendi:
                        # Model uykuya_don'u hiç konuşmadan çağırdı: sessizce uyumasın, vedalaşsın
                        self.veda_istendi = True
                        await self.sahne_mesaji(self.persona.veda)

    async def arac_cagrilari(self, live, arac: types.LiveServerToolCall) -> None:
        yanitlar = []
        for cagri in arac.function_calls or []:
            try:
                yanitlar.append(await self._arac_isle(live, cagri))
            except Exception as hata:  # BLOCKING çağrı yanıtsız kalırsa model donar: her zaman yanıt ver
                print(f"{GRI}⚠️  {cagri.name} hatası: {hata}{SIFIRLA}", flush=True)
                yanitlar.append(yanit(cagri, {"hata": f"{cagri.name} çalışmadı"}))
        if yanitlar:
            await live.send_tool_response(function_responses=yanitlar)

    async def _arac_isle(self, live, cagri: types.FunctionCall) -> types.FunctionResponse:
        argumanlar = cagri.args or {}
        if cagri.name == "kisiyi_tani":
            ad = (argumanlar.get("ad") or "").strip()
            bilgi = self.hafiza.tani(ad) if ad else {"hata": "ad boş"}
            if ad:
                self.aktif_kisi = bilgi.get("ad", ad)
                durum = "tanıdı" if bilgi.get("taniyor_musun") else "yeni kişi"
                print(f"{MOR}🧠 hafıza: {self.aktif_kisi} ({durum}){SIFIRLA}", flush=True)
                self._kaydet("hafiza", f"kisiyi_tani: {ad}", sonuc=bilgi)
            return yanit(cagri, bilgi)  # BLOCKING: model bunu alıp konuşmaya devam eder
        if cagri.name == "bak":
            gonderildi = await self.goruntu_gonder(live)
            return yanit(cagri, {"tamam": True, "not": "Kameradan son görüntü gönderildi, ona bakarak cevap ver."}
                         if gonderildi else {"hata": "Kamera şu an çalışmıyor; göremediğini söyle."})
        if cagri.name == "ekranda_goster":
            baslik, metin = argumanlar.get("baslik", ""), argumanlar.get("metin", "")
            self.govde.kart(baslik, metin)
            self._kaydet("kart", baslik, icerik=metin)
            return yanit(cagri, {"tamam": True})
        if cagri.name == "slayt":
            yon = argumanlar.get("yon", "ileri")
            basarili = bool(self.sunum and await asyncio.to_thread(slayt_tusu, yon))
            print(f"{MOR}🖥  slayt: {yon}{'' if basarili else ' (gönderilemedi)'}{SIFIRLA}", flush=True)
            self._kaydet("slayt", yon, basarili=basarili)
            return yanit(cagri, {"tamam": True} if basarili else {"hata": "Slayt değiştirilemedi"})
        if cagri.name == "uykuya_don":
            await self.veda_baslat(operatorden=False)
            return sessiz_yanit(cagri)
        if cagri.name == "jest" and argumanlar.get("ad") in JESTLER:  # eski sürümlerden kalma, zararsız
            self.govde.jest(argumanlar["ad"])
            return yanit(cagri)
        return yanit(cagri, {"hata": "bilinmeyen fonksiyon"})

    async def canli_altyazi(self) -> None:
        """Nimbus konuşurken altyazıyı sesin çalınan kısmına göre kelime kelime ilerletir."""
        son = ""
        while True:
            await asyncio.sleep(0.12)
            tur = self.altyazi_turu
            if not tur or not tur["alinan"] or not tur["metin"]:
                continue
            if tur["kesildi"]:
                metin, bitti = tur["metin"], True  # zaten duyulan kısma kadar kesilmiş
            else:
                oran = (self.hoparlor.calinan_bayt - tur["baslangic"]) / tur["alinan"]
                bitti = oran >= 0.99 and not self.yanit_basladi  # tur bitti ve ses tamamen çalındı
                metin = tur["metin"] if bitti else duyulan_kisim(tur["metin"], oran, uc="")
            if metin and metin != son:
                son = metin
                self.govde.altyazi("nimbus", metin, self.persona.ad)
                jest = self.ifade.oku(metin + (" " if bitti else ""))
                if jest:
                    self.govde.jest(jest)
                    self._kaydet("jest", jest)
            if bitti and self.altyazi_turu is tur:
                self.altyazi_turu = None
                son = ""

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
        self.aktif_kisi = None
        self.konusma_metni = []
        self.durum_degistir(Durum.KARSILAMA)
        try:
            # Kamera açılması Windows'ta birkaç saniye sürebiliyor: bağlantı kurulurken paralel aç
            kamera_hazir = None
            if self.kamera and self.a.ilk_bakis:
                kamera_hazir = asyncio.create_task(asyncio.to_thread(self.kamera.ac))
            async with self.istemci.aio.live.connect(model=self.a.model, config=self.live_ayari()) as live:
                self.live = live
                if kamera_hazir:
                    try:
                        await kamera_hazir
                        if getattr(self.kamera, "acilis_ms", None) is not None:
                            print(f"{GRI}📷 kamera {self.kamera.acilis_ms} ms'de açıldı{SIFIRLA}", flush=True)
                    except Exception as hata:
                        print(f"{GRI}⚠️  Kamera açılamadı: {hata}{SIFIRLA}", flush=True)
                goruntu = self.a.ilk_bakis and await self.goruntu_gonder(live)
                await self.sahne_mesaji(self.karsilama_mesaji(goruntu))
                gorevler = [asyncio.create_task(self.al(live)), asyncio.create_task(self.konusma_komutlari()),
                            asyncio.create_task(self.canli_altyazi())]
                bitis = asyncio.create_task(self.bitti.wait())
                await asyncio.wait([bitis, *gorevler], return_when=asyncio.FIRST_COMPLETED)
                for g in [bitis, *gorevler]:
                    g.cancel()
                sonuclar = await asyncio.gather(*gorevler, return_exceptions=True)
                for sonuc in sonuclar:  # bir görev gerçek bir hatayla bittiyse göster
                    if isinstance(sonuc, Exception) and not isinstance(sonuc, asyncio.CancelledError):
                        print(f"⚠️  Bağlantı hatası: {sonuc}", flush=True)
        except Exception as hata:
            if self.arama_acik and not self.live:
                # Bazı model/bölge kombinasyonları aramayı desteklemeyebilir: aramasız tekrar dene
                print(f"⚠️  Google araması ile bağlanılamadı ({str(hata)[:80]}); aramasız deneniyor.", flush=True)
                self.arama_acik = False
                self.live = None
                return await self.konusma()
            print(f"⚠️  Bağlantı kurulamadı: {hata}", flush=True)
        finally:
            self.live = None
            self.hoparlor.sustur()
            self._nimbus_yaz()
            if self.kamera:
                self.kamera.kapat()  # uykuda kamera kapalı (ışığı söner)
            self.durum_degistir(Durum.UYKU)
            self._hafizaya_yaz()

    def _hafizaya_yaz(self) -> None:
        """Konuşma bittikten sonra arka planda: kişi hakkında notları çıkar ve kaydet."""
        if not self.aktif_kisi or not self.konusma_metni:
            return
        ad, konusma = self.aktif_kisi, list(self.konusma_metni)
        eski = self.hafiza.kisiler.get(anahtar(ad), {}).get("notlar", [])

        async def gorev():
            try:
                notlar = await notlari_cikar(self.istemci, ad, eski, konusma)
            except Exception as hata:
                print(f"{GRI}⚠️  Hafıza notu çıkarılamadı ({str(hata)[:80]}); sadece görüşme kaydedildi.{SIFIRLA}", flush=True)
                notlar = eski
            self.hafiza.gorusmeyi_kaydet(ad, notlar)
            print(f"{MOR}🧠 {ad} hafızaya yazıldı ({len(notlar)} not){SIFIRLA}", flush=True)

        t = asyncio.create_task(gorev())
        self.arka_plan.add(t)
        t.add_done_callback(self.arka_plan.discard)

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
            self.konusma_metni.append(("sen", metin))
            self.govde.altyazi("sen", metin)
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
            # Altyazıyı burada değil canli_altyazi gönderiyor: metin sesten önce geldiği için
            # burada göndermek altyazıyı sesin önüne geçirirdi.
            self.konusma_metni.append(("nimbus", metin))
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
        self.hoparlor = Hoparlor(self.pya, self.govde, kaydir_ms=self.a.agiz_kaydir_ms)

        self.a.kayit_klasoru.mkdir(exist_ok=True)
        dosya = self.a.kayit_klasoru / f"konusma-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
        self.kayit = open(dosya, "a", encoding="utf-8")

        print(f"☁️  {arka_uc} | Model: {self.a.model} | Persona: {self.persona.ad} ({self.persona.ses})")
        print(f"🎙  Mikrofon: {self.mikrofon.ad}")
        if self.kamera:
            print(f"📷 Kamera açık (sadece uyanıkken){' · uyanınca bir kez bakar' if self.a.ilk_bakis else ''}")
        print(f"👄 Ağız senkronu: ses kartı gecikmesi {self.hoparlor.cikis_gecikmesi * 1000:.0f} ms "
              f"(ince ayar: .env NIMBUS_AGIZ_KAYDIR_MS={self.a.agiz_kaydir_ms})")
        if hasattr(self.govde, "baslat"):
            await self.govde.baslat()
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
            if self.arka_plan:  # yazılmayı bekleyen hafıza notları
                print(f"{GRI}🧠 Hafıza kaydediliyor...{SIFIRLA}", flush=True)
                await asyncio.wait(self.arka_plan, timeout=15)

    def kapat(self) -> None:
        if self.hoparlor:
            self.hoparlor.kapat()
        if self.mikrofon:
            self.mikrofon.kapat()
        if self.kayit:
            self.kayit.close()
        self.pya.terminate()
