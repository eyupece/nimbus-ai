// Nimbus ESP32 gövdesi: kulak (INMP441), ses (MAX98357A + hoparlör), ağız ve baş (2x MG90S),
// ışık (12'li NeoPixel halka) ve dokunma (TTP223).
//
// Beyin dizüstünde çalışır (python -m nimbus --esp32). ESP32 Wi-Fi'a bağlanır, dizüstünü UDP
// duyurusundan bulur ve WebSocket ile bağlanır:
//   ESP32 -> dizüstü: mikrofon sesi (16 kHz, 16-bit mono) + {"tip":"merhaba"} / {"tip":"dokunma"}
//   dizüstü -> ESP32: Nimbus'un sesi (24 kHz, 16-bit mono) + {"tip":"durum"|"jest"|"sustur"}
// Ağız servosu çalınan sesten burada hesaplanır: ağ gecikmesi ağız senkronunu bozmaz.
//
// Bağlantı şeması: donanim/BAGLANTI.md

#include <Adafruit_NeoPixel.h>
#include <Arduino.h>
#include <WebSocketsClient.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <driver/i2s.h>
#include <freertos/ringbuf.h>
#include <math.h>

#include "ayarlar.h"

#define SURUM "0.1.0"

// ---------- Pinler (donanim/BAGLANTI.md ile aynı) ----------
#define MIK_SCK 4
#define MIK_WS 5
#define MIK_SD 6
#define AMP_BCLK 15
#define AMP_LRC 16
#define AMP_DIN 7
#define SERVO_AGIZ 17
#define SERVO_BAS 18
#define LED_PIN 8
#define LED_SAYISI 12
#define DOKUNMA_PIN 9

// ---------- Varsayılan ayarlar (ayarlar.h ile değiştirilebilir) ----------
#ifndef SUNUCU_PORT
#define SUNUCU_PORT 8766
#endif
#ifndef SES_SEVIYESI
#define SES_SEVIYESI 70
#endif
#ifndef AGIZ_KAPALI
#define AGIZ_KAPALI 90
#endif
#ifndef AGIZ_ACIK
#define AGIZ_ACIK 60
#endif
#ifndef BAS_ORTA
#define BAS_ORTA 90
#endif
#ifndef BAS_UYKU
#define BAS_UYKU (BAS_ORTA + 20)
#endif
#ifndef MIK_KAYDIR
#define MIK_KAYDIR 12  // INMP441 32-bit örneğini 16-bit'e indirirken kazanç (küçük = daha yüksek ses)
#endif
#ifndef LED_PARLAKLIK
#define LED_PARLAKLIK 80  // 0-255
#endif

#define DUYURU_PORTU 8767
#define GIRIS_HIZI 16000
#define CIKIS_HIZI 24000
#define MIK_PARCA 512  // 32 ms
#define HOP_PARCA 480  // 20 ms
#define MIK_I2S I2S_NUM_0
#define HOP_I2S I2S_NUM_1
#define SERVO_AGIZ_KANAL 0
#define SERVO_BAS_KANAL 1
#define UZUN_DOKUNMA_MS 1200

// ---------- Paylaşılan durum ----------
static WebSocketsClient ws;
static WiFiUDP udp;
static Adafruit_NeoPixel halka(LED_SAYISI, LED_PIN, NEO_GRB + NEO_KHZ800);
static RingbufHandle_t hopTampon;  // dizüstünden gelen ses -> hoparlör
static RingbufHandle_t mikTampon;  // mikrofon -> dizüstü

static volatile bool bagli = false;
static volatile bool susturIstegi = false;
static volatile float agizDeger = 0;  // 0..1, hoparlör görevinde güncellenir
static volatile uint32_t sonSes = 0;  // son ses çalınma anı (ms)
static volatile float mikSeviye = 0;

static bool sunucuBilinen = false;
static IPAddress sunucuIp;
static uint16_t sunucuPort = SUNUCU_PORT;
static uint32_t kopmaAni = 0;

static char durumAd[16] = "uyku";
static char jestAd[16] = "";
static uint32_t jestBitis = 0;
static float basSu = BAS_UYKU;

// ---------- Servo (LEDC, 50 Hz) ----------
static void servoYaz(int kanal, float derece) {
  derece = constrain(derece, 0.0f, 180.0f);
  uint32_t mikrosaniye = 500 + (uint32_t)(derece / 180.0f * 1900.0f);  // MG90S: 0.5-2.4 ms
  ledcWrite(kanal, mikrosaniye * 16383 / 20000);
}

static void servolariKur() {
  ledcSetup(SERVO_AGIZ_KANAL, 50, 14);
  ledcAttachPin(SERVO_AGIZ, SERVO_AGIZ_KANAL);
  ledcSetup(SERVO_BAS_KANAL, 50, 14);
  ledcAttachPin(SERVO_BAS, SERVO_BAS_KANAL);
  servoYaz(SERVO_AGIZ_KANAL, AGIZ_KAPALI);
  servoYaz(SERVO_BAS_KANAL, basSu);
}

// ---------- I2S ----------
static void mikrofonuKur() {
  i2s_config_t c = {};
  c.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  c.sample_rate = GIRIS_HIZI;
  c.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
#ifdef MIK_SAG_KANAL
  c.channel_format = I2S_CHANNEL_FMT_ONLY_RIGHT;  // INMP441 L/R pini 3.3V'a bağlıysa
#else
  c.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;  // L/R pini GND'de (önerilen)
#endif
  c.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  c.dma_buf_count = 4;
  c.dma_buf_len = 256;
  i2s_pin_config_t p = {};
  p.mck_io_num = I2S_PIN_NO_CHANGE;
  p.bck_io_num = MIK_SCK;
  p.ws_io_num = MIK_WS;
  p.data_out_num = I2S_PIN_NO_CHANGE;
  p.data_in_num = MIK_SD;
  i2s_driver_install(MIK_I2S, &c, 0, NULL);
  i2s_set_pin(MIK_I2S, &p);
}

static void hoparloruKur() {
  i2s_config_t c = {};
  c.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX);
  c.sample_rate = CIKIS_HIZI;
  c.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  c.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;  // mono sesi iki kanala da yazıyoruz
  c.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  c.dma_buf_count = 6;
  c.dma_buf_len = 240;
  c.tx_desc_auto_clear = true;  // ses bitince cızırtı değil sessizlik
  i2s_pin_config_t p = {};
  p.mck_io_num = I2S_PIN_NO_CHANGE;
  p.bck_io_num = AMP_BCLK;
  p.ws_io_num = AMP_LRC;
  p.data_out_num = AMP_DIN;
  p.data_in_num = I2S_PIN_NO_CHANGE;
  i2s_driver_install(HOP_I2S, &c, 0, NULL);
  i2s_set_pin(HOP_I2S, &p);
  i2s_zero_dma_buffer(HOP_I2S);
}

// ---------- Ağız: ses şiddeti -> açıklık (dizüstündeki AgizYumusatici ile aynı) ----------
static void agziGuncelle(float siddet) {
  float hedef = (siddet - 250.0f) / (5000.0f - 250.0f);
  hedef = powf(constrain(hedef, 0.0f, 1.0f), 0.7f);
  float katsayi = hedef > agizDeger ? 0.65f : 0.30f;
  agizDeger = agizDeger + (hedef - agizDeger) * katsayi;
  servoYaz(SERVO_AGIZ_KANAL, AGIZ_KAPALI + agizDeger * (AGIZ_ACIK - AGIZ_KAPALI));
}

// ---------- Görevler ----------
static void hoparlorGorevi(void*) {
  static int16_t mono[HOP_PARCA];
  static int16_t stereo[HOP_PARCA * 2];
  for (;;) {
    if (susturIstegi) {  // söz kesildi: tampondaki sesi at
      size_t n;
      void* p;
      while ((p = xRingbufferReceiveUpTo(hopTampon, &n, 0, 64 * 1024)) != NULL) vRingbufferReturnItem(hopTampon, p);
      i2s_zero_dma_buffer(HOP_I2S);
      susturIstegi = false;
    }
    size_t n = 0;
    uint8_t* p = (uint8_t*)xRingbufferReceiveUpTo(hopTampon, &n, pdMS_TO_TICKS(20), HOP_PARCA * 2);
    if (p == NULL) {
      if (agizDeger > 0.01f) agziGuncelle(0);
      continue;
    }
    memcpy(mono, p, n);
    vRingbufferReturnItem(hopTampon, p);
    size_t ornek = n / 2;
    double toplam = 0;
    for (size_t i = 0; i < ornek; i++) {
      toplam += (double)mono[i] * mono[i];
      int16_t s = (int32_t)mono[i] * SES_SEVIYESI / 100;
      stereo[2 * i] = s;
      stereo[2 * i + 1] = s;
    }
    size_t yazilan;
    i2s_write(HOP_I2S, stereo, ornek * 4, &yazilan, portMAX_DELAY);
    agziGuncelle(ornek ? sqrtf(toplam / ornek) : 0);
    sonSes = millis();
  }
}

static void mikrofonGorevi(void*) {
  static int32_t ham[MIK_PARCA];
  static int16_t ornek[MIK_PARCA];
  for (;;) {
    size_t okunan = 0;
    i2s_read(MIK_I2S, ham, sizeof(ham), &okunan, portMAX_DELAY);
    size_t n = okunan / 4;
    double toplam = 0;
    for (size_t i = 0; i < n; i++) {
      int32_t s = ham[i] >> MIK_KAYDIR;
      s = constrain(s, -32768, 32767);
      ornek[i] = (int16_t)s;
      toplam += (double)s * s;
    }
    mikSeviye = n ? sqrtf(toplam / n) : 0;
    if (bagli && n) xRingbufferSend(mikTampon, ornek, n * 2, 0);  // dolarsa at: gecikme birikmesin
  }
}

// ---------- Olaylar ----------
// {"tip":"jest","ad":"gul"} içinden "ad" alanını çıkarır (JSON kütüphanesine gerek yok)
static bool alanAl(const char* json, const char* alan, char* cikti, size_t boy) {
  char aranan[24];
  snprintf(aranan, sizeof(aranan), "\"%s\":\"", alan);
  const char* bas = strstr(json, aranan);
  if (!bas) return false;
  bas += strlen(aranan);
  const char* son = strchr(bas, '"');
  if (!son) return false;
  size_t uzunluk = min((size_t)(son - bas), boy - 1);
  memcpy(cikti, bas, uzunluk);
  cikti[uzunluk] = 0;
  return true;
}

static void olayIsle(const char* json) {
  char tip[16];
  if (!alanAl(json, "tip", tip, sizeof(tip))) return;
  if (strcmp(tip, "sustur") == 0) {
    susturIstegi = true;
  } else if (strcmp(tip, "durum") == 0) {
    alanAl(json, "ad", durumAd, sizeof(durumAd));
    Serial.printf("durum: %s\n", durumAd);
  } else if (strcmp(tip, "jest") == 0) {
    if (alanAl(json, "ad", jestAd, sizeof(jestAd))) jestBitis = millis() + 1500;
  }
}

static void wsOlay(WStype_t tip, uint8_t* veri, size_t boy) {
  switch (tip) {
    case WStype_CONNECTED:
      bagli = true;
      Serial.println("Nimbus'a bağlandı");
      ws.sendTXT("{\"tip\":\"merhaba\",\"surum\":\"" SURUM "\"}");
      break;
    case WStype_DISCONNECTED:
      if (bagli) Serial.println("bağlantı koptu");
      bagli = false;
      kopmaAni = millis();
      break;
    case WStype_BIN:
      if (xRingbufferSend(hopTampon, veri, boy, pdMS_TO_TICKS(50)) != pdTRUE) Serial.println("hoparlör tamponu dolu");
      break;
    case WStype_TEXT: {
      char metin[160];
      size_t uzunluk = min(boy, sizeof(metin) - 1);
      memcpy(metin, veri, uzunluk);
      metin[uzunluk] = 0;
      olayIsle(metin);
      break;
    }
    default:
      break;
  }
}

static void baglan(IPAddress ip, uint16_t port) {
  sunucuIp = ip;
  sunucuPort = port;
  sunucuBilinen = true;
  Serial.printf("Nimbus: %s:%u\n", ip.toString().c_str(), port);
  ws.disconnect();
  ws.begin(ip, port, "/esp32?anahtar=" ANAHTAR);
}

// Dizüstü her 2 sn'de "NIMBUS 8766" yayınlar
static void duyuruDinle() {
  if (strlen(SUNUCU_IP) > 0) return;
  // Uzun süre bağlanamadıysak dizüstünün IP'si değişmiş olabilir: yeni duyuruyu kabul et
  bool yeniArayalim = !sunucuBilinen || (!bagli && millis() - kopmaAni > 10000);
  int boy = udp.parsePacket();
  if (boy <= 0) return;
  char mesaj[32];
  int uzunluk = udp.read(mesaj, sizeof(mesaj) - 1);
  if (uzunluk <= 0) return;
  mesaj[uzunluk] = 0;
  if (strncmp(mesaj, "NIMBUS ", 7) != 0 || !yeniArayalim) return;
  IPAddress ip = udp.remoteIP();
  uint16_t port = atoi(mesaj + 7);
  if (!sunucuBilinen || ip != sunucuIp || port != sunucuPort) baglan(ip, port);
}

// ---------- Dokunma ----------
static void dokunmaKontrol() {
  static bool basili = false, uzunGitti = false;
  static uint32_t basAni = 0;
  bool simdi = digitalRead(DOKUNMA_PIN) == HIGH;
  if (simdi && !basili) {
    basili = true;
    uzunGitti = false;
    basAni = millis();
  } else if (simdi && basili && !uzunGitti && millis() - basAni >= UZUN_DOKUNMA_MS) {
    uzunGitti = true;
    if (bagli) ws.sendTXT("{\"tip\":\"dokunma\",\"uzun\":true}");
  } else if (!simdi && basili) {
    basili = false;
    if (!uzunGitti && millis() - basAni > 40 && bagli) ws.sendTXT("{\"tip\":\"dokunma\",\"uzun\":false}");
  }
}

// ---------- Baş ve ışık ----------
static bool jestVar(const char* ad) { return millis() < jestBitis && strcmp(jestAd, ad) == 0; }

static void basGuncelle() {
  static uint32_t son = 0;
  if (millis() - son < 20) return;
  son = millis();
  float hedef = strcmp(durumAd, "uyku") == 0 ? BAS_UYKU : BAS_ORTA;
  if (jestVar("kas_kaldir") || jestVar("dusun")) hedef = BAS_ORTA + 15;
  else if (jestVar("saskin")) hedef = BAS_ORTA - 12;
  else if (jestVar("bak")) hedef = BAS_ORTA - 8;
  else if (jestVar("gul")) hedef = BAS_ORTA + 6 * sinf(millis() / 90.0f);  // keyifli sallanma
  float adim = jestVar("saskin") ? 4.0f : 1.5f;
  basSu += constrain(hedef - basSu, -adim, adim);
  servoYaz(SERVO_BAS_KANAL, basSu);
}

static uint32_t renk(float r, float g, float b, float k) {
  return halka.Color((uint8_t)(r * k), (uint8_t)(g * k), (uint8_t)(b * k));
}

static void isikGuncelle() {
  static uint32_t son = 0;
  if (millis() - son < 30) return;
  son = millis();
  uint32_t t = millis();
  float nefes = 0.5f + 0.5f * sinf(t / 900.0f);

  if (WiFi.status() != WL_CONNECTED) {  // Wi-Fi aranıyor: sarı dönen nokta
    halka.clear();
    halka.setPixelColor((t / 80) % LED_SAYISI, renk(255, 160, 0, 1));
  } else if (!bagli) {  // Wi-Fi var, Nimbus yok: turuncu yanıp sönme
    halka.fill(renk(255, 80, 0, 0.15f + 0.6f * nefes));
  } else if (millis() < jestBitis && strcmp(jestAd, "goz_kirp") == 0 && (t / 150) % 2) {
    halka.clear();
  } else if (millis() < jestBitis && strcmp(jestAd, "kizgin") == 0) {
    halka.fill(renk(255, 30, 0, 0.8f));
  } else if (millis() < jestBitis && strcmp(jestAd, "gul") == 0) {
    halka.fill(renk(255, 190, 40, 0.8f));
  } else if (millis() < jestBitis && strcmp(jestAd, "saskin") == 0) {
    halka.fill(renk(190, 60, 255, 0.9f));
  } else if (millis() < jestBitis && (strcmp(jestAd, "dusun") == 0 || strcmp(jestAd, "kas_kaldir") == 0)) {
    halka.clear();
    for (int i = 0; i < 3; i++) halka.setPixelColor((t / 70 + i) % LED_SAYISI, renk(60, 140, 255, 1 - i * 0.3f));
  } else if (strcmp(durumAd, "uyku") == 0) {  // uyku: yavaş mavi nefes
    halka.fill(renk(40, 70, 255, 0.05f + 0.25f * nefes));
  } else {  // uyanık: konuşurken sesle parlar
    float k = 0.3f + 0.7f * agizDeger;
    halka.fill(renk(150, 200, 255, k));
  }
  halka.show();
}

// ---------- Açılış testi: kabloları kontrol etmek için ----------
static void acilisTesti() {
  Serial.println("Açılış testi: ışık, ağız, baş, ses");
  for (int i = 0; i < LED_SAYISI; i++) {
    halka.setPixelColor(i, halka.ColorHSV(i * 65535 / LED_SAYISI, 255, 255));
    halka.show();
    delay(40);
  }
  servoYaz(SERVO_AGIZ_KANAL, AGIZ_ACIK);
  delay(300);
  servoYaz(SERVO_AGIZ_KANAL, AGIZ_KAPALI);
  servoYaz(SERVO_BAS_KANAL, BAS_ORTA - 15);
  delay(300);
  servoYaz(SERVO_BAS_KANAL, BAS_ORTA + 15);
  delay(300);
  servoYaz(SERVO_BAS_KANAL, basSu);
  // Kısa "bi-dip" sesi
  static int16_t ton[HOP_PARCA];
  for (int nota = 0; nota < 2; nota++) {
    float frekans = nota ? 1320.0f : 880.0f;
    for (int parca = 0; parca < 6; parca++) {
      for (int i = 0; i < HOP_PARCA; i++)
        ton[i] = (int16_t)(6000 * sinf(2 * PI * frekans * (parca * HOP_PARCA + i) / CIKIS_HIZI));
      xRingbufferSend(hopTampon, ton, sizeof(ton), portMAX_DELAY);
    }
  }
  halka.clear();
  halka.show();
}

// ---------- Kurulum ve döngü ----------
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.printf("\nNimbus ESP32 gövdesi %s\n", SURUM);

  pinMode(DOKUNMA_PIN, INPUT_PULLDOWN);
  halka.begin();
  halka.setBrightness(LED_PARLAKLIK);
  servolariKur();

  hopTampon = xRingbufferCreate(64 * 1024, RINGBUF_TYPE_BYTEBUF);  // ~1.3 sn ses
  mikTampon = xRingbufferCreate(16 * 1024, RINGBUF_TYPE_BYTEBUF);
  mikrofonuKur();
  hoparloruKur();
  xTaskCreatePinnedToCore(hoparlorGorevi, "hoparlor", 6144, NULL, 5, NULL, 1);
  xTaskCreatePinnedToCore(mikrofonGorevi, "mikrofon", 6144, NULL, 5, NULL, 0);
  acilisTesti();

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // güç tasarrufu kapalı: ses gecikmesi düşük kalsın
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_AD, WIFI_SIFRE);
  Serial.printf("Wi-Fi: %s\n", WIFI_AD);

  udp.begin(DUYURU_PORTU);
  ws.onEvent(wsOlay);
  ws.setReconnectInterval(2000);
  ws.enableHeartbeat(15000, 3000, 2);
  IPAddress sabit;
  if (strlen(SUNUCU_IP) > 0 && sabit.fromString(SUNUCU_IP)) baglan(sabit, SUNUCU_PORT);
}

void loop() {
  static bool wifiVardi = false;
  bool wifiVar = WiFi.status() == WL_CONNECTED;
  if (wifiVar != wifiVardi) {
    wifiVardi = wifiVar;
    if (wifiVar) Serial.printf("Wi-Fi bağlandı, IP: %s\n", WiFi.localIP().toString().c_str());
    else Serial.println("Wi-Fi yok, aranıyor...");
  }

  if (wifiVar) {
    ws.loop();
    duyuruDinle();
  }

  // Mikrofon sesini gönder
  static uint8_t gonder[MIK_PARCA * 2];
  size_t n;
  uint8_t* p;
  while (bagli && (p = (uint8_t*)xRingbufferReceiveUpTo(mikTampon, &n, 0, sizeof(gonder))) != NULL) {
    memcpy(gonder, p, n);
    vRingbufferReturnItem(mikTampon, p);
    ws.sendBIN(gonder, n);
  }

  dokunmaKontrol();
  basGuncelle();
  isikGuncelle();

  // Bağlı değilken arada bir mikrofon seviyesini yaz (kablo kontrolü için)
  static uint32_t sonRapor = 0;
  if (!bagli && millis() - sonRapor > 3000) {
    sonRapor = millis();
    Serial.printf("bekleniyor... mikrofon seviyesi: %.0f (konuşunca yükselmeli)\n", (float)mikSeviye);
  }
  delay(1);
}
