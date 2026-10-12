#include "HCSR04Sensor.h"

namespace {
const unsigned long kEchoTimeoutUs = 25000UL;  // ~4,3 m de alcance maximo
const float kSoundCmPerUs = 0.0343f;           // velocidad del sonido a ~20 C
const uint8_t kMaxSamples = 9;
}  // namespace

HCSR04Sensor::HCSR04Sensor(uint8_t trigPin, uint8_t echoPin)
    : trigPin_(trigPin), echoPin_(echoPin) {}

void HCSR04Sensor::begin() {
  pinMode(trigPin_, OUTPUT);
  pinMode(echoPin_, INPUT);
  digitalWrite(trigPin_, LOW);
}

float HCSR04Sensor::measureCm() {
  // Pulso de disparo de 10 us
  digitalWrite(trigPin_, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin_, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin_, LOW);

  const unsigned long durationUs = pulseIn(echoPin_, HIGH, kEchoTimeoutUs);
  if (durationUs == 0) return NAN;  // sin eco

  // El sonido va y vuelve: distancia = tiempo * velocidad / 2
  return static_cast<float>(durationUs) * kSoundCmPerUs / 2.0f;
}

float HCSR04Sensor::measureMedianCm(uint8_t samples, unsigned long gapMs) {
  if (samples > kMaxSamples) samples = kMaxSamples;
  if (samples == 0) samples = 1;

  float values[kMaxSamples];
  uint8_t count = 0;
  for (uint8_t i = 0; i < samples; i++) {
    const float value = measureCm();
    if (!isnan(value)) values[count++] = value;
    if (i + 1 < samples) delay(gapMs);
  }
  if (count < 2) return NAN;

  // Ordenamiento por insercion (arreglo pequeno)
  for (uint8_t i = 1; i < count; i++) {
    const float key = values[i];
    int8_t j = static_cast<int8_t>(i) - 1;
    while (j >= 0 && values[j] > key) {
      values[j + 1] = values[j];
      j--;
    }
    values[j + 1] = key;
  }

  if (count % 2 == 1) return values[count / 2];
  return (values[count / 2 - 1] + values[count / 2]) / 2.0f;
}
