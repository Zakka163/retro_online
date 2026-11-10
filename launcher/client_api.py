"""Client HTTP and Signaling API driver for Arcade Online Launcher."""

import json
import time
import logging
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional, Dict, Any, List, Tuple

logger = logging.getLogger("Arcade.ClientAPI")


class ArcadeClientAPI:
    """Communicates with the Arcade Online backend Matchmaking & Signaling server."""

    def __init__(self, server_url: str = "http://localhost:8080", timeout: float = 8.0):
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        logger.debug(f"ArcadeClientAPI diinisialisasi untuk server: {self.server_url} (timeout: {self.timeout}s)")

    def _request(self, method: str, path: str,
                 body: Optional[Dict[str, Any]] = None,
                 headers: Optional[Dict[str, str]] = None,
                 timeout: Optional[float] = None) -> Tuple[int, Dict[str, Any]]:
        """Perform an HTTP request and parse JSON output."""
        url = f"{self.server_url}{path}"
        req_headers = {"User-Agent": "ArcadeOnlineLauncher/1.0"}
        if headers:
            req_headers.update(headers)

        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            req_headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)

        t0 = time.time()
        req_timeout = timeout if timeout is not None else self.timeout
        try:
            with urllib.request.urlopen(req, timeout=req_timeout) as resp:
                elapsed = (time.time() - t0) * 1000.0
                status_code = resp.status
                resp_body = resp.read().decode("utf-8")
                resp_json = json.loads(resp_body) if resp_body else {}
                logger.debug(f"HTTP {method} {path} -> {status_code} ({elapsed:.1f}ms)")
                return status_code, resp_json
        except urllib.error.HTTPError as e:
            elapsed = (time.time() - t0) * 1000.0
            err_body = e.read().decode("utf-8")
            try:
                err_json = json.loads(err_body)
            except Exception:
                err_json = {"error": True, "message": str(e), "code": "HTTP_ERROR"}
            logger.warning(f"HTTP {method} {path} -> Error {e.code} ({elapsed:.1f}ms): {err_json.get('message')}")
            return e.code, err_json
        except urllib.error.URLError as e:
            elapsed = (time.time() - t0) * 1000.0
            logger.warning(f"HTTP {method} {path} -> Network Error ({elapsed:.1f}ms): {e.reason}")
            return 503, {"error": True, "code": "SERVICE_UNAVAILABLE", "message": str(e.reason)}
        except Exception as e:
            elapsed = (time.time() - t0) * 1000.0
            logger.error(f"HTTP {method} {path} -> Exception ({elapsed:.1f}ms): {e}")
            return 500, {"error": True, "code": "NETWORK_ERROR", "message": str(e)}

    def check_health(self) -> Tuple[bool, Dict[str, Any]]:
        """Check if server is reachable and online."""
        status, data = self._request("GET", "/api/health")
        is_online = (status == 200 and data.get("status") == "online")
        logger.debug(f"Pemeriksaan kesehatan server: {'ONLINE' if is_online else 'OFFLINE'}")
        return is_online, data

    def measure_latency_ms(self) -> float:
        """Measure HTTP round-trip latency to server in milliseconds."""
        start = time.time()
        ok, _ = self.check_health()
        if not ok:
            return -1.0
        latency = round((time.time() - start) * 1000.0, 1)
        logger.debug(f"Ping latensi server: {latency} ms")
        return latency

    def list_rooms(self, game_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List active waiting rooms."""
        path = "/api/rooms"
        if game_id:
            path += f"?game_id={urllib.parse.quote(game_id)}"
        status, data = self._request("GET", path)
        if status == 200:
            rooms = data.get("rooms", [])
            logger.debug(f"Daftar room dimuat: {len(rooms)} room aktif ditemukan (Filter: {game_id or 'SEMUA'})")
            return rooms
        return []

    def get_room(self, room_id: str, timeout: Optional[float] = None,
                 raise_on_error: bool = False) -> Optional[Dict[str, Any]]:
        """Fetch details of a specific room.
        
        Returns:
            room dict if room exists (HTTP 200).
            None if room was not found / deleted / expired (HTTP 404).
            
        Raises:
            ConnectionError if network timeout/failure occurs and raise_on_error is True.
        """
        status, data = self._request("GET", f"/api/rooms/{room_id}", timeout=timeout)
        if status == 200:
            return data.get("room")
        if status == 404:
            logger.warning(f"Room {room_id} tidak ditemukan pada server.")
            return None

        err_msg = data.get("message") or f"HTTP {status}"
        logger.warning(f"Gagal memeriksa status room {room_id} (Status {status}): {err_msg}")
        if raise_on_error or status >= 500 or data.get("code") in ("NETWORK_ERROR", "SERVICE_UNAVAILABLE"):
            if raise_on_error:
                raise ConnectionError(f"Gagal menghubungi server untuk room {room_id}: {err_msg}")
        return None

    def create_room(self, game_id: str, room_name: str, host_name: str,
                    compatibility: Dict[str, Any],
                    visibility: str = "public") -> Tuple[bool, Dict[str, Any]]:
        """Create a new room."""
        logger.info(f"Membuat room '{room_name}' untuk game '{game_id}' oleh '{host_name}'...")
        payload = {
            "game_id": game_id,
            "room_name": room_name,
            "host_name": host_name,
            "compatibility": compatibility,
            "visibility": visibility,
            "client_version": "1.0.0"
        }
        status, data = self._request("POST", "/api/rooms", body=payload)
        success = (status == 201)
        if success:
            logger.info(f"Room berhasil dibuat! ID: {data.get('room_id')} (Host Token: {data.get('host_token')[:6]}...)")
        else:
            logger.error(f"Gagal membuat room: {data.get('message')}")
        return success, data

    def join_room(self, room_id: str, player_name: str,
                  compatibility: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """Join an existing waiting room."""
        logger.info(f"Mengirim permintaan gabung ke room {room_id} sebagai '{player_name}'...")
        payload = {
            "player_name": player_name,
            "compatibility": compatibility,
            "client_version": "1.0.0"
        }
        status, data = self._request("POST", f"/api/rooms/{room_id}/join", body=payload)
        success = (status == 200)
        if success:
            logger.info(f"Berhasil bergabung ke room {room_id}! Player ID: {data.get('player_id')}")
        else:
            logger.warning(f"Gagal bergabung ke room {room_id}: {data.get('message')}")
        return success, data

    def leave_room(self, room_id: str, player_id: str, token: str) -> bool:
        """Leave room."""
        logger.info(f"Meninggalkan room {room_id} (Player ID: {player_id})")
        payload = {"player_id": player_id, "token": token}
        status, _ = self._request("POST", f"/api/rooms/{room_id}/leave", body=payload)
        return status == 200

    def close_room(self, room_id: str, host_token: str) -> bool:
        """Host close room."""
        logger.info(f"Menutup dan menghapus room {room_id} dari server")
        headers = {"X-Host-Token": host_token}
        status, _ = self._request("DELETE", f"/api/rooms/{room_id}", headers=headers)
        return status == 200

    def send_heartbeat(self, room_id: str, player_id: str, token: str,
                       timeout: Optional[float] = None,
                       raise_on_error: bool = False) -> bool:
        """Keep room and session alive.
        
        Returns:
            True if heartbeat acknowledged by server (HTTP 200).
            False if rejected by server (e.g. 400/403/404 room expired or token invalid).
            
        Raises:
            ConnectionError if network timeout/failure occurs and raise_on_error is True.
        """
        payload = {"player_id": player_id, "token": token}
        status, data = self._request("POST", f"/api/rooms/{room_id}/heartbeat", body=payload, timeout=timeout)
        if status == 200:
            return True
        if raise_on_error and (status >= 500 or data.get("code") in ("NETWORK_ERROR", "SERVICE_UNAVAILABLE")):
            raise ConnectionError(f"Heartbeat network error: {data.get('message', status)}")
        return False

    def send_signal(self, room_id: str, sender_id: str, event: str,
                    payload: Optional[Dict[str, Any]] = None,
                    target_id: Optional[str] = None) -> bool:
        """Send a signaling message to peer."""
        logger.debug(f"Mengirim sinyal [{event}] ke room {room_id} dari {sender_id}")
        req_body = {
            "sender_id": sender_id,
            "event": event,
            "payload": payload or {},
            "target_id": target_id
        }
        status, _ = self._request("POST", f"/api/rooms/{room_id}/signal", body=req_body)
        return status == 200

    def poll_signals(self, room_id: str, player_id: str,
                     since: float = 0.0, timeout: float = 4.0,
                     req_timeout: Optional[float] = None) -> List[Dict[str, Any]]:
        """Poll incoming signaling messages."""
        path = f"/api/rooms/{room_id}/poll?player_id={player_id}&since={since}&timeout={timeout}"
        status, data = self._request("GET", path, timeout=req_timeout or (timeout + 2.0))
        if status == 200:
            msgs = data.get("messages", [])
            if msgs:
                logger.debug(f"Menerima {len(msgs)} pesan sinyal dari room {room_id}: {[m.get('event') for m in msgs]}")
            return msgs
        return []

    def request_relay(self, room_id: str, token: str) -> Tuple[bool, Dict[str, Any]]:
        """Request fallback relay allocation from server."""
        logger.info(f"Meminta alokasi relay proxy untuk room {room_id}...")
        payload = {"token": token}
        status, data = self._request("POST", f"/api/rooms/{room_id}/relay", body=payload)
        success = (status == 200)
        if success:
            logger.info(f"Relay proxy aktif: {data.get('relay_host')}:{data.get('relay_port')} (Sesi: {data.get('relay_session_id')})")
        else:
            logger.error(f"Gagal mengalokasikan relay: {data.get('message')}")
        return success, data

