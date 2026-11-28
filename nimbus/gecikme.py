"""Gecikme ölçümü: aynı cümleleri farklı ayarlarla gönderip "sen sustun -> Nimbus'un ilk sesi" süresini karşılaştırır.

    ./n gecikme                    tüm ayar seçenekleri, her cümle 2 kez (~10 dk)
    ./n gecikme --sadece mevcut,sessizlik_300 --tekrar 3

Konuşan ses kaydedilmez: cümleler bir kez modelin kendisine (Puck sesiyle) seslendirtilir ve
data/gecikme/ altında saklanır. Ses gerçek zaman hızında gönderilir, arkasından sessizlik gelir;
ölçülen süre, cümlenin son sesi gönderildiği andan modelin ilk ses parçasının geldiği ana kadardır.
Arasında duraklama olan cümleler, kısa sessizlik ayarlarında modelin "lafı ağzından alıp almadığını" gösterir.
Rapor: logs/gecikme-*.md
"""

import argparse
import asyncio
import hashlib
import json
import time
from datetime import datetime

import numpy as np
from google.genai import types

from .araclar import SAHNE_ONEKI
from .ayarlar import KOK, Ayarlar
from .govde import SessizGovde
from .persona import Persona

GIRIS_HIZI = 16000
SES_KLASORU = KOK / "data" / "gecikme"
SESLENDIREN = "Puck"

# Tek parça: düz cümle. Liste: parçalar arasında (ms) duraklamayla söylenir.
CUMLELER: list = [
    "Selam Nimbus, nasılsın?",
    "Bana bulut bilişimi kısaca anlatır mısın?",
    "En sevdiğin renk ne?",
    "Bu etkinlikte en çok neyi merak ediyorsun?",
    ["Şey", 450, "sence yapay zekâ bizim işimizi elimizden alır mı?"],
    ["Bir şey soracağım", 700, "sen hiç yağmur oldun mu?"],
]

# Ayar seçenekleri: mevcut ayarlara göre farklar
VARYANTLAR: dict[str, dict] = {
    "mevcut": {},
    "sessizlik_300": {"sessizlik_ms": 300},
    "sessizlik_200": {"sessizlik_ms": 200},
    "parca_20ms": {"parca_ms": 20},
    "dusunme_minimal": {"dusunme": "minimal"},
    "aramasiz": {"arama": False},
}


# ---------- Ses yardımcıları ----------
def yeniden_ornekle(pcm: bytes, kaynak: int, hedef: int) -> bytes:
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    if len(x) == 0 or kaynak == hedef:
        return pcm
    n = int(len(x) * hedef / kaynak)
    y = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
    return np.clip(y, -32768, 32767).astype(np.int16).tobytes()


def kirp(pcm: bytes, hiz: int = GIRIS_HIZI, esik: int = 500, pay_ms: int = 40) -> bytes:
    """Baştaki ve sondaki sessizliği at (cümle sonu = son gerçek ses)."""
    x = np.frombuffer(pcm, dtype=np.int16)
    sesli = np.nonzero(np.abs(x) > esik)[0]
    if len(sesli) == 0:
        return b""
    pay = hiz * pay_ms // 1000
    return x[max(0, sesli[0] - pay): sesli[-1] + 1].tobytes()


def sessizlik(ms: int, hiz: int = GIRIS_HIZI) -> bytes:
    """Hafif gürültülü sessizlik (tam sıfır, gerçek mikrofona benzemez)."""
    n = hiz * ms // 1000
    return np.random.default_rng(ms).integers(-30, 30, n, dtype=np.int16).tobytes()


def ozet(degerler: list[float]) -> dict:
    if not degerler:
        return {"n": 0}
    s = sorted(degerler)
    return {"n": len(s), "ortanca": s[len(s) // 2], "en_iyi": s[0], "en_kotu": s[-1]}


def cumle_metni(c) -> str:
    return c if isinstance(c, str) else " … ".join(p for p in c if isinstance(p, str))


# ---------- Cümleleri seslendir (bir kerelik, önbellekli) ----------
async def seslendir(istemci, model: str, metin: str) -> bytes:
    ayar = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=SESLENDIREN))),
        system_instruction=("Sen bir seslendirme sanatçısısın. Sana verilen Türkçe cümleyi, başına ya da sonuna "
                            "hiçbir şey eklemeden, doğal bir sohbet tonunda aynen seslendir. Cevap verme, yorum yapma."),
    )
    parcalar = []
    async with istemci.aio.live.connect(model=model, config=ayar) as live:
        await live.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=f"Seslendir: {metin}")]), turn_complete=True)
        async for m in live.receive():
            ic = m.server_content
            if ic and ic.model_turn:
                for p in ic.model_turn.parts or []:
                    if p.inline_data and p.inline_data.data:
                        parcalar.append(p.inline_data.data)
            if ic and ic.turn_complete:
                break
    return kirp(yeniden_ornekle(b"".join(parcalar), 24000, GIRIS_HIZI))


async def cumle_sesleri(istemci, model: str) -> list[bytes]:
    SES_KLASORU.mkdir(parents=True, exist_ok=True)
    sesler = []
    for c in CUMLELER:
        parcalar = [c] if isinstance(c, str) else c
        birlesik = b""
        for p in parcalar:
            if isinstance(p, int):
                birlesik += sessizlik(p)
                continue
            dosya = SES_KLASORU / f"{hashlib.sha1((SESLENDIREN + p).encode()).hexdigest()[:12]}.pcm"
            if not dosya.exists():
                print(f"🎙  Seslendiriliyor: {p}", flush=True)
                dosya.write_bytes(await seslendir(istemci, model, p))
            birlesik += dosya.read_bytes()
        sesler.append(birlesik)
    return sesler


# ---------- Ölçüm ----------
def live_ayari(oturum, varyant: dict) -> types.LiveConnectConfig:
    oturum.arama_acik = varyant.get("arama", oturum.a.arama)
    ayar = oturum.live_ayari()
    if "sessizlik_ms" in varyant:
        ayar.realtime_input_config.automatic_activity_detection.silence_duration_ms = varyant["sessizlik_ms"]
    if varyant.get("dusunme"):
        ayar.thinking_config = types.ThinkingConfig(thinking_level=varyant["dusunme"].upper())
    return ayar


async def varyant_olc(istemci, oturum, ad: str, varyant: dict, sesler: list[bytes], tekrar: int) -> dict:
    parca_ms = varyant.get("parca_ms", 64)
    parca = GIRIS_HIZI * parca_ms // 1000 * 2
    sonuc = {"ad": ad, "gecikmeler": [], "vad_ms": [], "erken": 0, "zaman_asimi": 0, "hata": None, "cumleler": []}
    olay = {"ilk_ses": None, "bitti": asyncio.Event(), "vad_son": None}

    async def al(live):
        while True:
            async for m in live.receive():
                simdi = time.monotonic()
                if m.voice_activity and m.voice_activity.voice_activity_type == types.VoiceActivityType.ACTIVITY_END:
                    olay["vad_son"] = olay["vad_son"] or simdi
                if m.tool_call:  # gerçek hafızaya dokunmadan cevapla
                    await live.send_tool_response(function_responses=[
                        types.FunctionResponse(id=c.id, name=c.name, response={"sonuc": "tamam"})
                        for c in m.tool_call.function_calls or []])
                ic = m.server_content
                if not ic:
                    continue
                if ic.model_turn and any(p.inline_data for p in ic.model_turn.parts or []):
                    olay["ilk_ses"] = olay["ilk_ses"] or simdi
                if ic.turn_complete or ic.interrupted:
                    olay["bitti"].set()

    async def gonder(live, veri: bytes) -> float:
        """Gerçek zaman hızında gönderir; son parçanın gönderildiği anı döndürür."""
        bas = time.monotonic()
        for i in range(0, len(veri), parca):
            hedef = bas + i / 2 / GIRIS_HIZI
            bekle = hedef - time.monotonic()
            if bekle > 0:
                await asyncio.sleep(bekle)
            await live.send_realtime_input(audio=types.Blob(data=veri[i:i + parca], mime_type=f"audio/pcm;rate={GIRIS_HIZI}"))
        return time.monotonic()

    sessiz_parca = sessizlik(parca_ms)

    async def sessiz_akit(live, saniye: float, dur: asyncio.Event | None = None):
        son = time.monotonic() + saniye
        while time.monotonic() < son and not (dur and dur.is_set()):
            await live.send_realtime_input(audio=types.Blob(data=sessiz_parca, mime_type=f"audio/pcm;rate={GIRIS_HIZI}"))
            await asyncio.sleep(parca_ms / 1000)

    try:
        async with istemci.aio.live.connect(model=oturum.a.model, config=live_ayari(oturum, varyant)) as live:
            alici = asyncio.create_task(al(live))
            # Isınma: karşılama (ölçülmez)
            olay["bitti"].clear()
            await live.send_client_content(turns=types.Content(role="user", parts=[
                types.Part(text=f"{SAHNE_ONEKI} {oturum.karsilama_mesaji(False)}")]), turn_complete=True)
            await asyncio.wait_for(olay["bitti"].wait(), 20)
            await sessiz_akit(live, 1.0)
            for tur in range(tekrar):
                for i, ses in enumerate(sesler):
                    olay.update(ilk_ses=None, vad_son=None)
                    olay["bitti"].clear()
                    bitis = await gonder(live, ses)
                    sessiz = asyncio.create_task(sessiz_akit(live, 15, olay["bitti"]))
                    try:
                        await asyncio.wait_for(olay["bitti"].wait(), 15)
                    except asyncio.TimeoutError:
                        sonuc["zaman_asimi"] += 1
                    sessiz.cancel()
                    ilk = olay["ilk_ses"]
                    kayit = {"cumle": cumle_metni(CUMLELER[i]), "ms": None}
                    if ilk is None:
                        pass
                    elif ilk < bitis:  # cümle bitmeden cevap verdi: lafı ağzından aldı
                        sonuc["erken"] += 1
                        kayit["erken"] = True
                        olay["bitti"].clear()  # cümlenin tamamına verilecek ikinci cevabı bekle
                        sessiz = asyncio.create_task(sessiz_akit(live, 10, olay["bitti"]))
                        try:
                            await asyncio.wait_for(olay["bitti"].wait(), 10)
                        except asyncio.TimeoutError:
                            pass
                        sessiz.cancel()
                    else:
                        kayit["ms"] = round((ilk - bitis) * 1000)
                        sonuc["gecikmeler"].append(kayit["ms"])
                    if olay["vad_son"]:
                        sonuc["vad_ms"].append(round((olay["vad_son"] - bitis) * 1000))
                    sonuc["cumleler"].append(kayit)
                    durum = f"{kayit['ms']} ms" if kayit["ms"] is not None else ("ERKEN" if kayit.get("erken") else "cevap yok")
                    print(f"   {ad:<16} {durum:>9}  {kayit['cumle'][:50]}", flush=True)
                    await sessiz_akit(live, 1.2)  # cevabın "çalınması" ve nefes payı
            alici.cancel()
    except Exception as hata:
        sonuc["hata"] = str(hata)[:200]
        print(f"   {ad}: ⚠️  {sonuc['hata']}", flush=True)
    return sonuc


def rapor_yaz(sonuclar: list[dict], tekrar: int) -> str:
    satirlar = [f"# Gecikme ölçümü — {datetime.now():%d.%m.%Y %H:%M}", "",
                f"Her cümle {tekrar} kez · süre: cümlenin son sesi → Nimbus'un ilk ses parçası (çalma gecikmesi hariç)", "",
                "| Ayar | Ortanca | En iyi | En kötü | Ölçüm | Lafı ağzından aldı | Cevapsız | Hata |",
                "|---|---|---|---|---|---|---|---|"]
    for s in sonuclar:
        o = ozet(s["gecikmeler"])
        if o["n"]:
            satirlar.append(f"| {s['ad']} | **{o['ortanca']} ms** | {o['en_iyi']} | {o['en_kotu']} | {o['n']} | "
                            f"{s['erken']} | {s['zaman_asimi']} | {s['hata'] or ''} |")
        else:
            satirlar.append(f"| {s['ad']} | – | – | – | 0 | {s['erken']} | {s['zaman_asimi']} | {s['hata'] or ''} |")
    vad = [v for s in sonuclar for v in s["vad_ms"]]
    if vad:
        satirlar += ["", f"Sunucu 'konuşma bitti' sinyali: ortanca {ozet(vad)['ortanca']} ms (cümle sonundan)"]
    satirlar += ["", "## Ayrıntı", ""]
    for s in sonuclar:
        satirlar.append(f"**{s['ad']}**: " + ", ".join(
            f"{c['ms']}" if c["ms"] is not None else ("ERKEN" if c.get("erken") else "–") for c in s["cumleler"]))
    return "\n".join(satirlar) + "\n"


async def calistir(secilen: list[str], tekrar: int) -> None:
    from .oturum import Oturum, istemci_olustur

    a = Ayarlar.yukle()
    istemci, arka_uc = istemci_olustur(a)
    oturum = Oturum(a, Persona.yukle(a.persona), SessizGovde())
    print(f"☁️  {arka_uc} | {a.model} | {len(secilen)} ayar × {len(CUMLELER)} cümle × {tekrar}", flush=True)
    sesler = await cumle_sesleri(istemci, a.model)
    sonuclar = []
    for ad in secilen:
        print(f"▶ {ad}", flush=True)
        sonuclar.append(await varyant_olc(istemci, oturum, ad, VARYANTLAR[ad], sesler, tekrar))
    metin = rapor_yaz(sonuclar, tekrar)
    a.kayit_klasoru.mkdir(exist_ok=True)
    dosya = a.kayit_klasoru / f"gecikme-{datetime.now():%Y%m%d-%H%M%S}.md"
    dosya.write_text(metin, encoding="utf-8")
    (dosya.with_suffix(".json")).write_text(json.dumps(sonuclar, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n" + metin.split("## Ayrıntı")[0])
    print(f"📋 Rapor: {dosya}")


def main() -> None:
    p = argparse.ArgumentParser(prog="n gecikme", description="Gecikme ölçümü (ayar karşılaştırması)")
    p.add_argument("--sadece", help=f"Ayarlar (virgülle): {', '.join(VARYANTLAR)}")
    p.add_argument("--tekrar", type=int, default=2, help="Her cümle kaç kez (varsayılan 2)")
    a = p.parse_args()
    secilen = [s.strip() for s in a.sadece.split(",")] if a.sadece else list(VARYANTLAR)
    bilinmeyen = [s for s in secilen if s not in VARYANTLAR]
    if bilinmeyen:
        raise SystemExit(f"❌ Bilinmeyen ayar: {', '.join(bilinmeyen)}. Seçenekler: {', '.join(VARYANTLAR)}")
    try:
        asyncio.run(calistir(secilen, a.tekrar))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
