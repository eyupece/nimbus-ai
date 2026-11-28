"""Ses giriş/çıkışı: mikrofon seçimi, mikrofon okuma, hoparlör + ağız senkronu."""

import array
import asyncio
import math
import queue
import sys
import threading
import time

import pyaudio

FORMAT = pyaudio.paInt16
KANAL = 1
GIRIS_HIZI = 16000  # Live API girişi: 16 kHz, 16-bit mono PCM
CIKIS_HIZI = 24000  # Live API çıkışı: 24 kHz, 16-bit mono PCM
PARCA = 1024

# Gerçek mikrofon olmayan "geri döngü" cihazları (sistem sesini kaydeder)
GERI_DONGU = ("stereo mix", "stereo karışımı", "loopback", "what u hear", "wave out")
# Windows'un "varsayılana yönlendir" sanal cihazları; varsayılan Stereo Mix ise onu kaydeder
YONLENDIRICI = ("sound mapper", "ses eşleyici", "primary sound capture", "birincil ses yakalama")

# Ağız senkronu: 20 ms'lik pencerelerde ses şiddeti -> 0..1 açıklık
AGIZ_PENCERE = int(CIKIS_HIZI * 0.02) * 2  # bayt
AGIZ_TABAN = 250    # bu şiddetin altı: ağız kapalı
AGIZ_TAVAN = 5000   # bu şiddetin üstü: ağız tam açık


def rms(veri: bytes) -> float:
    ornekler = array.array("h", veri[: len(veri) // 2 * 2])
    return math.sqrt(sum(x * x for x in ornekler) / len(ornekler)) if ornekler else 0.0


def cihaz_adi(d: dict) -> str:
    """Windows (MME) Türkçe cihaz adlarını bozuk gösterebiliyor: 'KulaklÄ±k' -> 'Kulaklık'."""
    try:
        return d["name"].encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return d["name"]


def giris_cihazlari(pya: pyaudio.PyAudio) -> list[dict]:
    """Varsayılan ses API'sindeki (Windows'ta MME) giriş cihazları."""
    api = pya.get_default_host_api_info()["index"]
    return [
        d
        for i in range(pya.get_device_count())
        if (d := pya.get_device_info_by_index(i))["maxInputChannels"] > 0 and d["hostApi"] == api
    ]


def mikrofon_sec(pya: pyaudio.PyAudio, secim: str | None) -> dict:
    """Numara ya da isim parçasıyla seç; verilmezse geri döngü olmayan ilk uygun cihaz."""
    cihazlar = giris_cihazlari(pya)
    if secim:
        if secim.isdigit():
            return pya.get_device_info_by_index(int(secim))
        for d in cihazlar:
            if secim.lower() in cihaz_adi(d).lower():
                return d
        sys.exit(f"❌ '{secim}' adında mikrofon yok. Liste için: python -m nimbus --cihazlar")

    varsayilan = pya.get_default_input_device_info()
    if not any(k in cihaz_adi(varsayilan).lower() for k in GERI_DONGU):
        return varsayilan
    for d in cihazlar:
        if not any(k in cihaz_adi(d).lower() for k in GERI_DONGU + YONLENDIRICI):
            print(f"⚠️  Varsayılan giriş '{cihaz_adi(varsayilan)}' bir geri döngü cihazı, atlandı.")
            return d
    sys.exit("❌ Gerçek bir mikrofon bulunamadı. Liste için: python -m nimbus --cihazlar")


def cihazlari_listele() -> None:
    pya = pyaudio.PyAudio()
    varsayilan = pya.get_default_input_device_info()["index"]
    print("Giriş cihazları (--mikrofon NUMARA ya da isim parçası ile seç):\n")
    for d in giris_cihazlari(pya):
        isaret = "  ← varsayılan" if d["index"] == varsayilan else ""
        uyari = "  (geri döngü, mikrofon değil)" if any(k in cihaz_adi(d).lower() for k in GERI_DONGU) else ""
        print(f"  [{d['index']:>2}] {cihaz_adi(d)}{isaret}{uyari}")
    pya.terminate()


def mikrofon_testi(secim: str | None, saniye: int = 8) -> None:
    """API'ye bağlanmadan mikrofonun ses alıp almadığını gösterir."""
    pya = pyaudio.PyAudio()
    giris = mikrofon_sec(pya, secim)
    akis = pya.open(format=FORMAT, channels=KANAL, rate=GIRIS_HIZI, input=True,
                    input_device_index=giris["index"], frames_per_buffer=PARCA)
    print(f"🎙  {cihaz_adi(giris)} - {saniye} saniye konuş, çubuk hareket etmeli:\n")
    bitis = time.monotonic() + saniye
    en_yuksek = 0.0
    while time.monotonic() < bitis:
        deger = rms(akis.read(PARCA, exception_on_overflow=False))
        en_yuksek = max(en_yuksek, deger)
        print(f"\r  {'█' * min(40, int(deger / 150)):<40} {deger:6.0f}", end="", flush=True)
    akis.close()
    pya.terminate()
    durum = "✅ ses alınıyor" if en_yuksek > 500 else "⚠️  neredeyse hiç ses yok, başka mikrofon dene"
    print(f"\n\n{durum} (en yüksek seviye: {en_yuksek:.0f})")


class Mikrofon:
    def __init__(self, pya: pyaudio.PyAudio, secim: str | None):
        self.cihaz = mikrofon_sec(pya, secim)
        self.ad = cihaz_adi(self.cihaz)
        self._akis = pya.open(format=FORMAT, channels=KANAL, rate=GIRIS_HIZI, input=True,
                              input_device_index=self.cihaz["index"], frames_per_buffer=PARCA)

    async def oku(self) -> bytes:
        return await asyncio.to_thread(self._akis.read, PARCA, exception_on_overflow=False)

    def kapat(self) -> None:
        self._akis.close()


class AgizYumusatici:
    """Ses şiddetini 0-1 arası ağız açıklığına çevirir: hızlı açılır, yavaş kapanır (doğal konuşma)."""

    def __init__(self, tavan: float = AGIZ_TAVAN, acilma: float = 0.65, kapanma: float = 0.30):
        self.tavan, self.acilma, self.kapanma = tavan, acilma, kapanma
        self.deger = 0.0

    def __call__(self, ses_siddeti: float) -> float:
        hedef = max(0.0, min(1.0, (ses_siddeti - AGIZ_TABAN) / (self.tavan - AGIZ_TABAN)))
        hedef = hedef ** 0.7  # sessiz hecelerde de ağız biraz açılsın
        katsayi = self.acilma if hedef > self.deger else self.kapanma
        self.deger += (hedef - self.deger) * katsayi
        return self.deger


class Hoparlor:
    """Kendi iş parçacığında çalar; ağız açıklığını sesin gerçekten duyulduğu ana göre bildirir.

    Ses kartına yazılan ses, işletim sisteminin tamponu yüzünden ~100-200 ms sonra duyulur.
    Ağız hareketleri bu gecikme kadar ertelenir (+ NIMBUS_AGIZ_KAYDIR_MS ile ince ayar).
    """

    def __init__(self, pya: pyaudio.PyAudio, govde, kaydir_ms: int = 0, akis=None):
        self.govde = govde
        self.konusuyor_bitis = 0.0  # yarım dubleks için: son sesin bitiş zamanı
        self.calinan_bayt = 0  # şimdiye kadar ses kartına yazılan ses (kesilme oranı için)
        self._kuyruk: queue.Queue[bytes] = queue.Queue()
        self._agiz_kuyrugu: queue.Queue[tuple[float, float]] = queue.Queue()
        self._kesildi = threading.Event()
        # akis: ses kartı yerine başka bir çıkış (örn. Wi-Fi üzerinden ESP32 hoparlörü)
        self._akis = akis or pya.open(format=FORMAT, channels=KANAL, rate=CIKIS_HIZI, output=True,
                                      frames_per_buffer=AGIZ_PENCERE // 2)
        self.cikis_gecikmesi = self._akis.get_output_latency() + kaydir_ms / 1000
        self._calis = True
        self._is = threading.Thread(target=self._dongu, daemon=True)
        self._agiz_is = threading.Thread(target=self._agiz_dongusu, daemon=True)
        self._is.start()
        self._agiz_is.start()

    def cal(self, veri: bytes) -> None:
        self._kuyruk.put(veri)

    def sustur(self) -> None:
        """Söz kesildiğinde: kuyruktaki ve çalmakta olan sesi bırak, ağzı kapat."""
        self._kesildi.set()
        for k in (self._kuyruk, self._agiz_kuyrugu):
            while not k.empty():
                try:
                    k.get_nowait()
                except queue.Empty:
                    break
        self.konusuyor_bitis = time.monotonic()
        if hasattr(self._akis, "temizle"):
            self._akis.temizle()
        self._agiz_kuyrugu.put((0.0, 0.0))

    def _dongu(self) -> None:
        yumusat = AgizYumusatici()
        while self._calis:
            try:
                veri = self._kuyruk.get(timeout=0.06)
            except queue.Empty:
                if yumusat.deger > 0:
                    yumusat.deger = 0.0
                    self._agiz_kuyrugu.put((time.monotonic() + self.cikis_gecikmesi, 0.0))
                continue
            self._kesildi.clear()
            for i in range(0, len(veri), AGIZ_PENCERE):
                if self._kesildi.is_set():
                    break
                dilim = veri[i : i + AGIZ_PENCERE]
                aciklik = yumusat(rms(dilim))
                self._akis.write(dilim)
                self.calinan_bayt += len(dilim)
                simdi = time.monotonic()
                self.konusuyor_bitis = simdi + self.cikis_gecikmesi
                # Bu dilim, tampondaki sesten sonra, yaklaşık cikis_gecikmesi kadar sonra duyulacak
                self._agiz_kuyrugu.put((simdi + self.cikis_gecikmesi, aciklik))

    def _agiz_dongusu(self) -> None:
        """Ağız değerlerini zamanı gelince gövdeye iletir."""
        while self._calis:
            try:
                zaman, aciklik = self._agiz_kuyrugu.get(timeout=0.2)
            except queue.Empty:
                continue
            bekle = zaman - time.monotonic()
            if bekle > 0:
                time.sleep(bekle)
            self.govde.agiz(aciklik)

    def kapat(self) -> None:
        self._calis = False
        self._agiz_kuyrugu.put((0.0, 0.0))  # ağız iş parçacığını uyandır
        self._is.join(timeout=0.5)
        self._agiz_is.join(timeout=0.5)
        self._akis.close()
