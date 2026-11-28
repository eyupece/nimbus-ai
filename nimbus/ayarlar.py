"""`.env` dosyasından okunan çalışma ayarları."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

KOK = Path(__file__).resolve().parent.parent


@dataclass
class Ayarlar:
    arka_uc: str  # "vertex" ya da "gemini"
    model: str
    proje: str | None
    bolge: str
    gemini_anahtar: str | None
    mikrofon: str | None
    sessizlik_ms: int
    agiz_kaydir_ms: int  # ağız senkronu ince ayarı: + geciktirir, - öne alır
    arama: bool  # Google araması (hava, haber, maç...)
    konum: str | None  # modele söylenecek konum, örn. "Konya"
    kamera: int | None  # kamera indeksi; None = kamera kapalı
    ilk_bakis: bool  # uyanınca bir kez bakıp görünüşe laf soksun mu
    persona: Path  # varsayılan persona dosyası
    esp32: bool  # ESP32 bedeniyle çalış
    esp32_anahtar: str | None  # ESP32'nin bağlanırken gösterdiği gizli anahtar
    kayit_klasoru: Path

    @classmethod
    def yukle(cls) -> "Ayarlar":
        load_dotenv(KOK / ".env")
        return cls(
            arka_uc=os.getenv("NIMBUS_BACKEND", "vertex").lower(),
            model=os.getenv("NIMBUS_MODEL", "gemini-3.8-live"),
            proje=os.getenv("GOOGLE_CLOUD_PROJECT"),
            bolge=os.getenv("GOOGLE_CLOUD_LOCATION", "eu"),
            gemini_anahtar=os.getenv("GEMINI_API_KEY"),
            mikrofon=os.getenv("NIMBUS_MIKROFON"),
            sessizlik_ms=int(os.getenv("NIMBUS_SESSIZLIK_MS", "400")),
            agiz_kaydir_ms=int(os.getenv("NIMBUS_AGIZ_KAYDIR_MS", "0")),
            arama=os.getenv("NIMBUS_ARAMA", "1") != "0",
            konum=os.getenv("NIMBUS_KONUM") or None,
            kamera=int(os.environ["NIMBUS_KAMERA"]) if os.getenv("NIMBUS_KAMERA", "").strip().isdigit() else None,
            ilk_bakis=os.getenv("NIMBUS_ILK_BAKIS", "1") != "0",
            persona=KOK / os.getenv("NIMBUS_PERSONA", "personas/nimbus.yaml"),
            esp32=os.getenv("NIMBUS_ESP32", "0") == "1",
            esp32_anahtar=os.getenv("NIMBUS_ESP32_ANAHTAR") or None,
            kayit_klasoru=KOK / "logs",
        )


def env_yaz(anahtar: str, deger: str) -> None:
    """`.env` dosyasına bir satır ekler ya da varsa günceller (değeri ekrana yazmaz)."""
    dosya = KOK / ".env"
    satirlar = dosya.read_text(encoding="utf-8").splitlines() if dosya.exists() else []
    yeni = f"{anahtar}={deger}"
    for i, satir in enumerate(satirlar):
        if satir.split("=", 1)[0].strip() == anahtar:
            satirlar[i] = yeni
            break
    else:
        satirlar.append(yeni)
    dosya.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    os.environ[anahtar] = deger


def esp32_anahtari() -> str:
    """ESP32 anahtarını döndürür; yoksa rastgele üretip `.env`'e yazar."""
    import secrets

    load_dotenv(KOK / ".env")
    anahtar = os.getenv("NIMBUS_ESP32_ANAHTAR")
    if not anahtar:
        anahtar = secrets.token_urlsafe(18)
        env_yaz("NIMBUS_ESP32_ANAHTAR", anahtar)
        print("🔑 ESP32 anahtarı oluşturuldu ve .env dosyasına yazıldı.")
    return anahtar
