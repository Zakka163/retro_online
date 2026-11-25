"""HTTP REST API and Signaling Handler for Arcade Online Launcher."""

import base64
import json
import os
import shutil
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional, Dict, Any, Tuple

from .room_store import RoomStore
from .signaling import SignalingHub
from .relay import RelayServer
from .device_store import DeviceStore
from .rom_store import RomStore
from .dashboard import DASHBOARD_HTML, list_vps_logs, read_vps_log, read_update_manifest


class ArcadeAPIHandler(BaseHTTPRequestHandler):
    """HTTP REST Handler for Matchmaking, Signaling, and Relay session requests."""

    # Dependency injection properties set by ArcadeServer
    store: RoomStore = None  # type: ignore
    signaling: SignalingHub = None  # type: ignore
    device_store: Optional[DeviceStore] = None
    rom_store: Optional[RomStore] = None
    relay: Optional[RelayServer] = None
    public_relay_host: str = "127.0.0.1"
    server_version: str = "1.0.0"
    updates_dir: str = os.environ.get("ARCADE_UPDATES_DIR") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "updates")
    )
    logs_dir: str = os.environ.get("ARCADE_LOGS_DIR") or (
        "/root/log_testing" if os.path.isdir("/root/log_testing") else os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "log_testing")
        )
    )
    admin_user: str = os.environ.get("ARCADE_ADMIN_USER", "admin")
    admin_pass: str = os.environ.get("ARCADE_ADMIN_PASS", "arcade2026")

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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
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

    def _require_admin_auth(self) -> bool:
        """Verify HTTP Basic Auth for /admin and /api/admin/* endpoints."""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth[6:].strip()).decode("utf-8")
                user, pwd = decoded.split(":", 1)
                if user == self.admin_user and pwd == self.admin_pass:
                    return True
            except Exception:
                pass
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("WWW-Authenticate", 'Basic realm="Arcade Online Admin"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Authentication required")
        return False

    def do_OPTIONS(self) -> None:
        """Support CORS pre-flight."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Host-Token, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = urllib.parse.parse_qs(parsed.query)

        # GET /api/roms/manifest & /api/roms/file/{filename}
        if path == "/api/roms/manifest":
            data = self.rom_store.get_manifest() if self.rom_store else {"games": [], "deleted": []}
            self._send_json(HTTPStatus.OK, data)
            return

        if path.startswith("/api/roms/file/"):
            fname = urllib.parse.unquote(path[len("/api/roms/file/"):])
            fpath = self.rom_store.get_file_path(fname) if self.rom_store else None
            if not fpath:
                self._send_error(HTTPStatus.NOT_FOUND, "ROM_NOT_FOUND", "ROM file not found")
                return
            size = os.path.getsize(fpath)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(size))
            self.send_header("Content-Disposition", f'attachment; filename="{os.path.basename(fpath)}"')
            self.end_headers()
            with open(fpath, "rb") as rf:
                shutil.copyfileobj(rf, self.wfile)
            return

        # GET /api/health
        if path == "/api/health":
            self._send_json(HTTPStatus.OK, {
                "status": "online",
                "version": self.server_version,
                "online_players": self.store.count_online_players() if self.store else 0,
                "timestamp": time.time()
            })
            return

        # GET /api/version
        if path == "/api/version":
            manifest_path = os.path.join(self.updates_dir, "manifest.json")
            if os.path.isfile(manifest_path):
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                    manifest.setdefault("update_available", True)
                    self._send_json(HTTPStatus.OK, manifest)
                    return
                except Exception as e:
                    self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "MANIFEST_ERROR", str(e))
                    return
            self._send_json(HTTPStatus.OK, {
                "update_available": False,
                "version": self.server_version,
            })
            return

        # GET /api/update/bundle
        if path == "/api/update/bundle":
            manifest_path = os.path.join(self.updates_dir, "manifest.json")
            if not os.path.isfile(manifest_path):
                self._send_error(HTTPStatus.NOT_FOUND, "NO_UPDATE_BUNDLE", "No update bundle published")
                return
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                filename = os.path.basename(str(manifest.get("filename", "")))
                bundle_path = os.path.join(self.updates_dir, filename)
                if not filename or not os.path.isfile(bundle_path):
                    self._send_error(HTTPStatus.NOT_FOUND, "BUNDLE_MISSING", "Update bundle file not found")
                    return
                size = os.path.getsize(bundle_path)
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/gzip")
                self.send_header("Content-Length", str(size))
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.end_headers()
                with open(bundle_path, "rb") as bf:
                    shutil.copyfileobj(bf, self.wfile)
            except Exception as e:
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "BUNDLE_READ_ERROR", str(e))
            return

        # GET /admin/logout
        if path == "/admin/logout":
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.send_header("WWW-Authenticate", 'Basic realm="Arcade Online Admin"')
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Logged out")
            return

        # GET /admin
        if path == "/admin":
            if not self._require_admin_auth():
                return
            html_bytes = DASHBOARD_HTML.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_bytes)))
            self.end_headers()
            self.wfile.write(html_bytes)
            return

        # GET /api/admin/*
        if path.startswith("/api/admin"):
            if not self._require_admin_auth():
                return
            if path == "/api/admin/overview":
                devices = self.device_store.list_devices() if self.device_store else []
                rooms = self.store.list_rooms(status=None) if self.store else []
                self._send_json(HTTPStatus.OK, {
                    "server_version": self.server_version,
                    "devices_total": len(devices),
                    "devices_online": sum(1 for d in devices if d.get("online")),
                    "rooms_active": len(rooms),
                    "update": read_update_manifest(self.updates_dir),
                })
                return
            if path == "/api/admin/devices":
                devices = self.device_store.list_devices() if self.device_store else []
                self._send_json(HTTPStatus.OK, {"devices": devices})
                return
            if path == "/api/admin/games":
                games = self.device_store.get_games_summary() if self.device_store else []
                self._send_json(HTTPStatus.OK, {"games": games})
                return
            if path == "/api/admin/roms":
                roms = self.rom_store.list_games() if self.rom_store else []
                self._send_json(HTTPStatus.OK, {"roms": roms})
                return
            if path == "/api/admin/logs":
                self._send_json(HTTPStatus.OK, {"logs": list_vps_logs(self.logs_dir)})
                return
            parts_adm = path.split("/")
            if len(parts_adm) == 5 and parts_adm[3] == "logs":
                fname = urllib.parse.unquote(parts_adm[4])
                if query.get("download", ["0"])[0] == "1":
                    safe = os.path.basename(fname)
                    full = os.path.join(self.logs_dir, safe)
                    if not safe.endswith(".log") or not os.path.isfile(full):
                        self._send_error(HTTPStatus.NOT_FOUND, "LOG_NOT_FOUND", "Log file not found")
                        return
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(os.path.getsize(full)))
                    self.send_header("Content-Disposition", f'attachment; filename="{safe}"')
                    self.end_headers()
                    with open(full, "rb") as lf:
                        shutil.copyfileobj(lf, self.wfile)
                    return
                errors_only = query.get("errors_only", ["0"])[0] == "1"
                data = read_vps_log(self.logs_dir, fname, errors_only=errors_only)
                if not data:
                    self._send_error(HTTPStatus.NOT_FOUND, "LOG_NOT_FOUND", "Log file not found")
                    return
                self._send_json(HTTPStatus.OK, data)
                return

        # GET /api/rooms
        if path == "/api/rooms":
            game_id = query.get("game_id", [None])[0]
            status = query.get("status", ["waiting"])[0]
            if status == "all":
                status = None
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
        query = urllib.parse.parse_qs(parsed.query)

        # POST /api/admin/roms/upload?filename=...&display_name=...&core=...
        if path == "/api/admin/roms/upload":
            if not self._require_admin_auth():
                return
            if not self.rom_store:
                self._send_error(HTTPStatus.SERVICE_UNAVAILABLE, "NO_ROM_STORE", "RomStore not initialized")
                return
            filename = query.get("filename", [""])[0]
            display_name = query.get("display_name", [""])[0]
            core = query.get("core", ["fbneo"])[0]
            content_len = int(self.headers.get("Content-Length", 0))
            if not filename or content_len <= 0:
                self._send_error(HTTPStatus.BAD_REQUEST, "INVALID_UPLOAD", "File and filename are required")
                return
            try:
                entry = self.rom_store.save_uploaded_rom(
                    filename=filename,
                    stream=self.rfile,
                    content_len=content_len,
                    display_name=display_name,
                    core=core,
                )
                self._send_json(HTTPStatus.CREATED, {"ok": True, "rom": entry})
            except Exception as e:
                self._send_error(HTTPStatus.BAD_REQUEST, "UPLOAD_FAILED", str(e))
            return

        body = self._read_json_body()
        if body is None:
            self._send_error(HTTPStatus.BAD_REQUEST, "INVALID_JSON", "Request body is not valid JSON")
            return

        # POST /api/devices/heartbeat
        if path == "/api/devices/heartbeat":
            if not self.device_store:
                self._send_json(HTTPStatus.OK, {"ok": True, "commands": []})
                return
            machine_id = str(body.get("machine_id") or body.get("hostname") or body.get("player_name") or "").strip()
            player_name = str(body.get("player_name") or machine_id or "Unknown").strip()
            if not machine_id:
                self._send_error(HTTPStatus.BAD_REQUEST, "MISSING_MACHINE_ID", "machine_id is required")
                return
            cmds = self.device_store.upsert_heartbeat(
                machine_id=machine_id,
                player_name=player_name,
                hostname=str(body.get("hostname", "")),
                ip_local=str(body.get("ip_local", "")),
                ip_public=str(self.client_address[0] if self.client_address else ""),
                os_info=str(body.get("os_info", "")),
                launcher_version=str(body.get("launcher_version", "")),
                wifi_signal=str(body.get("wifi_signal", "")),
                status=str(body.get("status", "idle")),
                current_game=str(body.get("current_game", "")),
                games=body.get("games") if isinstance(body.get("games"), list) else None,
                config=body.get("config") if isinstance(body.get("config"), dict) else None,
            )
            self._send_json(HTTPStatus.OK, {"ok": True, "commands": cmds})
            return

        # POST /api/admin/devices/{id}/command
        parts_cmd = path.split("/")
        if len(parts_cmd) == 6 and parts_cmd[1] == "api" and parts_cmd[2] == "admin" and parts_cmd[3] == "devices" and parts_cmd[5] == "command":
            if not self._require_admin_auth():
                return
            if not self.device_store:
                self._send_error(HTTPStatus.SERVICE_UNAVAILABLE, "NO_DEVICE_STORE", "DeviceStore not initialized")
                return
            machine_id = urllib.parse.unquote(parts_cmd[4])
            command = str(body.get("command", "")).strip()
            if not command:
                self._send_error(HTTPStatus.BAD_REQUEST, "MISSING_COMMAND", "command is required")
                return
            cmd_id = self.device_store.queue_command(
                machine_id=machine_id,
                command=command,
                payload=body.get("payload") if isinstance(body.get("payload"), dict) else {},
            )
            self._send_json(HTTPStatus.OK, {"ok": True, "command_id": cmd_id})
            return

        # POST /api/admin/updates/publish
        if path == "/api/admin/updates/publish":
            if not self._require_admin_auth():
                return
            ver = str(body.get("version", "")).strip()
            notes = str(body.get("notes", "")).strip()
            if not ver:
                self._send_error(HTTPStatus.BAD_REQUEST, "MISSING_VERSION", "version is required")
                return
            os.makedirs(self.updates_dir, exist_ok=True)
            manifest_path = os.path.join(self.updates_dir, "manifest.json")
            manifest: Dict[str, Any] = {}
            if os.path.isfile(manifest_path):
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                except Exception:
                    manifest = {}
            manifest["update_available"] = True
            manifest["version"] = ver
            manifest["notes"] = notes
            manifest["released_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
                f.write("\n")

            notified = 0
            if self.device_store:
                for dev in self.device_store.list_devices():
                    if dev.get("online"):
                        self.device_store.queue_command(dev["machine_id"], "check_update", {})
                        notified += 1
            self._send_json(HTTPStatus.OK, {"ok": True, "manifest": manifest, "notified": notified})
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

    def do_PUT(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        parts = path.split("/")
        if len(parts) == 5 and parts[1] == "api" and parts[2] == "admin" and parts[3] == "roms":
            if not self._require_admin_auth():
                return
            if not self.rom_store:
                self._send_error(HTTPStatus.SERVICE_UNAVAILABLE, "NO_ROM_STORE", "RomStore not initialized")
                return
            body = self._read_json_body() or {}
            fname = urllib.parse.unquote(parts[4])
            updated = self.rom_store.update_game(
                filename=fname,
                display_name=body.get("display_name"),
                core=body.get("core"),
            )
            if not updated:
                self._send_error(HTTPStatus.NOT_FOUND, "ROM_NOT_FOUND", "Game not found")
                return
            self._send_json(HTTPStatus.OK, {"ok": True, "rom": updated})
            return
        self._send_error(HTTPStatus.NOT_FOUND, "ENDPOINT_NOT_FOUND", "Requested endpoint does not exist")

    def do_DELETE(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        parts = path.split("/")

        if len(parts) == 5 and parts[1] == "api" and parts[2] == "admin" and parts[3] == "devices":
            if not self._require_admin_auth():
                return
            if not self.device_store:
                self._send_error(HTTPStatus.SERVICE_UNAVAILABLE, "NO_DEVICE_STORE", "DeviceStore not initialized")
                return
            mid = urllib.parse.unquote(parts[4])
            ok = self.device_store.delete_device(mid)
            self._send_json(HTTPStatus.OK, {"ok": ok})
            return

        if len(parts) == 5 and parts[1] == "api" and parts[2] == "admin" and parts[3] == "roms":
            if not self._require_admin_auth():
                return
            if not self.rom_store:
                self._send_error(HTTPStatus.SERVICE_UNAVAILABLE, "NO_ROM_STORE", "RomStore not initialized")
                return
            fname = urllib.parse.unquote(parts[4])
            ok = self.rom_store.delete_game(fname)
            self._send_json(HTTPStatus.OK, {"ok": ok})
            return

        if len(parts) == 5 and parts[1] == "api" and parts[2] == "admin" and parts[3] == "rooms":
            if not self._require_admin_auth():
                return
            room_id = parts[4]
            room = self.store.get_room(room_id)
            if not room:
                self._send_error(HTTPStatus.NOT_FOUND, "ROOM_NOT_FOUND", "Room not found")
                return
            ok = self.store.close_room(room_id, room.host_token)
            if ok:
                self.signaling.send_event(
                    room_id=room_id,
                    sender_id="server",
                    event="room.closed",
                    payload={"room_id": room_id}
                )
            self._send_json(HTTPStatus.OK, {"ok": ok})
            return

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
                self._send_json(HTTPStatus.OK, {"ok": True, "message": "Room closed"})
            else:
                self._send_error(HTTPStatus.FORBIDDEN, "FORBIDDEN", "Invalid host token or room already closed")
            return

        self._send_error(HTTPStatus.NOT_FOUND, "ENDPOINT_NOT_FOUND", "Requested endpoint does not exist")


class ArcadeServer:
    """Combines Matchmaking REST API, Signaling Hub, and Netplay Relay."""

    def __init__(self, http_host: str = "0.0.0.0", http_port: int = 8080,
                 relay_port: int = 55436, public_relay_host: str = "127.0.0.1",
                 updates_dir: Optional[str] = None, db_path: Optional[str] = None,
                 logs_dir: Optional[str] = None, roms_dir: Optional[str] = None):
        self.http_host = http_host
        self.http_port = http_port
        self.relay_port = relay_port
        self.public_relay_host = public_relay_host
        self.updates_dir = updates_dir or os.environ.get("ARCADE_UPDATES_DIR") or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "updates")
        )
        self.logs_dir = logs_dir or os.environ.get("ARCADE_LOGS_DIR") or (
            "/root/log_testing" if os.path.isdir("/root/log_testing") else os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "log_testing")
            )
        )
        self.roms_dir = roms_dir or os.environ.get("ARCADE_ROMS_DIR") or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "roms_repo")
        )

        self.store = RoomStore()
        self.signaling = SignalingHub()
        self.device_store = DeviceStore(db_path=db_path)
        self.rom_store = RomStore(roms_dir=self.roms_dir)
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
        ConfiguredHandler.device_store = self.device_store
        ConfiguredHandler.rom_store = self.rom_store
        ConfiguredHandler.relay = self.relay
        ConfiguredHandler.public_relay_host = self.public_relay_host
        ConfiguredHandler.updates_dir = self.updates_dir
        ConfiguredHandler.logs_dir = self.logs_dir

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

