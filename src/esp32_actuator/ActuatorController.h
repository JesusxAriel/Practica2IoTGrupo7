#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>

#include "LedActuator.h"

/** Agrupa los 3 LEDs (rojo, amarillo, verde) y aplica mensajes SET_STATE. */
class ActuatorController {
 public:
  ActuatorController(uint8_t redPin, uint8_t yellowPin, uint8_t greenPin);

  /** Inicializa los pines y deja el estado de seguridad (FAULT). */
  void begin();

  /**
   * Aplica un SET_STATE (campos led_red, led_yellow, led_green y blink_ms).
   * Devuelve false, sin cambiar nada, si algun campo es invalido.
   */
  bool applyState(const JsonDocument& message);

  /** Estado de seguridad (FAULT): los 3 LEDs (rojo, amarillo y verde) parpadean a 500 ms. */
  void showFault();

  /** Llamar en cada loop() (maneja el parpadeo). */
  void update();

  const String& currentRange() const { return range_; }

 private:
  LedActuator red_;
  LedActuator yellow_;
  LedActuator green_;
  String range_;
};
