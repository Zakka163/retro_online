"""Unit tests for Arcade Matchmaking & Signaling REST API."""

import io
import json
import unittest
from unittest.mock import patch
from server.api import ArcadeAPIHandler
from server.room_store import RoomStore
from server.signaling import SignalingHub
from server.relay import RelayServer
from launcher.client_api import ArcadeClientAPI


class MockSocket:
    def __init__(self, request_bytes: bytes):
        self.rfile = io.BytesIO(request_bytes)
        self.wfile = io.BytesIO()

    def makefile(self, mode: str, *args, **kwargs):
        if "b" in mode:
            return self.rfile if "r" in mode else self.wfile
        return io.TextIOWrapper(self.rfile if "r" in mode else self.wfile)

    def sendall(self, data: bytes):
        self.wfile.write(data)


def simulate_http_request(method: str, path: str, body: dict = None, headers: dict = None):
    store = RoomStore()
    signaling = SignalingHub()
    relay = RelayServer()

    class TestHandler(ArcadeAPIHandler):
        pass

    TestHandler.store = store
    TestHandler.signaling = signaling
    TestHandler.relay = relay
    TestHandler.public_relay_host = "relay.example.com"

    body_bytes = json.dumps(body).encode("utf-8") if body else b""
    raw = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\n"
    if headers:
        for k, v in headers.items():
            raw += f"{k}: {v}\r\n"
    if body_bytes:
        raw += f"Content-Length: {len(body_bytes)}\r\nContent-Type: application/json\r\n"
    raw += "\r\n"

    raw_bytes = raw.encode("utf-8") + body_bytes
    mock_sock = MockSocket(raw_bytes)

    handler = TestHandler(mock_sock, ("127.0.0.1", 1234), None)

    # Parse written response
    resp_bytes = mock_sock.wfile.getvalue()
    parts = resp_bytes.split(b"\r\n\r\n", 1)
    header_block = parts[0].decode("utf-8")
    status_line = header_block.split("\r\n")[0]
    status_code = int(status_line.split()[1])

    resp_json = None
    if len(parts) > 1 and parts[1]:
        resp_json = json.loads(parts[1].decode("utf-8"))

    return status_code, resp_json, store, signaling, relay


class TestServerAPI(unittest.TestCase):

    def test_health_check(self):
        status, data, _, _, _ = simulate_http_request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "online")
        self.assertEqual(data["version"], "1.0.0")

    def test_create_room_and_list(self):
        create_payload = {
            "game_id": "street-fighter-ii",
            "room_name": "Ryu's Dojo",
            "host_name": "Ryu",
            "compatibility": {
                "core": "mame2003_plus",
                "core_version": "2003-plus"
            }
        }
        status, data, store, _, _ = simulate_http_request("POST", "/api/rooms", body=create_payload)
        self.assertEqual(status, 201)
        self.assertIn("room_id", data)
        self.assertIn("host_token", data)
        self.assertEqual(data["status"], "waiting")

    def test_join_room_flow(self):
        # 1. Create room
        store = RoomStore()
        signaling = SignalingHub()
        room, host_token = store.create_room(
            game_id="street-fighter-ii",
            name="Ken vs Ryu",
            host_name="Ryu",
            compatibility={"core": "mame2003_plus"}
        )

        class TestHandler(ArcadeAPIHandler):
            pass

        TestHandler.store = store
        TestHandler.signaling = signaling
        TestHandler.relay = RelayServer()

        # Join request
        body = {
            "player_name": "Ken",
            "compatibility": {"core": "mame2003_plus"}
        }
        body_bytes = json.dumps(body).encode("utf-8")
        raw = f"POST /api/rooms/{room.room_id}/join HTTP/1.1\r\nHost: localhost\r\nContent-Length: {len(body_bytes)}\r\n\r\n"
        mock_sock = MockSocket(raw.encode("utf-8") + body_bytes)

        TestHandler(mock_sock, ("127.0.0.1", 1234), None)
        parts = mock_sock.wfile.getvalue().split(b"\r\n\r\n", 1)
        resp_json = json.loads(parts[1].decode("utf-8"))

        self.assertTrue(resp_json.get("ok"))
        self.assertIn("client_token", resp_json)
        self.assertEqual(store.get_room(room.room_id).client.name, "Ken")


class TestArcadeClientAPIErrors(unittest.TestCase):
    def setUp(self):
        self.api = ArcadeClientAPI(server_url="http://mock-server.test")

    @patch.object(ArcadeClientAPI, "_request")
    def test_get_room_not_found(self, mock_request):
        mock_request.return_value = (404, {"error": True, "message": "Room not found"})
        res = self.api.get_room("room123", raise_on_error=True)
        self.assertIsNone(res)

    @patch.object(ArcadeClientAPI, "_request")
    def test_get_room_timeout_raises(self, mock_request):
        mock_request.return_value = (500, {"error": True, "code": "NETWORK_ERROR", "message": "timed out"})
        with self.assertRaises(ConnectionError):
            self.api.get_room("room123", raise_on_error=True)

    @patch.object(ArcadeClientAPI, "_request")
    def test_send_heartbeat_timeout_raises(self, mock_request):
        mock_request.return_value = (500, {"error": True, "code": "NETWORK_ERROR", "message": "timed out"})
        with self.assertRaises(ConnectionError):
            self.api.send_heartbeat("room123", "p1", "token1", raise_on_error=True)


if __name__ == "__main__":
    unittest.main()

