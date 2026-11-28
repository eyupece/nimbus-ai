// Bu dosyayı elle düzenlemene gerek yok: ./n esp32-yukle, .env'deki değerlerden include/ayarlar.h üretir.
// Elle derleyeceksen bu dosyayı ayarlar.h olarak kopyalayıp doldur (ayarlar.h git'e girmez).
#pragma once

#define WIFI_AD "wifi-adi"
#define WIFI_SIFRE "wifi-sifresi"
#define ANAHTAR "NIMBUS_ESP32_ANAHTAR-degeri"
#define SUNUCU_IP ""  // boş bırak: dizüstü otomatik bulunur. Bulunamazsa dizüstünün IP'si, örn. "192.168.1.20"

// İsteğe bağlı ayarlar (varsayılanlar src/main.cpp'de):
// #define SES_SEVIYESI 70   // 0-100
// #define AGIZ_KAPALI 90    // ağız servosu kapalı açısı
// #define AGIZ_ACIK 60      // ağız servosu tam açık açısı
// #define BAS_ORTA 90       // baş servosu düz bakış
