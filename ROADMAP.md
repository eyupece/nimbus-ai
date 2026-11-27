# Nimbus Yol Haritası

> **Nimbus, buluttan objelere ruh üfler.**
> Tema bağımsız bir "konuşan obje" çekirdeği: dinler, düşünür, konuşur, hareket eder.
> Beyin Google Cloud'da (Gemini Live), gövde sahnede (sanal yüz → servo).

Süre planı yok; görev listesi var. Her fazın sonunda gösterilebilir bir şey (🎬) çıkar.

## 📍 Şu an neredeyiz
- **Son güncelleme:** 27 Kasım 2026
- **Tamamlanan:** Faz 0 (ses döngüsü çalışıyor, Vertex AI + `gemini-3.8-live`, ~1.3 sn gecikme)
- **Şimdi:** Faz 1 → bulut yüz + ağız senkronu v2 + yerel jestler + persona v2.1 (canlı test bekliyor), sıradaki: 🎬 ilk demo videosu
- **Sonraki 🎬:** bulut yüzlü sanal Nimbus ile ilk demo videosu
- **Açık sorular:** ses seçimi (Bluetooth'suz dinleme testi), karar modu senaryosu (bkz. Fikir havuzu)

---

## Mimari

```
Mikrofon ──► Gemini Live (WebSocket) ──► Hoparlör
                 │            │
       persona + mod     fonksiyon çağrıları
                 │            ▼
            Durum makinesi ─► Gövde arayüzü ─► Sanal yüz (tarayıcı)
                                            └► ESP32 + servo (Faz 2)
```

- **Ağız senkronu modelden gelmez:** çıkan sesin genliğinden lokal hesaplanır (gecikmesiz).
- **Fonksiyon çağrıları jestler içindir:** başı çevir, gözleri kıs, dramatik duraklama, mod değiştir.
- **Gövde arayüzü tek arayüzdür:** arkasında önce sanal yüz, sonra servo. Kodun geri kalanı farkı bilmez.
- **Model:** `gemini-3.8-live`, Vertex AI `eu` bölgesi (B planı: Gemini metin + Chirp 3 HD / ElevenLabs TTS).

## Konuşma akışı (karışık mod)

```
UYKU ─(tetik)─► KARŞILAMA ─► SOHBET (serbest)
                               │
               (operatör tuşu ya da model "karar zamanı" der)
                               ▼
                     SORGU (3-4 soru) ─► DÜŞÜNME ("hımmm…")
                                             ▼
                               KARAR + gerekçe ─► VEDA ─► UYKU
```

> İlk demoda **SORGU → KARAR kısmı yok**: akış UYKU → KARŞILAMA → SOHBET → VEDA. Karar modu fikir havuzunda.

- **Tetik:** önce klavye tuşu, Faz 2'de başa takma/kaldırma sensörü.
- **Operatör kontrolü her zaman var:** uyandır, karar zamanı, sıfırla.
- **Persona dosyası (YAML):** ad, üslup, ses, özellik yüzdeleri, kategoriler, soru havuzu, yasaklar, karar formatı. Tema değişince sadece bu dosya değişir.

---

## Faz 0: Keşif ✅
- [x] Windows'ta Python ortamı, public repo
- [x] Minimal döngü: mikrofon → Live → hoparlör (`spike/faz0_ses_dongusu.py`)
- [ ] Türkçe sesleri karşılaştır, 2-3 aday seç (şimdilik Charon)
- [x] Gecikme ve söz kesme testi
- [x] **Karar:** Gemini Live şimdilik yeterli, B planına gerek yok

**Faz 0 bulguları (27 Kasım 2026)**
- **Arka uç:** Vertex AI, `devfest-konya-2026` projesi, `eu` çoklu bölge, model `gemini-3.8-live`.
  AI Studio anahtarı hesap düzeyindeki "prepayment credits are depleted" hatasına takıldı; Vertex, Cloud kredileriyle sorunsuz.
  `gemini-3.8-live` tekil bölgede (örn. `europe-west4`) yok; `eu` veya `us-central1` kullan.
- **Gecikme** (sen sustuktan sonra ilk ses): `us-central1` ~1.4 sn, `eu` ~1.3 sn. Bluetooth HFP modu dahil.
  Sessizlik algılama 400 ms, hassasiyet yüksek.
- **Söz kesme:** sorunsuz.
- **Karakter:** persona talimatlarına tutarlı uyuyor ("Hımm...", "evlat", kısa cevap + karşı soru).
- **Sorunlar:** ilk cümlede dil algılama bazen kayıyor (Portekizce/İspanyolca yazıya döküm);
  Bluetooth kulaklık mikrofonu yazıya dökme kalitesini düşürüyor. Windows'ta varsayılan giriş "Stereo Mix" olabiliyor (artık otomatik atlanıyor).

**Faz 1 ara ölçüm (27 Kasım 2026, `python -m nimbus`, Poly V4320 kablolu kulaklık, `eu`)**
- Gecikme ortanca **1.2 sn** (en iyi 1.0, en kötü 1.5). Bluetooth'tan kabloluya geçmek ~100-200 ms kazandırdı.
- Yazıya döküm 9/9 doğru; dil kayması görülmedi.
- "Sus" kuralı çalışıyor: "Peki... susuyorum."

**Durum makinesi testi (27 Kasım 2026)**
- Uyandırma → jest + anında kendini tanıtma ✓; "Uyusak mı?" deyince model kendisi vedalaşıp uykuya döndü ✓ (`uykuya_don`).
- Jestler BLOCKING: jestsiz cevaplar ~1.0-1.3 sn, **jestli cevaplar ~1.8-2.1 sn** (fonksiyon gidiş-dönüşü ~0.7 sn ekliyor).
  NON_BLOCKING + SILENT denendi: model jestle turu bitirip susuyordu.
- Karakter fazla felsefi ve "evlat" tekrarı çok; persona ince ayarı gerekecek.
- Not: kablolu kulaklık sadece bu test içindi, zorunlu değil. Bluetooth mikrofonlar telefon moduna düşüp kaliteyi/gecikmeyi kötüleştirebiliyor; sahne mikrofonu Faz 4'te seçilecek. Cihazı isimle seç (`NIMBUS_MIKROFON=...`), numaralar değişebiliyor.

## Faz 1: Çekirdek ve sanal yüz
- [ ] Gecikmeyi 1 sn altına indirme denemeleri: ~~kablolu mikrofon~~ (1.2 sn ✓), sessizlik süresi ayarı, dolgu replikleri
- [ ] Dil algılama kaymasına çözüm: Türkçe dil ipucu dene (`--dil-ipucu` hazır, test edilecek)
- [x] Deneme scriptini pakete böl: ses / oturum / persona / gövde (`nimbus/`)
- [x] Persona YAML v2 + yükleyici (özellik yüzdeleri, kurallar, hikâye)
- [x] Durum makinesi (UYKU → KARŞILAMA → SOHBET → VEDA), her kişi için ayrı Live bağlantısı
- [x] Fonksiyonlar: `jest(ad)` (göz kırp, gözleri kıs, şaşkın, düşün, gül, kızgın) ve `uykuya_don()`; sessiz (SILENT) yanıt
- [x] Ses genliğinden ağız senkronu → gövdeye bildiriliyor
- [x] Ağız senkronu v2: ses kartı gecikmesi kadar erteleme (ağız sesin önüne geçiyordu), 4 basamak yerine 0-1 sürekli açıklık,
      hızlı açılma / yavaş kapanma yumuşatması; ince ayar `NIMBUS_AGIZ_KAYDIR_MS` (servoda mekanik gecikme için de kullanılacak)
- [x] Jest gecikmesi: jestler artık modelden değil söylenen metinden yerelde üretiliyor (`ifade.py`), kelime duyulduğu an yüzde beliriyor
- [x] Persona v2.1: daha az felsefe, "Hımm"/"evlat" en fazla beş cevapta bir, daha çok espri (canlı test bekliyor)
- [x] Sanal yüz: **bulut karakter** (`web/index.html`), lokal HTTP + WebSocket sunucusu, ağız senkronu, 6 jest, uyku animasyonu, altyazı
- [x] Operatör komutları: Enter/u uyandır, v veda, s sıfırla, q çık
- [x] Konuşma kaydı (`logs/*.jsonl`)
- [ ] 🎬 İlk demo videosu

## Faz 1.5: Jarvis yetenekleri
- [ ] **Eylem:** sonuç ekranı, LED (WLED), slayt kontrolü
- [ ] **Hafıza:** kişi kaydı, `hatirla` / `kimdi` fonksiyonları, oturum başında özet
- [ ] **Görme:** `bak()` ile istek üzerine tek kare; bağlam sıkıştırma + oturum devamı
- [ ] **Ek özellik (opsiyonel, varsayılan kapalı):** lokal yüz tanıma (embedding'ler cihazda kalır, README'de açık rıza notu)
- [ ] 🎬 "Seni gördü ve hatırladı" videosu

## Faz 2: Donanım
- [ ] Mimari kararı: ESP32-S3 ince istemci mi, Raspberry Pi bağımsız mı?
- [ ] Alışveriş: ESP32-S3, servo, INMP441 mikrofon, MAX98357A amfi, hoparlör, güç
- [ ] Gövde arayüzünün servo arka ucu + ağız senkronu
- [ ] Başa takma / kaldırma sensörü
- [ ] Jestleri önceden animasyon olarak hazırlama (Bottango / Blender), modelin fonksiyonla tetiklemesi
- [ ] 🎬 Fiziksel demo videosu

## Faz 3: Kabuk ve tema
- [ ] Tema belli olunca persona + kabuk tasarımı
- [ ] Ağız mekanizması, 3D baskı ya da hazır obje

## Faz 4: Sahne ve yayın
- [ ] Gürültülü salon testi (yönlü mikrofon, yedek bas-konuş modu)
- [ ] Yedekler: mobil hotspot, kayıtlı demo videosu
- [x] Ücretli katman (Vertex AI kredisi) Faz 0'dan beri kullanılıyor
- [ ] README, blog, konuşma hikâyesi: *"Hareket eden obje → konuşan karakter → seni gören ve hatırlayan Jarvis"*

---

## Karar günlüğü
| Tarih | Karar | Neden |
|---|---|---|
| 27.11.2026 | Ürün tema bağımsız bir "konuşan obje" kiti olacak | DevFest teması her yıl değişiyor, teknoloji aynı kalıyor |
| 27.11.2026 | Beyin: Gemini Live (Claude yok) | Ses + model + araç çağrısı tek bağlantıda, düşük gecikme, Google kredileri, DevFest uyumu |
| 27.11.2026 | Marka adı **Nimbus**, repo `eyupece/nimbus-ai` | Bulut (Google Cloud) + hale/ruh + Nimbus 2000 göndermesi |
| 27.11.2026 | Repo baştan public, şimdilik doğrudan `main` | Görünürlük, IP riskini azaltma; çekirdek oturunca branch + PR düzeni |
| 27.11.2026 | Yüz tanıma opsiyonel ek özellik, varsayılan kapalı | Ana özellik değil; alanda KVKK izinleri hazır ama public repo başka ortamlarda kullanılacak |
| 27.11.2026 | Arka uç: Vertex AI (`devfest-konya-2026`, `eu`) | AI Studio prepay hatası; Vertex Cloud kredisiyle çalışıyor, veriler eğitimde kullanılmıyor |
| 27.11.2026 | Faz 0 sonucu: Gemini Live yeterli, B planı yok | Karakter tutarlı, söz kesme sorunsuz, gecikme ~1.3 sn (iyileştirilecek) |
| 27.11.2026 | Faz 1: düz `google-genai` SDK (ADK yok) | Faz 0 kodu çalışıyor; ses akışı ve gecikme tamamen bizim kontrolümüzde |
| 27.11.2026 | Sanal yüz: bulut karakter | Nimbus markasıyla bütünleşik; temaya göre sonra değişir |
| 27.11.2026 | İlk demoda karar modu yok | Önce sohbet + yüz; karar senaryosu sonra seçilecek |
| 27.11.2026 | Her kişi için ayrı Live bağlantısı (uyandır → bağlan, veda → kapat) | Bağlam temiz kalır, oturum süre sınırına takılmaz, uykuda maliyet yok |
| 27.11.2026 | Operatör yönlendirmesi `[Sahne yönetimi]` önekli metin mesajıyla | Model sesli cevap verir, operatörden bahsetmez; ayrı bir kanal gerekmez |
| 27.11.2026 | Jestler model fonksiyonu değil, metinden yerel kural | BLOCKING jest cevabı 0.5-2.5 sn geciktiriyordu (bir seferinde 3.9 sn); NON_BLOCKING'de model susuyordu |
| 27.11.2026 | Ağız ses kartı gecikmesi kadar ertelenir, 0-1 sürekli açıklık | Ağız sesin ~100-200 ms önünden gidiyordu, 4 basamak kaba görünüyordu |
| 27.11.2026 | Commit'leri Claude atar (Eyüp adına), push'u Eyüp yapar | Bu oturumun GitHub yazma yetkisi yok; Eyüp kod/komutla uğraşmak istemiyor |

## Fikir havuzu (ertelenenler)
- **Karar modu senaryoları** (SORGU → KARAR): Nimbus 3-4 soru sorup kişi hakkında dramatik bir karar açıklar.
  1. **GDG teknoloji evleri:** Cloud / Android / Web / AI. *"Hımm… gece yarısı kod yazan ama her şeyi ölçeklemek isteyen bir ruh… CLOUD!"* DevFest'e birebir uyar, fotoğraf anı yaratır.
  2. **Geliştirici kişilik tipleri:** Kaşif / Mimar / Sanatçı / Hacker. Teknolojiden bağımsız, eğlenceli.
  3. **Kehanet:** kategori yok, kişiye özel komik bir kehanet. En serbest, her seferinde farklı.
- **Trend radarı agent'ı:** haftalık kaynak tarama + proje adayları + Türkçe bülten (şapkadan sonraki "çılgın projeyi" bulan araç).
- **Claude'u ikinci beyin olarak eklemek:** Gemini Live konuşur, ağır kararlarda araç çağrısıyla Claude'a danışır.
- **Diğer "beklenmedik cihaza AI" fikirleri:** çevirmeli telefon, daktilo, fiş yazıcısı, konuşan saksı.

## Bilinen riskler
- **Yankı ve salon gürültüsü:** ilk testler kulaklıkla; hoparlörde `--yarim-dubleks`.
- **Salon interneti:** Live API tamamen bulutta; yedek bağlantı şart.
- **Türkçe ses kalitesi:** eski modellerde ses robotlaşması ve isim telaffuz hataları raporlanmış; Faz 0'da kulakla doğrula.
- **Proaktif ses:** `gemini-3.8-live`'da kapatılamıyor; model bazen cevap vermemeyi seçebilir, sahne akışında hesaba kat.
- **Fikri mülkiyet:** repo'da "Sorting Hat" / "Hogwarts" yok; örnek personalar özgün.

## Referanslar
| Proje | Ne alıyoruz |
|---|---|
| [GefryV3/esp32-voice-assistant](https://github.com/GefryV3/esp32-voice-assistant) (MIT) | ESP32-S3 ince istemci + Python beyin + Gemini Live mimarisi |
| [stoney66/talking-prop](https://github.com/stoney66/talking-prop) (MIT) | Ses şiddetinden 4 seviyeli çene senkronu, persona dosyası, yarım dubleks |
| [Thokoop/billy-b-assistant](https://github.com/Thokoop/billy-b-assistant) (kişisel/eğitim lisansı, sadece fikir) | Yüzdelik persona özellikleri, web arayüzü, fiziksel müdahale düğmesi |
| [amazing8bits/talking-skull](https://github.com/amazing8bits/talking-skull) | Kişiyi fark edip bakma, düşünürken göz jestleri, çenenin sesin önünden gitmesi |
| [madebyparth/nova-ai](https://github.com/madebyparth/nova-ai) (MIT) | En sade ESP32 + FastAPI + Gemini Live örneği |
| [ElatoAI](https://github.com/ImPapaGhost/ElatoAI) | B planı: ElevenLabs / çoklu sağlayıcı ESP32 |
| [ADK bidi-streaming](https://adk.dev/streaming/dev-guide/part1) | Değerlendirildi, şimdilik düz SDK tercih edildi (Karar günlüğü) |
| ghelfyfx (Instagram) | İlham: büyülü görünen animatronik objeler |
