# Faz 2 Alışveriş Listesi

> Hazırlanma: 28 Kasım 2026. Fiyatlar o gün arama sonuçlarında görülen KDV dahil fiyatlardır; stok ve fiyat değişir,
> sepete eklemeden önce kontrol et. "Tahmini" yazanlar için Türkiye fiyatına bakılamadı.

## Mimari kararı (öneri): ESP32-S3 "ince istemci"

Nimbus'un beyni (Gemini Live, hafıza, kamera, bulut yüz) zaten dizüstünde Python olarak çalışıyor. ESP32 sadece
**kulak, ağız ve kas** olur: mikrofonu Wi-Fi üzerinden dizüstüne akıtır, gelen sesi hoparlöre verir, servoları oynatır.

- Kod değişikliği az: `govde.py`'ye yeni bir "ESP32 gövdesi" eklenir (ağız senkronu ve jestler hazır), `ses.py`'ye ağ üzerinden ses.
- Raspberry Pi'ye göre ucuz, küçük, az güç harcar; şapka/obje içine sığar.
- Referans: [GefryV3/esp32-voice-assistant](https://github.com/GefryV3/esp32-voice-assistant) aynı mimariyi kullanıyor.

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
| 5 V 3 A USB-C adaptör (ya da powerbank) | 1 | Servolar + amfi için yeterli akım | tahmini 150–250 TL | — |

**Zorunlu toplam: yaklaşık 1.500–2.000 TL**

## İsteğe bağlı (sahne etkisi)

| Parça | Ne için | Yaklaşık fiyat |
|---|---|---|
| **WS2812B 12'li NeoPixel halka** | Göz/ruh hali ışığı; karar anında renk (yol haritasındaki LED maddesi) | ~130 TL ([Cimri: 12 bit halka](https://www.cimri.com/ws2812b)) |
| **ESP32-S3 N16R8 + OV2640 kameralı kart** | Kamerayı objenin içine taşımak (şu an dizüstü kamerası kullanılıyor) | ~975 TL ([Robotikdepo](https://robotikdepo.com/esp32-s3-n16r8-ov2640-wifi-bluetooth-kamera-board)) |
| TTP223 dokunmatik modül | "Başa takınca uyan" tetiği (alternatif: ESP32-S3'ün kendi dokunmatik pinleri, ek parça gerekmez) | tahmini 20–40 TL |

## Notlar

- **Lehimli pinli** kart al ("LEHİMLİ" yazanlar); lehim istemeyen breadboard prototipi için şart.
- INMP441 ve MAX98357A modüllerinin pin başlıkları bazen lehimsiz gelir; ürün sayfasında "lehimli" yazıp yazmadığına bak.
  Lehimsizse ya lehimli olanı seç ya da bir makerspace/GDG etkinliğinde lehimlet.
- Servolar ESP32'nin 3.3 V pininden değil 5 V adaptörden beslenmeli (topraklar ortak).
- Kargo eşiği: Robotistan ~1.500 TL üzeri ücretsiz; mümkünse her şeyi tek mağazadan al.
