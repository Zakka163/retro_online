"""Data models for Room, Player, Compatibility, and Signaling."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


@dataclass
class CompatibilityInfo:
    """Compatibility requirements and assets specification."""
    core: str
    core_version: Optional[str] = None
    rom_hash: Optional[str] = None


@dataclass
class Player:
    """Connected participant in a room."""
    player_id: str
    name: str
    role: str                       # 'host' or 'client'
    token: str                      # Session authorization token
    ip_candidate: Optional[str] = None
    port_candidate: int = 55435
    connected: bool = True
    last_heartbeat: float = field(default_factory=time.time)


@dataclass
class Room:
    """Arcade Netplay matchmaking room."""
    room_id: str
    game_id: str
    name: str
    host: Player
    compatibility: Dict[str, Any]
    client_version: str = "1.0.0"
    visibility: str = "public"      # 'public' or 'private'
    status: str = "waiting"         # 'waiting', 'connecting', 'playing', 'closed'
    client: Optional[Player] = None
    connection_mode: Optional[str] = None  # 'direct' or 'relay'
    relay_session_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 180.0)

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def is_full(self) -> bool:
        return self.client is not None

    def refresh_ttl(self, seconds: float = 120.0) -> None:
        self.expires_at = time.time() + seconds

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary for API clients."""
        now = time.time()
        host_active = (now - self.host.last_heartbeat) < 10.0
        client_active = (self.client is not None) and ((now - self.client.last_heartbeat) < 10.0)
        return {
            "room_id": self.room_id,
            "game_id": self.game_id,
            "name": self.name,
            "status": self.status,
            "visibility": self.visibility,
            "host_name": self.host.name,
            "has_client": self.client is not None,
            "client_name": self.client.name if self.client else None,
            "host_active": host_active,
            "client_active": client_active,
            "compatibility": self.compatibility,
            "client_version": self.client_version,
            "connection_mode": self.connection_mode,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


@dataclass
class SignalingMessage:
    """Signaling event routed between peers."""
    event: str
    room_id: str
    sender_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    target_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event,
            "room_id": self.room_id,
            "sender_id": self.sender_id,
            "target_id": self.target_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }

