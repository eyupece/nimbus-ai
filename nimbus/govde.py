"""Gövde arayüzü: Nimbus'un dış dünyadaki bedeni.

Kodun geri kalanı sadece bu arayüzü bilir. Arkasında bugün konsol,
yakında tarayıcıdaki bulut yüz, Faz 2'de ESP32 + servo olacak.

Not: `agiz` hoparlör iş parçacığından (thread) çağrılır; gerçek gövdeler bunu
kendi olay döngülerine güvenli şekilde aktarmalıdır.
"""

from typing import Protocol

# Modelin çağırabileceği jestler (fonksiyon tanımları Faz 1'in sonraki adımında)
JESTLER = ("goz_kirp", "gozleri_kis", "saskin", "dusun", "gul", "kizgin", "kas_kaldir", "bak")
JEST_EMOJI = {"goz_kirp": "😉 göz kırptı", "gozleri_kis": "🤨 gözlerini kıstı", "saskin": "😮 şaşırdı",
              "dusun": "🤔 düşündü", "gul": "😄 gülümsedi", "kizgin": "😠 sitem etti",
              "kas_kaldir": "🤔 kaşlarını kaldırdı", "bak": "👀 kameradan baktı"}


class Govde(Protocol):
    def agiz(self, aciklik: float) -> None:
        """Ağız açıklığı: 0.0 (kapalı) - 1.0 (tam açık). ~20 ms'de bir, sesin duyulduğu anda çağrılır."""

    def jest(self, ad: str) -> None:
        """Kısa bir ifade/hareket: JESTLER listesinden."""

    def durum(self, ad: str) -> None:
        """Konuşma durumu değişti: uyku, karsilama, sohbet, veda..."""

    def altyazi(self, kim: str, metin: str, ad: str = "Nimbus") -> None:
        """Söylenen cümle: kim = "sen" ya da "nimbus"."""

    def kart(self, baslik: str, metin: str) -> None:
        """Ekranda bilgi kartı (ekranı olan gövdeler)."""


class SessizGovde:
    """Hiçbir şey yapmayan gövde (sadece ses)."""

    def agiz(self, aciklik: float) -> None:
        pass

    def jest(self, ad: str) -> None:
        pass

    def durum(self, ad: str) -> None:
        pass

    def altyazi(self, kim: str, metin: str, ad: str = "Nimbus") -> None:
        pass

    def kart(self, baslik: str, metin: str) -> None:
        pass


class KonsolGovde(SessizGovde):
    """Jest ve durum değişikliklerini terminale yazar (hata ayıklama için)."""

    def jest(self, ad: str) -> None:
        print(f"\033[95m{JEST_EMOJI.get(ad, '🎭 ' + ad)}\033[0m", flush=True)

    def durum(self, ad: str) -> None:
        print(f"\033[95m🔄 durum: {ad}\033[0m", flush=True)

    def kart(self, baslik: str, metin: str) -> None:
        print(f"\033[96m🪧 [{baslik}] {metin.replace(chr(10), ' · ')}\033[0m", flush=True)
