"""Komut satırı: python -m nimbus [seçenekler]"""

import argparse
import asyncio
from pathlib import Path

from .ayarlar import KOK, Ayarlar
from .govde import KonsolGovde, SessizGovde
from .oturum import Oturum
from .persona import Persona
from .ses import cihazlari_listele, mikrofon_testi
from .web import WebGovde

ORNEK_SESLER = ["Charon", "Puck", "Kore", "Fenrir", "Aoede", "Leda", "Orus", "Zephyr"]


def main() -> None:
    p = argparse.ArgumentParser(prog="nimbus", description="Nimbus: buluttan objelere ruh üfler")
    p.add_argument("--persona", default=str(KOK / "personas" / "nimbus.yaml"), help="Persona YAML dosyası")
    p.add_argument("--ses", help=f"Persona'daki sesi geçersiz kıl. Örnekler: {', '.join(ORNEK_SESLER)}")
    p.add_argument("--mikrofon", help="Mikrofon numarası ya da isim parçası (.env: NIMBUS_MIKROFON)")
    p.add_argument("--yarim-dubleks", action="store_true", help="Nimbus konuşurken mikrofonu sustur")
    p.add_argument("--dil-ipucu", action="store_true", help="Modele persona dilini (tr-TR) açıkça bildir")
    p.add_argument("--govde", choices=["web", "konsol", "sessiz"], default="web",
                   help="web: tarayıcıda bulut yüz (varsayılan), konsol: sadece terminal")
    p.add_argument("--port", type=int, default=8765, help="Bulut yüz sunucusunun portu")
    p.add_argument("--tarayici-acma", action="store_true", help="Tarayıcıyı otomatik açma")
    p.add_argument("--cihazlar", action="store_true", help="Giriş cihazlarını listele ve çık")
    p.add_argument("--mikrofon-testi", action="store_true", help="API'siz mikrofon seviyesi testi")
    p.add_argument("--ses-dinle", nargs="?", const="", metavar="SESLER",
                   help="Sesleri art arda dinle: boş = önerilenler, 'hepsi' ya da 'Puck,Fenrir'")
    p.add_argument("--cumle", help="--ses-dinle ile okunacak cümle")
    p.add_argument("--kamera", nargs="?", const=0, type=int, metavar="INDEKS",
                   help="Kamerayla çalıştır (görme). Varsayılan kamera 0. .env: NIMBUS_KAMERA")
    p.add_argument("--sunum", action="store_true",
                   help="Sunum modu: 'sonraki slayt' gibi komutlarla ön plandaki pencereye ok tuşu gönderir")
    p.add_argument("--kamera-testi", nargs="?", const=0, type=int, metavar="INDEKS", help="Kamera çalışıyor mu")
    p.add_argument("--hafiza", action="store_true", help="Nimbus'un hatırladığı kişileri listele")
    p.add_argument("--unut", metavar="AD", help="Bir kişiyi hafızadan tamamen sil")
    a = p.parse_args()

    ayarlar = Ayarlar.yukle()
    if a.mikrofon:
        ayarlar.mikrofon = a.mikrofon

    if a.cihazlar:
        return cihazlari_listele()
    if a.mikrofon_testi:
        return mikrofon_testi(ayarlar.mikrofon)
    if a.kamera_testi is not None:
        from .kamera import kamera_testi
        return kamera_testi(a.kamera_testi)
    if a.hafiza or a.unut:
        from .hafiza import hafizayi_listele, kisiyi_unut
        return kisiyi_unut(a.unut) if a.unut else hafizayi_listele()
    if a.ses_dinle is not None:
        from .ses_dinle import ses_dinle
        return ses_dinle(a.ses_dinle, a.cumle)

    persona = Persona.yukle(Path(a.persona))
    if a.ses:
        persona.ses = a.ses

    if a.govde == "web":
        govde = WebGovde(port=a.port, tarayici_ac=not a.tarayici_acma, konsol=KonsolGovde())
    elif a.govde == "konsol":
        govde = KonsolGovde()
    else:
        govde = SessizGovde()
    kamera_indeksi = a.kamera if a.kamera is not None else ayarlar.kamera
    kamera = None
    if kamera_indeksi is not None:
        from .kamera import Kamera
        kamera = Kamera(kamera_indeksi)
    oturum = Oturum(ayarlar, persona, govde, yarim_dubleks=a.yarim_dubleks, dil_ipucu=a.dil_ipucu, kamera=kamera,
                    sunum=a.sunum)
    if a.sunum:
        print("🖥  Sunum modu: slayt komutları ön plandaki pencereye ok tuşu gönderir (sunumu öne al).")
    try:
        asyncio.run(oturum.calistir())
    except KeyboardInterrupt:
        pass
    finally:
        oturum.ozet_yaz()
        print("\n👋 Görüşürüz.")
        try:
            oturum.kapat()
        except KeyboardInterrupt:
            pass  # kapanırken tekrar Ctrl+C'ye basıldı; iş parçacıkları zaten arka planda (daemon)


if __name__ == "__main__":
    main()
