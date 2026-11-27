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

# Ağız senkronu: 20 ms'lik pencerelerde ses şiddeti -> 0..3 açıklık
AGIZ_PENCERE = int(CIKIS_HIZI * 0.02) * 2  # bayt
AGIZ_ESIKLERI = (300, 1500, 4000)


def rms(veri: bytes) -> float:
    ornekler = array.array("h", veri[: len(veri) // 2 * 2])
    return math.sqrt(sum(x * x for x in ornekler) / len(ornekler)) if ornekler else 0.0


def agiz_seviyesi(deger: float) -> int:
    return sum(deger > e for e in AGIZ_ESIKLERI)


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


class Hoparlor:
    """Kendi iş parçacığında çalar; her 20 ms'de gövdeye ağız seviyesini bildirir."""

    def __init__(self, pya: pyaudio.PyAudio, govde):
        self.govde = govde
        self.konusuyor_bitis = 0.0  # yarım dubleks için: son sesin bitiş zamanı
        self._kuyruk: queue.Queue[bytes] = queue.Queue()
        self._kesildi = threading.Event()
        self._akis = pya.open(format=FORMAT, channels=KANAL, rate=CIKIS_HIZI, output=True)
        self._calis = True
        self._is = threading.Thread(target=self._dongu, daemon=True)
        self._is.start()

    def cal(self, veri: bytes) -> None:
        self._kuyruk.put(veri)

    def sustur(self) -> None:
        """Söz kesildiğinde: kuyruktaki ve çalmakta olan sesi bırak."""
        self._kesildi.set()
        while not self._kuyruk.empty():
            try:
                self._kuyruk.get_nowait()
            except queue.Empty:
                break

    def _dongu(self) -> None:
        agiz_acik = False
        while self._calis:
            try:
                veri = self._kuyruk.get(timeout=0.06)
            except queue.Empty:
                if agiz_acik:
                    self.govde.agiz(0)
                    agiz_acik = False
                continue
            self._kesildi.clear()
            for i in range(0, len(veri), AGIZ_PENCERE):
                if self._kesildi.is_set():
                    break
                dilim = veri[i : i + AGIZ_PENCERE]
                # Ağzı sesten bir pencere (~20 ms) önce hareket ettir: servo gecikmesini telafi eder
                self.govde.agiz(agiz_seviyesi(rms(dilim)))
                agiz_acik = True
                self.konusuyor_bitis = time.monotonic() + len(dilim) / 2 / CIKIS_HIZI
                self._akis.write(dilim)

    def kapat(self) -> None:
        self._calis = False
        self._is.join(timeout=1)
        self._akis.close()
