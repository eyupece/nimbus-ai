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
        "Sunumdaki slaytı değiştir. 'Sonraki slayt', 'devam', 'geri dön', 'başa dön' gibi isteklerde çağır; "
        "çağırdıktan sonra çok kısa bir laf at (bir cümle), slaytı anlatmaya kalkma."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={"yon": types.Schema(type=types.Type.STRING, enum=["ileri", "geri", "basa"])},
        required=["yon"],
    ),
    behavior=types.Behavior.BLOCKING,
)])

SUNUM_TALIMATI = (
    "Şu an sunum modundasın: sahnede sunum yapan kişinin yardımcısısın. Slayt değiştirmesi istenince slayt "
    "fonksiyonunu çağır. Sunucunun sözünü kesme, kısa ve esprili ol; sana bir şey sorulmadıkça uzun konuşma."
)

# Windows sanal tuş kodları
_TUSLAR = {"ileri": 0x27, "geri": 0x25, "basa": 0x24}  # sağ ok, sol ok, Home


def slayt_tusu(yon: str) -> bool:
    """Ön plandaki pencereye (PowerPoint, Google Slaytlar, PDF...) ok tuşu gönderir."""
    kod = _TUSLAR.get(yon)
    if kod is None:
        return False
    if os.name != "nt":
        print(f"⚠️  Slayt kontrolü şimdilik sadece Windows'ta çalışıyor (istenen: {yon})", file=sys.stderr)
        return False
    import ctypes

    kullanici = ctypes.windll.user32
    kullanici.keybd_event(kod, 0, 0, 0)  # bas
    kullanici.keybd_event(kod, 0, 2, 0)  # bırak (KEYEVENTF_KEYUP)
    return True
