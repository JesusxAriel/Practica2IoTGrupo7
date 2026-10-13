"""Algoritmo de control: clasificacion de rangos y decision de comandos."""

import threading
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional

from protocol import Protocol, format_distance


class Range(Enum):
    """Estado del sistema. FAULT no es un rango de distancia: es un estado seguro."""

    FAULT = "FAULT"
    CLOSE = "CLOSE"
    MEDIUM = "MEDIUM"
    FAR = "FAR"


# Comportamiento de los LEDs para cada estado (parte del mensaje SET_STATE).


LED_PROFILES: Dict[Range, Dict[str, Any]] = {
    Range.CLOSE: {
        "led_red": "BLINK",
        "led_yellow": "OFF",
        "led_green": "OFF",
        "blink_ms": 150,
    },
    Range.MEDIUM: {
        "led_red": "OFF",
        "led_yellow": "BLINK",
        "led_green": "OFF",
        "blink_ms": 500,
    },
    Range.FAR: {
        "led_red": "OFF",
        "led_yellow": "OFF",
        "led_green": "ON",
    },
    Range.FAULT: {
        "led_red": "BLINK",
        "led_yellow": "BLINK",
        "led_green": "BLINK",
        "blink_ms": 500,
    },
}


class RangeClassifier:
    """Clasifica una distancia en CLOSE, MEDIUM o FAR (intervalos [a, b))."""

    CLOSE_MAX_CM = 15.0    # CLOSE:  [0, 15)
    MEDIUM_MAX_CM = 40.0   # MEDIUM: [15, 40)  /  FAR: [40, +inf)
    MIN_VALID_CM = 2.0     # limites de lectura valida del HC-SR04
    MAX_VALID_CM = 400.0

    @classmethod
    def is_valid(cls, distance_cm: Optional[float]) -> bool:
        return distance_cm is not None and cls.MIN_VALID_CM <= distance_cm <= cls.MAX_VALID_CM

    def classify(self, distance_cm: float) -> Range:
        if distance_cm < self.CLOSE_MAX_CM:
            return Range.CLOSE
        if distance_cm < self.MEDIUM_MAX_CM:
            return Range.MEDIUM
        return Range.FAR


class ControlEngine:
    """Mantiene el estado actual y envia SET_STATE a los actuadores al cambiar.

    El estado es compartido por varios hilos (uno por cliente y el watchdog),
    por eso toda transicion y su envio se hacen bajo un mismo candado: asi los
    comandos llegan al actuador en el mismo orden en que se decidieron.
    """

    WATCHDOG_PERIOD_S = 0.5
    MAX_PENDING_ACKS = 64

    def __init__(
        self,
        registry: Any,
        logger: Any,
        sensor_timeout_s: float = 3.0,
        classifier: Optional[RangeClassifier] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._registry = registry
        self._logger = logger
        self._timeout_s = sensor_timeout_s
        self._classifier = classifier or RangeClassifier()
        self._clock = clock
        self._lock = threading.RLock()
        self._range = Range.FAULT          # estado inicial: sin informacion confiable
        self._last_valid: Optional[float] = None
        self._seq = 0
        self._pending: Dict[int, float] = {}   # seq de SET_STATE -> instante de envio
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ #
    # Estado
    # ------------------------------------------------------------------ #
    @property
    def current_range(self) -> Range:
        with self._lock:
            return self._range

    # ------------------------------------------------------------------ #
    # Eventos de entrada
    # ------------------------------------------------------------------ #
    def on_data(self, sensor_id: str, seq: int, distance_cm: Optional[float]) -> None:
        """Procesa una lectura del sensor."""
        if not RangeClassifier.is_valid(distance_cm):
            self._logger.log(
                "DATA_INVALID", sensor_id, seq, f"distance_cm={format_distance(distance_cm)}"
            )
            return
        with self._lock:
            self._last_valid = self._clock()
            self._transition_locked(self._classifier.classify(distance_cm))

    def on_actuator_connected(self, session: Any) -> None:
        """Sincroniza un actuador recien conectado con el estado actual."""
        with self._lock:
            self._send_state_locked([session])

    def on_ack(self, client_id: str, seq: int) -> None:
        """Registra el ACK de un SET_STATE y el tiempo de ida y vuelta."""
        with self._lock:
            sent_at = self._pending.pop(seq, None)
        if sent_at is None:
            self._logger.log("ACK_UNKNOWN", client_id, seq)
            return
        rtt_ms = (self._clock() - sent_at) * 1000.0
        self._logger.log("ACK_RECEIVED", client_id, seq, f"rtt_ms={rtt_ms:.1f}")

    def on_sensor_disconnected(self) -> None:
        """El sensor cerro su conexion: no hay informacion confiable."""
        with self._lock:
            self._transition_locked(Range.FAULT, reason="sensor desconectado")

    def check_watchdog(self) -> None:
        """Pasa a FAULT si no hay lecturas validas desde hace mas del timeout."""
        with self._lock:
            if self._range is Range.FAULT:
                return
            silent = self._last_valid is None or (self._clock() - self._last_valid) > self._timeout_s
            if silent:
                self._transition_locked(Range.FAULT, reason="sin lecturas validas")

    # ------------------------------------------------------------------ #
    # Watchdog
    # ------------------------------------------------------------------ #
    def start_watchdog(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._watchdog_loop, name="watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _watchdog_loop(self) -> None:
        while not self._stop.wait(self.WATCHDOG_PERIOD_S):
            self.check_watchdog()

    # ------------------------------------------------------------------ #
    # Internos (se llaman con el candado tomado)
    # ------------------------------------------------------------------ #
    def _transition_locked(self, new_range: Range, reason: str = "") -> None:
        if new_range is self._range:
            return
        old = self._range
        self._range = new_range
        self._logger.log("STATE_CHANGE", seq="", detail=f"{old.value}->{new_range.value} {reason}".strip())
        self._send_state_locked(self._registry.sessions_of_type("ACTUATOR"))

    def _send_state_locked(self, sessions: Any) -> None:
        self._seq += 1
        message = Protocol.set_state(self._seq, self._range.value, LED_PROFILES[self._range])
        for session in sessions:
            self._pending[self._seq] = self._clock()
            while len(self._pending) > self.MAX_PENDING_ACKS:
                self._pending.pop(next(iter(self._pending)))
            if session.send(message):
                self._logger.log("SET_STATE_SENT", session.client_id or "", self._seq, self._range.value)
