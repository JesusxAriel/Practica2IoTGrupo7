#include "LedActuator.h"

LedActuator::LedActuator(uint8_t pin)
    : pin_(pin), mode_(LedMode::OFF), blinkMs_(200), lastToggleMs_(0), level_(false) {}

void LedActuator::begin() {
  pinMode(pin_, OUTPUT);
  mode_ = LedMode::OFF;
  level_ = false;
  digitalWrite(pin_, LOW);
}

void LedActuator::set(LedMode mode, unsigned long blinkMs) {
  // Si ya esta en ese modo (y mismo periodo), no se reinicia el parpadeo.
  if (mode == mode_ && (mode != LedMode::BLINK || blinkMs == blinkMs_)) return;

  mode_ = mode;
  blinkMs_ = blinkMs;
  switch (mode_) {
    case LedMode::OFF:
      level_ = false;
      break;
    case LedMode::ON:
      level_ = true;
      break;
    case LedMode::BLINK:
      level_ = true;
      lastToggleMs_ = millis();
      break;
  }
  digitalWrite(pin_, level_ ? HIGH : LOW);
}

void LedActuator::update() {
  if (mode_ != LedMode::BLINK) return;
  const unsigned long now = millis();
  if (now - lastToggleMs_ >= blinkMs_) {
    level_ = !level_;
    digitalWrite(pin_, level_ ? HIGH : LOW);
    lastToggleMs_ = now;
  }
}

bool LedActuator::parseMode(const char* text, LedMode& out) {
  if (strcmp(text, "OFF") == 0) {
    out = LedMode::OFF;
  } else if (strcmp(text, "ON") == 0) {
    out = LedMode::ON;
  } else if (strcmp(text, "BLINK") == 0) {
    out = LedMode::BLINK;
  } else {
    return false;
  }
  return true;
}
