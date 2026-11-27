# ☁️ Nimbus

**Nimbus, buluttan objelere ruh üfler.**

Bir şapkaya, kafatasına, kitaba ya da herhangi bir objeye; seni dinleyen, düşünen,
Türkçe konuşan ve hareket eden bir karakter yerleştirmek için açık kaynak bir kit.
Beyin Google Cloud'da (Gemini Live), gövde sahnede.

> 🚧 Erken aşama: şu an Faz 0 (ses döngüsü keşfi). Plan için [ROADMAP.md](ROADMAP.md).

## Hızlı başlangıç (Faz 0)

Gereken: Python 3.11+ (öneri: 3.12), mikrofon, kulaklık.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
copy .env.example .env          # Windows  (macOS/Linux: cp .env.example .env)
```

`.env` dosyasını açıp [Google AI Studio](https://aistudio.google.com/apikey)'dan aldığın
anahtarı `GEMINI_API_KEY=` satırına yapıştır. Sonra:

```bash
python spike/faz0_ses_dongusu.py                  # varsayılan ses (Charon)
python spike/faz0_ses_dongusu.py --ses Puck       # başka ses dene
python spike/faz0_ses_dongusu.py --yarim-dubleks  # kulaklık yoksa (yankıyı önler)
```

Kişiliği değiştirmek için `personas/nimbus.yaml` dosyasını düzenle.

## Gizlilik notu
Kamera, hafıza ve (opsiyonel) yüz tanıma özellikleri kişisel veri işler.
Kullanmadan önce ilgili mevzuata (KVKK, GDPR vb.) uygun açık rıza alın.
Yüz tanıma modülü varsayılan olarak kapalıdır ve veriler cihazda kalır.

## Lisans
MIT (eklenecek)
