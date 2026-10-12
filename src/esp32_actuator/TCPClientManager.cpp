#include "TCPClientManager.h"

#include "SDPMessage.h"

TCPClientManager::TCPClientManager(const char* serverIp, uint16_t serverPort,
                                   const char* clientId, const char* clientType)
    : serverIp_(serverIp),
      serverPort_(serverPort),
      clientId_(clientId),
      clientType_(clientType),
      state_(State::DISCONNECTED),
      discarding_(false),
      attemptNow_(true),
      backoffMs_(kBackoffMinMs),
      lastAttemptMs_(0),
      connectedAtMs_(0),
      lastPingMs_(0),
      lastPongMs_(0),
      pingSeq_(0) {}

void TCPClientManager::begin() {
  state_ = State::DISCONNECTED;
  attemptNow_ = true;
  backoffMs_ = kBackoffMinMs;
}

void TCPClientManager::update() {
  const unsigned long now = millis();

  if (WiFi.status() != WL_CONNECTED) {
    if (state_ != State::DISCONNECTED) drop("WiFi perdido");
    return;
  }

  if (state_ == State::DISCONNECTED) {
    if (attemptNow_ || now - lastAttemptMs_ >= backoffMs_) {
      attemptNow_ = false;
      lastAttemptMs_ = now;
      tryConnect();
    }
    return;
  }

  if (!client_.connected()) {
    drop("conexion cerrada por el servidor");
    return;
  }

  if (state_ == State::WAIT_INIT_ACK && now - connectedAtMs_ > kInitAckTimeoutMs) {
    drop("sin INIT_ACK");
    return;
  }

  if (state_ == State::READY) {
    if (now - lastPongMs_ > kPongTimeoutMs) {
      drop("sin PONG del servidor");
      return;
    }
    if (now - lastPingMs_ >= kPingPeriodMs) {
      lastPingMs_ = now;
      writeLine(SDPMessage::buildPing(clientId_, pingSeq_++, now));
    }
  }
}

bool TCPClientManager::receive(JsonDocument& doc) {
  if (state_ == State::DISCONNECTED) return false;

  while (client_.available() > 0) {
    const char c = static_cast<char>(client_.read());
    if (c == '\r') continue;

    if (c != '\n') {
      if (discarding_) continue;
      if (rxBuffer_.length() >= kMaxLineBytes) {
        Serial.println(F("[TCP] Linea demasiado larga, se descarta"));
        rxBuffer_ = "";
        discarding_ = true;
      } else {
        rxBuffer_ += c;
      }
      continue;
    }

    // Fin de linea
    if (discarding_) {
      discarding_ = false;
      rxBuffer_ = "";
      continue;
    }
    const String line = rxBuffer_;
    rxBuffer_ = "";
    if (line.length() == 0) continue;

    if (!SDPMessage::parse(line, doc)) {
      Serial.println(F("[TCP] JSON invalido descartado"));
      continue;
    }

    const char* cmd = doc["cmd"] | "";
    if (strcmp(cmd, "INIT_ACK") == 0) {
      state_ = State::READY;
      lastPingMs_ = millis();
      lastPongMs_ = millis();
      Serial.println(F("[TCP] Registrado en el servidor (INIT_ACK)"));
      continue;
    }
    if (strcmp(cmd, "PONG") == 0) {
      lastPongMs_ = millis();
      continue;
    }
    return true;  // mensaje para la aplicacion
  }
  return false;
}

bool TCPClientManager::sendLine(const String& json) {
  if (state_ != State::READY) return false;
  return writeLine(json);
}

void TCPClientManager::tryConnect() {
  Serial.print(F("[TCP] Conectando a "));
  Serial.print(serverIp_);
  Serial.print(':');
  Serial.println(serverPort_);

  if (client_.connect(serverIp_, serverPort_, kConnectTimeoutMs)) {
    client_.setNoDelay(true);  // desactiva Nagle: menor latencia
    rxBuffer_ = "";
    discarding_ = false;
    state_ = State::WAIT_INIT_ACK;
    connectedAtMs_ = millis();
    backoffMs_ = kBackoffMinMs;
    Serial.println(F("[TCP] Conectado, enviando INIT"));
    writeLine(SDPMessage::buildInit(clientType_, clientId_));
  } else {
    backoffMs_ = backoffMs_ * 2;  // 1 -> 2 -> 4 -> 5 s
    if (backoffMs_ > kBackoffMaxMs) backoffMs_ = kBackoffMaxMs;
    Serial.print(F("[TCP] Fallo, reintento en "));
    Serial.print(backoffMs_);
    Serial.println(F(" ms"));
  }
}

void TCPClientManager::drop(const char* reason) {
  Serial.print(F("[TCP] Desconectado: "));
  Serial.println(reason);
  client_.stop();
  state_ = State::DISCONNECTED;
  rxBuffer_ = "";
  discarding_ = false;
  attemptNow_ = false;
  backoffMs_ = kBackoffMinMs;
  lastAttemptMs_ = millis();  // primer reintento tras 1 s
}

bool TCPClientManager::writeLine(const String& json) {
  String out = json;
  out += '\n';
  const size_t written =
      client_.write(reinterpret_cast<const uint8_t*>(out.c_str()), out.length());
  if (written != out.length()) {
    drop("error de escritura");
    return false;
  }
  return true;
}
