#pragma once
#include <Arduino.h>

/**
 * Sensor ultrasonico HC-SR04.
 *
 * IMPORTANTE: el pin Echo entrega 5 V. Conectarlo al ESP32 a traves de un
 * divisor de tension (1 kOhm en serie + 2 kOhm a GND) para obtener ~3,3 V.
 */
class HCSR04Sensor {
 public:
  HCSR04Sensor(uint8_t trigPin, uint8_t echoPin);

  void begin();

  /**
   * Una medicion en cm. Devuelve NAN si no hubo eco dentro de 25 ms
   * (objeto fuera de alcance o sensor desconectado). El valor crudo no se
   * limita: el servidor valida el rango 2 - 400 cm.
   */
  float measureCm();

  /**
   * Mediana de `samples` mediciones (maximo 9), separadas gapMs milisegundos.
   * Descarta lecturas sin eco; devuelve NAN si hay menos de 2 validas.
   */
  float measureMedianCm(uint8_t samples = 3, unsigned long gapMs = 10);

 private:
  uint8_t trigPin_;
  uint8_t echoPin_;
};
