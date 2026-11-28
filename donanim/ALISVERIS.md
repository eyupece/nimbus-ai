# Faz 2 Alışveriş Listesi

> Hazırlanma: 28 Kasım 2026. Fiyatlar o gün arama sonuçlarında görülen KDV dahil fiyatlardır; stok ve fiyat değişir,
> sepete eklemeden önce kontrol et. "Tahmini" yazanlar için Türkiye fiyatına bakılamadı.

## Mimari kararı: ESP32-S3 "ince istemci" (onaylandı, 28.11.2026)

Nimbus'un beyni (Gemini Live, hafıza, kamera, bulut yüz) zaten dizüstünde Python olarak çalışıyor. ESP32 sadece
**kulak, ağız ve kas** olur: mikrofonu Wi-Fi üzerinden dizüstüne akıtır, gelen sesi hoparlöre verir, servoları oynatır.

- Kod değişikliği az: `govde.py`'ye yeni bir "ESP32 gövdesi" eklenir (ağız senkronu ve jestler hazır), `ses.py`'ye ağ üzerinden ses.
- Raspberry Pi'ye göre ucuz, küçük, az güç harcar; şapka/obje içine sığar.
- Referans: [GefryV3/esp32-voice-assistant](https://github.com/GefryV3/esp32-voice-assistant) aynı mimariyi kullanıyor.
- Ses objenin kendi hoparlöründen çıkar; dizüstü aynı Wi-Fi'da açık olmalı (başka odada olabilir).
- Raspberry Pi kapısı açık: ileride dizüstüsüz istersek beyin bir Pi'ye taşınır, ESP32 tarafı değişmez.
  (Pi 5 4GB tek başına ~3.800–5.000 TL + adaptör; mikrofon/amfi/servo yine gerekir.)

Bağlantı şeması: [`BAGLANTI.md`](BAGLANTI.md) · Yazılım: [`esp32/`](esp32/) (`./n esp32-yukle`)

## Zorunlu parçalar

| Parça | Adet | Ne için | Yaklaşık fiyat (KDV dahil) | Örnek satıcı |
|---|---|---|---|---|
| **ESP32-S3 N16R8 DevKitC-1** (16 MB flash, 8 MB PSRAM, lehimli pinli) | 1 | Beyin değil sinir sistemi: Wi-Fi, I2S ses, servo | ~540–705 TL | [Robo Dünya](https://www.robodunya.com/esp32-s3-n16r8-wifi-ve-bluetooth-gelistirme-karti) (~541 TL), [Robolink](https://www.robolinkmarket.com/esp32-s3-n16r8-wifi-ve-bluetooth-gelistirme-karti) (705 TL), [Robiz](https://robiz.net/esp32s3n16r8) (660 TL) |
| **INMP441 I2S MEMS mikrofon** | 2 (1 yedek) | Nimbus'un kulağı | ~145–160 TL/adet | [Direnc.net](https://www.direnc.net/inmp441-mems-i2s-cok-yonlu-mikrofon-modulu-en) (145 TL), [Robolink](https://www.robolinkmarket.com/inmp441-omnidirection-mikrofon-modulu) (160 TL) |
| **MAX98357A I2S 3W amfi** | 1 | Hoparlörü sürer (dijital ses → hoparlör) | ~135–155 TL | [Robotronik](https://www.robotronik.com.tr/max98357-i2s-5v-3w-class-d-dijital-ses-yukseltici-amplifikator-modulu-a0466) (135 TL), [Robo90](https://www.robo90.com/max98357-i2s-3w-amplifikator-modulu) (150 TL), [Bigbang3d](https://www.bigbang3d.com/urun/max98357a-i2s-3w-class-d-mono-ses-amplifikator-modulu) (156 TL) |
| **Mini hoparlör 4 Ω 3 W, ~40 mm** | 1 | Nimbus'un sesi | tahmini 75–150 TL | Robotistan / Direnc.net "4 ohm 3W hoparlör" araması |
| **MG90S servo (180°, metal dişli)** | 2 | 1: ağız/çene, 1: baş eğme ya da göz kapağı | ~125–130 TL/adet | [Robotistan](https://www.robotistan.com/mg90s-servo-motor-en) (127 TL), [Robotus](https://www.robotus.net/towerpro-mg90s-metal-disli-servo-motor) |
| Breadboard + erkek-erkek / erkek-dişi jumper kablo seti | 1 | Lehimsiz prototip | tahmini 100–200 TL | herhangi bir elektronik mağazası |
| 1000 µF 10 V+ elektrolitik kondansatör | 2 | Servo çekişinde ESP32'nin resetlenmesini önler | tahmini 10–20 TL | — |
| 5 V 3 A adaptör, 5.5×2.1 mm DC jak | 1 | Servolar, amfi ve LED için güç | tahmini 150–250 TL | — |
| DC jak dişi **vidalı klemens** adaptörü (5.5×2.1) | 1 | Adaptörü lehimsiz breadboard rayına bağlar | tahmini 15–30 TL | — |
| **WS2812B 12'li NeoPixel halka** | 1 | Göz/ruh hali ışığı: uyku, konuşma, jestlerde renk | ~130 TL ([Cimri: 12 bit halka](https://www.cimri.com/ws2812b)) | — |
| **TTP223 dokunmatik modül** | 1 | Dokun: uyan / sus; basılı tut: vedalaş | tahmini 20–40 TL | — |

Jumper setinde **dişi-erkek** kablolar olsun: ESP32 breadboard'a takılmıyor, pinlerinden kabloyla bağlanıyor.

**Toplam: yaklaşık 1.700–2.300 TL**

## Sonraya bırakılan

| Parça | Neden şimdi değil | Yaklaşık fiyat |
|---|---|---|
| **ESP32-S3 N16R8 + OV2640 kameralı kart** | Ana kartın yerine geçmiyor (ikinci bir ESP32); Wi-Fi'dan görüntü ayrı iş; dizüstü kamerası iyi çalışıyor. Pi'ye geçersek Pi kamerası daha iyi | ~975 TL ([Robotikdepo](https://robotikdepo.com/esp32-s3-n16r8-ov2640-wifi-bluetooth-kamera-board)) |

## Notlar

- **Lehimli pinli** ESP32 kartı al ("LEHİMLİ" yazanlar).
- INMP441 ve MAX98357A modüllerinin pin başlıkları neredeyse her satıcıda **ayrı** gelir (lehim gerekir). Ürün sayfasında
  "lehimli" yazan varsa onu seç; yoksa tanıdığına lehimlet (~15 dk, liste: [`BAGLANTI.md`](BAGLANTI.md#lehim-gereken-yerler-tanıdığına-götür)).
  Lehimden tamamen kaçmanın yolu hazır kutu kartlar (ESP32-S3-BOX vb.); pahalı ve servo bağlamak zorlaşıyor, önermiyoruz.
- Servolar ESP32'nin 3.3 V pininden değil 5 V adaptörden beslenmeli (topraklar ortak).
- Kargo eşiği: Robotistan ~1.500 TL üzeri ücretsiz; mümkünse her şeyi tek mağazadan al.
