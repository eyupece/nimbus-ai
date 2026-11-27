"""Ses seçme aracı: aynı cümleyi farklı Gemini Live sesleriyle art arda okutur.

    python -m nimbus --ses-dinle                 # önerilen sesler
    python -m nimbus --ses-dinle Puck,Fenrir     # sadece bunlar
    python -m nimbus --ses-dinle hepsi           # 30 sesin tamamı
"""

import asyncio

import pyaudio
from google.genai import types

from .ayarlar import Ayarlar
from .oturum import istemci_olustur
from .ses import CIKIS_HIZI, FORMAT, KANAL

# Gemini Live / Chirp 3 HD sesleri
TUM_SESLER = [
    "Achernar", "Achird", "Algenib", "Algieba", "Alnilam", "Aoede", "Autonoe", "Callirrhoe",
    "Charon", "Despina", "Enceladus", "Erinome", "Fenrir", "Gacrux", "Iapetus", "Kore",
    "Laomedeia", "Leda", "Orus", "Puck", "Pulcherrima", "Rasalgethi", "Sadachbia",
    "Sadaltager", "Schedar", "Sulafat", "Umbriel", "Vindemiatrix", "Zephyr", "Zubenelgenubi",
]
# Genç / enerjik karaktere uyabilecekler önce
ONERILEN = ["Puck", "Fenrir", "Zephyr", "Leda", "Achird", "Sadachbia", "Laomedeia",
            "Algenib", "Umbriel", "Orus", "Enceladus", "Iapetus"]

ORNEK_CUMLE = (
    "Ya şaka mısın, ben bulutum diyorum! Hava durumunu bile benden iyi bilen yok. "
    "Neyse, adın ne senin? Tanışalım bari."
)

TALIMAT = (
    "Sen bir seslendirme sanatçısısın. Sana verilen Türkçe metni, çok bilmiş ve şımarık "
    "bir ergen karakter gibi, doğal ve canlı bir tonla AYNEN oku. Metne hiçbir şey ekleme, "
    "başka hiçbir şey söyleme."
)


async def _seslendir(istemci, model: str, ses: str, metin: str) -> bytes:
    ayar = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=TALIMAT,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=ses))
        ),
    )
    ses_verisi = bytearray()
    async with istemci.aio.live.connect(model=model, config=ayar) as live:
        await live.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=metin)]), turn_complete=True
        )
        async for yanit in live.receive():
            icerik = yanit.server_content
            if icerik and icerik.model_turn:
                for parca in icerik.model_turn.parts or []:
                    if parca.inline_data and parca.inline_data.data:
                        ses_verisi.extend(parca.inline_data.data)
            if icerik and icerik.turn_complete:
                break
    return bytes(ses_verisi)


async def _calistir(sesler: list[str], metin: str) -> None:
    a = Ayarlar.yukle()
    istemci, arka_uc = istemci_olustur(a)
    pya = pyaudio.PyAudio()
    akis = pya.open(format=FORMAT, channels=KANAL, rate=CIKIS_HIZI, output=True)
    print(f"☁️  {arka_uc} | Model: {a.model}\n🗣  \"{metin}\"\n")
    try:
        # Bir sonraki sesi, mevcut çalarken hazırla
        siradaki = asyncio.create_task(_seslendir(istemci, a.model, sesler[0], metin))
        for i, ses in enumerate(sesler):
            try:
                veri = await siradaki
            except Exception as hata:
                print(f"  [{i + 1:>2}/{len(sesler)}] {ses:<14} ⚠️  çalışmadı: {str(hata)[:80]}")
                veri = None
            if i + 1 < len(sesler):
                siradaki = asyncio.create_task(_seslendir(istemci, a.model, sesler[i + 1], metin))
            if veri:
                print(f"  [{i + 1:>2}/{len(sesler)}] ▶ {ses}", flush=True)
                await asyncio.to_thread(akis.write, veri)
                await asyncio.sleep(0.6)
    finally:
        akis.close()
        pya.terminate()
    print("\nBeğendiğin sesi söyle; .env'de değil persona dosyasındaki `ses:` satırında duruyor.")
    print("Tek ses denemek için: python -m nimbus --ses AD")


def ses_dinle(secim: str | None, metin: str | None = None) -> None:
    if not secim:
        sesler = ONERILEN
    elif secim.lower() == "hepsi":
        sesler = TUM_SESLER
    else:
        sesler = [s.strip() for s in secim.split(",") if s.strip()]
    asyncio.run(_calistir(sesler, metin or ORNEK_CUMLE))
