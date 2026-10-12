#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>

/**
 * Construccion y analisis de mensajes SDP v1 (JSON de una linea).
 * Los metodos build* devuelven el JSON SIN el terminador de linea; el
 * terminador lo agrega TCPClientManager al enviar.
 */
class SDPMessage {
 public:
  static String buildInit(const char* type, const char* id);

  /** Si distanceCm es NAN (sin eco) envia distance_cm:null y err:"NO_ECHO". */
  static String buildData(const char* id, uint32_t seq, uint32_t ts, float distanceCm);

  static String buildAck(const char* id, uint32_t seq);
  static String buildPing(const char* id, uint32_t seq, uint32_t ts);

  /** Analiza una linea JSON. Devuelve false si no es JSON valido. */
  static bool parse(const String& line, JsonDocument& doc);
};
