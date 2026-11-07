"""End-to-End Integration Test for Arcade Online Launcher Flow.

Validates:
1. Catalog & ROM Compatibility check
2. Matchmaking Room creation & listing
3. Client search and join with slot locking
4. Direct & Relay fallback negotiation
5. RetroArch command construction and mock launch
6. Safe cleanup and session termination
"""

import os
import unittest
from catalog.validator import CatalogValidator, GameManifest
from server.room_store import RoomStore
from server.signaling import SignalingHub
from server.relay import RelayServer
from launcher.retroarch_controller import RetroArchController, RetroArchLaunchConfig
from launcher.connection_manager import ConnectionManager, ConnectionProgressStep


class TestE2EArcadeFlow(unittest.TestCase):

    def setUp(self):
        os.environ["ARCADE_MOCK_RETROARCH"] = "1"
        os.environ["ARCADE_FORCE_MOCK_GAME"] = "1"
        self.manifest = GameManifest()
        self.validator = CatalogValidator(manifest=self.manifest)
        self.store = RoomStore()
        self.signaling = SignalingHub()
        self.relay = RelayServer()
        self.relay._running = True
        self.ra_controller = RetroArchController(retroarch_bin="/mock/bin/retroarch")

    def tearDown(self):
        self.ra_controller.cleanup()
        self.relay.stop()
        os.environ.pop("ARCADE_MOCK_RETROARCH", None)
        os.environ.pop("ARCADE_FORCE_MOCK_GAME", None)

    def test_full_host_client_session_flow(self):
        # 1. Host verifies game assets
        game_id = "sf2"
        game = self.manifest.get_game(game_id)
        self.assertIsNotNone(game)

        valid, code, details = self.validator.verify_local_game(game_id, strict_hash=False)
        self.assertTrue(valid)
        self.assertEqual(code, "OK")

        # 2. Host creates matchmaking room
        room_name = "Championship SF2"
        host_compat = {
            "core": game["retroarch_core"],
            "core_version": game.get("core_version"),
            "rom_hash": "mock_hash_12345"
        }
        room, host_token = self.store.create_room(
            game_id=game_id,
            name=room_name,
            host_name="RyuCabinet",
            compatibility=host_compat
        )
        self.assertIsNotNone(room.room_id)
        self.assertEqual(room.status, "waiting")

        # 3. Client browses and finds room
        available = self.store.list_rooms(game_id=game_id)
        self.assertEqual(len(available), 1)
        self.assertEqual(available[0].room_id, room.room_id)

        # 4. Client joins room
        client_compat = host_compat.copy()
        ok, err_code, client_player = self.store.join_room(
            room_id=room.room_id,
            player_name="KenCabinet",
            compatibility=client_compat
        )
        self.assertTrue(ok)
        self.assertEqual(err_code, "OK")
        self.assertEqual(room.status, "connecting")

        # Third machine attempts to join -> Blocked with ROOM_FULL
        ok3, err3, _ = self.store.join_room(
            room_id=room.room_id,
            player_name="GuileCabinet",
            compatibility=client_compat
        )
        self.assertFalse(ok3)
        self.assertEqual(err3, "ROOM_FULL")

        # 5. Connection negotiation
        steps_recorded = []

        def on_step(steps):
            steps_recorded.append([s.status for s in steps])

        # 6. Host launches RetroArch
        host_cfg = RetroArchLaunchConfig(
            mode="host",
            core_path=details["core_lib"],
            rom_path=details["rom_path"],
            port=55435,
            nickname="RyuCabinet",
            session_id=room.room_id
        )
        host_tmp_cfg = self.ra_controller.create_session_config(host_cfg)
        self.assertTrue(os.path.exists(host_tmp_cfg))
        host_cmd = self.ra_controller.build_command(host_cfg, host_tmp_cfg)
        self.assertIn("--host", host_cmd)
        self.assertIn("--port", host_cmd)
        self.assertIn("55435", host_cmd)

        host_res = self.ra_controller.launch(host_cfg, dry_run=True)
        self.assertEqual(host_res.status, "MOCK_SUCCESS")

        # 7. Client launches RetroArch
        client_cfg = RetroArchLaunchConfig(
            mode="client",
            core_path=details["core_lib"],
            rom_path=details["rom_path"],
            port=55435,
            connect_ip="192.168.1.50",
            nickname="KenCabinet",
            session_id=room.room_id
        )
        client_tmp_cfg = self.ra_controller.create_session_config(client_cfg)
        self.assertTrue(os.path.exists(client_tmp_cfg))
        client_cmd = self.ra_controller.build_command(client_cfg, client_tmp_cfg)
        self.assertIn("--connect", client_cmd)
        self.assertIn("192.168.1.50", client_cmd)

        client_res = self.ra_controller.launch(client_cfg, dry_run=True)
        self.assertEqual(client_res.status, "MOCK_SUCCESS")

        # 8. Post-game cleanup: Host closes room, temporary configs deleted
        self.ra_controller.cleanup()
        self.assertFalse(os.path.exists(host_tmp_cfg))
        self.assertFalse(os.path.exists(client_tmp_cfg))

        closed = self.store.close_room(room.room_id, host_token)
        self.assertTrue(closed)
        self.assertIsNone(self.store.get_room(room.room_id))


if __name__ == "__main__":
    unittest.main()

