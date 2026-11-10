"""Connection Manager: Direct-First, Relay-Fallback Strategy.

Implements Section 6 of the spec:
1. Candidate exchange over signaling channel.
2. Direct connection probe with configurable timeout.
3. Transparent fallback to authenticated TCP Relay if direct probe fails.
4. Step-by-step progress callbacks for user-friendly UI connection screen.
"""

import os
import time
import socket
import logging
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict, Any, Callable, List

from .client_api import ArcadeClientAPI
from server.relay import LocalRelayBridge

logger = logging.getLogger("Arcade.Connection")

# Standard user-facing error messages from spec Section 11
ERROR_MESSAGES = {
    "SERVICE_UNAVAILABLE": "Layanan online sedang tidak tersedia",
    "ROOM_FULL": "Room sudah penuh",
    "GAME_MISMATCH": "Versi game tidak cocok",
    "CORE_MISMATCH": "Sistem game belum kompatibel",
    "DIRECT_TIMEOUT": "Menyiapkan jalur koneksi alternatif...",
    "RELAY_UNAVAILABLE": "Koneksi online belum tersedia",
    "NETPLAY_HANDSHAKE_FAILED": "Gagal memulai permainan",
    "PEER_DISCONNECTED": "Lawan terputus dari permainan",
}


@dataclass
class ConnectionProgressStep:
    """Checklist item for Section 4.6 UI."""
    index: int
    label: str
    status: str  # 'pending', 'active', 'completed', 'failed'


@dataclass
class ConnectionResult:
    """Outcome of connection negotiation."""
    success: bool
    mode: str = "direct"            # 'direct' or 'relay'
    target_ip: str = "127.0.0.1"    # Host IP for RetroArch --connect
    target_port: int = 55435        # Port for RetroArch
    local_bridge: Optional[LocalRelayBridge] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    steps: List[ConnectionProgressStep] = field(default_factory=list)


def get_local_ip() -> str:
    """Determine local network IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class ConnectionManager:
    """Coordinates direct P2P connectivity and Relay fallback."""

    def __init__(self, api: ArcadeClientAPI,
                 direct_timeout: float = 3.0,
                 overall_timeout: float = 20.0):
        self.api = api
        self.direct_timeout = direct_timeout
        self.overall_timeout = overall_timeout

    def _init_steps(self) -> List[ConnectionProgressStep]:
        return [
            ConnectionProgressStep(0, "Menemukan room", "pending"),
            ConnectionProgressStep(1, "Memeriksa game", "pending"),
            ConnectionProgressStep(2, "Memeriksa kompatibilitas", "pending"),
            ConnectionProgressStep(3, "Membangun koneksi langsung", "pending"),
            ConnectionProgressStep(4, "Menyiapkan jalur alternatif", "pending"),
            ConnectionProgressStep(5, "Menjalankan permainan", "pending"),
        ]

    def _update_step(self, steps: List[ConnectionProgressStep],
                     step_idx: int, status: str,
                     on_progress: Optional[Callable[[List[ConnectionProgressStep]], None]]) -> None:
        if 0 <= step_idx < len(steps):
            steps[step_idx].status = status
            if on_progress:
                on_progress(steps)

    def negotiate_as_host(self, room_id: str, host_id: str, host_token: str,
                          netplay_port: int = 55435,
                          on_progress: Optional[Callable[[List[ConnectionProgressStep]], None]] = None) -> ConnectionResult:
        """Host flow: publish candidate, wait for client, fall back to relay if needed."""
        steps = self._init_steps()
        self._update_step(steps, 0, "completed", on_progress)
        self._update_step(steps, 1, "completed", on_progress)
        self._update_step(steps, 2, "completed", on_progress)

        is_mock = bool(os.environ.get("ARCADE_MOCK_RETROARCH"))
        if is_mock:
            self._update_step(steps, 3, "completed", on_progress)
            self._update_step(steps, 5, "completed", on_progress)
            return ConnectionResult(
                success=True,
                mode="direct",
                target_ip="127.0.0.1",
                target_port=netplay_port,
                steps=steps
            )

        self._update_step(steps, 3, "active", on_progress)

        # 1. Open temporary probe listener so Client can verify TCP reachability
        probe_sock = None
        try:
            probe_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            probe_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                import struct
                # Avoid TIME_WAIT on netplay_port when probe socket closes
                probe_sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
            except Exception:
                pass
            probe_sock.bind(("0.0.0.0", netplay_port))
            probe_sock.listen(1)
            probe_sock.setblocking(False)
        except Exception as e:
            logger.debug(f"Probe socket bind on {netplay_port} skipped: {e}")
            probe_sock = None

        # Broadcast Host candidate IP and port
        local_ip = get_local_ip()
        logger.info(f"[Host] Memulai negosiasi koneksi room {room_id}. Kandidat IP lokal: {local_ip}:{netplay_port}")
        self.api.send_signal(
            room_id=room_id,
            sender_id=host_id,
            event="connection.candidate",
            payload={"ip": local_ip, "port": netplay_port}
        )

        # 2. Wait for client response
        start_time = time.time()
        last_poll = time.time()
        bridge = None

        try:
            while (time.time() - start_time) < self.overall_timeout:
                # Check if client pinged our temporary probe listener
                if probe_sock:
                    try:
                        conn, client_addr = probe_sock.accept()
                        try:
                            import struct
                            conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                        except Exception:
                            pass
                        conn.close()
                        logger.info(f"[Host] Probe langsung dari Client diterima dari {client_addr}! Mode: DIRECT P2P.")
                        self.api.send_signal(room_id, host_id, "connection.direct_success")
                        self._update_step(steps, 3, "completed", on_progress)
                        self._update_step(steps, 5, "completed", on_progress)
                        return ConnectionResult(
                            success=True,
                            mode="direct",
                            target_ip=local_ip,
                            target_port=netplay_port,
                            steps=steps
                        )
                    except (BlockingIOError, InterruptedError):
                        pass
                    except Exception:
                        pass

                messages = self.api.poll_signals(room_id, host_id, since=last_poll, timeout=1.5)
                last_poll = time.time()

                for msg in messages:
                    event = msg.get("event")
                    if event == "connection.direct_success":
                        logger.info(f"[Host] Sinyal direct_success diterima dari Client! Mode: DIRECT P2P.")
                        self._update_step(steps, 3, "completed", on_progress)
                        self._update_step(steps, 5, "completed", on_progress)
                        return ConnectionResult(
                            success=True,
                            mode="direct",
                            target_ip=local_ip,
                            target_port=netplay_port,
                            steps=steps
                        )

                    if event == "connection.relay_required":
                        logger.warning(f"[Host] Client gagal probe langsung. Mengaktifkan FALLBACK TCP RELAY...")
                        self._update_step(steps, 3, "failed", on_progress)
                        self._update_step(steps, 4, "active", on_progress)

                        # Obtain relay session
                        ok, relay_info = self.api.request_relay(room_id, host_token)
                        if not ok:
                            logger.error(f"[Host] Gagal mengalokasikan sesi relay!")
                            self._update_step(steps, 4, "failed", on_progress)
                            return ConnectionResult(
                                success=False,
                                error_code="RELAY_UNAVAILABLE",
                                error_message=ERROR_MESSAGES["RELAY_UNAVAILABLE"],
                                steps=steps
                            )

                        logger.info(f"[Host] Membuka Local Relay Bridge ke {relay_info['relay_host']}:{relay_info['relay_port']} (Session: {relay_info['relay_session_id']})")
                        # Start Host Local Relay Bridge to bridge local RetroArch port to VPS
                        bridge = LocalRelayBridge(
                            relay_host=relay_info["relay_host"],
                            relay_port=relay_info["relay_port"],
                            session_id=relay_info["relay_session_id"],
                            token=relay_info["relay_token"],
                            role="HOST",
                            local_target_port=netplay_port
                        )
                        bridge.start()

                        self._update_step(steps, 4, "completed", on_progress)
                        self._update_step(steps, 5, "completed", on_progress)
                        return ConnectionResult(
                            success=True,
                            mode="relay",
                            target_ip="127.0.0.1",
                            target_port=netplay_port,
                            local_bridge=bridge,
                            steps=steps
                        )

                time.sleep(0.2)
        finally:
            if probe_sock:
                try:
                    probe_sock.close()
                except Exception:
                    pass

        return ConnectionResult(
            success=False,
            error_code="DIRECT_TIMEOUT",
            error_message=ERROR_MESSAGES["DIRECT_TIMEOUT"],
            steps=steps
        )

    def negotiate_as_client(self, room_id: str, client_id: str, client_token: str,
                            on_progress: Optional[Callable[[List[ConnectionProgressStep]], None]] = None) -> ConnectionResult:
        """Client flow: discover host candidate, test direct connection, fallback to relay."""
        steps = self._init_steps()
        self._update_step(steps, 0, "completed", on_progress)
        self._update_step(steps, 1, "completed", on_progress)
        self._update_step(steps, 2, "completed", on_progress)

        is_mock = bool(os.environ.get("ARCADE_MOCK_RETROARCH"))
        if is_mock:
            self._update_step(steps, 3, "completed", on_progress)
            self._update_step(steps, 5, "completed", on_progress)
            return ConnectionResult(
                success=True,
                mode="direct",
                target_ip="127.0.0.1",
                target_port=55435,
                steps=steps
            )

        self._update_step(steps, 3, "active", on_progress)

        # 1. Discover host candidate IP & port
        logger.info(f"[Client] Memulai negosiasi koneksi room {room_id}...")
        start_time = time.time()
        host_candidate = None
        last_poll = time.time() - 30.0  # include initial history

        while (time.time() - start_time) < (self.overall_timeout / 2):
            messages = self.api.poll_signals(room_id, client_id, since=last_poll, timeout=2.0)
            last_poll = time.time()
            for msg in messages:
                if msg.get("event") == "connection.candidate":
                    host_candidate = msg.get("payload")
                    break
            if host_candidate:
                break
            time.sleep(0.3)

        if not host_candidate:
            logger.error("[Client] Gagal menemukan kandidat IP dari Host!")
            self._update_step(steps, 3, "failed", on_progress)
            return ConnectionResult(
                success=False,
                error_code="PEER_DISCONNECTED",
                error_message=ERROR_MESSAGES["PEER_DISCONNECTED"],
                steps=steps
            )

        host_ip = host_candidate.get("ip")
        host_port = int(host_candidate.get("port", 55435))
        logger.info(f"[Client] Kandidat Host ditemukan: {host_ip}:{host_port}")

        # 2. Probe direct connection
        direct_ok = False
        target_connect_ip = host_ip
        candidate_ips = [host_ip]
        local_my_ip = get_local_ip()
        if (host_ip == local_my_ip or host_ip.startswith("192.168.") or host_ip.startswith("10.")) and "127.0.0.1" not in candidate_ips:
            candidate_ips.append("127.0.0.1")

        logger.info(f"[Client] Menguji probe koneksi langsung ke: {candidate_ips} (timeout: {self.direct_timeout}s)...")
        for cand_ip in candidate_ips:
            try:
                probe_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                probe_sock.settimeout(self.direct_timeout)
                probe_sock.connect((cand_ip, host_port))
                probe_sock.close()
                direct_ok = True
                target_connect_ip = cand_ip
                logger.info(f"[Client] Probe langsung ke {cand_ip}:{host_port} BERHASIL! Mode: DIRECT P2P.")
                break
            except Exception as e:
                logger.debug(f"[Client] Probe ke {cand_ip}:{host_port} gagal: {e}")
                direct_ok = False

        if direct_ok:
            # Direct connection succeeded!
            self.api.send_signal(room_id, client_id, "connection.direct_success")
            self._update_step(steps, 3, "completed", on_progress)
            self._update_step(steps, 5, "completed", on_progress)
            return ConnectionResult(
                success=True,
                mode="direct",
                target_ip=target_connect_ip,
                target_port=host_port,
                steps=steps
            )

        # 3. Direct probe failed / timed out -> Fall back to Relay
        logger.warning("[Client] Probe koneksi langsung gagal/timeout. Beralih ke FALLBACK TCP RELAY...")
        self._update_step(steps, 3, "failed", on_progress)
        self._update_step(steps, 4, "active", on_progress)
        self.api.send_signal(room_id, client_id, "connection.relay_required")

        ok, relay_info = self.api.request_relay(room_id, client_token)
        if not ok:
            logger.error("[Client] Gagal meminta alokasi relay proxy!")
            self._update_step(steps, 4, "failed", on_progress)
            return ConnectionResult(
                success=False,
                error_code="RELAY_UNAVAILABLE",
                error_message=ERROR_MESSAGES["RELAY_UNAVAILABLE"],
                steps=steps
            )

        # Choose an ephemeral local port for Client's local bridge
        local_client_port = 55438
        logger.info(f"[Client] Membuka Local Relay Bridge pada port {local_client_port} -> Relay {relay_info['relay_host']}:{relay_info['relay_port']}")
        bridge = LocalRelayBridge(
            relay_host=relay_info["relay_host"],
            relay_port=relay_info["relay_port"],
            session_id=relay_info["relay_session_id"],
            token=relay_info["relay_token"],
            role="CLIENT",
            local_target_port=local_client_port
        )
        bridge.start()

        self._update_step(steps, 4, "completed", on_progress)
        self._update_step(steps, 5, "completed", on_progress)
        return ConnectionResult(
            success=True,
            mode="relay",
            target_ip="127.0.0.1",
            target_port=local_client_port,
            local_bridge=bridge,
            steps=steps
        )

