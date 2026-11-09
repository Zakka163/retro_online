"""Unit tests for Netplay Relay Server protocol and bidirectional bridging."""

import socket
import threading
import time
import unittest
from server.relay import RelayServer, RelaySession


class TestRelayServer(unittest.TestCase):

    def setUp(self):
        self.server = RelayServer()
        self.server._running = True

    def tearDown(self):
        self.server.stop()

    def test_relay_authentication_failure_via_socketpair(self):
        client_end, server_end = socket.socketpair()

        # Send invalid auth handshake
        client_end.sendall(b"ARCADE_RELAY badsession badtoken HOST\n")

        # Process handshake
        t = threading.Thread(target=self.server._handle_handshake, args=(server_end, ("127.0.0.1", 1234)))
        t.start()
        t.join(timeout=1.0)

        resp = client_end.recv(64)
        client_end.close()
        self.assertIn(b"ERR INVALID_AUTH", resp)

    def test_relay_bidirectional_bridge_via_socketpair(self):
        session_id, token = self.server.allocate_session(room_id="room123")

        # Create socket pairs for host and client
        host_client_end, host_server_end = socket.socketpair()
        peer_client_end, peer_server_end = socket.socketpair()

        # Handshake host
        host_client_end.sendall(f"ARCADE_RELAY {session_id} {token} HOST\n".encode("utf-8"))
        th = threading.Thread(target=self.server._handle_handshake, args=(host_server_end, ("127.0.0.1", 1111)))
        th.start()
        th.join(timeout=1.0)

        # Handshake client
        peer_client_end.sendall(f"ARCADE_RELAY {session_id} {token} CLIENT\n".encode("utf-8"))
        tc = threading.Thread(target=self.server._handle_handshake, args=(peer_server_end, ("127.0.0.1", 2222)))
        tc.start()
        tc.join(timeout=1.0)

        # Read OK CONNECTED on both ends
        host_resp = host_client_end.recv(64)
        peer_resp = peer_client_end.recv(64)
        self.assertIn(b"OK CONNECTED", host_resp)
        self.assertIn(b"OK CONNECTED", peer_resp)

        # Host sends netplay packet
        host_client_end.sendall(b"HADOUKEN_PACKET_P1")
        time.sleep(0.05)
        received_by_client = peer_client_end.recv(64)
        self.assertEqual(received_by_client, b"HADOUKEN_PACKET_P1")

        # Client sends response
        peer_client_end.sendall(b"SHORYUKEN_PACKET_P2")
        time.sleep(0.05)
        received_by_host = host_client_end.recv(64)
        self.assertEqual(received_by_host, b"SHORYUKEN_PACKET_P2")

        session = self.server.get_session(session_id)
        self.assertIsNotNone(session)
        self.assertEqual(session.status, "bridged")
        self.assertGreater(session.bytes_host_to_client, 0)
        self.assertGreater(session.bytes_client_to_host, 0)

        session.close()
        host_client_end.close()
        peer_client_end.close()

    def test_relay_peer_reconnect_and_resume(self):
        """Verify peer can disconnect, have traffic buffered, reconnect, and resume."""
        session_id, token = self.server.allocate_session(room_id="reconnect_room")

        host_client_end, host_server_end = socket.socketpair()
        peer_client_end, peer_server_end = socket.socketpair()

        # Initial handshakes
        host_client_end.sendall(f"ARCADE_RELAY {session_id} {token} HOST\n".encode("utf-8"))
        th = threading.Thread(target=self.server._handle_handshake, args=(host_server_end, ("127.0.0.1", 1111)))
        th.start()
        th.join(timeout=1.0)

        peer_client_end.sendall(f"ARCADE_RELAY {session_id} {token} CLIENT\n".encode("utf-8"))
        tc = threading.Thread(target=self.server._handle_handshake, args=(peer_server_end, ("127.0.0.1", 2222)))
        tc.start()
        tc.join(timeout=1.0)

        host_client_end.recv(64)
        peer_client_end.recv(64)

        # 1. Client suddenly disconnects
        peer_client_end.close()
        time.sleep(0.1)

        # 2. Host sends data while Client is disconnected (should be buffered by server)
        host_client_end.sendall(b"PACKET_DURING_OUTAGE")
        time.sleep(0.1)

        # 3. Client reconnects with a new socket
        new_client_end, new_server_end = socket.socketpair()
        new_client_end.sendall(f"ARCADE_RELAY {session_id} {token} CLIENT\n".encode("utf-8"))
        t_reconnect = threading.Thread(target=self.server._handle_handshake, args=(new_server_end, ("127.0.0.1", 3333)))
        t_reconnect.start()
        t_reconnect.join(timeout=1.0)

        # Client receives OK CONNECTED and the buffered packet!
        received = b""
        start_t = time.time()
        while b"PACKET_DURING_OUTAGE" not in received and (time.time() - start_t < 2.0):
            chunk = new_client_end.recv(64)
            if not chunk:
                break
            received += chunk

        self.assertIn(b"OK CONNECTED", received)
        self.assertIn(b"PACKET_DURING_OUTAGE", received)

        # 4. Bidirectional exchange continues after reconnection
        new_client_end.sendall(b"CLIENT_BACK_ONLINE")
        time.sleep(0.05)
        recv_by_host = host_client_end.recv(64)
        self.assertEqual(recv_by_host, b"CLIENT_BACK_ONLINE")

        session = self.server.get_session(session_id)
        self.assertIsNotNone(session)
        self.assertEqual(session.status, "bridged")

        session.close()
        host_client_end.close()
        new_client_end.close()

    def test_local_relay_bridge_reconnect_loop(self):
        """Verify LocalRelayBridge attempts reconnection to RelayServer when relay socket drops."""
        from server.relay import LocalRelayBridge
        from unittest.mock import MagicMock, patch

        bridge = LocalRelayBridge(
            relay_host="127.0.0.1",
            relay_port=55436,
            session_id="session123",
            token="token123",
            role="CLIENT",
            local_target_port=55438,
            reconnect_timeout=0.6
        )

        mock_local, mock_ra = socket.socketpair()
        mock_relay1, mock_server1 = socket.socketpair()
        mock_relay2, mock_server2 = socket.socketpair()

        # Step 1: Initial connection returns mock_relay1, then second call returns mock_relay2
        with patch.object(bridge, "_connect_relay_socket", side_effect=[mock_relay1, mock_relay2]):
            bridge._running = True
            bridge._client_listen_sock = MagicMock()
            bridge._client_listen_sock.accept.return_value = (mock_local, ("127.0.0.1", 12345))

            t = threading.Thread(target=bridge._run_bridge, daemon=True)
            t.start()

            time.sleep(0.1)
            # Exchange packet between local RA and relay1
            mock_ra.sendall(b"PING_FROM_RA")
            time.sleep(0.05)
            self.assertEqual(mock_server1.recv(64), b"PING_FROM_RA")

            # Simulate network drop on relay1
            mock_server1.close()
            time.sleep(0.2)

            # Bridge should have reconnected and acquired mock_relay2!
            # Server2 sends packet to bridge
            mock_server2.sendall(b"PONG_AFTER_RECONNECT")
            time.sleep(0.05)
            self.assertEqual(mock_ra.recv(64), b"PONG_AFTER_RECONNECT")

            # Verify disconnect_event is NOT set because reconnect succeeded!
            self.assertFalse(bridge.disconnect_event.is_set())

            # Stop bridge cleanly
            bridge.stop()
            mock_ra.close()
            mock_local.close()
            mock_server2.close()
            t.join(timeout=1.0)


if __name__ == "__main__":
    unittest.main()
