#include "WiFiManager.h"

WiFiManager::WiFiManager(const char* ssid, const char* password)
    : ssid_(ssid), password_(password), lastAttemptMs_(0) {}

bool WiFiManager::connect(unsigned long timeoutMs) {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // sin ahorro de energia: menor latencia
  WiFi.begin(ssid_, password_);

  Serial.print(F("[WiFi] Conectando a "));
  Serial.print(ssid_);
  const unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < timeoutMs) {
    delay(250);
    Serial.print('.');
  }
  lastAttemptMs_ = millis();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print(F("\n[WiFi] Conectado. IP: "));
    Serial.println(WiFi.localIP());
    return true;
  }
  Serial.println(F("\n[WiFi] No se pudo conectar (se reintentara)."));
  return false;
}

bool WiFiManager::isConnected() const { return WiFi.status() == WL_CONNECTED; }

void WiFiManager::ensureConnected() {
  if (isConnected()) return;
  const unsigned long now = millis();
  if (now - lastAttemptMs_ < kRetryPeriodMs) return;
  lastAttemptMs_ = now;
  Serial.println(F("[WiFi] Senal perdida, reintentando..."));
  WiFi.disconnect();
  WiFi.begin(ssid_, password_);
}
