"""Hafıza: Nimbus'un tanıştığı kişileri hatırlaması.

Kayıtlar sadece bu bilgisayarda, `data/hafiza.json` dosyasında durur (git'e girmez).
- Konuşma sırasında: model `kisiyi_tani(ad)` çağırır, bildiklerimiz ona döner.
- Konuşma bitince: konuşma metninden kişi hakkında kısa notlar ayrı bir metin modeliyle çıkarılır.

Komut satırı:
    python -m nimbus --hafiza            # kimleri hatırlıyor
    python -m nimbus --unut Eyüp         # bir kişiyi tamamen sil
"""

import difflib
import json
from datetime import datetime
from pathlib import Path

from google.genai import types

from .ayarlar import KOK

DOSYA = KOK / "data" / "hafiza.json"
EN_FAZLA_NOT = 8

# Sırayla denenir; projede/bölgede ilk çalışan metin modeli kullanılır
OZET_MODELLERI = ("gemini-3.5-flash", "gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash-lite")
_calisan_model: str | None = None  # ilk başarılı model hatırlanır, her seferinde baştan denenmez


def anahtar(ad: str) -> str:
    """Türkçe büyük/küçük harf duyarsız isim anahtarı: 'EYÜP' -> 'eyüp', 'İrem' -> 'irem'."""
    ad = ad.strip().replace("I", "ı").replace("İ", "i")
    return " ".join(ad.lower().split())


class Hafiza:
    def __init__(self, dosya: Path = DOSYA):
        self.dosya = dosya
        self.kisiler: dict[str, dict] = {}
        if dosya.exists():
            try:
                self.kisiler = json.loads(dosya.read_text(encoding="utf-8")).get("kisiler", {})
            except (json.JSONDecodeError, OSError):
                print(f"⚠️  Hafıza dosyası okunamadı, boş başlıyor: {dosya}")

    def kaydet(self) -> None:
        self.dosya.parent.mkdir(exist_ok=True)
        gecici = self.dosya.with_suffix(".tmp")
        gecici.write_text(json.dumps({"kisiler": self.kisiler}, ensure_ascii=False, indent=2), encoding="utf-8")
        gecici.replace(self.dosya)  # yarım yazılmış dosya kalmasın

    # ---------- Konuşma sırasında ----------
    def tani(self, ad: str) -> dict:
        """Modele dönecek bilgi: tanıyor muyuz, ne biliyoruz, benzer isimler."""
        k = anahtar(ad)
        kisi = self.kisiler.get(k)
        if kisi:
            gun = (datetime.now() - datetime.fromisoformat(kisi["son_gorulme"])).days
            return {
                "taniyor_musun": True,
                "ad": kisi["ad"],
                "kacinci_gorusme": kisi["gorusme_sayisi"] + 1,
                "son_gorusme": "bugün" if gun == 0 else ("dün" if gun == 1 else f"{gun} gün önce"),
                "bildiklerin": kisi.get("notlar", []),
                "ipucu": "Onu tanıdığını doğal ve esprili şekilde belli et; bildiklerinden birine kısaca değin.",
            }
        benzer = difflib.get_close_matches(k, self.kisiler.keys(), n=2, cutoff=0.6)
        sonuc = {
            "taniyor_musun": False, "ad": ad.strip(),
            "ipucu": ("Yeni tanışıyorsunuz. Konuşma tanıma isimleri sık yanlış duyar: adını cevabında doğal şekilde bir kez "
                      f"teyit et (örneğin '{ad.strip()} mi dedin?'). Farklı bir ad söylerse kisiyi_tani'yi doğru adla tekrar çağır."),
        }
        if benzer:
            adlar = [self.kisiler[b]["ad"] for b in benzer]
            sonuc["benzer_isimler"] = adlar
            sonuc["ipucu"] = (f"İsim yanlış duyulmuş olabilir; tanıdığın biri olabilir: {', '.join(adlar)}. "
                              f"Kısaca sor (örneğin 'Sen {adlar[0]} değil misin?'); evet derse kisiyi_tani'yi o adla tekrar çağır.")
        return sonuc

    # ---------- Konuşma bitince ----------
    def gorusmeyi_kaydet(self, ad: str, yeni_notlar: list[str]) -> None:
        k = anahtar(ad)
        simdi = datetime.now().isoformat(timespec="seconds")
        kisi = self.kisiler.setdefault(k, {"ad": ad.strip(), "ilk_gorulme": simdi, "gorusme_sayisi": 0, "notlar": []})
        kisi["son_gorulme"] = simdi
        kisi["gorusme_sayisi"] += 1
        kisi["notlar"] = [n.strip() for n in yeni_notlar if n and n.strip()][:EN_FAZLA_NOT]
        self.kaydet()

    def unut(self, ad: str) -> bool:
        if self.kisiler.pop(anahtar(ad), None) is not None:
            self.kaydet()
            return True
        return False


async def notlari_cikar(istemci, ad: str, eski_notlar: list[str], konusma: list[tuple[str, str]]) -> list[str]:
    """Konuşma metninden kişi hakkında kısa notlar çıkarır (eski notlarla birleştirerek)."""
    metin = "\n".join(f"{'Kişi' if kim == 'sen' else 'Nimbus'}: {s}" for kim, s in konusma)
    istem = (
        f"Aşağıda Nimbus adlı konuşan bir bulut karakteri ile {ad} adlı kişi arasındaki konuşma var.\n"
        f"{ad} hakkında daha önce bilinenler: {json.dumps(eski_notlar, ensure_ascii=False)}\n\n"
        f"KONUŞMA:\n{metin}\n\n"
        f"{ad} hakkında hatırlanmaya değer bilgileri (memleketi, işi, ilgi alanları, sevdikleri, ilginç/komik anlar, "
        f"Nimbus'la arasındaki şakalar) eski bilgilerle birleştirip en fazla {EN_FAZLA_NOT} kısa Türkçe not olarak ver. "
        "Her not tek kısa cümle olsun. Sadece konuşmada geçenleri yaz, uydurma. Hassas kişisel veri (sağlık, din, "
        "siyaset, adres, telefon) yazma. Sadece JSON dizi döndür: [\"not 1\", \"not 2\"]"
    )
    global _calisan_model
    ayar = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2)
    son_hata = None
    for model in ([_calisan_model] if _calisan_model else []) + [m for m in OZET_MODELLERI if m != _calisan_model]:
        try:
            yanit = await istemci.aio.models.generate_content(model=model, contents=istem, config=ayar)
            notlar = json.loads(yanit.text)
            if isinstance(notlar, list):
                _calisan_model = model
                return [str(n) for n in notlar]
        except Exception as hata:  # model bu bölgede yoksa sıradakini dene
            son_hata = hata
    raise RuntimeError(f"Not çıkarılamadı: {son_hata}")


def hafizayi_listele() -> None:
    h = Hafiza()
    if not h.kisiler:
        print("Nimbus henüz kimseyi hatırlamıyor.")
        return
    print(f"Nimbus'un hatırladıkları ({h.dosya}):\n")
    for kisi in h.kisiler.values():
        print(f"• {kisi['ad']}  ({kisi['gorusme_sayisi']} görüşme, son: {kisi['son_gorulme'][:16].replace('T', ' ')})")
        for n in kisi.get("notlar", []):
            print(f"    - {n}")


def kisiyi_unut(ad: str) -> None:
    print(f"🧹 {ad} unutuldu." if Hafiza().unut(ad) else f"'{ad}' adında biri hafızada yok.")
