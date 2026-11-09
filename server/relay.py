"""High-Performance TCP Netplay Relay Service.

Provides authenticated, bidirectional TCP stream forwarding between Host and Client
when direct P2P connections are obstructed by CGNAT or symmetric firewalls.
Enforces TCP_NODELAY, session tokens, activity timeouts, and bandwidth observability.
"""

import socket
import select
import threading
import time
import uuid
import logging
from typing import Dict, Optional, Tuple, Any

logger = logging.getLogger("Arcade.Relay")


class RelaySession:
    """Manages an active relay bridge for a matched room pair."""

    def __init__(self, session_id: str, room_id: str, token: str, max_duration: float = 7200.0,
                 reconnect_timeout: float = 15.0):
        self.session_id = session_id
        self.room_id = room_id
        self.token = token
        self.max_duration = max_duration
        self.reconnect_timeout = reconnect_timeout
        self.created_at = time.time()
        self.status = "waiting"  # 'waiting', 'bridged', 'reconnecting', 'closed'

        self.host_sock: Optional[socket.socket] = None
        self.client_sock: Optional[socket.socket] = None

        self.pending_to_host = bytearray()
        self.pending_to_client = bytearray()

        self.bytes_host_to_client = 0
        self.bytes_client_to_host = 0
        self.last_activity = time.time()
        self._close_event = threading.Event()
        self._disconnect_start: Optional[float] = None

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.max_duration

    def close(self) -> None:
        """Close all sockets associated with this relay session."""
        self.status = "closed"
        self._close_event.set()

        for sock in (self.host_sock, self.client_sock):
            if sock:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    sock.close()
                except Exception:
                    pass

        self.host_sock = None
        self.client_sock = None


class RelayServer:
    """Standalone TCP Relay Server for RetroArch Netplay sessions."""

    def __init__(self, host: str = "0.0.0.0", port: int = 55436, timeout: float = 30.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sessions: Dict[str, RelaySession] = {}
        self._lock = threading.RLock()
        self._running = False
        self._server_sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None

    def allocate_session(self, room_id: str) -> Tuple[str, str]:
        """Generate a new authorized relay session and secret token."""
        with self._lock:
            session_id = uuid.uuid4().hex[:12]
            token = uuid.uuid4().hex
            session = RelaySession(session_id=session_id, room_id=room_id, token=token)
            self.sessions[session_id] = session
            return session_id, token

    def get_session(self, session_id: str) -> Optional[RelaySession]:
        with self._lock:
            return self.sessions.get(session_id)

    def start(self) -> None:
        """Start listening for incoming relay connections."""
        self._running = True
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.port))
        self._server_sock.listen(50)

        # Retrieve actual bound port if port 0 was passed
        self.port = self._server_sock.getsockname()[1]

        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()
        logger.info(f"Relay server listening on {self.host}:{self.port}")

    def stop(self) -> None:
        """Shut down the relay server and active sessions."""
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass

        with self._lock:
            for s in list(self.sessions.values()):
                s.close()
            self.sessions.clear()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _accept_loop(self) -> None:
        while self._running:
            try:
                conn, addr = self._server_sock.accept()
                threading.Thread(target=self._handle_handshake, args=(conn, addr), daemon=True).start()
            except Exception:
                if not self._running:
                    break

    def _handle_handshake(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        """Process authentication handshake: ARCADE_RELAY <session_id> <token> <ROLE>."""
        try:
            conn.settimeout(10.0)
            # Read handshake line terminated by newline
            data = b""
            while b"\n" not in data and len(data) < 256:
                chunk = conn.recv(64)
                if not chunk:
                    break
                data += chunk

            line = data.decode("utf-8", errors="ignore").strip()
            parts = line.split()

            if len(parts) != 4 or parts[0] != "ARCADE_RELAY":
                conn.sendall(b"ERR INVALID_PROTOCOL\n")
                conn.close()
                return

            _, session_id, token, role = parts
            role = role.upper()

            with self._lock:
                session = self.sessions.get(session_id)
                if not session or session.token != token or session.status == "closed":
                    conn.sendall(b"ERR INVALID_AUTH\n")
                    conn.close()
                    return

                # Reset timeout so the socket does not time out while waiting for the other player
                conn.settimeout(None)

                # Configure socket for reliable, low-latency streaming
                try:
                    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    conn.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)
                    conn.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 262144)
                except OSError:
                    pass

                is_reconnect = False
                if role == "HOST":
                    if session.host_sock:
                        is_reconnect = True
                        try:
                            session.host_sock.close()
                        except Exception:
                            pass
                    session.host_sock = conn
                elif role == "CLIENT":
                    if session.client_sock:
                        is_reconnect = True
                        try:
                            session.client_sock.close()
                        except Exception:
                            pass
                    session.client_sock = conn
                else:
                    conn.sendall(b"ERR UNKNOWN_ROLE\n")
                    conn.close()
                    return

                # If this is a reconnect during an active or reconnecting session
                if is_reconnect or session.status in ("bridged", "reconnecting"):
                    conn.sendall(b"OK CONNECTED\n")
                    if role == "HOST" and session.pending_to_host:
                        try:
                            conn.sendall(bytes(session.pending_to_host))
                            session.pending_to_host.clear()
                        except Exception:
                            pass
                    elif role == "CLIENT" and session.pending_to_client:
                        try:
                            conn.sendall(bytes(session.pending_to_client))
                            session.pending_to_client.clear()
                        except Exception:
                            pass
                    session.status = "bridged"
                    session._disconnect_start = None
                    logger.info(f"[RelayServer] {role} berhasil RECONNECT untuk room {session.room_id}")
                    return

                # If both sides are now present for the first time, initiate bidirectional bridge!
                if session.host_sock and session.client_sock:
                    session.status = "bridged"
                    threading.Thread(target=self._bridge_session, args=(session,), daemon=True).start()

        except Exception as e:
            logger.debug(f"Handshake error: {e}")
            try:
                conn.close()
            except Exception:
                pass

    def _bridge_session(self, session: RelaySession) -> None:
        """Forward all traffic bidirectionally with TCP_NODELAY and reconnect tolerance."""
        h_sock = session.host_sock
        c_sock = session.client_sock
        if not h_sock or not c_sock:
            return

        try:
            for s in (h_sock, c_sock):
                s.settimeout(30.0)
                s.sendall(b"OK CONNECTED\n")

            while self._running and not session._close_event.is_set():
                h_sock = session.host_sock
                c_sock = session.client_sock

                active_sockets = [s for s in (h_sock, c_sock) if s is not None]
                if not active_sockets:
                    break

                # Check if one peer disconnected and we are in reconnect grace period
                if len(active_sockets) < 2:
                    if session._disconnect_start is None:
                        session._disconnect_start = time.time()
                    if (time.time() - session._disconnect_start) > session.reconnect_timeout:
                        logger.info(f"[RelayServer] Reconnect timeout ({session.reconnect_timeout}s) tercapai untuk room {session.room_id}.")
                        break
                else:
                    session._disconnect_start = None

                try:
                    rlist, _, _ = select.select(active_sockets, [], [], 0.5)
                except (ValueError, OSError):
                    continue

                for s in rlist:
                    is_h = (s is session.host_sock)
                    other = session.client_sock if is_h else session.host_sock
                    s_role = "HOST" if is_h else "CLIENT"

                    try:
                        data = s.recv(65536)
                        if not data:
                            logger.info(f"[RelayServer] {s_role} socket terputus (EOF) untuk room {session.room_id}. Menunggu reconnect...")
                            with self._lock:
                                if is_h:
                                    session.host_sock = None
                                else:
                                    session.client_sock = None
                                session.status = "reconnecting"
                                session._disconnect_start = time.time()
                            try:
                                s.close()
                            except Exception:
                                pass
                            break

                        session.last_activity = time.time()
                        if other:
                            other.sendall(data)
                        else:
                            # Buffer packets while the other side is reconnecting
                            buf = session.pending_to_client if is_h else session.pending_to_host
                            if len(buf) < 1048576:
                                buf.extend(data)

                        if is_h:
                            session.bytes_host_to_client += len(data)
                        else:
                            session.bytes_client_to_host += len(data)
                    except (socket.timeout, BlockingIOError, InterruptedError):
                        continue
                    except (ConnectionResetError, BrokenPipeError) as e:
                        logger.info(f"[RelayServer] {s_role} connection reset ({e}) untuk room {session.room_id}. Menunggu reconnect...")
                        with self._lock:
                            if is_h:
                                session.host_sock = None
                            else:
                                session.client_sock = None
                            session.status = "reconnecting"
                            session._disconnect_start = time.time()
                        try:
                            s.close()
                        except Exception:
                            pass
                        break
                    except Exception as e:
                        logger.warning(f"[RelayServer] Relay error pada {s_role}: {e}")
                        with self._lock:
                            if is_h:
                                session.host_sock = None
                            else:
                                session.client_sock = None
                            session.status = "reconnecting"
                            session._disconnect_start = time.time()
                        try:
                            s.close()
                        except Exception:
                            pass
                        break

        except (OSError, ValueError):
            session.close()
        except Exception as e:
            if not session._close_event.is_set():
                logger.error(f"Bridge session error: {e}")
            session.close()
        finally:
            session.close()


class LocalRelayBridge:
    """Client-side local bridge running on arcade cabinet to pipe RetroArch through Relay."""

    def __init__(self, relay_host: str, relay_port: int, session_id: str,
                 token: str, role: str, local_target_port: int,
                 reconnect_timeout: float = 15.0):
        self.relay_host = relay_host
        self.relay_port = relay_port
        self.session_id = session_id
        self.token = token
        self.role = role.upper()
        self.local_target_port = local_target_port
        self.reconnect_timeout = reconnect_timeout
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.disconnect_event = threading.Event()
        self.ready_event = threading.Event()
        self._client_listen_sock: Optional[socket.socket] = None

    def start(self) -> None:
        self._running = True
        if self.role == "CLIENT":
            try:
                self._client_listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._client_listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._client_listen_sock.bind(("127.0.0.1", self.local_target_port))
                self._client_listen_sock.listen(1)
                self._client_listen_sock.settimeout(30.0)
                logger.info(f"[LocalRelayBridge] Port listening Client {self.local_target_port} siap.")
            except Exception as e:
                logger.warning(f"[LocalRelayBridge] Pre-bind listen port {self.local_target_port} error: {e}")
        self.ready_event.set()
        self._thread = threading.Thread(target=self._run_bridge, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._client_listen_sock:
            try:
                self._client_listen_sock.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _connect_relay_socket(self, timeout: float = 8.0) -> Optional[socket.socket]:
        """Establish outbound socket to Relay Server and complete authentication."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((self.relay_host, self.relay_port))
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

            handshake = f"ARCADE_RELAY {self.session_id} {self.token} {self.role}\n"
            sock.sendall(handshake.encode("utf-8"))

            sock.settimeout(timeout)
            response = b""
            while b"\n" not in response and not self._stop_event.is_set():
                try:
                    chunk = sock.recv(64)
                    if not chunk:
                        break
                    response += chunk
                except (socket.timeout, BlockingIOError):
                    continue

            if b"OK CONNECTED" in response:
                try:
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 262144)
                except OSError:
                    pass
                sock.settimeout(30.0)
                return sock
            else:
                logger.debug(f"[LocalRelayBridge] Handshake relay ditolak / respon: {response}")
                try:
                    sock.close()
                except Exception:
                    pass
                return None
        except Exception as e:
            logger.debug(f"[LocalRelayBridge] Gagal terhubung ke relay: {e}")
            return None

    def _run_bridge(self) -> None:
        """Connect to Relay VPS, authenticate, and bridge with local socket."""
        relay_sock = None
        local_sock = None
        try:
            # 1. Handle local socket connection
            if self.role == "CLIENT":
                listen_sock = self._client_listen_sock
                if listen_sock is None:
                    listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    listen_sock.bind(("127.0.0.1", self.local_target_port))
                    listen_sock.listen(1)
                    listen_sock.settimeout(30.0)

                try:
                    logger.info(f"[LocalRelayBridge] Menunggu koneksi RetroArch Client di 127.0.0.1:{self.local_target_port}...")
                    local_sock, _ = listen_sock.accept()
                    logger.info("[LocalRelayBridge] RetroArch Client berhasil terhubung ke bridge lokal!")
                finally:
                    try:
                        listen_sock.close()
                    except Exception:
                        pass
                    self._client_listen_sock = None

            # 2. Connect to Relay Server (wait up to 60s initially for opponent)
            logger.info(f"[LocalRelayBridge] Menghubungkan ke Relay VPS {self.relay_host}:{self.relay_port}...")
            relay_sock = self._connect_relay_socket(timeout=60.0)
            if not relay_sock:
                logger.warning("[LocalRelayBridge] Handshake relay gagal atau ditutup.")
                return

            # 3. For Host: bridge connects to local RetroArch server listening on local_target_port
            if self.role == "HOST":
                connected = False
                for attempt in range(60):
                    if self._stop_event.is_set():
                        break
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.connect(("127.0.0.1", self.local_target_port))
                        local_sock = s
                        connected = True
                        logger.info(f"[LocalRelayBridge] Berhasil terhubung ke RetroArch Host lokal pada port {self.local_target_port} (percobaan ke-{attempt+1})")
                        break
                    except (ConnectionRefusedError, OSError):
                        try:
                            s.close()
                        except Exception:
                            pass
                        time.sleep(0.2)

                if not connected:
                    logger.error(f"[LocalRelayBridge] Gagal terhubung ke RetroArch Host lokal pada port {self.local_target_port} setelah 12 detik!")
                    if relay_sock:
                        relay_sock.close()
                    return

            try:
                local_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                local_sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                local_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)
                local_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 262144)
            except OSError:
                pass
            local_sock.settimeout(30.0)

            sockets = [relay_sock, local_sock]

            while self._running and not self._stop_event.is_set():
                try:
                    rlist, _, _ = select.select(sockets, [], [], 0.5)
                except (ValueError, OSError):
                    break

                for s in rlist:
                    if s is local_sock:
                        # Traffic from local RetroArch to Relay VPS
                        try:
                            data = local_sock.recv(65536)
                            if not data:
                                logger.info("[LocalRelayBridge] RetroArch lokal ditutup (EOF).")
                                self.disconnect_event.set()
                                return
                            if relay_sock:
                                relay_sock.sendall(data)
                        except (socket.timeout, BlockingIOError, InterruptedError):
                            continue
                        except (ConnectionResetError, BrokenPipeError):
                            logger.info("[LocalRelayBridge] Koneksi RetroArch lokal terputus.")
                            self.disconnect_event.set()
                            return
                        except Exception as e:
                            logger.warning(f"[LocalRelayBridge] Error pada RetroArch lokal: {e}")
                            self.disconnect_event.set()
                            return

                    elif s is relay_sock:
                        # Traffic from Relay VPS to local RetroArch
                        relay_failed = False
                        try:
                            data = relay_sock.recv(65536)
                            if not data:
                                logger.info("[LocalRelayBridge] Koneksi Relay VPS ditutup (EOF).")
                                relay_failed = True
                            else:
                                local_sock.sendall(data)
                        except (socket.timeout, BlockingIOError, InterruptedError):
                            continue
                        except (ConnectionResetError, BrokenPipeError) as e:
                            logger.info(f"[LocalRelayBridge] Koneksi Relay VPS terputus: {e}")
                            relay_failed = True
                        except Exception as e:
                            logger.warning(f"[LocalRelayBridge] Error pada Relay VPS: {e}")
                            relay_failed = True

                        if relay_failed:
                            # Do not kill local RetroArch immediately! Attempt auto-reconnect to VPS
                            try:
                                relay_sock.close()
                            except Exception:
                                pass
                            relay_sock = None

                            logger.warning(
                                f"[LocalRelayBridge] Jalur ke Relay VPS terputus. "
                                f"Mencoba reconnect otomatis (toleransi {self.reconnect_timeout}s)..."
                            )

                            reconnect_start = time.time()
                            while (
                                self._running
                                and not self._stop_event.is_set()
                                and (time.time() - reconnect_start) < self.reconnect_timeout
                            ):
                                # Check if local RetroArch is still alive during reconnect wait
                                try:
                                    r_local, _, _ = select.select([local_sock], [], [], 0.2)
                                    if r_local:
                                        peek = local_sock.recv(1, socket.MSG_PEEK)
                                        if not peek:
                                            logger.info("[LocalRelayBridge] RetroArch lokal ditutup saat reconnect.")
                                            self.disconnect_event.set()
                                            return
                                except Exception:
                                    self.disconnect_event.set()
                                    return

                                new_relay = self._connect_relay_socket(timeout=3.0)
                                if new_relay:
                                    relay_sock = new_relay
                                    sockets = [relay_sock, local_sock]
                                    logger.info("[LocalRelayBridge] Berhasil RECONNECT ke Relay VPS! Melanjutkan permainan...")
                                    break
                                time.sleep(0.5)

                            if not relay_sock:
                                logger.error(f"[LocalRelayBridge] Gagal reconnect ke Relay VPS setelah {self.reconnect_timeout}s.")
                                self.disconnect_event.set()
                                return

        except Exception as e:
            logger.debug(f"LocalRelayBridge exception: {e}")
            self.disconnect_event.set()
        finally:
            if not self._stop_event.is_set():
                self.disconnect_event.set()
            if relay_sock:
                try:
                    relay_sock.close()
                except Exception:
                    pass
            if local_sock:
                try:
                    local_sock.close()
                except Exception:
                    pass
            if self._client_listen_sock:
                try:
                    self._client_listen_sock.close()
                except Exception:
                    pass
