"""Görme: kameradan istek üzerine tek kare (sürekli video yok).

Kamera sadece Nimbus uyanıkken açıktır; uyuyunca kapanır (kamera ışığı söner).
Kareler diske yazılmaz, sadece o anki konuşmada modele gönderilir.

    python -m nimbus --kamera              # kamerayla çalıştır (varsayılan kamera 0)
    python -m nimbus --kamera 1            # başka kamera
    python -m nimbus --kamera-testi        # kamera çalışıyor mu (görüntü kaydetmez)
"""

import os
import threading
import time
from pathlib import Path

EN_BUYUK_KENAR = 768  # modele gönderilecek karenin en uzun kenarı (piksel)
JPEG_KALITESI = 80


class KameraHatasi(RuntimeError):
    pass


def _jpeg(kare) -> bytes:
    import cv2

    y, g = kare.shape[:2]
    olcek = EN_BUYUK_KENAR / max(y, g)
    if olcek < 1:
        kare = cv2.resize(kare, (int(g * olcek), int(y * olcek)), interpolation=cv2.INTER_AREA)
    tamam, veri = cv2.imencode(".jpg", kare, [cv2.IMWRITE_JPEG_QUALITY, JPEG_KALITESI])
    if not tamam:
        raise KameraHatasi("Kare JPEG'e çevrilemedi")
    return veri.tobytes()


class Kamera:
    """Arka planda son kareyi tutar (kamera tamponundaki eski kareler gönderilmesin)."""

    def __init__(self, indeks: int = 0):
        self.indeks = indeks
        self._cap = None
        self._son = None
        self._calis = False
        self._is: threading.Thread | None = None

    @property
    def acik(self) -> bool:
        return self._calis

    def ac(self) -> None:
        if self._calis:
            return
        try:
            import cv2
        except ImportError as e:
            raise KameraHatasi("OpenCV yüklü değil: pip install -r requirements.txt") from e
        # Windows'ta DirectShow çok daha hızlı açılıyor
        cap = cv2.VideoCapture(self.indeks, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(self.indeks)
        if not cap.isOpened():
            raise KameraHatasi(f"Kamera {self.indeks} açılamadı (başka bir uygulama kullanıyor olabilir)")
        self._cap, self._son, self._calis = cap, None, True
        self._is = threading.Thread(target=self._dongu, daemon=True)
        self._is.start()

    def _dongu(self) -> None:
        while self._calis:
            tamam, kare = self._cap.read()
            if tamam:
                self._son = kare
            else:
                time.sleep(0.05)

    def kare_al(self, zaman_asimi: float = 3.0) -> bytes:
        """Son kareyi JPEG olarak döndürür (gerekirse kamerayı açar)."""
        self.ac()
        bitis = time.monotonic() + zaman_asimi
        while self._son is None:
            if time.monotonic() > bitis:
                raise KameraHatasi("Kameradan görüntü gelmedi")
            time.sleep(0.03)
        return _jpeg(self._son)

    def kapat(self) -> None:
        self._calis = False
        if self._is:
            self._is.join(timeout=1)
        if self._cap is not None:
            self._cap.release()
        self._cap = self._son = self._is = None


class SabitGorsel:
    """Test ve senaryolar için: kamera yerine hep aynı resmi 'gösterir'."""

    def __init__(self, yol: Path):
        self.yol = Path(yol)
        self.acik = False

    def ac(self) -> None:
        self.acik = True

    def kare_al(self, zaman_asimi: float = 3.0) -> bytes:
        return self.yol.read_bytes()

    def kapat(self) -> None:
        self.acik = False


def kamera_testi(indeks: int = 0) -> None:
    k = Kamera(indeks)
    try:
        baslangic = time.monotonic()
        veri = k.kare_al()
        import cv2
        import numpy as np

        kare = cv2.imdecode(np.frombuffer(veri, np.uint8), cv2.IMREAD_COLOR)
        parlaklik = float(kare.mean())
        print(f"📷 Kamera {indeks} çalışıyor: {kare.shape[1]}x{kare.shape[0]}, "
              f"{(time.monotonic() - baslangic) * 1000:.0f} ms'de açıldı, ortalama parlaklık {parlaklik:.0f}/255")
        if parlaklik < 15:
            print("⚠️  Görüntü neredeyse siyah: kamera kapağı kapalı ya da ışık yetersiz olabilir.")
        print("Görüntü kaydedilmedi.")
    except KameraHatasi as e:
        print(f"❌ {e}")
    finally:
        k.kapat()
