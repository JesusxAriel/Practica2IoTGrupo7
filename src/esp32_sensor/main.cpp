/**
 * Practica 2 - SIS-234 - Objeto Inteligente 1 (sensor ultrasonico)
 *
 * Mide la distancia con un HC-SR04 cada 300 ms y la envia al servidor TCP
 * con el protocolo SDP (mensaje DATA).
 *
 * Bibliotecas: ArduinoJson v7 (declarada en platformio.ini, se instala sola al compilar).
 * Antes de compilar: copiar config.example.h a config.h y completar los datos. Compilar y cargar con: pio run -e sensor -t upload
 */
#include <Arduino.h>
#include <ArduinoJson.h>

#include "HCSR04Sensor.h"
#include "SDPMessage.h"
#include "TCPClientManager.h"
#include "WiFiManager.h"
#include "config.h"

// Pines (ver diagrama de circuito). Echo pasa por divisor de tension.
static const uint8_t TRIG_PIN = 5;
static const uint8_t ECHO_PIN = 18;

static const unsigned long SAMPLE_PERIOD_MS = 300;  // ~3,3 lecturas/s

WiFiManager wifi(WIFI_SSID, WIFI_PASSWORD);
TCPClientManager tcp(SERVER_IP, SERVER_PORT, CLIENT_ID, "SENSOR");
HCSR04Sensor sensor(TRIG_PIN, ECHO_PIN);

uint32_t dataSeq = 0;
unsigned long lastSampleMs = 0;

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println(F("\n=== ESP32 SENSOR (SDP) ==="));

  sensor.begin();
  wifi.connect();
  tcp.begin();
  lastSampleMs = millis();
}

void loop() {
  wifi.ensureConnected();
  tcp.update();

  // Mensajes del servidor (en el sensor solo se esperan ERROR)
  JsonDocument incoming;
  while (tcp.receive(incoming)) {
    const char* cmd = incoming["cmd"] | "";
    if (strcmp(cmd, "ERROR") == 0) {
      Serial.print(F("[SDP] ERROR del servidor: "));
      Serial.println(incoming["code"] | "?");
    }
  }

  const unsigned long now = millis();
  if (now - lastSampleMs >= SAMPLE_PERIOD_MS) {
    // Mantiene el ritmo de 300 ms; si hubo una pausa larga (reconexion), no acumula rafagas
    lastSampleMs = (now - lastSampleMs > 2 * SAMPLE_PERIOD_MS) ? now : lastSampleMs + SAMPLE_PERIOD_MS;

    const float distance = sensor.measureMedianCm();
    if (isnan(distance)) {
      Serial.println(F("[SENSOR] sin eco"));
    } else {
      Serial.print(F("[SENSOR] "));
      Serial.print(distance, 1);
      Serial.println(F(" cm"));
    }

    if (tcp.isReady()) {
      tcp.sendLine(SDPMessage::buildData(CLIENT_ID, dataSeq++, now, distance));
    }
  }
}
