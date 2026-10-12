/**
 * Practica 2 - SIS-234 - Objeto Inteligente 2 (actuadores: 3 LEDs)
 *
 * Se registra en el servidor TCP, recibe mensajes SET_STATE y enciende los
 * LEDs segun el rango de distancia. Responde con ACK tras aplicar cada estado.
 *
 * Si pierde la conexion con el servidor, muestra el estado de seguridad FAULT
 * (los 3 LEDs parpadeando) hasta recibir de nuevo el estado actual.
 *
 * Bibliotecas: ArduinoJson v7 (declarada en platformio.ini, se instala sola al compilar).
 * Antes de compilar: copiar config.example.h a config.h y completar los datos. Compilar y cargar con: pio run -e actuator -t upload
 */
#include <Arduino.h>
#include <ArduinoJson.h>

#include "ActuatorController.h"
#include "SDPMessage.h"
#include "TCPClientManager.h"
#include "WiFiManager.h"
#include "config.h"

// Pines (cada LED con resistencia de 220 ohm a GND). GPIO 21 en lugar de 5
// para el verde, porque GPIO 5 es un pin de arranque (strapping) del ESP32.
static const uint8_t RED_PIN = 19;
static const uint8_t YELLOW_PIN = 18;
static const uint8_t GREEN_PIN = 21;

WiFiManager wifi(WIFI_SSID, WIFI_PASSWORD);
TCPClientManager tcp(SERVER_IP, SERVER_PORT, CLIENT_ID, "ACTUATOR");
ActuatorController leds(RED_PIN, YELLOW_PIN, GREEN_PIN);

bool wasReady = false;

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println(F("\n=== ESP32 ACTUADOR (SDP) ==="));

  leds.begin();  // arranca en FAULT (amarillo parpadeando)
  wifi.connect();
  tcp.begin();
}

void loop() {
  wifi.ensureConnected();
  tcp.update();

  // Sin conexion al servidor no se conoce el estado real: estado de seguridad.
  const bool ready = tcp.isReady();
  if (wasReady && !ready) {
    leds.showFault();
  }
  wasReady = ready;

  JsonDocument incoming;
  while (tcp.receive(incoming)) {
    const char* cmd = incoming["cmd"] | "";
    if (strcmp(cmd, "SET_STATE") == 0) {
      if (leds.applyState(incoming)) {
        const uint32_t seq = incoming["seq"] | 0;
        tcp.sendLine(SDPMessage::buildAck(CLIENT_ID, seq));
      }
    } else if (strcmp(cmd, "ERROR") == 0) {
      Serial.print(F("[SDP] ERROR del servidor: "));
      Serial.println(incoming["code"] | "?");
    }
  }

  leds.update();
}
