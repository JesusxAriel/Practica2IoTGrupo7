#include "ActuatorController.h"

namespace {
const unsigned long kDefaultBlinkMs = 200;
const unsigned long kMinBlinkMs = 50;
const unsigned long kMaxBlinkMs = 5000;
}  // namespace

ActuatorController::ActuatorController(uint8_t redPin, uint8_t yellowPin, uint8_t greenPin)
    : red_(redPin), yellow_(yellowPin), green_(greenPin), range_("FAULT") {}

void ActuatorController::begin() {
  red_.begin();
  yellow_.begin();
  green_.begin();
  showFault();
}

bool ActuatorController::applyState(const JsonDocument& message) {
  LedMode red, yellow, green;
  if (!LedActuator::parseMode(message["led_red"] | "", red) ||
      !LedActuator::parseMode(message["led_yellow"] | "", yellow) ||
      !LedActuator::parseMode(message["led_green"] | "", green)) {
    Serial.println(F("[LED] SET_STATE invalido, se ignora"));
    return false;
  }

  unsigned long blinkMs = message["blink_ms"] | static_cast<int>(kDefaultBlinkMs);
  if (blinkMs < kMinBlinkMs || blinkMs > kMaxBlinkMs) blinkMs = kDefaultBlinkMs;

  red_.set(red, blinkMs);
  yellow_.set(yellow, blinkMs);
  green_.set(green, blinkMs);
  range_ = String(message["range"] | "?");

  Serial.print(F("[LED] Estado aplicado: "));
  Serial.println(range_);
  return true;
}

void ActuatorController::showFault() {
  red_.set(LedMode::BLINK, 500);
  yellow_.set(LedMode::BLINK, 500);
  green_.set(LedMode::BLINK, 500);
  range_ = "FAULT";
}

void ActuatorController::update() {
  red_.update();
  yellow_.update();
  green_.update();
}
