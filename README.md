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

**Kısayol:** sanal ortamı etkinleştirmeden `./n` kullanabilirsin: `./n` (= `python -m nimbus`),
`./n --kamera`, `./n senaryo --sadece hava_durumu`, `./n test`.

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

Çalıştırınca tarayıcıda **bulut yüz** açılır (http://localhost:8765): ağız sesle senkron hareket eder,
jestler yüzde canlanır, konuşmalar altyazı olarak görünür. Sadece terminal için `--govde konsol`,
tarayıcının otomatik açılmaması için `--tarayici-acma`. Sunucusuz önizleme: `web/index.html?demo`.

Nimbus **uykuda** başlar. Terminalde operatör komutları (yazıp Enter):

| Komut | Ne yapar |
|---|---|
| `Enter` ya da `u` | Uyandır: Nimbus kendini tanıtır, konuşma başlar |
| `v` | Vedalaş ve uykuya dön |
| `s` | Sıfırla: hemen sustur, uykuya dön |
| `q` | Çık |

Karşındaki "görüşürüz" derse Nimbus kendisi de vedalaşıp uykuya döner.

### Sunum modu ve bilgi kartları

```bash
python -m nimbus --sunum     # "Nimbus, sonraki slayt" → ön plandaki pencereye sağ ok tuşu
```

Sunumu (PowerPoint, Google Slaytlar, PDF) öne al; Nimbus "sonraki slayt", "geri dön", "başa dön"
komutlarında ok tuşu gönderir ve araya kısa laf atar. Bulut yüzün sağ üstünde, Nimbus gerektiğinde
ya da "ekranda göster" denince **bilgi kartı** açar (hava durumu, kısa liste...).

### Görme (kamera)

```bash
python -m nimbus --kamera-testi     # kamera çalışıyor mu (görüntü kaydetmez)
python -m nimbus --kamera           # kamerayla çalıştır (başka kamera: --kamera 1)
```

Nimbus uyanınca bir kez bakıp görünüşüne laf sokar (kapatmak için `.env`: `NIMBUS_ILK_BAKIS=0`);
"bana bak", "elimde ne var?" gibi isteklerde kameradan **tek kare** alır. Sürekli video gönderilmez,
kareler diske yazılmaz, kamera sadece Nimbus uyanıkken açıktır. Kişinin fiziksel özelliklerine
(kilo, güzellik, yaş...) yorum yapmaz.

### Hafıza

Nimbus tanıştığı kişileri hatırlar: adını söyleyen kişiyi tanır, konuşma bitince onun hakkında
kısa notlar çıkarır. Kayıtlar **sadece bu bilgisayarda**, `data/hafiza.json` dosyasında durur (git'e girmez).

```bash
python -m nimbus --hafiza          # kimleri hatırlıyor
python -m nimbus --unut Eyüp       # bir kişiyi tamamen unut
```

Mikrofonu her seferinde yazmamak için `.env` dosyasına `NIMBUS_MIKROFON=5` ekle.
Çıkışta (`Ctrl+C`) gecikme özeti yazılır; konuşma kaydı `logs/` klasörüne düşer (git'e girmez).

**İpuçları:** Windows'ta varsayılan giriş "Stereo Mix" olabilir (otomatik atlanır).
Bluetooth kulaklığın mikrofonu kullanılınca ses "telefon modu"na düşer; ses kalitesini
değerlendirirken dahili ya da kablolu mikrofon kullan.

### ESP32 bedeni (Faz 2)
Nimbus'un fiziksel bedeni: ESP32-S3 + mikrofon + hoparlör + 2 servo (ağız, baş) + LED halka + dokunmatik.
Beyin dizüstünde kalır, ESP32 Wi-Fi ile bağlanır. Parçalar: [`donanim/ALISVERIS.md`](donanim/ALISVERIS.md),
kablolama: [`donanim/BAGLANTI.md`](donanim/BAGLANTI.md).

```bash
./n esp32-yukle            # .env'deki Wi-Fi bilgileriyle ESP32'ye yazılımı yükle
./n --esp32                # Nimbus'u ESP32 bedeniyle başlat (ekrandaki bulut yüz de çalışır)
./n --esp32-sanal          # donanım olmadan dene: bu bilgisayarın mikrofonu/hoparlörü ağ üzerinden
```

ESP32 modunda Nimbus konuşurken mikrofon kapalıdır (aynı kutuda yankı olmasın); sözünü kesmek için
dokunmatiğe dokun ya da terminale `k` yaz.

## Proje yapısı

```
nimbus/
  __main__.py   komut satırı (python -m nimbus)
  ayarlar.py    .env ayarları
  persona.py    persona YAML -> sistem talimatı
  ses.py        mikrofon, hoparlör, ağız senkronu
  oturum.py     durum makinesi + Gemini Live oturumu, yazıya döküm, kayıt
  durum.py      durumlar ve operatör komutları
  araclar.py    modelin çağırdığı fonksiyonlar (kisiyi_tani, uykuya_don) + Google araması
  hafiza.py     kişileri hatırlama (data/hafiza.json), konuşma sonrası not çıkarma
  ifade.py      söylenen metinden yüz ifadesi
  ses_dinle.py  sesleri art arda dinleme aracı
  kamera.py     görme: istek üzerine tek kare (OpenCV)
  eylem.py      ekranda bilgi kartı, sunum modunda slayt kontrolü
  senaryo.py    senaryo koşucusu (gerçek Gemini, sessiz, raporlu)
senaryolar/     test senaryoları (YAML)
tests/          otomatik testler (pytest, sahte Gemini)
  govde.py      gövde arayüzü (konsol -> sanal yüz -> servo)
  web.py        bulut yüz sunucusu (HTTP + WebSocket)
  esp32.py      ESP32 bedeni köprüsü (Wi-Fi üzerinden mikrofon, hoparlör, servo, LED)
web/index.html  bulut yüz (SVG + CSS + JS, harici bağımlılık yok)
personas/       karakter dosyaları (nimbus.yaml genel, gdg-konya.yaml GDG Cloud Konya)
bilgi/          kişiliğe eklenen bilgi dosyaları (topluluk, etkinlikler)
donanim/        Faz 2 bedeni: alışveriş listesi, bağlantı şeması, esp32/ yazılımı
spike/          Faz 0 deneme scripti (arşiv)
```

## Testler

**Otomatik testler** (mikrofon ve internet gerekmez; sahte Gemini ile):

```bash
pip install -r requirements-dev.txt
pytest
```

**Senaryo testleri** (gerçek Gemini ile, sesi atlayarak, yazılı konuşmalar):

```bash
python -m nimbus.senaryo                        # senaryolar/temel.yaml'daki tüm senaryolar
python -m nimbus.senaryo --sadece hava_durumu   # bazıları
```

Her cevap kurallarla (uzunluk, emoji, talimat sızıntısı...) ve bir değerlendirici modelle puanlanır.
Rapor `logs/senaryo-*.md` dosyasına yazılır. Gerçek hafızaya dokunmaz.

## Gizlilik notu
Kamera, hafıza ve (opsiyonel) yüz tanıma özellikleri kişisel veri işler.
Kullanmadan önce ilgili mevzuata (KVKK, GDPR vb.) uygun açık rıza alın.
Yüz tanıma modülü varsayılan olarak kapalıdır ve veriler cihazda kalır.

## Lisans
MIT (eklenecek)
