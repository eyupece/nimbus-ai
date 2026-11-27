"""Eylem: Nimbus'un dünyaya dokunması.

- ekranda_goster: bulut yüzün yanında bilgi kartı (hava durumu, tanım, kısa liste...)
- slayt: sunum modunda slaytı ileri/geri alır (--sunum ile açılır; açık olan pencereye tuş gönderir)
"""

import os
import sys

from google.genai import types

EKRAN = types.Tool(function_declarations=[types.FunctionDeclaration(
    name="ekranda_goster",
    description=(
        "Yanındaki ekranda kısa bir bilgi kartı göster. Önemli bir bilgiyi (hava durumu, bir tanım, kısa bir liste, "
        "bir sayı) görsel olarak da göstermek istediğinde ya da karşındaki 'ekranda göster/yaz' derse kullan. "
        "Kart kısa olsun: başlık birkaç kelime, metin en fazla 4-5 kısa satır. Kartı okumana gerek yok, "
        "konuşurken kısaca değin."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "baslik": types.Schema(type=types.Type.STRING, description="Kısa başlık"),
            "metin": types.Schema(type=types.Type.STRING, description="Kart metni; satırları \\n ile ayır"),
        },
        required=["baslik", "metin"],
    ),
    behavior=types.Behavior.BLOCKING,
)])

SLAYT = types.Tool(function_declarations=[types.FunctionDeclaration(
    name="slayt",
    description=(
        "Sunumdaki slaytı değiştir. 'Sonraki slayt', 'devam', 'geri dön', 'başa dön', '3 slayt ileri', "
        "'17. slayta git' gibi isteklerde çağır. Birden fazla adım için adet ver (tek tek çağırma); "
        "belirli bir slayta gitmek için yon='git' ve numara ver. Çağırdıktan sonra çok kısa bir laf at (bir cümle), "
        "slaytı anlatmaya kalkma."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "yon": types.Schema(type=types.Type.STRING, enum=["ileri", "geri", "basa", "git"]),
            "adet": types.Schema(type=types.Type.INTEGER, description="ileri/geri için kaç slayt (varsayılan 1)"),
            "numara": types.Schema(type=types.Type.INTEGER, description="yon='git' için hedef slayt numarası"),
        },
        required=["yon"],
    ),
    behavior=types.Behavior.BLOCKING,
)])

SUNUM_TALIMATI = (
    "Şu an sunum modundasın: sahnede sunum yapan kişinin yardımcısısın. Slayt değiştirmesi istenince slayt "
    "fonksiyonunu çağır. Sunucunun sözünü kesme, kısa ve esprili ol; sana bir şey sorulmadıkça uzun konuşma."
)

# Windows sanal tuş kodları
_TUSLAR = {"ileri": 0x27, "geri": 0x25, "basa": 0x24, "enter": 0x0D}  # sağ ok, sol ok, Home, Enter
EN_FAZLA_ADET = 30


def tus_dizisi(yon: str, adet: int = 1, numara: int | None = None) -> list[int]:
    """İstenen slayt hareketi için basılacak tuşlar. 'git': numara yazıp Enter (PowerPoint, Google Slaytlar)."""
    if yon == "git":
        if not numara or numara < 1:
            return []
        return [0x30 + int(r) for r in str(numara)] + [_TUSLAR["enter"]]  # '1','7', Enter
    kod = _TUSLAR.get(yon)
    if kod is None:
        return []
    return [kod] * (1 if yon == "basa" else max(1, min(int(adet or 1), EN_FAZLA_ADET)))


def slayt_tusu(yon: str, adet: int = 1, numara: int | None = None) -> bool:
    """Ön plandaki pencereye (PowerPoint, Google Slaytlar, PDF...) tuş gönderir."""
    tuslar = tus_dizisi(yon, adet, numara)
    if not tuslar:
        return False
    if os.name != "nt":
        print(f"⚠️  Slayt kontrolü şimdilik sadece Windows'ta çalışıyor (istenen: {yon})", file=sys.stderr)
        return False
    import ctypes
    import time

    kullanici = ctypes.windll.user32
    for kod in tuslar:
        kullanici.keybd_event(kod, 0, 0, 0)  # bas
        kullanici.keybd_event(kod, 0, 2, 0)  # bırak (KEYEVENTF_KEYUP)
        time.sleep(0.08)  # sunum programı her basışı yakalasın
    return True
