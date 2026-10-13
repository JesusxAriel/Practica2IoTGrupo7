"""Registro de eventos del servidor en CSV, con marcas de tiempo.

La columna ``mono_ms`` usa un reloj monotonico: la diferencia entre el evento
DATA y el evento SET_STATE_SENT es la latencia de procesamiento del servidor.
"""

import csv
import os
import threading
import time
from datetime import datetime
from typing import Any


class EventLogger:
    """Escribe eventos en ``<log_dir>/sdp_<fecha>.csv`` (seguro entre hilos)."""

    FIELDS = ["timestamp", "mono_ms", "event", "client_id", "seq", "detail"]

    def __init__(self, log_dir: str = "logs", console: bool = True) -> None:
        os.makedirs(log_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = os.path.join(log_dir, f"sdp_{stamp}.csv")
        self._file = open(self.path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow(self.FIELDS)
        self._file.flush()
        self._console = console
        self._lock = threading.Lock()

    def log(self, event: str, client_id: str = "", seq: Any = "", detail: str = "") -> None:
        now = datetime.now().isoformat(timespec="milliseconds")
        mono_ms = f"{time.monotonic() * 1000:.3f}"
        with self._lock:
            if self._file.closed:
                return
            self._writer.writerow([now, mono_ms, event, client_id, seq, detail])
            self._file.flush()
            if self._console:
                parts = [now[11:], f"{event:<14}", client_id, str(seq), detail]
                print(" ".join(p for p in parts if p != ""), flush=True)

    def close(self) -> None:
        with self._lock:
            if not self._file.closed:
                self._file.close()
