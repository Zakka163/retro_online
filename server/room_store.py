"""In-Memory Thread-safe Room Store with TTL expiration."""

import time
import uuid
import threading
from typing import Optional, List, Dict, Tuple, Any
from .models import Room, Player


class RoomStore:
    """Manages active rooms and peer sessions."""

    def __init__(self, default_ttl: float = 120.0):
        self.default_ttl = default_ttl
        self._rooms: Dict[str, Room] = {}
        self._lock = threading.RLock()

    def create_room(self, game_id: str, name: str, host_name: str,
                    compatibility: Dict[str, Any],
                    visibility: str = "public",
                    client_version: str = "1.0.0") -> Tuple[Room, str]:
        """Create a new room and return (room, host_token)."""
        with self._lock:
            self.cleanup_expired()

            room_id = uuid.uuid4().hex[:8]
            player_id = f"p1_{uuid.uuid4().hex[:6]}"
            host_token = uuid.uuid4().hex

            host_player = Player(
                player_id=player_id,
                name=host_name,
                role="host",
                token=host_token
            )

            room = Room(
                room_id=room_id,
                game_id=game_id,
                name=name or f"{host_name}'s {game_id.upper()} Room",
                host=host_player,
                compatibility=compatibility,
                client_version=client_version,
                visibility=visibility,
                status="waiting",
                expires_at=time.time() + self.default_ttl
            )

            self._rooms[room_id] = room
            return room, host_token

    def get_room(self, room_id: str) -> Optional[Room]:
        """Retrieve room by ID, returning None if expired or not found."""
        with self._lock:
            room = self._rooms.get(room_id)
            if not room:
                return None
            if room.is_expired:
                del self._rooms[room_id]
                return None

            # Detect dead heartbeat if in active 2-player match
            now = time.time()
            if room.client is not None:
                if (now - room.host.last_heartbeat) > 12.0:
                    room.status = "closed"
                elif (now - room.client.last_heartbeat) > 12.0:
                    room.client = None
                    room.status = "waiting"

            return room

    def list_rooms(self, game_id: Optional[str] = None,
                   status: Optional[str] = "waiting") -> List[Room]:
        """List active joinable rooms."""
        with self._lock:
            self.cleanup_expired()
            results = []
            for room in self._rooms.values():
                if room.visibility != "public":
                    continue
                if game_id and room.game_id != game_id:
                    continue
                if status and room.status != status:
                    continue
                results.append(room)
            return results

    def join_room(self, room_id: str, player_name: str,
                  compatibility: Dict[str, Any],
                  client_version: str = "1.0.0") -> Tuple[bool, str, Optional[Player]]:
        """Attempt to join an existing room as Client."""
        with self._lock:
            room = self.get_room(room_id)
            if not room:
                return False, "ROOM_NOT_FOUND", None
            if room.status != "waiting" or room.is_full:
                return False, "ROOM_FULL", None

            # Compatibility check: core must match
            req_core = room.compatibility.get("core")
            client_core = compatibility.get("core")
            if req_core and client_core and req_core != client_core:
                return False, "CORE_MISMATCH", None

            # Core version check
            req_cver = room.compatibility.get("core_version")
            client_cver = compatibility.get("core_version")
            if req_cver and client_cver and req_cver != client_cver:
                return False, "CORE_MISMATCH", None

            # ROM hash check
            req_hash = room.compatibility.get("rom_hash")
            client_hash = compatibility.get("rom_hash")
            if req_hash and client_hash and req_hash.lower() != client_hash.lower():
                return False, "GAME_MISMATCH", None

            player_id = f"p2_{uuid.uuid4().hex[:6]}"
            client_token = uuid.uuid4().hex

            client_player = Player(
                player_id=player_id,
                name=player_name,
                role="client",
                token=client_token
            )

            room.client = client_player
            room.status = "connecting"
            room.refresh_ttl(self.default_ttl)
            return True, "OK", client_player

    def leave_room(self, room_id: str, player_id: str, token: str) -> bool:
        """Handle player leaving room."""
        with self._lock:
            room = self._rooms.get(room_id)
            if not room:
                return False

            if room.host.player_id == player_id and room.host.token == token:
                # Host left -> close entire room
                room.status = "closed"
                del self._rooms[room_id]
                return True

            if room.client and room.client.player_id == player_id and room.client.token == token:
                # Client left -> reset room back to waiting
                room.client = None
                room.status = "waiting"
                room.refresh_ttl(self.default_ttl)
                return True

            return False

    def close_room(self, room_id: str, host_token: str) -> bool:
        """Host explicitly closes the room."""
        with self._lock:
            room = self._rooms.get(room_id)
            if not room:
                return False
            if room.host.token != host_token:
                return False

            room.status = "closed"
            del self._rooms[room_id]
            return True

    def heartbeat(self, room_id: str, player_id: str, token: str) -> bool:
        """Update last heartbeat and refresh room TTL."""
        with self._lock:
            room = self._rooms.get(room_id)
            if not room:
                return False

            if room.host.player_id == player_id and room.host.token == token:
                room.host.last_heartbeat = time.time()
                room.refresh_ttl(self.default_ttl)
                return True

            if room.client and room.client.player_id == player_id and room.client.token == token:
                room.client.last_heartbeat = time.time()
                room.refresh_ttl(self.default_ttl)
                return True

            return False

    def cleanup_expired(self) -> int:
        """Remove rooms that have exceeded their TTL."""
        now = time.time()
        expired = [rid for rid, r in self._rooms.items() if now > r.expires_at]
        for rid in expired:
            del self._rooms[rid]
        return len(expired)

    def count_online_players(self, game_id: Optional[str] = None) -> int:
        """Count total players across active rooms."""
        with self._lock:
            total = 0
            for r in self._rooms.values():
                if game_id and r.game_id != game_id:
                    continue
                total += 1  # Host
                if r.client:
                    total += 1
            return total

