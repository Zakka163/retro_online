"""HTTP REST API and Signaling Handler for Arcade Online Launcher."""

import json
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional, Dict, Any, Tuple

from .room_store import RoomStore
from .signaling import SignalingHub
from .relay import RelayServer


class ArcadeAPIHandler(BaseHTTPRequestHandler):
    """HTTP REST Handler for Matchmaking, Signaling, and Relay session requests."""

    # Dependency injection properties set by ArcadeServer
    store: RoomStore = None  # type: ignore
    signaling: SignalingHub = None  # type: ignore
    relay: Optional[RelayServer] = None
    public_relay_host: str = "127.0.0.1"
    server_version: str = "1.0.0"

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default HTTP access logging in console unless debugging."""
        pass

    def _send_json(self, status_code: int, data: Dict[str, Any]) -> None:
        """Send JSON response with proper headers."""
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Host-Token, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.end_headers()
        self.wfile.write(payload)

    def _send_error(self, status_code: int, code: str, message: str) -> None:
        """Send standardized error response according to spec Section 11."""
        self._send_json(status_code, {
            "error": True,
            "code": code,
            "message": message
        })

    def _read_json_body(self) -> Optional[Dict[str, Any]]:
        """Read and parse JSON request body."""
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len <= 0:
            return {}
        try:
            body = self.rfile.read(content_len).decode("utf-8")
            return json.loads(body)
        except Exception:
            return None

    def do_OPTIONS(self) -> None:
        """Support CORS pre-flight."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Host-Token, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = urllib.parse.parse_qs(parsed.query)

        # GET /api/health
        if path == "/api/health":
            self._send_json(HTTPStatus.OK, {
                "status": "online",
                "version": self.server_version,
                "online_players": self.store.count_online_players() if self.store else 0,
                "timestamp": time.time()
            })
            return

        # GET /api/rooms
        if path == "/api/rooms":
            game_id = query.get("game_id", [None])[0]
            status = query.get("status", ["waiting"])[0]
            rooms = self.store.list_rooms(game_id=game_id, status=status)
            self._send_json(HTTPStatus.OK, {
                "rooms": [r.to_dict() for r in rooms],
                "online_players": self.store.count_online_players(game_id=game_id)
            })
            return

        # GET /api/rooms/{id}
        parts = path.split("/")
        if len(parts) == 4 and parts[1] == "api" and parts[2] == "rooms":
            room_id = parts[3]
            room = self.store.get_room(room_id)
            if not room:
                self._send_error(HTTPStatus.NOT_FOUND, "ROOM_NOT_FOUND", "Room does not exist or has expired")
                return
            self._send_json(HTTPStatus.OK, {"room": room.to_dict()})
            return

        # GET /api/rooms/{id}/poll?player_id=...&since=...
        if len(parts) == 5 and parts[1] == "api" and parts[2] == "rooms" and parts[4] == "poll":
            room_id = parts[3]
            player_id = query.get("player_id", [None])[0]
            if not player_id:
                self._send_error(HTTPStatus.BAD_REQUEST, "MISSING_PLAYER_ID", "player_id query param is required")
                return

            since = float(query.get("since", [0.0])[0])
            timeout = min(float(query.get("timeout", [5.0])[0]), 15.0)

            messages = self.signaling.poll_messages(
                room_id=room_id,
                player_id=player_id,
                since_timestamp=since,
                timeout=timeout
            )
            self._send_json(HTTPStatus.OK, {
                "messages": [m.to_dict() for m in messages],
                "timestamp": time.time()
            })
            return

        self._send_error(HTTPStatus.NOT_FOUND, "ENDPOINT_NOT_FOUND", "Requested endpoint does not exist")

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        body = self._read_json_body()
        if body is None:
            self._send_error(HTTPStatus.BAD_REQUEST, "INVALID_JSON", "Request body is not valid JSON")
            return

        # POST /api/rooms
        if path == "/api/rooms":
            game_id = body.get("game_id")
            if not game_id:
                self._send_error(HTTPStatus.BAD_REQUEST, "MISSING_GAME_ID", "game_id is required")
                return

            room_name = body.get("room_name") or body.get("name")
            host_name = body.get("host_name") or "Player 1"
            compat = body.get("compatibility", {})
            visibility = body.get("visibility", "public")
            client_version = body.get("client_version", "1.0.0")

            room, host_token = self.store.create_room(
                game_id=game_id,
                name=room_name,
                host_name=host_name,
                compatibility=compat,
                visibility=visibility,
                client_version=client_version
            )

            # Auto register host into signaling channel
            self.signaling.register_peer(room.room_id, room.host.player_id)
            self.signaling.send_event(
                room_id=room.room_id,
                sender_id=room.host.player_id,
                event="room.created",
                payload={"room": room.to_dict()}
            )

            self._send_json(HTTPStatus.CREATED, {
                "room_id": room.room_id,
                "status": room.status,
                "expires_at": room.expires_at,
                "host_token": host_token,
                "player_id": room.host.player_id,
                "room": room.to_dict()
            })
            return

        parts = path.split("/")
        if len(parts) >= 4 and parts[1] == "api" and parts[2] == "rooms":
            room_id = parts[3]
            action = parts[4] if len(parts) >= 5 else None

            # POST /api/rooms/{id}/join
            if action == "join":
                player_name = body.get("player_name") or "Player 2"
                compat = body.get("compatibility", {})
                client_version = body.get("client_version", "1.0.0")

                ok, code, client_player = self.store.join_room(
                    room_id=room_id,
                    player_name=player_name,
                    compatibility=compat,
                    client_version=client_version
                )
                if not ok:
                    status_code = HTTPStatus.CONFLICT if code == "ROOM_FULL" else HTTPStatus.BAD_REQUEST
                    msg = "Room is full" if code == "ROOM_FULL" else f"Compatibility error: {code}"
                    self._send_error(status_code, code, msg)
                    return

                # Register client into signaling and notify host
                self.signaling.register_peer(room_id, client_player.player_id)
                self.signaling.send_event(
                    room_id=room_id,
                    sender_id=client_player.player_id,
                    event="room.joined",
                    payload={"client_name": client_player.name, "client_id": client_player.player_id}
                )

                room = self.store.get_room(room_id)
                self._send_json(HTTPStatus.OK, {
                    "ok": True,
                    "player_id": client_player.player_id,
                    "client_token": client_player.token,
                    "status": room.status if room else "connecting",
                    "room": room.to_dict() if room else None
                })
                return

            # POST /api/rooms/{id}/leave
            if action == "leave":
                player_id = body.get("player_id")
                token = body.get("token")
                if not player_id or not token:
                    self._send_error(HTTPStatus.BAD_REQUEST, "MISSING_CREDENTIALS", "player_id and token required")
                    return

                ok = self.store.leave_room(room_id, player_id, token)
                if ok:
                    self.signaling.send_event(
                        room_id=room_id,
                        sender_id=player_id,
                        event="peer.left",
                        payload={"player_id": player_id}
                    )
                    self.signaling.unregister_peer(room_id, player_id)
                    self._send_json(HTTPStatus.OK, {"ok": True, "message": "Left room"})
                else:
                    self._send_error(HTTPStatus.FORBIDDEN, "FORBIDDEN", "Invalid credentials or room not found")
                return

            # POST /api/rooms/{id}/heartbeat
            if action == "heartbeat":
                player_id = body.get("player_id")
                token = body.get("token")
                if not player_id or not token:
                    self._send_error(HTTPStatus.BAD_REQUEST, "MISSING_CREDENTIALS", "player_id and token required")
                    return

                ok = self.store.heartbeat(room_id, player_id, token)
                if ok:
                    self._send_json(HTTPStatus.OK, {"ok": True, "refreshed": True})
                else:
                    self._send_error(HTTPStatus.NOT_FOUND, "ROOM_NOT_FOUND", "Room not found or token invalid")
                return

            # POST /api/rooms/{id}/signal
            if action == "signal":
                sender_id = body.get("sender_id")
                event = body.get("event")
                payload = body.get("payload", {})
                target_id = body.get("target_id")

                if not sender_id or not event:
                    self._send_error(HTTPStatus.BAD_REQUEST, "MISSING_FIELDS", "sender_id and event required")
                    return

                msg = self.signaling.send_event(
                    room_id=room_id,
                    sender_id=sender_id,
                    event=event,
                    payload=payload,
                    target_id=target_id
                )
                self._send_json(HTTPStatus.OK, {"ok": True, "message": msg.to_dict()})
                return

            # POST /api/rooms/{id}/relay
            if action == "relay":
                token = body.get("token")
                room = self.store.get_room(room_id)
                if not room:
                    self._send_error(HTTPStatus.NOT_FOUND, "ROOM_NOT_FOUND", "Room not found")
                    return

                # Verify token belongs to host or client of this room
                is_authorized = (room.host.token == token) or (room.client and room.client.token == token)
                if not is_authorized:
                    self._send_error(HTTPStatus.FORBIDDEN, "FORBIDDEN", "Unauthorized relay session request")
                    return

                if not self.relay:
                    self._send_error(HTTPStatus.SERVICE_UNAVAILABLE, "RELAY_UNAVAILABLE", "Relay service not running")
                    return

                # Allocate or retrieve existing relay session for this room
                if not room.relay_session_id or not self.relay.get_session(room.relay_session_id):
                    session_id, relay_token = self.relay.allocate_session(room_id=room_id)
                    room.relay_session_id = session_id
                    room.connection_mode = "relay"
                else:
                    session = self.relay.get_session(room.relay_session_id)
                    session_id = session.session_id
                    relay_token = session.token

                # Determine relay host: prefer explicit config, or auto-detect from client's incoming Host header
                relay_host = self.public_relay_host
                host_header = self.headers.get("Host", "").split(":")[0]
                if (relay_host in ("127.0.0.1", "0.0.0.0", "auto", "") and host_header and host_header not in ("localhost", "127.0.0.1")):
                    relay_host = host_header

                self._send_json(HTTPStatus.OK, {
                    "ok": True,
                    "relay_session_id": session_id,
                    "relay_token": relay_token,
                    "relay_host": relay_host,
                    "relay_port": self.relay.port
                })
                return

        self._send_error(HTTPStatus.NOT_FOUND, "ENDPOINT_NOT_FOUND", "Requested endpoint does not exist")

    def do_DELETE(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        parts = path.split("/")

        if len(parts) == 4 and parts[1] == "api" and parts[2] == "rooms":
            room_id = parts[3]
            host_token = self.headers.get("X-Host-Token")
            if not host_token:
                body = self._read_json_body() or {}
                host_token = body.get("host_token")

            if not host_token:
                self._send_error(HTTPStatus.BAD_REQUEST, "MISSING_TOKEN", "host_token required to close room")
                return

            ok = self.store.close_room(room_id, host_token)
            if ok:
                self.signaling.send_event(
                    room_id=room_id,
                    sender_id="server",
                    event="room.closed",
                    payload={"room_id": room_id}
                )
                self.signaling.clear_room(room_id)
                self._send_json(HTTPStatus.OK, {"ok": True, "message": "Room closed"})
            else:
                self._send_error(HTTPStatus.FORBIDDEN, "FORBIDDEN", "Invalid host token or room already closed")
            return

        self._send_error(HTTPStatus.NOT_FOUND, "ENDPOINT_NOT_FOUND", "Requested endpoint does not exist")


class ArcadeServer:
    """Combines Matchmaking REST API, Signaling Hub, and Netplay Relay."""

    def __init__(self, http_host: str = "0.0.0.0", http_port: int = 8080,
                 relay_port: int = 55436, public_relay_host: str = "127.0.0.1"):
        self.http_host = http_host
        self.http_port = http_port
        self.relay_port = relay_port
        self.public_relay_host = public_relay_host

        self.store = RoomStore()
        self.signaling = SignalingHub()
        self.relay: Optional[RelayServer] = None
        self.httpd: Optional[ThreadingHTTPServer] = None
        self._http_thread = None

    def start(self, enable_relay: bool = True) -> None:
        """Start both HTTP and Relay services."""
        if enable_relay:
            self.relay = RelayServer(host=self.http_host, port=self.relay_port)
            self.relay.start()

        class ConfiguredHandler(ArcadeAPIHandler):
            pass

        ConfiguredHandler.store = self.store
        ConfiguredHandler.signaling = self.signaling
        ConfiguredHandler.relay = self.relay
        ConfiguredHandler.public_relay_host = self.public_relay_host

        self.httpd = ThreadingHTTPServer((self.http_host, self.http_port), ConfiguredHandler)
        self.http_port = self.httpd.server_port

        import threading
        self._http_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._http_thread.start()

    def stop(self) -> None:
        """Stop all running services cleanly."""
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
        if self.relay:
            self.relay.stop()

