"""Komut satırı: python -m nimbus [seçenekler]"""

import argparse
import asyncio
from pathlib import Path

from .ayarlar import KOK, Ayarlar
from .govde import KonsolGovde, SessizGovde
from .oturum import Oturum
from .persona import Persona
from .ses import cihazlari_listele, mikrofon_testi

ORNEK_SESLER = ["Charon", "Puck", "Kore", "Fenrir", "Aoede", "Leda", "Orus", "Zephyr"]


def main() -> None:
    p = argparse.ArgumentParser(prog="nimbus", description="Nimbus: buluttan objelere ruh üfler")
    p.add_argument("--persona", default=str(KOK / "personas" / "nimbus.yaml"), help="Persona YAML dosyası")
    p.add_argument("--ses", help=f"Persona'daki sesi geçersiz kıl. Örnekler: {', '.join(ORNEK_SESLER)}")
    p.add_argument("--mikrofon", help="Mikrofon numarası ya da isim parçası (.env: NIMBUS_MIKROFON)")
    p.add_argument("--yarim-dubleks", action="store_true", help="Nimbus konuşurken mikrofonu sustur")
    p.add_argument("--dil-ipucu", action="store_true", help="Modele persona dilini (tr-TR) açıkça bildir")
    p.add_argument("--govde", choices=["konsol", "sessiz"], default="konsol", help="Gövde arka ucu")
    p.add_argument("--cihazlar", action="store_true", help="Giriş cihazlarını listele ve çık")
    p.add_argument("--mikrofon-testi", action="store_true", help="API'siz mikrofon seviyesi testi")
    a = p.parse_args()

    ayarlar = Ayarlar.yukle()
    if a.mikrofon:
        ayarlar.mikrofon = a.mikrofon

    if a.cihazlar:
        return cihazlari_listele()
    if a.mikrofon_testi:
        return mikrofon_testi(ayarlar.mikrofon)

    persona = Persona.yukle(Path(a.persona))
    if a.ses:
        persona.ses = a.ses

    govde = KonsolGovde() if a.govde == "konsol" else SessizGovde()
    oturum = Oturum(ayarlar, persona, govde, yarim_dubleks=a.yarim_dubleks, dil_ipucu=a.dil_ipucu)
    try:
        asyncio.run(oturum.calistir())
    except KeyboardInterrupt:
        oturum.ozet_yaz()
        print("\n👋 Görüşürüz.")
    finally:
        oturum.kapat()


if __name__ == "__main__":
    main()
