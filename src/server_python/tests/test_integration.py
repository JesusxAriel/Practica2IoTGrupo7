"""Pruebas de integracion del servidor con clientes simulados (sin ESP32).

Ejecutar desde src/server_python:
    python -m unittest discover -s tests -v
"""

import json
import os
import socket
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from control_engine import ControlEngine, Range, RangeClassifier  # noqa: E402
from event_logger import EventLogger  # noqa: E402
from tcp_server import ClientRegistry, TCPServer  # noqa: E402


class FakeClient:
    """Cliente TCP minimo que habla SDP."""

    def __init__(self, port: int, client_id: str, client_type: str, register: bool = True):
        self.id = client_id
        self.type = client_type
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=3)
        self.buffer = b""
        self.seq = 0
        if register:
            self.send({"cmd": "INIT", "type": client_type, "id": client_id, "ver": 1})
            assert self.recv()["cmd"] == "INIT_ACK"

    def send(self, message: dict) -> None:
        self.sock.sendall((json.dumps(message) + "\n").encode())

    def send_raw(self, text: str) -> None:
        self.sock.sendall(text.encode())

    def recv(self, timeout: float = 2.0):
        """Siguiente mensaje JSON, o None si hay timeout o el servidor cerro."""
        self.sock.settimeout(timeout)
        while b"\n" not in self.buffer:
            try:
                chunk = self.sock.recv(4096)
            except (socket.timeout, OSError):
                return None
            if not chunk:
                return None
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b"\n", 1)
        return json.loads(line)

    def send_data(self, distance) -> None:
        self.seq += 1
        message = {"cmd": "DATA", "id": self.id, "seq": self.seq, "ts": self.seq * 300,
                   "distance_cm": distance}
        if distance is None:
            message["err"] = "NO_ECHO"
        self.send(message)

    def ack(self, state: dict) -> None:
        self.send({"cmd": "ACK", "id": self.id, "seq": state["seq"]})

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class ServerTestCase(unittest.TestCase):
    SENSOR_TIMEOUT = 1.0

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.logger = EventLogger(self.tmp.name, console=False)
        self.registry = ClientRegistry()
        self.engine = ControlEngine(self.registry, self.logger, sensor_timeout_s=self.SENSOR_TIMEOUT)
        self.server = TCPServer("127.0.0.1", 0, self.registry, self.engine, self.logger)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.engine.start_watchdog()
        self.clients = []

    def tearDown(self):
        for client in self.clients:
            client.close()
        self.server.stop()
        self.engine.stop()
        self.logger.close()
        self.tmp.cleanup()

    def connect(self, client_id, client_type, register=True):
        client = FakeClient(self.server.port, client_id, client_type, register)
        self.clients.append(client)
        return client

    def connect_pair(self):
        actuator = self.connect("ESP32_LEDS", "ACTUATOR")
        initial = actuator.recv()
        self.assertEqual(initial["range"], "FAULT")
        sensor = self.connect("ESP32_ULTRASONIC", "SENSOR")
        return sensor, actuator


class TestRangeClassifier(unittest.TestCase):
    def test_boundaries_are_contiguous_without_overlap(self):
        c = RangeClassifier()
        self.assertIs(c.classify(0.0), Range.CLOSE)
        self.assertIs(c.classify(14.9), Range.CLOSE)
        self.assertIs(c.classify(15.0), Range.MEDIUM)
        self.assertIs(c.classify(39.9), Range.MEDIUM)
        self.assertIs(c.classify(40.0), Range.FAR)
        self.assertIs(c.classify(399.0), Range.FAR)

    def test_valid_reading_limits(self):
        self.assertFalse(RangeClassifier.is_valid(None))
        self.assertFalse(RangeClassifier.is_valid(1.9))
        self.assertTrue(RangeClassifier.is_valid(2.0))
        self.assertTrue(RangeClassifier.is_valid(400.0))
        self.assertFalse(RangeClassifier.is_valid(400.1))


class TestServer(ServerTestCase):
    def test_actuator_gets_initial_fault_state(self):
        actuator = self.connect("ESP32_LEDS", "ACTUATOR", register=False)
        actuator.send({"cmd": "INIT", "type": "ACTUATOR", "id": "ESP32_LEDS", "ver": 1})
        self.assertEqual(actuator.recv()["cmd"], "INIT_ACK")
        state = actuator.recv()
        self.assertEqual(state["cmd"], "SET_STATE")
        self.assertEqual(state["range"], "FAULT")
        self.assertEqual(state["led_yellow"], "BLINK")

    def test_each_range_sends_expected_leds(self):
        sensor, actuator = self.connect_pair()
        expected = {
            8.0: ("CLOSE", "BLINK", "OFF", "OFF"),
            25.0: ("MEDIUM", "OFF", "BLINK", "OFF"),
            60.0: ("FAR", "OFF", "OFF", "ON"),
        }
        for distance, (rng, red, yellow, green) in expected.items():
            sensor.send_data(distance)
            state = actuator.recv()
            self.assertEqual(state["range"], rng)
            self.assertEqual((state["led_red"], state["led_yellow"], state["led_green"]),
                             (red, yellow, green))
            actuator.ack(state)
        self.assertEqual(state["cmd"], "SET_STATE")

    def test_boundary_values(self):
        sensor, actuator = self.connect_pair()
        # (distancia, rango esperado). Solo hay SET_STATE cuando el rango cambia.
        sequence = [(14.9, "CLOSE"), (15.0, "MEDIUM"), (39.9, "MEDIUM"), (40.0, "FAR"), (39.9, "MEDIUM")]
        current = "FAULT"
        for distance, rng in sequence:
            sensor.send_data(distance)
            if rng != current:
                self.assertEqual(actuator.recv()["range"], rng, f"distancia {distance}")
                current = rng
            else:
                self.assertIsNone(actuator.recv(timeout=0.2), f"distancia {distance}")

    def test_no_command_when_range_does_not_change(self):
        sensor, actuator = self.connect_pair()
        sensor.send_data(60.0)
        self.assertEqual(actuator.recv()["range"], "FAR")
        sensor.send_data(70.0)
        sensor.send_data(80.0)
        self.assertIsNone(actuator.recv(timeout=0.4))

    def test_invalid_readings_do_not_change_state_but_watchdog_does(self):
        sensor, actuator = self.connect_pair()
        sensor.send_data(25.0)
        self.assertEqual(actuator.recv()["range"], "MEDIUM")
        sensor.send_data(None)   # sin eco
        sensor.send_data(1.0)    # fuera de rango
        self.assertIsNone(actuator.recv(timeout=0.5))
        state = actuator.recv(timeout=3.0)  # el watchdog entra a FAULT
        self.assertEqual(state["range"], "FAULT")

    def test_sensor_disconnect_goes_to_fault_and_recovers(self):
        sensor, actuator = self.connect_pair()
        sensor.send_data(60.0)
        self.assertEqual(actuator.recv()["range"], "FAR")
        sensor.close()
        self.assertEqual(actuator.recv()["range"], "FAULT")
        sensor2 = self.connect("ESP32_ULTRASONIC", "SENSOR")
        sensor2.send_data(10.0)
        self.assertEqual(actuator.recv()["range"], "CLOSE")

    def test_reconnected_actuator_receives_current_state(self):
        sensor, actuator = self.connect_pair()
        sensor.send_data(25.0)
        self.assertEqual(actuator.recv()["range"], "MEDIUM")
        actuator.close()
        actuator2 = self.connect("ESP32_LEDS", "ACTUATOR", register=False)
        actuator2.send({"cmd": "INIT", "type": "ACTUATOR", "id": "ESP32_LEDS", "ver": 1})
        self.assertEqual(actuator2.recv()["cmd"], "INIT_ACK")
        self.assertEqual(actuator2.recv()["range"], "MEDIUM")

    def test_duplicate_id_replaces_old_session(self):
        first = self.connect("ESP32_LEDS", "ACTUATOR")
        first.recv()  # SET_STATE inicial
        second = self.connect("ESP32_LEDS", "ACTUATOR")
        self.assertEqual(second.recv()["range"], "FAULT")
        self.assertIsNone(first.recv(timeout=1.0))  # su conexion fue cerrada

    def test_ping_pong(self):
        actuator = self.connect("ESP32_LEDS", "ACTUATOR")
        actuator.recv()
        actuator.send({"cmd": "PING", "id": "ESP32_LEDS", "seq": 7, "ts": 1000})
        self.assertEqual(actuator.recv(), {"cmd": "PONG", "seq": 7})

    def test_ack_records_rtt_in_log(self):
        sensor, actuator = self.connect_pair()
        sensor.send_data(25.0)
        actuator.ack(actuator.recv())
        actuator.recv(timeout=0.3)
        with open(self.logger.path, encoding="utf-8") as handle:
            content = handle.read()
        self.assertIn("ACK_RECEIVED", content)
        self.assertIn("rtt_ms=", content)

    def test_bad_json_and_server_keeps_running(self):
        client = self.connect("X", "SENSOR", register=False)
        client.send_raw("esto no es json\n")
        self.assertEqual(client.recv()["code"], "BAD_JSON")
        client.send({"cmd": "INIT", "type": "SENSOR", "id": "X", "ver": 1})
        self.assertEqual(client.recv()["cmd"], "INIT_ACK")

    def test_error_codes(self):
        client = self.connect("X", "SENSOR", register=False)
        client.send({"cmd": "DATA", "id": "X", "seq": 1, "ts": 1, "distance_cm": 10})
        self.assertEqual(client.recv()["code"], "NOT_REGISTERED")
        client.send({"cmd": "HOLA"})
        self.assertEqual(client.recv()["code"], "UNKNOWN_CMD")
        client.send({"cmd": "INIT", "type": "SENSOR"})
        self.assertEqual(client.recv()["code"], "MISSING_FIELD")
        client.send_raw("{" + "a" * 400 + "}\n")
        self.assertEqual(client.recv()["code"], "LINE_TOO_LONG")
        client.send({"cmd": "INIT", "type": "SENSOR", "id": "X", "ver": 1})
        self.assertEqual(client.recv()["cmd"], "INIT_ACK")


if __name__ == "__main__":
    unittest.main()
