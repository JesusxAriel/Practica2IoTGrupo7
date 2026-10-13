"""Servidor TCP: acepta conexiones, atiende un hilo por cliente y aplica SDP."""

import socket
import threading
from typing import Any, Dict, List, Optional, Tuple

from protocol import MAX_LINE_BYTES, Protocol, ProtocolError, format_distance


class ClientRegistry:
    """Mapa seguro entre hilos de id de cliente -> sesion activa."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: Dict[str, "ClientSession"] = {}

    def register(self, session: "ClientSession") -> Optional["ClientSession"]:
        """Registra la sesion y devuelve la anterior con el mismo id (si habia)."""
        with self._lock:
            previous = self._sessions.get(session.client_id)
            self._sessions[session.client_id] = session
            return previous

    def remove(self, session: "ClientSession") -> bool:
        """Quita la sesion. Devuelve True solo si era la sesion vigente de ese id."""
        with self._lock:
            if self._sessions.get(session.client_id) is session:
                del self._sessions[session.client_id]
                return True
            return False

    def sessions_of_type(self, client_type: str) -> List["ClientSession"]:
        with self._lock:
            return [s for s in self._sessions.values() if s.client_type == client_type]

    def all_sessions(self) -> List["ClientSession"]:
        with self._lock:
            return list(self._sessions.values())


class ClientSession(threading.Thread):
    """Atiende a un cliente conectado (sensor o actuador) en su propio hilo."""

    def __init__(
        self,
        sock: socket.socket,
        address: Tuple[str, int],
        registry: ClientRegistry,
        engine: Any,
        logger: Any,
    ) -> None:
        super().__init__(name=f"client-{address[0]}:{address[1]}", daemon=True)
        self._sock = sock
        self._address = address
        self._registry = registry
        self._engine = engine
        self._logger = logger
        self._rfile = sock.makefile("rb")
        self._send_lock = threading.Lock()
        self._close_lock = threading.Lock()
        self._closed = False
        self.client_id: Optional[str] = None
        self.client_type: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Ciclo de vida
    # ------------------------------------------------------------------ #
    def run(self) -> None:
        self._logger.log("CONNECT", detail=f"{self._address[0]}:{self._address[1]}")
        reason = "conexion cerrada por el cliente"
        try:
            while True:
                line = self._rfile.readline(MAX_LINE_BYTES + 1)
                if not line:
                    break
                if not line.endswith(b"\n"):
                    if len(line) > MAX_LINE_BYTES:
                        self._reject("LINE_TOO_LONG", "linea mayor a 256 bytes")
                        self._discard_rest_of_line()
                        continue
                    break  # el cliente cerro con una linea incompleta
                self._handle_line(line)
        except socket.timeout:
            reason = "sin mensajes por mas de 15 s"
        except OSError as exc:
            reason = f"error de socket: {exc}"
        finally:
            self._cleanup(reason)

    def close(self) -> None:
        """Cierra el socket (idempotente). Desbloquea la lectura del hilo."""
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        for action in (lambda: self._sock.shutdown(socket.SHUT_RDWR), self._sock.close):
            try:
                action()
            except OSError:
                pass

    def send(self, message: Dict[str, Any]) -> bool:
        """Envia un mensaje. Devuelve False (y cierra la sesion) si falla."""
        data = Protocol.encode(message)
        try:
            with self._send_lock:
                self._sock.sendall(data)
            return True
        except OSError:
            self.close()
            return False

    def _cleanup(self, reason: str) -> None:
        self.close()
        try:
            self._rfile.close()
        except OSError:
            pass
        if self.client_id is None:
            self._logger.log("DISCONNECT", detail=reason)
            return
        was_current = self._registry.remove(self)
        self._logger.log("DISCONNECT", self.client_id, detail=reason)
        if was_current and self.client_type == "SENSOR":
            self._engine.on_sensor_disconnected()

    def _discard_rest_of_line(self) -> None:
        while True:
            chunk = self._rfile.readline(MAX_LINE_BYTES)
            if not chunk or chunk.endswith(b"\n"):
                return

    # ------------------------------------------------------------------ #
    # Manejo de mensajes
    # ------------------------------------------------------------------ #
    def _handle_line(self, line: bytes) -> None:
        try:
            message = Protocol.decode(line)
        except ProtocolError as exc:
            self._reject(exc.code, exc.message)
            return

        cmd = message["cmd"]
        if cmd == "INIT":
            self._handle_init(message)
            return
        if self.client_id is None:
            self._reject("NOT_REGISTERED", "enviar INIT primero")
            return
        if message["id"] != self.client_id:
            self._reject("NOT_REGISTERED", "el id no coincide con el registrado")
            return

        if cmd == "DATA":
            self._handle_data(message)
        elif cmd == "ACK":
            self._handle_ack(message)
        elif cmd == "PING":
            self.send(Protocol.pong(message["seq"]))

    def _handle_init(self, message: Dict[str, Any]) -> None:
        if self.client_id is not None:
            self._reject("UNKNOWN_CMD", "la sesion ya esta registrada")
            return
        self.client_id = message["id"]
        self.client_type = message["type"]
        previous = self._registry.register(self)
        if previous is not None:
            self._logger.log("SESSION_REPLACED", self.client_id, detail="se cierra la sesion anterior")
            previous.close()
        self._logger.log("REGISTER", self.client_id, detail=self.client_type)
        self.send(Protocol.init_ack(self.client_id))
        if self.client_type == "ACTUATOR":
            self._engine.on_actuator_connected(self)

    def _handle_data(self, message: Dict[str, Any]) -> None:
        if self.client_type != "SENSOR":
            self._reject("UNKNOWN_CMD", "solo el sensor puede enviar DATA")
            return
        distance = message["distance_cm"]
        detail = f"distance_cm={format_distance(distance)}"
        if "err" in message:
            detail += f" err={message['err']}"
        self._logger.log("DATA", self.client_id, message["seq"], detail)
        self._engine.on_data(self.client_id, message["seq"], distance)

    def _handle_ack(self, message: Dict[str, Any]) -> None:
        if self.client_type != "ACTUATOR":
            self._reject("UNKNOWN_CMD", "solo el actuador puede enviar ACK")
            return
        self._engine.on_ack(self.client_id, message["seq"])

    def _reject(self, code: str, text: str) -> None:
        self._logger.log("ERROR_SENT", self.client_id or "", detail=f"{code}: {text}")
        self.send(Protocol.error(code, text))


class TCPServer:
    """Escucha en un puerto TCP y crea una ClientSession por conexion."""

    def __init__(
        self,
        host: str,
        port: int,
        registry: ClientRegistry,
        engine: Any,
        logger: Any,
        idle_timeout_s: float = 15.0,
    ) -> None:
        self._registry = registry
        self._engine = engine
        self._logger = logger
        self._idle_timeout_s = idle_timeout_s
        self._stop = threading.Event()
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind((host, port))
        self._listener.listen(8)
        self._listener.settimeout(1.0)
        self.port = self._listener.getsockname()[1]  # util cuando port=0

    def serve_forever(self) -> None:
        self._logger.log("SERVER_START", detail=f"puerto {self.port}")
        while not self._stop.is_set():
            try:
                conn, address = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # baja latencia
            conn.settimeout(self._idle_timeout_s)
            ClientSession(conn, address, self._registry, self._engine, self._logger).start()
        self._logger.log("SERVER_STOP")

    def stop(self) -> None:
        self._stop.set()
        try:
            self._listener.close()
        except OSError:
            pass
        for session in self._registry.all_sessions():
            session.close()
