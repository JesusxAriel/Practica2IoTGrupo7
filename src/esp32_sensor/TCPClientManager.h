#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>
#include <WiFi.h>

/**
 * Cliente TCP del protocolo SDP.
 *
 * Se encarga de: conectar al servidor, registrarse (INIT / INIT_ACK), enviar
 * PING y vigilar el PONG, reconectar con espera creciente (1, 2, 4, 5 s) y
 * leer lineas JSON sin bloquear. INIT_ACK y PONG se consumen internamente;
 * el resto de mensajes se entrega a la aplicacion con receive().
 *
 * Uso en loop():
 *   tcp.update();
 *   while (tcp.receive(doc)) { ... }
 */
class TCPClientManager {
 public:
  TCPClientManager(const char* serverIp, uint16_t serverPort,
                   const char* clientId, const char* clientType);

  void begin();

  /** Mantiene la conexion y los temporizadores. Llamar en cada loop(). */
  void update();

  /**
   * Lee del socket (sin bloquear). Devuelve true cuando hay un mensaje de
   * aplicacion en doc (por ejemplo SET_STATE o ERROR). Llamar hasta que
   * devuelva false.
   */
  bool receive(JsonDocument& doc);

  /** Envia una linea JSON (agrega '\n'). Solo si ya se completo el registro. */
  bool sendLine(const String& json);

  /** true si hay conexion TCP y el servidor respondio INIT_ACK. */
  bool isReady() const { return state_ == State::READY; }

 private:
  enum class State { DISCONNECTED, WAIT_INIT_ACK, READY };

  static const unsigned long kBackoffMinMs = 1000;
  static const unsigned long kBackoffMaxMs = 5000;
  static const unsigned long kConnectTimeoutMs = 2000;
  static const unsigned long kInitAckTimeoutMs = 5000;
  static const unsigned long kPingPeriodMs = 5000;
  static const unsigned long kPongTimeoutMs = 15000;
  static const size_t kMaxLineBytes = 256;

  void tryConnect();
  void drop(const char* reason);
  bool writeLine(const String& json);

  const char* serverIp_;
  uint16_t serverPort_;
  const char* clientId_;
  const char* clientType_;

  WiFiClient client_;
  State state_;
  String rxBuffer_;
  bool discarding_;
  bool attemptNow_;
  unsigned long backoffMs_;
  unsigned long lastAttemptMs_;
  unsigned long connectedAtMs_;
  unsigned long lastPingMs_;
  unsigned long lastPongMs_;
  uint32_t pingSeq_;
};
