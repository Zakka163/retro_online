"""Signaling Hub for real-time room communication.

Maintains event message queues for peers and provides event routing
for connection candidates, direct connection negotiations, and relay status.
Supports both HTTP polling and WebSocket clients.
"""

import time
import queue
import threading
from typing import Dict, List, Optional, Any
from .models import SignalingMessage


class SignalingHub:
    """Manages signaling channels for rooms and connected peers."""

    def __init__(self, message_history_ttl: float = 60.0):
        self.message_history_ttl = message_history_ttl
        # room_id -> list of SignalingMessage
        self._messages: Dict[str, List[SignalingMessage]] = {}
        # (room_id, player_id) -> queue.Queue of SignalingMessage for real-time push
        self._queues: Dict[str, Dict[str, queue.Queue]] = {}
        self._lock = threading.RLock()

    def register_peer(self, room_id: str, player_id: str) -> None:
        """Register a peer to receive direct queued events."""
        with self._lock:
            if room_id not in self._queues:
                self._queues[room_id] = {}
            if player_id not in self._queues[room_id]:
                self._queues[room_id][player_id] = queue.Queue(maxsize=100)

    def unregister_peer(self, room_id: str, player_id: str) -> None:
        """Unregister a peer upon leaving."""
        with self._lock:
            if room_id in self._queues and player_id in self._queues[room_id]:
                del self._queues[room_id][player_id]
            if room_id in self._queues and not self._queues[room_id]:
                del self._queues[room_id]

    def send_event(self, room_id: str, sender_id: str, event: str,
                   payload: Optional[Dict[str, Any]] = None,
                   target_id: Optional[str] = None) -> SignalingMessage:
        """Broadcast or route an event to peer(s) in a room."""
        with self._lock:
            msg = SignalingMessage(
                event=event,
                room_id=room_id,
                sender_id=sender_id,
                target_id=target_id,
                payload=payload or {},
                timestamp=time.time()
            )

            # Store in history
            if room_id not in self._messages:
                self._messages[room_id] = []
            self._messages[room_id].append(msg)

            # Prune old history
            cutoff = time.time() - self.message_history_ttl
            self._messages[room_id] = [m for m in self._messages[room_id] if m.timestamp > cutoff]

            # Push to queues
            room_peers = self._queues.get(room_id, {})
            for pid, q in room_peers.items():
                if pid == sender_id:
                    continue  # Do not echo back to sender
                if target_id and pid != target_id:
                    continue
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    # Drop oldest if queue full
                    try:
                        q.get_nowait()
                        q.put_nowait(msg)
                    except (queue.Empty, queue.Full):
                        pass

            return msg

    def poll_messages(self, room_id: str, player_id: str,
                      since_timestamp: float = 0.0,
                      timeout: float = 5.0) -> List[SignalingMessage]:
        """Poll for new messages, waiting up to timeout if none are immediately available."""
        # 1. First check if any missed history exists
        with self._lock:
            history = self._messages.get(room_id, [])
            missed = [
                m for m in history
                if m.timestamp > since_timestamp
                and m.sender_id != player_id
                and (m.target_id is None or m.target_id == player_id)
            ]
            if missed:
                return missed

            # Ensure peer queue is registered
            self.register_peer(room_id, player_id)
            q = self._queues[room_id][player_id]

        # 2. Wait on the queue for new incoming events
        messages = []
        try:
            msg = q.get(timeout=timeout)
            messages.append(msg)
            # Drain any additional available messages
            while not q.empty():
                try:
                    messages.append(q.get_nowait())
                except queue.Empty:
                    break
        except queue.Empty:
            pass

        return messages

    def clear_room(self, room_id: str) -> None:
        """Clear all signaling queues and history for a closed room."""
        with self._lock:
            self._messages.pop(room_id, None)
            self._queues.pop(room_id, None)

