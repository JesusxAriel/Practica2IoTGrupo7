#pragma once
#include <Arduino.h>

enum class LedMode { OFF, ON, BLINK };

/**
 * Un LED con tres modos: apagado, encendido fijo o parpadeo.
 * El parpadeo es no bloqueante (usa millis()): hay que llamar a update()
 * en cada vuelta de loop().
 */
class LedActuator {
 public:
  explicit LedActuator(uint8_t pin);

  void begin();

  /** Cambia el modo. blinkMs es la mitad del periodo (tiempo encendido). */
  void set(LedMode mode, unsigned long blinkMs = 200);

  void update();

  LedMode mode() const { return mode_; }

  /** Convierte "OFF" / "ON" / "BLINK" a LedMode. Devuelve false si no es valido. */
  static bool parseMode(const char* text, LedMode& out);

 private:
  uint8_t pin_;
  LedMode mode_;
  unsigned long blinkMs_;
  unsigned long lastToggleMs_;
  bool level_;
};
