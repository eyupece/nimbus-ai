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
            kayit_klasoru=KOK / "logs",
        )
