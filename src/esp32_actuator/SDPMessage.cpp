#include "SDPMessage.h"

namespace {
String serialize(const JsonDocument& doc) {
  String out;
  serializeJson(doc, out);
  return out;
}
}  // namespace

String SDPMessage::buildInit(const char* type, const char* id) {
  JsonDocument doc;
  doc["cmd"] = "INIT";
  doc["type"] = type;
  doc["id"] = id;
  doc["ver"] = 1;
  return serialize(doc);
}

String SDPMessage::buildData(const char* id, uint32_t seq, uint32_t ts, float distanceCm) {
  JsonDocument doc;
  doc["cmd"] = "DATA";
  doc["id"] = id;
  doc["seq"] = seq;
  doc["ts"] = ts;
  if (isnan(distanceCm)) {
    doc["distance_cm"] = nullptr;
    doc["err"] = "NO_ECHO";
  } else {
    doc["distance_cm"] = roundf(distanceCm * 10.0f) / 10.0f;  // 1 decimal
  }
  return serialize(doc);
}

String SDPMessage::buildAck(const char* id, uint32_t seq) {
  JsonDocument doc;
  doc["cmd"] = "ACK";
  doc["id"] = id;
  doc["seq"] = seq;
  return serialize(doc);
}

String SDPMessage::buildPing(const char* id, uint32_t seq, uint32_t ts) {
  JsonDocument doc;
  doc["cmd"] = "PING";
  doc["id"] = id;
  doc["seq"] = seq;
  doc["ts"] = ts;
  return serialize(doc);
}

bool SDPMessage::parse(const String& line, JsonDocument& doc) {
  DeserializationError error = deserializeJson(doc, line);
  return !error;
}
