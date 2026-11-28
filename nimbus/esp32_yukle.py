"""ESP32'ye Nimbus yazılımını yükler (Wi-Fi bilgileri .env'den okunur).

    ./n esp32-yukle                 derle + yükle + seri ekranı aç
    ./n esp32-yukle --port COM5     belirli bir porta yükle
    ./n esp32-yukle --sadece-derle  donanım olmadan derleme kontrolü (derleyiciyi de indirir)
    ./n esp32-izle                  sadece seri ekran (ESP32 ne diyor?)

İlk çalıştırmada PlatformIO ve ESP32 derleyicisi indirilir (birkaç yüz MB, 5-10 dk).
"""

import argparse
import importlib.util
import os
import subprocess
import sys

from dotenv import load_dotenv

from .ayarlar import KOK, esp32_anahtari

PROJE = KOK / "donanim" / "esp32"
AYAR_DOSYASI = PROJE / "include" / "ayarlar.h"
# .env anahtarı -> ayarlar.h tanımı (isteğe bağlı ince ayarlar)
SAYISAL = {
    "NIMBUS_ESP32_SES": "SES_SEVIYESI",
    "NIMBUS_ESP32_AGIZ_KAPALI": "AGIZ_KAPALI",
    "NIMBUS_ESP32_AGIZ_ACIK": "AGIZ_ACIK",
    "NIMBUS_ESP32_BAS_ORTA": "BAS_ORTA",
    "NIMBUS_ESP32_MIK_KAYDIR": "MIK_KAYDIR",
    "NIMBUS_ESP32_LED": "LED_PARLAKLIK",
}


def c_metni(deger: str) -> str:
    return '"' + deger.replace("\\", "\\\\").replace('"', '\\"') + '"'


def ayar_dosyasi_yaz(wifi_ad: str, wifi_sifre: str, anahtar: str, sunucu: str) -> None:
    satirlar = [
        "// Otomatik üretildi (./n esp32-yukle). Elle düzenleme; .env'i değiştir. Git'e girmez.",
        "#pragma once",
        f"#define WIFI_AD {c_metni(wifi_ad)}",
        f"#define WIFI_SIFRE {c_metni(wifi_sifre)}",
        f"#define ANAHTAR {c_metni(anahtar)}",
        f"#define SUNUCU_IP {c_metni(sunucu)}",
    ]
    for env, tanim in SAYISAL.items():
        deger = os.getenv(env, "").strip()
        if deger.lstrip("-").isdigit():
            satirlar.append(f"#define {tanim} {int(deger)}")
    AYAR_DOSYASI.write_text("\n".join(satirlar) + "\n", encoding="utf-8")


def platformio_hazirla() -> None:
    if importlib.util.find_spec("platformio") is None:
        print("📦 PlatformIO kuruluyor (bir kerelik)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "platformio"])


def pio(*argumanlar: str) -> int:
    return subprocess.call([sys.executable, "-m", "platformio", *argumanlar])


def main() -> None:
    p = argparse.ArgumentParser(prog="n esp32-yukle", description="ESP32'ye Nimbus yazılımını yükle")
    p.add_argument("--port", help="Seri port, örn. COM5 (boş: otomatik)")
    p.add_argument("--sadece-derle", action="store_true", help="Yükleme yapma, sadece derle")
    p.add_argument("--sadece-izle", action="store_true", help="Sadece seri ekranı aç")
    p.add_argument("--izleme", action="store_true", help="Yükledikten sonra seri ekranı açma")
    a = p.parse_args()

    load_dotenv(KOK / ".env")
    platformio_hazirla()
    port = ["--port", a.port] if a.port else []

    if a.sadece_izle:
        print("👀 ESP32 seri ekranı (çıkmak için Ctrl+C)")
        sys.exit(pio("device", "monitor", "-d", str(PROJE), *port))

    wifi_ad = os.getenv("NIMBUS_WIFI_AD", "")
    wifi_sifre = os.getenv("NIMBUS_WIFI_SIFRE", "")
    if not wifi_ad and not a.sadece_derle:
        sys.exit("❌ .env dosyasına Wi-Fi bilgilerini ekle:\n"
                 "   NIMBUS_WIFI_AD=ag-adi\n   NIMBUS_WIFI_SIFRE=sifre\n"
                 "(ESP32 ve bu bilgisayar aynı ağda olmalı; telefon hotspot'u da olur. Sadece 2.4 GHz.)")
    ayar_dosyasi_yaz(wifi_ad or "derleme-testi", wifi_sifre, esp32_anahtari(), os.getenv("NIMBUS_ESP32_SUNUCU", ""))

    if a.sadece_derle:
        print("🔧 Derleniyor (ilk seferde derleyici indirilir, 5-10 dk sürebilir)...")
        kod = pio("run", "-d", str(PROJE))
        print("✅ Derleme başarılı." if kod == 0 else "❌ Derleme hatası: çıktıyı kopyalayıp gönder.")
        sys.exit(kod)

    print("⬆️  ESP32'ye yükleniyor (kartı USB ile tak; 'COM' yazan USB girişini kullan)...")
    kod = pio("run", "-d", str(PROJE), "-t", "upload", *(["--upload-port", a.port] if a.port else []))
    if kod != 0:
        sys.exit("❌ Yüklenemedi. Kartın BOOT tuşuna basılı tutup RST'ye bas, bırak ve tekrar dene.")
    print("✅ Yüklendi.")
    if not a.izleme:
        print("👀 ESP32 seri ekranı (çıkmak için Ctrl+C)")
        sys.exit(pio("device", "monitor", "-d", str(PROJE), *port))


if __name__ == "__main__":
    main()
