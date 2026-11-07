"""Server main entrypoint for standalone VPS deployment."""

import argparse
import logging
import signal
import sys
import time

from .api import ArcadeServer

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger("ArcadeServerApp")


def main() -> None:
    parser = argparse.ArgumentParser(description="Arcade Online Matchmaking, Signaling & Relay Server")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP API bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="HTTP API bind port (default: 8080)")
    parser.add_argument("--relay-port", type=int, default=55436, help="Relay TCP bind port (default: 55436)")
    parser.add_argument("--public-relay-host", default="auto", help="Public IP/domain for relay clients to connect to (default: auto-detected from incoming requests)")
    parser.add_argument("--no-relay", action="store_true", help="Disable embedded Netplay Relay service")

    args = parser.parse_args()

    server = ArcadeServer(
        http_host=args.host,
        http_port=args.port,
        relay_port=args.relay_port,
        public_relay_host=args.public_relay_host
    )

    def shutdown_handler(signum, frame):
        logger.info("Shutdown signal received. Stopping server...")
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    logger.info("Starting Arcade Online Server...")
    try:
        server.start(enable_relay=not args.no_relay)
    except OSError as e:
        if e.errno == 48 or "Address already in use" in str(e):
            logger.error(
                f"\n[!] GAGAL MEMULAI SERVER: Port {args.port} atau {args.relay_port} SUDAH DIGUNAKAN (Address already in use)!\n"
                f"    Kemungkinan penyebab:\n"
                f"    1. Server SUDAH BERJALAN di latar belakang (misal via Docker atau terminal lain).\n"
                f"       -> Jika sudah berjalan, Anda TIDAK PERLU menjalankannya lagi. Langsung jalankan launcher!\n"
                f"    2. Ada proses/Docker yang menduduki port 8080 atau 55436.\n"
                f"       -> Anda bisa mematikan proses lama: lsof -ti :{args.port},{args.relay_port} | xargs kill -9\n"
                f"       -> Atau jalankan di port lain: python3 -m server.app --port 8081 --relay-port 55437\n"
            )
            sys.exit(1)
        raise
    logger.info(f"API & Signaling active at http://{args.host}:{server.http_port}/api")
    if not args.no_relay:
        logger.info(f"Netplay Relay active on TCP port {args.relay_port} (public host: {args.public_relay_host})")

    logger.info("Arcade Online Server is ready for players. Press Ctrl+C to terminate.")

    while True:
        time.sleep(1.0)


if __name__ == "__main__":
    main()

