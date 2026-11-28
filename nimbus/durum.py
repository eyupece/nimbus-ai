"""Konuşma durumları ve sahne operatörü komutları."""

import asyncio
import sys
import threading
from enum import Enum


class Durum(str, Enum):
    UYKU = "uyku"            # bağlantı yok, mikrofon dinlenmiyor
    KARSILAMA = "karsilama"  # yeni biri geldi, Nimbus kendini tanıtıyor
    SOHBET = "sohbet"        # serbest konuşma
    VEDA = "veda"            # vedalaşıyor, bitince uykuya döner


# Operatör komutları (terminale yazıp Enter)
KOMUTLAR = {
    "u": "uyandır (ya da sadece Enter)",
    "k": "sözünü kes (konuşurken)",
    "v": "vedalaş ve uykuya dön",
    "s": "sıfırla: hemen sustur ve uykuya dön",
    "q": "çık",
}


def komut_yardimi() -> str:
    return "  ".join(f"[{k}] {v}" for k, v in KOMUTLAR.items())


def operator_dinle(kuyruk: asyncio.Queue, dongu: asyncio.AbstractEventLoop) -> None:
    """Terminalden satır satır komut okur (Git Bash dahil her terminalde çalışır)."""

    def oku():
        for satir in sys.stdin:
            dongu.call_soon_threadsafe(kuyruk.put_nowait, satir.strip().lower())

    threading.Thread(target=oku, daemon=True).start()
