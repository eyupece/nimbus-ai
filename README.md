# ☁️ Nimbus

**Nimbus, buluttan objelere ruh üfler.**

Bir şapkaya, kafatasına, kitaba ya da herhangi bir objeye; seni dinleyen, düşünen,
Türkçe konuşan ve hareket eden bir karakter yerleştirmek için açık kaynak bir kit.
Beyin Google Cloud'da (Gemini Live), gövde sahnede.

> 🚧 Erken aşama: Faz 0 (ses döngüsü) tamamlandı, Faz 1 sürüyor. Plan ve bulgular için [ROADMAP.md](ROADMAP.md).

## Hızlı başlangıç

Gereken: Python 3.11+ (öneri 3.12/3.13), mikrofon, kulaklık.

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash  (PowerShell: .venv\Scripts\activate, macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env            # sadece ilk kurulumda!
```

### Arka uç seçimi (`.env`)

**A) Vertex AI (önerilen, Google Cloud kredisiyle çalışır)**

```bash
gcloud auth application-default login
gcloud config set project PROJE_ID
gcloud auth application-default set-quota-project PROJE_ID
gcloud services enable aiplatform.googleapis.com
```

```
NIMBUS_BACKEND=vertex
GOOGLE_CLOUD_PROJECT=PROJE_ID
GOOGLE_CLOUD_LOCATION=eu        # ya da us-central1 (gemini-3.8-live tekil Avrupa bölgelerinde yok)
NIMBUS_MODEL=gemini-3.8-live
```

**B) Gemini API (AI Studio anahtarı)**

```
NIMBUS_BACKEND=gemini
GEMINI_API_KEY=...
```

### Çalıştır

```bash
python -m nimbus --cihazlar                      # mikrofonları listele
python -m nimbus --mikrofon-testi --mikrofon 5   # API'siz mikrofon testi
python -m nimbus --mikrofon 5                    # Nimbus ile konuş
python -m nimbus --mikrofon 5 --ses Puck         # başka ses
python -m nimbus --yarim-dubleks                 # kulaklık yoksa (yankıyı önler)
python -m nimbus --dil-ipucu                     # modele Türkçe dil ipucu ver
```

Mikrofonu her seferinde yazmamak için `.env` dosyasına `NIMBUS_MIKROFON=5` ekle.
Çıkışta (`Ctrl+C`) gecikme özeti yazılır; konuşma kaydı `logs/` klasörüne düşer (git'e girmez).

**İpuçları:** Windows'ta varsayılan giriş "Stereo Mix" olabilir (otomatik atlanır).
Bluetooth kulaklığın mikrofonu kullanılınca ses "telefon modu"na düşer; ses kalitesini
değerlendirirken dahili ya da kablolu mikrofon kullan.

## Proje yapısı

```
nimbus/
  __main__.py   komut satırı (python -m nimbus)
  ayarlar.py    .env ayarları
  persona.py    persona YAML -> sistem talimatı
  ses.py        mikrofon, hoparlör, ağız senkronu
  oturum.py     Gemini Live oturumu, yazıya döküm, kayıt
  govde.py      gövde arayüzü (konsol -> sanal yüz -> servo)
personas/       karakter dosyaları
spike/          Faz 0 deneme scripti (arşiv)
```

## Gizlilik notu
Kamera, hafıza ve (opsiyonel) yüz tanıma özellikleri kişisel veri işler.
Kullanmadan önce ilgili mevzuata (KVKK, GDPR vb.) uygun açık rıza alın.
Yüz tanıma modülü varsayılan olarak kapalıdır ve veriler cihazda kalır.

## Lisans
MIT (eklenecek)
