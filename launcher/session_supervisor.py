"""Active Netplay Session Supervisor.

Supervises live RetroArch Netplay gameplay between Host and Client.
Monitors room status, peer heartbeat, signaling events, and relay health.
Automatically terminates the local RetroArch emulator if the peer disconnects,
leaves the room, closes the game, or drops connection, ensuring both players
are synchronized and returned cleanly to the launcher.
"""

import time
import threading
import logging
from typing import Optional, Callable, Dict, Any

from .client_api import ArcadeClientAPI
from .retroarch_controller import RetroArchController
from server.relay import LocalRelayBridge

logger = logging.getLogger("Arcade.Supervisor")


class SessionSupervisor:
    """Monitors live Netplay session and enforces mutual disconnection."""

    def __init__(self, api: ArcadeClientAPI, room_id: str, player_id: str,
                 token: str, role: str, ra_controller: RetroArchController,
                 local_bridge: Optional[LocalRelayBridge] = None,
                 poll_interval: float = 1.0,
                 max_network_failures: int = 5,
                 on_disconnect: Optional[Callable[[str], None]] = None):
        self.api = api
        self.room_id = room_id
        self.player_id = player_id
        self.token = token
        self.role = role.lower()  # 'host' or 'client'
        self.ra_controller = ra_controller
        self.local_bridge = local_bridge
        self.poll_interval = poll_interval
        self.max_network_failures = max_network_failures
        self.on_disconnect = on_disconnect

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.peer_disconnected = False
        self.disconnect_reason: Optional[str] = None
        self._last_poll = time.time()
        self._network_failure_count = 0

    def start(self) -> None:
        """Start the supervisor background thread."""
        self._stop_event.clear()
        self.peer_disconnected = False
        self.disconnect_reason = None
        self._last_poll = time.time()
        self._network_failure_count = 0
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.debug(f"SessionSupervisor aktif untuk room {self.room_id} (role={self.role})")

    def stop(self) -> None:
        """Stop the supervisor background thread."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logger.debug(f"SessionSupervisor dinonaktifkan untuk room {self.room_id}")

    def _trigger_disconnect(self, reason: str) -> None:
        """Handle peer disconnect: terminate local game and set flags."""
        if self.peer_disconnected or self._stop_event.is_set():
            return

        self.peer_disconnected = True
        self.disconnect_reason = reason
        logger.warning(f"[MUTUAL DISCONNECT] {reason} Menghentikan emulator lokal...")

        try:
            self.ra_controller.terminate()
        except Exception as e:
            logger.debug(f"Error terminating RetroArch: {e}")

        if self.on_disconnect:
            try:
                self.on_disconnect(reason)
            except Exception:
                pass

        self._stop_event.set()

    def _run_loop(self) -> None:
        """Periodic background supervision loop."""
        # Wait up to 5 seconds for active_process to appear if not already present
        process_appeared = (self.ra_controller.active_process is not None)
        if not process_appeared:
            for _ in range(50):
                if self._stop_event.is_set():
                    return
                if self.ra_controller.active_process is not None:
                    process_appeared = True
                    break
                self._stop_event.wait(0.1)

        while not self._stop_event.is_set():
            # 1. Check if local RetroArch process exited on its own
            proc = self.ra_controller.active_process
            if process_appeared and proc is not None and proc.poll() is not None:
                # Local player closed the emulator normally
                logger.debug("Proses RetroArch lokal telah selesai.")
                return

            # 2. Check LocalRelayBridge health if in Relay mode
            if self.local_bridge and hasattr(self.local_bridge, "disconnect_event"):
                if self.local_bridge.disconnect_event.is_set():
                    self._trigger_disconnect("Jalur koneksi Relay Netplay terputus.")
                    return

            # 3. Send heartbeat to server to keep room alive (using resilient timeout)
            network_call_failed = False
            try:
                hb_ok = self.api.send_heartbeat(self.room_id, self.player_id, self.token,
                                                 timeout=3.0, raise_on_error=True)
                if not hb_ok:
                    # Heartbeat explicitly rejected by server (e.g. 404 Room expired or 403 token invalid)
                    try:
                        room = self.api.get_room(self.room_id, timeout=3.0, raise_on_error=True)
                        if room is None:
                            self._trigger_disconnect("Room di server telah ditutup oleh lawan atau kedaluwarsa.")
                            return
                    except Exception:
                        network_call_failed = True
            except Exception as e:
                logger.debug(f"Heartbeat check exception: {e}")
                network_call_failed = True

            # 4. Check room state and peer presence on server
            try:
                room = self.api.get_room(self.room_id, timeout=3.0, raise_on_error=True)
                if room is None:
                    self._trigger_disconnect("Room telah ditutup atau lawan keluar.")
                    return

                # Reset failure counter on successful server response
                self._network_failure_count = 0

                if self.role == "host":
                    # Host checks if Client is still in the room and active
                    has_client = room.get("has_client", False)
                    status = room.get("status", "")
                    client_active = room.get("client_active", True)

                    if not has_client or status == "waiting":
                        self._trigger_disconnect("Lawan (Client) telah meninggalkan permainan.")
                        return
                    if not client_active:
                        self._trigger_disconnect("Koneksi lawan (Client) terputus di tengah permainan (timeout).")
                        return
                    if status in ("closed", "finished"):
                        self._trigger_disconnect("Sesi permainan telah ditutup.")
                        return

                elif self.role == "client":
                    # Client checks if room is closed or host is inactive
                    status = room.get("status", "")
                    host_active = room.get("host_active", True)

                    if not host_active:
                        self._trigger_disconnect("Koneksi lawan (Host) terputus di tengah permainan (timeout).")
                        return
                    if status in ("closed", "finished"):
                        self._trigger_disconnect("Host telah menutup room.")
                        return
            except Exception as e:
                logger.debug(f"Room query warning: {e}")
                network_call_failed = True

            # If local internet connection drops completely (e.g. 5 consecutive timeouts ~= 15s)
            if network_call_failed:
                self._network_failure_count += 1
                logger.warning(
                    f"Gangguan koneksi HTTP ke server ({self._network_failure_count}/{self.max_network_failures}). "
                    f"Mencoba mempertahankan sesi..."
                )
                if self._network_failure_count >= self.max_network_failures:
                    self._trigger_disconnect("Koneksi internet Anda terputus di tengah permainan.")
                    return
            else:
                self._network_failure_count = 0

            # 5. Poll signaling messages for immediate disconnect events
            try:
                signals = self.api.poll_signals(self.room_id, self.player_id,
                                                 since=self._last_poll, timeout=0.1)
                self._last_poll = time.time()
                for s in signals:
                    event = s.get("event")
                    if event in ("peer.left", "room.closed", "session.terminated"):
                        reason = s.get("payload", {}).get("reason", "Lawan keluar dari permainan.")
                        self._trigger_disconnect(f"Pemberitahuan: {reason}")
                        return
            except Exception as e:
                logger.debug(f"Signal polling warning: {e}")

            # Wait for next poll interval or stop signal
            self._stop_event.wait(self.poll_interval)
