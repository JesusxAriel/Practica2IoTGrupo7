#pragma once
#include <Arduino.h>
#include <WiFi.h>

/**
 * Conexion WiFi (modo estacion) al hotspot del celular.
 * El ESP32 solo soporta 2,4 GHz.
 */
class WiFiManager {
 public:
  WiFiManager(const char* ssid, const char* password);

  /** Conecta y espera hasta timeoutMs. Devuelve true si quedo conectado. */
  bool connect(unsigned long timeoutMs = 15000);

  bool isConnected() const;

  /** Llamar en loop(): si se perdio la senal, reintenta cada 5 s (no bloquea). */
  void ensureConnected();

 private:
  static const unsigned long kRetryPeriodMs = 5000;

  const char* ssid_;
  const char* password_;
  unsigned long lastAttemptMs_;
};
