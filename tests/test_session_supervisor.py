"""Unit tests for Active Session Supervisor."""

import time
import unittest
from unittest.mock import MagicMock, patch

from launcher.session_supervisor import SessionSupervisor


class TestSessionSupervisor(unittest.TestCase):
    """Test suite for live Netplay session monitoring and mutual disconnection."""

    def setUp(self):
        self.mock_api = MagicMock()
        self.mock_ra_controller = MagicMock()
        self.mock_proc = MagicMock()
        self.mock_proc.poll.return_value = None  # Process running
        self.mock_ra_controller.active_process = self.mock_proc

    def test_peer_left_signal_triggers_disconnect(self):
        """Supervisor should terminate local emulator when peer.left signal is polled."""
        self.mock_api.send_heartbeat.return_value = True
        self.mock_api.get_room.return_value = {"has_client": True, "status": "playing"}
        self.mock_api.poll_signals.return_value = [
            {"event": "peer.left", "payload": {"reason": "Opponent quit"}}
        ]

        disconnect_called = []
        supervisor = SessionSupervisor(
            api=self.mock_api,
            room_id="room1",
            player_id="p1",
            token="token1",
            role="host",
            ra_controller=self.mock_ra_controller,
            poll_interval=0.05,
            on_disconnect=lambda r: disconnect_called.append(r)
        )

        supervisor.start()
        time.sleep(0.3)
        supervisor.stop()

        self.assertTrue(supervisor.peer_disconnected)
        self.assertIn("Opponent quit", supervisor.disconnect_reason)
        self.mock_ra_controller.terminate.assert_called_once()
        self.assertEqual(len(disconnect_called), 1)

    def test_room_closed_triggers_disconnect(self):
        """Supervisor should terminate local emulator when room is closed/deleted on server."""
        self.mock_api.send_heartbeat.return_value = False
        self.mock_api.get_room.return_value = None  # 404 Room not found
        self.mock_api.poll_signals.return_value = []

        supervisor = SessionSupervisor(
            api=self.mock_api,
            room_id="room2",
            player_id="p2",
            token="token2",
            role="client",
            ra_controller=self.mock_ra_controller,
            poll_interval=0.05
        )

        supervisor.start()
        time.sleep(0.3)
        supervisor.stop()

        self.assertTrue(supervisor.peer_disconnected)
        self.mock_ra_controller.terminate.assert_called_once()

    def test_relay_disconnect_event_triggers_termination(self):
        """Supervisor should terminate emulator if LocalRelayBridge loses connection."""
        self.mock_api.send_heartbeat.return_value = True
        self.mock_api.get_room.return_value = {"has_client": True, "status": "playing"}
        self.mock_api.poll_signals.return_value = []

        mock_bridge = MagicMock()
        mock_bridge.disconnect_event.is_set.return_value = True

        supervisor = SessionSupervisor(
            api=self.mock_api,
            room_id="room3",
            player_id="p1",
            token="token1",
            role="host",
            ra_controller=self.mock_ra_controller,
            local_bridge=mock_bridge,
            poll_interval=0.05
        )

        supervisor.start()
        time.sleep(0.3)
        supervisor.stop()

        self.assertTrue(supervisor.peer_disconnected)
        self.mock_ra_controller.terminate.assert_called_once()

    def test_local_exit_does_not_trigger_peer_disconnect(self):
        """If local RetroArch process terminates normally, supervisor exits cleanly."""
        self.mock_proc.poll.return_value = 0  # Process already exited cleanly

        supervisor = SessionSupervisor(
            api=self.mock_api,
            room_id="room4",
            player_id="p1",
            token="token1",
            role="host",
            ra_controller=self.mock_ra_controller,
            poll_interval=0.05
        )

        supervisor.start()
        time.sleep(0.2)
        supervisor.stop()

        self.assertFalse(supervisor.peer_disconnected)
        self.mock_ra_controller.terminate.assert_not_called()

    def test_local_internet_loss_triggers_termination(self):
        """If local internet connection drops (repeated network failures), terminate emulator."""
        self.mock_api.send_heartbeat.side_effect = Exception("Network unreachable")
        self.mock_api.get_room.side_effect = Exception("Network unreachable")
        self.mock_api.poll_signals.return_value = []

        supervisor = SessionSupervisor(
            api=self.mock_api,
            room_id="room5",
            player_id="p1",
            token="token1",
            role="host",
            ra_controller=self.mock_ra_controller,
            poll_interval=0.05
        )

        supervisor.start()
        time.sleep(0.3)
        supervisor.stop()

        self.assertTrue(supervisor.peer_disconnected)
        self.assertIn("Koneksi internet Anda terputus", supervisor.disconnect_reason)
        self.mock_ra_controller.terminate.assert_called_once()

    def test_opponent_inactive_triggers_termination(self):
        """If opponent's connection drops (client_active is False), terminate emulator."""
        self.mock_api.send_heartbeat.return_value = True
        self.mock_api.get_room.return_value = {
            "has_client": True,
            "status": "playing",
            "client_active": False  # Opponent heartbeat timed out
        }
        self.mock_api.poll_signals.return_value = []

        supervisor = SessionSupervisor(
            api=self.mock_api,
            room_id="room6",
            player_id="p1",
            token="token1",
            role="host",
            ra_controller=self.mock_ra_controller,
            poll_interval=0.05
        )

        supervisor.start()
        time.sleep(0.3)
        supervisor.stop()

        self.assertTrue(supervisor.peer_disconnected)
        self.assertIn("terputus di tengah permainan", supervisor.disconnect_reason)
        self.mock_ra_controller.terminate.assert_called_once()


if __name__ == "__main__":
    unittest.main()

