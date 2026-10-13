"""Punto de entrada del servidor SDP.

Uso:
    python main.py [--host 0.0.0.0] [--port 5050] [--log-dir logs]
                   [--sensor-timeout 3.0] [--quiet]
"""

import argparse
import socket

from control_engine import ControlEngine
from event_logger import EventLogger
from tcp_server import ClientRegistry, TCPServer


def guess_local_ip() -> str:
    """IP local probable de la PC (la que debe ir en SERVER_IP de los ESP32)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))  # no envia datos; solo elige la interfaz
            return probe.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "desconocida"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Servidor SmartDistance Protocol (SDP)")
    parser.add_argument("--host", default="0.0.0.0", help="interfaz de escucha")
    parser.add_argument("--port", type=int, default=5050, help="puerto TCP")
    parser.add_argument("--log-dir", default="logs", help="carpeta de los CSV de eventos")
    parser.add_argument("--sensor-timeout", type=float, default=3.0,
                        help="segundos sin lectura valida antes de entrar a FAULT")
    parser.add_argument("--quiet", action="store_true", help="no imprimir eventos en consola")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logger = EventLogger(args.log_dir, console=not args.quiet)
    registry = ClientRegistry()
    engine = ControlEngine(registry, logger, sensor_timeout_s=args.sensor_timeout)
    server = TCPServer(args.host, args.port, registry, engine, logger)

    print(f"Servidor SDP escuchando en {args.host}:{server.port}")
    print(f"IP local probable (SERVER_IP de los ESP32): {guess_local_ip()}")
    print(f"Log de eventos: {logger.path}")
    print("Ctrl+C para detener.")

    engine.start_watchdog()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDeteniendo servidor...")
    finally:
        server.stop()
        engine.stop()
        logger.close()


if __name__ == "__main__":
    main()
