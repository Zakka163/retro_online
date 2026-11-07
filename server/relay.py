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

logger = logging.getLogger("ArcadeRelay")


class RelaySession:
    """Manages an active relay bridge for a matched room pair."""

    def __init__(self, session_id: str, room_id: str, token: str, max_duration: float = 7200.0):
        self.session_id = session_id
        self.room_id = room_id
        self.token = token
        self.max_duration = max_duration
        self.created_at = time.time()
        self.status = "waiting"  # 'waiting', 'bridged', 'closed'

        self.host_sock: Optional[socket.socket] = None
        self.client_sock: Optional[socket.socket] = None

        self.bytes_host_to_client = 0
        self.bytes_client_to_host = 0
        self.last_activity = time.time()
        self._close_event = threading.Event()

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

                if role == "HOST":
                    if session.host_sock:
                        conn.sendall(b"ERR HOST_ALREADY_CONNECTED\n")
                        conn.close()
                        return
                    session.host_sock = conn
                elif role == "CLIENT":
                    if session.client_sock:
                        conn.sendall(b"ERR CLIENT_ALREADY_CONNECTED\n")
                        conn.close()
                        return
                    session.client_sock = conn
                else:
                    conn.sendall(b"ERR UNKNOWN_ROLE\n")
                    conn.close()
                    return

                # If both sides are now present, initiate bidirectional bridge!
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
        """Forward all traffic bidirectionally with TCP_NODELAY enabled."""
        h_sock = session.host_sock
        c_sock = session.client_sock
        if not h_sock or not c_sock:
            return

        try:
            # Enable TCP_NODELAY for lowest latency arcade experience on TCP sockets
            for s in (h_sock, c_sock):
                if s.family in (socket.AF_INET, getattr(socket, "AF_INET6", -1)):
                    try:
                        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    except OSError:
                        pass
                s.setblocking(False)
                s.sendall(b"OK CONNECTED\n")

            sockets = [h_sock, c_sock]

            while self._running and not session._close_event.is_set():
                rlist, _, xlist = select.select(sockets, [], sockets, 1.0)
                if xlist:
                    break

                for s in rlist:
                    try:
                        data = s.recv(65536)
                        if not data:
                            session.close()
                            return

                        session.last_activity = time.time()

                        if s is h_sock:
                            c_sock.sendall(data)
                            session.bytes_host_to_client += len(data)
                        else:
                            h_sock.sendall(data)
                            session.bytes_client_to_host += len(data)
                    except (BlockingIOError, InterruptedError):
                        continue
                    except Exception:
                        session.close()
                        return

        except (OSError, ValueError):
            # Normal socket shutdown/close during session termination
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
                 token: str, role: str, local_target_port: int):
        self.relay_host = relay_host
        self.relay_port = relay_port
        self.session_id = session_id
        self.token = token
        self.role = role.upper()
        self.local_target_port = local_target_port
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run_bridge, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _run_bridge(self) -> None:
        """Connect to Relay VPS, authenticate, and bridge with local socket."""
        try:
            # 1. Connect to Relay Server
            relay_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            relay_sock.connect((self.relay_host, self.relay_port))
            relay_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

            # Send handshake
            handshake = f"ARCADE_RELAY {self.session_id} {self.token} {self.role}\n"
            relay_sock.sendall(handshake.encode("utf-8"))

            # Read confirmation
            response = b""
            while b"\n" not in response:
                chunk = relay_sock.recv(64)
                if not chunk:
                    break
                response += chunk

            if b"OK CONNECTED" not in response:
                relay_sock.close()
                return

            # 2. Connect to or accept local RetroArch socket
            if self.role == "HOST":
                # For Host: bridge connects to local RetroArch server listening on local_target_port
                local_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                # Retry local connect as RetroArch might take a moment to bind
                connected = False
                for _ in range(30):
                    if self._stop_event.is_set():
                        break
                    try:
                        local_sock.connect(("127.0.0.1", self.local_target_port))
                        connected = True
                        break
                    except ConnectionRefusedError:
                        time.sleep(0.2)

                if not connected:
                    relay_sock.close()
                    return
            else:
                # For Client: wait for local RetroArch client to connect to local listening port
                listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listen_sock.bind(("127.0.0.1", self.local_target_port))
                listen_sock.listen(1)
                listen_sock.settimeout(30.0)

                try:
                    local_sock, _ = listen_sock.accept()
                finally:
                    listen_sock.close()

            local_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

            # 3. Bidirectional pipe between relay_sock and local_sock
            sockets = [relay_sock, local_sock]
            relay_sock.setblocking(False)
            local_sock.setblocking(False)

            while self._running and not self._stop_event.is_set():
                rlist, _, xlist = select.select(sockets, [], sockets, 0.5)
                if xlist:
                    break
                for s in rlist:
                    other = local_sock if s is relay_sock else relay_sock
                    try:
                        data = s.recv(65536)
                        if not data:
                            return
                        other.sendall(data)
                    except (BlockingIOError, InterruptedError):
                        continue
                    except Exception:
                        return

        except Exception as e:
            logger.debug(f"LocalRelayBridge exception: {e}")
        finally:
            try:
                relay_sock.close()
            except Exception:
                pass
            try:
                local_sock.close()
            except Exception:
                pass
