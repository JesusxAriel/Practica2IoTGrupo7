"""Protocolo de aplicacion SmartDistance Protocol (SDP) v1.

Cada mensaje es un objeto JSON en una sola linea (UTF-8) terminada en ``\\n``.
Este modulo solo conoce el formato de los mensajes: no abre sockets ni toma
decisiones de control.
"""

import json
import math
from typing import Any, Dict, Optional

MAX_LINE_BYTES = 256
ENCODING = "utf-8"
PROTOCOL_VERSION = 1


class ProtocolError(Exception):
    """Mensaje que no cumple SDP. ``code`` es el codigo que se envia en ERROR."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


class Protocol:
    """Codifica, decodifica y valida mensajes SDP."""

    CLIENT_TYPES = ("SENSOR", "ACTUATOR")

    # Campos obligatorios de los mensajes que envian los clientes.
    _REQUIRED_FIELDS = {
        "INIT": ("type", "id"),
        "DATA": ("id", "seq", "ts", "distance_cm"),
        "ACK": ("id", "seq"),
        "PING": ("id", "seq"),
    }

    # ------------------------------------------------------------------ #
    # Decodificacion (cliente -> servidor)
    # ------------------------------------------------------------------ #
    @classmethod
    def decode(cls, raw: bytes) -> Dict[str, Any]:
        """Convierte una linea recibida en un diccionario validado.

        Raises:
            ProtocolError: con el codigo BAD_JSON, UNKNOWN_CMD o MISSING_FIELD.
        """
        try:
            text = raw.decode(ENCODING).strip()
        except UnicodeDecodeError:
            raise ProtocolError("BAD_JSON", "la linea no es UTF-8 valido") from None

        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            raise ProtocolError("BAD_JSON", "linea no valida") from None

        if not isinstance(message, dict):
            raise ProtocolError("BAD_JSON", "se esperaba un objeto JSON")

        cmd = message.get("cmd")
        if not isinstance(cmd, str) or cmd not in cls._REQUIRED_FIELDS:
            raise ProtocolError("UNKNOWN_CMD", f"comando desconocido: {cmd!r}")

        missing = [f for f in cls._REQUIRED_FIELDS[cmd] if f not in message]
        if missing:
            raise ProtocolError("MISSING_FIELD", f"faltan campos: {', '.join(missing)}")

        cls._validate_types(message)
        return message

    @classmethod
    def _validate_types(cls, message: Dict[str, Any]) -> None:
        cmd = message["cmd"]
        client_id = message["id"]
        if not isinstance(client_id, str) or not client_id:
            raise ProtocolError("BAD_JSON", "id debe ser un texto no vacio")

        if cmd == "INIT" and message["type"] not in cls.CLIENT_TYPES:
            raise ProtocolError("BAD_JSON", "type debe ser SENSOR o ACTUATOR")

        if cmd in ("DATA", "ACK", "PING") and not _is_int(message["seq"]):
            raise ProtocolError("BAD_JSON", "seq debe ser un entero")

        if cmd == "DATA":
            if not _is_int(message["ts"]):
                raise ProtocolError("BAD_JSON", "ts debe ser un entero")
            distance = message["distance_cm"]
            if distance is not None and not _is_number(distance):
                raise ProtocolError("BAD_JSON", "distance_cm debe ser numero o null")

    # ------------------------------------------------------------------ #
    # Construccion de mensajes (servidor -> cliente)
    # ------------------------------------------------------------------ #
    @staticmethod
    def init_ack(client_id: str) -> Dict[str, Any]:
        return {"cmd": "INIT_ACK", "id": client_id, "status": "OK"}

    @staticmethod
    def set_state(seq: int, range_name: str, profile: Dict[str, Any]) -> Dict[str, Any]:
        message: Dict[str, Any] = {"cmd": "SET_STATE", "seq": seq, "range": range_name}
        message.update(profile)
        return message

    @staticmethod
    def pong(seq: int) -> Dict[str, Any]:
        return {"cmd": "PONG", "seq": seq}

    @staticmethod
    def error(code: str, text: str) -> Dict[str, Any]:
        return {"cmd": "ERROR", "code": code, "msg": text}

    @staticmethod
    def encode(message: Dict[str, Any]) -> bytes:
        """Serializa un mensaje a una linea JSON compacta terminada en ``\\n``."""
        return (json.dumps(message, separators=(",", ":")) + "\n").encode(ENCODING)


def format_distance(distance_cm: Optional[float]) -> str:
    """Texto legible de una distancia para logs."""
    return "null" if distance_cm is None else f"{distance_cm:.1f}"
