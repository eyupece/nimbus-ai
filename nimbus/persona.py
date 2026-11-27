"""Persona (kişilik) dosyası: karakteri koddan ayırır. Tema değişince sadece YAML değişir."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Özellik adı -> modele anlatırken kullanılacak açıklama
OZELLIK_ACIKLAMALARI = {
    "alay": "alaycılık",
    "dram": "dramatiklik",
    "sicaklik": "sıcaklık / sevecenlik",
    "merak": "karşındakine merak",
    "bilgelik": "bilgelik",
    "sabir": "sabır",
}


@dataclass
class Persona:
    ad: str
    ses: str = "Charon"
    dil: str = "tr-TR"
    hikaye: str = ""
    ozellikler: dict[str, int] = field(default_factory=dict)
    kurallar: list[str] = field(default_factory=list)
    ornekler: list[dict] = field(default_factory=list)  # [{"kisi": "...", "nimbus": "..."}]
    karsilama: str = ""
    veda: str = ""
    bilgi_dosyasi: str = ""  # proje köküne göre; içeriği talimata "bildiklerin" olarak eklenir

    @classmethod
    def yukle(cls, yol: Path) -> "Persona":
        with open(yol, encoding="utf-8") as f:
            veri = yaml.safe_load(f) or {}
        bilinen = {k: v for k, v in veri.items() if k in cls.__dataclass_fields__}
        return cls(**bilinen)

    def sistem_talimati(self) -> str:
        """Persona alanlarından modele gidecek sistem talimatını üretir."""
        # "Sen X'sin" eki isme göre değiştiği için ekten bağımsız bir kalıp kullanıyoruz
        parcalar = [f"Senin adın {self.ad}. {self.hikaye.strip()}"]

        if self.ozellikler:
            satirlar = [
                f"- {OZELLIK_ACIKLAMALARI.get(ad, ad)}: %{deger}"
                for ad, deger in self.ozellikler.items()
            ]
            parcalar.append(
                "Kişilik ayarların (0 = hiç, 100 = son derece):\n" + "\n".join(satirlar)
            )

        if self.kurallar:
            parcalar.append("Kurallar:\n" + "\n".join(f"- {k}" for k in self.kurallar))

        if self.bilgi_dosyasi:
            from .ayarlar import KOK

            yol = KOK / self.bilgi_dosyasi
            if yol.exists():
                parcalar.append(
                    "Bildiğin bilgiler (bunlara dayan; burada olmayan bir tarih, yer, isim ya da etkinlik uydurma):\n\n"
                    + yol.read_text(encoding="utf-8").strip()
                )

        if self.ornekler:
            satirlar = [f"Karşındaki: {o['kisi']}\n{self.ad}: {o['nimbus']}" for o in self.ornekler]
            parcalar.append(
                "Konuşma tarzı örnekleri. Bu cümleleri ASLA aynen tekrarlama; sadece tonu, doğallığı ve "
                "espri anlayışını yakala, her seferinde yeni ve bağlama özel cümleler kur:\n\n"
                + "\n\n".join(satirlar)
            )

        return "\n\n".join(parcalar)
