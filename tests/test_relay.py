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


if __name__ == "__main__":
    unittest.main()
