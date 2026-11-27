# Nimbus Yol Haritası

> **Nimbus, buluttan objelere ruh üfler.**
> Tema bağımsız bir "konuşan obje" çekirdeği: dinler, düşünür, konuşur, hareket eder.
> Beyin Google Cloud'da (Gemini Live), gövde sahnede (sanal yüz → servo).

Süre planı yok; görev listesi var. Her fazın sonunda gösterilebilir bir şey (🎬) çıkar.

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

## Faz 1: Çekirdek ve sanal yüz
- [ ] Gecikmeyi 1 sn altına indirme denemeleri: kablolu/dahili mikrofon, sessizlik süresi ayarı, dolgu replikleri
- [ ] Dil algılama kaymasına çözüm: Türkçe dil ipucu (`language_code=tr-TR`) dene
- [ ] Karar anı için `gemini-3.8-live-extended-thinking` değerlendirmesi
- [ ] Persona YAML + yükleyici
- [ ] Durum makinesi + mod fonksiyonları
- [ ] Gövde fonksiyon tanımları
- [ ] Ses genliğinden ağız senkronu (4 seviye, 20 ms pencere, servoya göre hafif önden gitme)
- [ ] Sanal yüz: lokal web sunucusu + WebSocket + SVG yüz
- [ ] Operatör klavye kısayolları
- [ ] Konuşma kaydı (transcript log)
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
| [ADK bidi-streaming](https://adk.dev/streaming/dev-guide/part1) | Faz 1'de çerçeve olarak değerlendirilecek |
| ghelfyfx (Instagram) | İlham: büyülü görünen animatronik objeler |
