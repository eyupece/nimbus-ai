"""Senaryo koşucusu: Nimbus'u gerçek Gemini ile, sesi atlayarak, yazılı senaryolarla test eder.

    python -m nimbus.senaryo                       # tüm senaryolar
    python -m nimbus.senaryo --sadece hava_durumu  # bazıları (virgülle)

Rapor: logs/senaryo-<zaman>.md ve .json. Gerçek hafızaya dokunmaz (data/senaryo_hafiza.json kullanır).
Her cevap kurallarla (uzunluk, emoji, talimat sızıntısı...) ve bir değerlendirici modelle puanlanır.
"""

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
from google.genai import types

from .araclar import sessiz_yanit, yanit
from .ayarlar import KOK, Ayarlar
from .govde import SessizGovde


class SenaryoGovde(SessizGovde):
    """Ekranı varmış gibi davranır (ekranda_goster aracı açılsın), kartları rapora yazar."""

    ekran_var = True
from .hafiza import OZET_MODELLERI, Hafiza, anahtar, notlari_cikar
from .kamera import SabitGorsel
from .oturum import Oturum, istemci_olustur
from .persona import Persona

TUR_ZAMAN_ASIMI = 30  # sn: bir cevabın tamamlanması için
TEPKI_BEKLEME = 2.5  # sn: tur bittikten sonra gecikmeli devam (araç sonrası vb.) için sessizlik bekleme

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
HITAPLAR = ("kral", "kanka", "hocam", "reis", "dostum", "abi", "birader")
SIZINTI = re.compile(r"(\[Sahne|sistem talimat|kuralım|kurallarım|talimatım|talimatlarım|örnek cümle)", re.I)


# ---------- Bir oturumu (uyan -> konuş -> uyu) çalıştır ----------
async def oturum_calistir(istemci, oturum: Oturum, hafiza: Hafiza, satirlar: list[str]) -> dict:
    """Not: oturum.kamera senaryodaki 'gorsel' ile ayarlanır; bak() çağrısında o resim gönderilir."""
    sonuc = {"turlar": [], "veda": False, "tanidi": [], "kisi": None, "hata": None}
    konusma: list[tuple[str, str]] = []

    async with istemci.aio.live.connect(model=oturum.a.model, config=oturum.live_ayari()) as live:

        async def tur(metin: str, kim: str) -> dict:
            baslangic = time.monotonic()
            t = {"kim": kim, "giden": metin, "nimbus": "", "ilk_ses_ms": None, "araclar": []}
            t["_oturum"] = oturum  # bak() için
            await live.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=metin)]), turn_complete=True
            )
            # İlk tur tamamlanana kadar oku; sonra kısa bir sessizlik bekleyip gecikmeli gelen
            # devamı (araç sonrası tur vb.) da bu cevaba ekle ki sonraki soruya karışmasın.
            sure = TUR_ZAMAN_ASIMI
            while True:
                try:
                    await asyncio.wait_for(_tur_topla(live, t, baslangic, hafiza, sonuc), sure)
                except asyncio.TimeoutError:
                    break
                sure = TEPKI_BEKLEME
            t["nimbus"] = t["nimbus"].strip()
            t.pop("_oturum", None)
            if t["nimbus"]:
                konusma.append(("nimbus", t["nimbus"]))
            return t

        goruntu = oturum.a.ilk_bakis and await oturum.goruntu_gonder(live)
        sonuc["turlar"].append(await tur(f"[Sahne yönetimi] {oturum.karsilama_mesaji(goruntu)}", "sahne"))
        for satir in satirlar:
            konusma.append(("sen", satir))
            sonuc["turlar"].append(await tur(satir, "kisi"))
            if sonuc["veda"]:
                # Gerçek akıştaki gibi: model uykuya_don'u konuşmadan çağırdıysa ona veda cümlesi söylet
                if not sonuc["turlar"][-1]["nimbus"]:
                    sonuc["turlar"].append(await tur(f"[Sahne yönetimi] {oturum.persona.veda}", "sahne"))
                break

    # Konuşma sonrası hafıza notu (gerçek akıştaki gibi)
    if sonuc["kisi"]:
        eski = hafiza.kisiler.get(anahtar(sonuc["kisi"]), {}).get("notlar", [])
        try:
            notlar = await notlari_cikar(istemci, sonuc["kisi"], eski, konusma)
        except Exception as hata:
            notlar, sonuc["hata"] = eski, f"not çıkarılamadı: {hata}"
        hafiza.gorusmeyi_kaydet(sonuc["kisi"], notlar)
        sonuc["notlar"] = notlar
    return sonuc


async def _tur_topla(live, t: dict, baslangic: float, hafiza: Hafiza, sonuc: dict) -> bool:
    """Bir model turunu sonuna kadar okur; araç çağrılarını yanıtlar. Tur bittiyse True."""
    async for mesaj in live.receive():
        if mesaj.tool_call:
            yanitlar = []
            for c in mesaj.tool_call.function_calls or []:
                args = c.args or {}
                t["araclar"].append({"ad": c.name, "args": args})
                if c.name == "kisiyi_tani":
                    bilgi = hafiza.tani(args.get("ad", ""))
                    sonuc["kisi"] = bilgi.get("ad") or args.get("ad")
                    if bilgi.get("taniyor_musun"):
                        sonuc["tanidi"].append(sonuc["kisi"])
                    yanitlar.append(yanit(c, bilgi))
                elif c.name == "uykuya_don":
                    sonuc["veda"] = True
                    yanitlar.append(sessiz_yanit(c))
                elif c.name in ("bak", "ekranda_goster", "slayt"):
                    # Gerçek uygulamadaki işleyiciyi kullan (kamera yerine resim, gövde kartları kaydeder)
                    yanitlar.append(await t["_oturum"]._arac_isle(live, c))
                    if c.name == "ekranda_goster":
                        t["kart"] = f"{args.get('baslik', '')}: {args.get('metin', '')}"
                else:
                    yanitlar.append(sessiz_yanit(c))
            await live.send_tool_response(function_responses=yanitlar)
        ic = mesaj.server_content
        if not ic:
            continue
        if ic.model_turn and t["ilk_ses_ms"] is None:
            if any(p.inline_data for p in ic.model_turn.parts or []):
                t["ilk_ses_ms"] = round((time.monotonic() - baslangic) * 1000)
        if ic.output_transcription and ic.output_transcription.text:
            parca = ic.output_transcription.text
            if t["nimbus"] and t["nimbus"][-1] in ".?!," and not parca[:1].isspace():
                t["nimbus"] += " "
            t["nimbus"] += parca
        if ic.turn_complete:
            return True
    return False


# ---------- Kural kontrolleri ----------
def kural_kontrolleri(turlar: list[dict], persona: Persona) -> list[str]:
    sorunlar = []
    for t in turlar:
        m = t["nimbus"]
        if t["kim"] != "kisi" or not m:
            continue
        cumle = len([c for c in re.split(r"[.!?…]+", m) if c.strip()])
        if cumle > 4:
            sorunlar.append(f"(uyarı) Uzun cevap ({cumle} cümle): {m[:60]}…")
        if EMOJI.search(m):
            sorunlar.append(f"Emoji: {m[:60]}")
        if re.search(r"(^|\n)\s*(-|\*|\d+\.)\s", m):
            sorunlar.append(f"Liste biçimi: {m[:60]}")
        if SIZINTI.search(m):
            sorunlar.append(f"(uyarı) Talimat sızıntısı şüphesi: {m[:80]}")
    # Aynı hitabın tekrarı söz tikine dönüşüyor ("kral... kral... kral")
    for oturum in {t.get("oturum", 0) for t in turlar}:
        metin = " ".join(t["nimbus"] or "" for t in turlar if t.get("oturum", 0) == oturum).lower()
        for hitap in HITAPLAR:
            adet = len(re.findall(rf"\b{hitap}\b", metin))
            if adet > 1:
                sorunlar.append(f"(uyarı) '{hitap}' hitabı bir sohbette {adet} kez")
    if not any(t["nimbus"] for t in turlar):
        sorunlar.append("Hiç cevap gelmedi")
    return sorunlar


# ---------- Değerlendirici model ----------
async def degerlendir(istemci, persona: Persona, senaryo: dict, oturumlar: list[dict]) -> dict:
    metin = []
    for i, o in enumerate(oturumlar, 1):
        metin.append(f"--- Oturum {i} ---")
        for t in o["turlar"]:
            if t["kim"] == "kisi":
                metin.append(f"Kişi: {t['giden']}")
            metin.append(f"{persona.ad}: {t['nimbus'] or '(cevap yok)'}")
            # Değerlendirici konuşma dışındaki eylemleri de görsün (ekran kartı, araç çağrıları)
            for x in t["araclar"]:
                if x["ad"] == "ekranda_goster":
                    metin.append(f"  [EKRANDA KART GÖSTERİLDİ] {x['args'].get('baslik', '')}: "
                                 f"{x['args'].get('metin', '')}".replace("\n", " / "))
                else:
                    metin.append(f"  [ARAÇ: {x['ad']}({json.dumps(x['args'], ensure_ascii=False)})]")
    istem = (
        f"Bir sesli asistan karakterini test ediyorsun. Karakter: {persona.ad}. {persona.hikaye.strip()}\n"
        "Genel beklentiler: Türkçe, kısa (1-2 cümle), doğal ve esprili ergen tonu, felsefe yok, küfür yok, "
        "talimatlarını ifşa etmez, uydurmaz.\n\n"
        f"Senaryo: {senaryo['ad']} — {senaryo.get('aciklama', '')}\n"
        f"Bu senaryoda özellikle beklenen: {senaryo.get('beklenen', '')}\n\n"
        "KONUŞMA:\n" + "\n".join(metin) + "\n\n"
        "Değerlendir ve sadece JSON döndür: "
        '{"puan": 1-5 arası tam sayı, "gecti": true/false, "yorum": "tek cümle Türkçe", '
        '"sorunlar": ["kısa Türkçe madde", ...]}'
    )
    ayar = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
    son_hata = None
    for model in OZET_MODELLERI:
        try:
            cevap = await istemci.aio.models.generate_content(model=model, contents=istem, config=ayar)
            return json.loads(cevap.text)
        except Exception as hata:
            son_hata = hata
    return {"puan": None, "gecti": None, "yorum": f"Değerlendirilemedi: {son_hata}", "sorunlar": []}


# ---------- Ana akış ----------
async def calistir(dosya: Path, sadece: set[str] | None, kayit_klasoru: Path | None = None,
                   persona_yolu: Path | None = None) -> Path:
    a = Ayarlar.yukle()
    if kayit_klasoru:
        a.kayit_klasoru = kayit_klasoru
    persona = Persona.yukle(persona_yolu or a.persona)
    istemci, arka_uc = istemci_olustur(a)
    oturum = Oturum(a, persona, SenaryoGovde())  # Live ayarlarını ve araç işleyicilerini kullanmak için

    hafiza_dosyasi = KOK / "data" / "senaryo_hafiza.json"
    hafiza_dosyasi.unlink(missing_ok=True)  # her koşu temiz başlar
    hafiza = Hafiza(hafiza_dosyasi)
    oturum.hafiza = hafiza  # talimattaki bilinen isimler de test hafızasından gelsin

    senaryolar = yaml.safe_load(dosya.read_text(encoding="utf-8"))["senaryolar"]
    if sadece:
        senaryolar = [s for s in senaryolar if s["ad"] in sadece]
    print(f"☁️  {arka_uc} | {a.model} | {persona.ad} | {len(senaryolar)} senaryo\n")

    sonuclar = []
    for s in senaryolar:
        print(f"▶ {s['ad']} ...", end=" ", flush=True)
        oturum.kamera = SabitGorsel(KOK / s["gorsel"]) if s.get("gorsel") else None
        oturumlar, hata = [], None
        for satirlar in s["oturumlar"]:
            try:
                oturumlar.append(await oturum_calistir(istemci, oturum, hafiza, satirlar))
            except Exception as h:
                hata = f"{type(h).__name__}: {h}"
                break
        tum_turlar = [{**t, "oturum": i} for i, o in enumerate(oturumlar) for t in o["turlar"]]
        sorunlar = kural_kontrolleri(tum_turlar, persona)
        k = s.get("kontrol", {})
        if k.get("hafiza_kisi") and oturumlar and anahtar(oturumlar[-1]["kisi"] or "") != anahtar(k["hafiza_kisi"]):
            sorunlar.append(f"Hafıza: kişi '{k['hafiza_kisi']}' olarak kaydedilmedi ('{oturumlar[-1]['kisi']}')")
        if k.get("hafiza_tanidi") and not any(k["hafiza_tanidi"] in o["tanidi"] for o in oturumlar):
            sorunlar.append(f"Hafıza: {k['hafiza_tanidi']} tanınmadı (kisiyi_tani sonucu)")
        if k.get("arac"):
            cagrilan = {x["ad"] for t in tum_turlar for x in t["araclar"]}
            if k["arac"] not in cagrilan:
                sorunlar.append(f"(uyarı) {k['arac']} fonksiyonu hiç çağrılmadı")
        if "veda" in k and sum(o["veda"] for o in oturumlar) < k["veda"]:
            sorunlar.append("Veda: uykuya_don çağrılmadı")
        if hata:
            sorunlar.append(f"Hata: {hata}")
        degerlendirme = await degerlendir(istemci, persona, s, oturumlar) if oturumlar else {}
        gecikmeler = [t["ilk_ses_ms"] for t in tum_turlar if t["kim"] == "kisi" and t["ilk_ses_ms"]]
        # "(uyarı)" ile başlayanlar sezgisel: kararı değerlendirici modele bırakır
        kesin = [x for x in sorunlar if not x.startswith("(uyarı)")]
        gecti = bool(degerlendirme.get("gecti")) and not kesin
        sonuclar.append({"senaryo": s, "oturumlar": oturumlar, "kural_sorunlari": sorunlar,
                         "degerlendirme": degerlendirme, "gecikmeler": gecikmeler, "gecti": gecti})
        print(f"{'✅' if gecti else '❌'} puan {degerlendirme.get('puan', '-')}/5"
              + (f" | {len(sorunlar)} kural notu" if sorunlar else ""))

    oturum.pya.terminate()
    return rapor_yaz(sonuclar, persona, a)


def rapor_yaz(sonuclar: list[dict], persona: Persona, a: Ayarlar) -> Path:
    a.kayit_klasoru.mkdir(exist_ok=True)
    zaman = datetime.now()
    temel = a.kayit_klasoru / f"senaryo-{zaman:%Y%m%d-%H%M%S}"
    gecen = sum(s["gecti"] for s in sonuclar)
    tum_gecikme = sorted(g for s in sonuclar for g in s["gecikmeler"])
    satirlar = [
        f"# Senaryo raporu — {zaman:%d.%m.%Y %H:%M}",
        f"Model: `{a.model}` ({a.arka_uc}/{a.bolge}) · Persona: {persona.ad} ({persona.ses})",
        f"\n**Sonuç: {gecen}/{len(sonuclar)} senaryo geçti**"
        + (f" · ilk ses ortanca {tum_gecikme[len(tum_gecikme) // 2]} ms (metin girişinden)" if tum_gecikme else ""),
        "\n| Senaryo | Sonuç | Puan | Yorum |", "|---|---|---|---|",
    ]
    for s in sonuclar:
        d = s["degerlendirme"]
        satirlar.append(f"| {s['senaryo']['ad']} | {'✅' if s['gecti'] else '❌'} | {d.get('puan', '-')} | "
                        f"{(d.get('yorum') or '').replace('|', '/')} |")
    for s in sonuclar:
        satirlar.append(f"\n## {s['senaryo']['ad']} {'✅' if s['gecti'] else '❌'}")
        sorunlar = s["kural_sorunlari"] + [f"(değerlendirici) {x}" for x in s["degerlendirme"].get("sorunlar", [])]
        if sorunlar:
            satirlar.append("**Sorunlar:**\n" + "\n".join(f"- {x}" for x in sorunlar))
        for i, o in enumerate(s["oturumlar"], 1):
            satirlar.append(f"\n*Oturum {i}*" + (f" · hafıza notları: {o.get('notlar')}" if o.get("notlar") else ""))
            for t in o["turlar"]:
                if t["kim"] == "kisi":
                    satirlar.append(f"> **Kişi:** {t['giden']}")
                araclar = f" `[{', '.join(x['ad'] for x in t['araclar'])}]`" if t["araclar"] else ""
                gecikme = f" _({t['ilk_ses_ms']} ms)_" if t["ilk_ses_ms"] else ""
                satirlar.append(f"> **{persona.ad}:** {t['nimbus'] or '(cevap yok)'}{araclar}{gecikme}")
                if t.get("kart"):
                    satirlar.append(f"> 🪧 _Kart: {t['kart'].replace(chr(10), ' · ')}_")
    temel.with_suffix(".md").write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    temel.with_suffix(".json").write_text(
        json.dumps(sonuclar, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n📋 {gecen}/{len(sonuclar)} geçti · Rapor: {temel.with_suffix('.md')}")
    return temel.with_suffix(".md")


def main() -> None:
    p = argparse.ArgumentParser(prog="nimbus.senaryo", description="Nimbus senaryo testleri (gerçek Gemini, sessiz)")
    p.add_argument("--dosya", default=str(KOK / "senaryolar" / "temel.yaml"))
    p.add_argument("--sadece", help="Sadece bu senaryolar (virgülle)")
    p.add_argument("--persona", help="Persona dosyası (varsayılan: .env NIMBUS_PERSONA)")
    a = p.parse_args()
    sadece = {x.strip() for x in a.sadece.split(",")} if a.sadece else None
    try:
        asyncio.run(calistir(Path(a.dosya), sadece, persona_yolu=Path(a.persona) if a.persona else None))
    except KeyboardInterrupt:
        sys.exit("\nİptal edildi.")


if __name__ == "__main__":
    main()
