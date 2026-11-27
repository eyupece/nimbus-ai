"""Söylenen metinden yüz ifadesi (jest) çıkarır: model fonksiyon çağırmadan, gecikmesiz.

Jest, ilgili kelime altyazıda göründüğü an (yani sesle aynı anda) tetiklenir.
Kurallar basit anahtar kelime/noktalama eşleşmesidir; persona'ya göre genişletilebilir.
"""

import re
import time

# (jest, düzenli ifade) — ilk eşleşen kazanır, sıra önemlidir
KURALLAR: list[tuple[str, re.Pattern]] = [
    ("saskin", re.compile(r"\b(vay|yok artık|ne\?!|nasıl yani|olamaz|hayret|inanılmaz|cidden mi|ciddi misin|oha)", re.I)),
    ("kizgin", re.compile(r"\b(saygısız|terbiyesiz|yeter artık|hiç hoş değil|sinir|alındım|küstüm)", re.I)),
    ("gul", re.compile(r"\b(haha|ahah|hah|güzel|sevindim|harika|hoşuma|tatlı|aferin|şahane|keyif|efsane)", re.I)),
    ("goz_kirp", re.compile(r"\b(aramızda|sır|şaka|belki de|kim bilir|bak sen|demiştim|herkes bilir)", re.I)),
    ("gozleri_kis", re.compile(r"\b(emin misin|gerçekten mi|bakalım|şüpheli|hmm+\?|of+\b|abartma|eski kafa|cringe)", re.I)),
    ("dusun", re.compile(r"\b(hı+mm+|düşüneyim|bir saniye|dur bakalım|ilginç|yani bence)", re.I)),
]

ARALIK_SN = 2.5  # iki jest arasında en az bu kadar süre


class IfadeOkuyucu:
    def __init__(self):
        self.islenen = 0  # metnin ne kadarı tarandı (aynı kelime iki kez tetiklemesin)
        self.son_jest_ani = 0.0

    def yeni_tur(self) -> None:
        self.islenen = 0

    def oku(self, gorunen_metin: str) -> str | None:
        """Altyazıda yeni görünen kısmı tarar; jest gerekiyorsa adını döndürür."""
        # Son kelime yarım olabilir: sadece son boşluğa kadar olan kısmı değerlendir
        sinir = gorunen_metin.rfind(" ")
        if sinir <= self.islenen:
            return None
        eski, self.islenen = self.islenen, sinir
        if time.monotonic() - self.son_jest_ani < ARALIK_SN:
            return None
        hedef = gorunen_metin[:sinir]
        for jest, desen in KURALLAR:
            # Tüm metinde ara (çok kelimeli ifadeler bölünmesin), ama sadece yeni biten eşleşmede tetikle
            if any(m.end() > eski for m in desen.finditer(hedef)):
                self.son_jest_ani = time.monotonic()
                return jest
        return None
