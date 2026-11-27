"""Gövde arayüzü: Nimbus'un dış dünyadaki bedeni.

Kodun geri kalanı sadece bu arayüzü bilir. Arkasında bugün konsol,
yakında tarayıcıdaki bulut yüz, Faz 2'de ESP32 + servo olacak.

Not: `agiz` hoparlör iş parçacığından (thread) çağrılır; gerçek gövdeler bunu
kendi olay döngülerine güvenli şekilde aktarmalıdır.
"""

from typing import Protocol

# Modelin çağırabileceği jestler (fonksiyon tanımları Faz 1'in sonraki adımında)
JESTLER = ("goz_kirp", "gozleri_kis", "saskin", "dusun", "gul", "kizgin")
JEST_EMOJI = {"goz_kirp": "😉 göz kırptı", "gozleri_kis": "🤨 gözlerini kıstı", "saskin": "😮 şaşırdı",
              "dusun": "🤔 düşündü", "gul": "😄 gülümsedi", "kizgin": "😠 sitem etti"}


class Govde(Protocol):
    def agiz(self, seviye: int) -> None:
        """Ağız açıklığı: 0 (kapalı) - 3 (tam açık). ~20 ms'de bir çağrılır."""

    def jest(self, ad: str) -> None:
        """Kısa bir ifade/hareket: JESTLER listesinden."""

    def durum(self, ad: str) -> None:
        """Konuşma durumu değişti: uyku, karsilama, sohbet, veda..."""


class SessizGovde:
    """Hiçbir şey yapmayan gövde (sadece ses)."""

    def agiz(self, seviye: int) -> None:
        pass

    def jest(self, ad: str) -> None:
        pass

    def durum(self, ad: str) -> None:
        pass


class KonsolGovde(SessizGovde):
    """Jest ve durum değişikliklerini terminale yazar (hata ayıklama için)."""

    def jest(self, ad: str) -> None:
        print(f"\033[95m{JEST_EMOJI.get(ad, '🎭 ' + ad)}\033[0m", flush=True)

    def durum(self, ad: str) -> None:
        print(f"\033[95m🔄 durum: {ad}\033[0m", flush=True)
