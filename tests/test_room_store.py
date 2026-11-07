"""Unit tests for In-Memory Room Store."""

import time
import unittest
from server.room_store import RoomStore


class TestRoomStore(unittest.TestCase):

    def setUp(self):
        self.store = RoomStore(default_ttl=2.0)

    def test_create_and_get_room(self):
        room, host_token = self.store.create_room(
            game_id="street-fighter-ii",
            name="Ryu Arena",
            host_name="Ryu",
            compatibility={"core": "mame2003_plus", "core_version": "2003-plus"}
        )
        self.assertIsNotNone(room)
        self.assertEqual(room.game_id, "street-fighter-ii")
        self.assertEqual(room.host.name, "Ryu")
        self.assertEqual(room.status, "waiting")

        fetched = self.store.get_room(room.room_id)
        self.assertEqual(fetched.room_id, room.room_id)

    def test_join_room_success(self):
        room, _ = self.store.create_room(
            game_id="street-fighter-ii",
            name="Ryu Arena",
            host_name="Ryu",
            compatibility={"core": "mame2003_plus", "core_version": "2003-plus"}
        )
        ok, err, client = self.store.join_room(
            room_id=room.room_id,
            player_name="Ken",
            compatibility={"core": "mame2003_plus", "core_version": "2003-plus"}
        )
        self.assertTrue(ok)
        self.assertEqual(err, "OK")
        self.assertIsNotNone(client)
        self.assertEqual(client.name, "Ken")
        self.assertEqual(room.status, "connecting")

        # Second join should fail with ROOM_FULL
        ok2, err2, _ = self.store.join_room(
            room_id=room.room_id,
            player_name="Guile",
            compatibility={"core": "mame2003_plus", "core_version": "2003-plus"}
        )
        self.assertFalse(ok2)
        self.assertEqual(err2, "ROOM_FULL")

    def test_join_room_compatibility_mismatch(self):
        room, _ = self.store.create_room(
            game_id="street-fighter-ii",
            name="Ryu Arena",
            host_name="Ryu",
            compatibility={"core": "mame2003_plus", "rom_hash": "abc1234"}
        )
        # Core mismatch
        ok, err, _ = self.store.join_room(
            room_id=room.room_id,
            player_name="Ken",
            compatibility={"core": "fbalpha", "rom_hash": "abc1234"}
        )
        self.assertFalse(ok)
        self.assertEqual(err, "CORE_MISMATCH")

        # Hash mismatch
        ok2, err2, _ = self.store.join_room(
            room_id=room.room_id,
            player_name="Ken",
            compatibility={"core": "mame2003_plus", "rom_hash": "xyz9999"}
        )
        self.assertFalse(ok2)
        self.assertEqual(err2, "GAME_MISMATCH")

    def test_ttl_expiration(self):
        short_store = RoomStore(default_ttl=0.1)
        room, _ = short_store.create_room(
            game_id="street-fighter-ii",
            name="Quick Room",
            host_name="Ryu",
            compatibility={"core": "mame2003_plus"}
        )
        time.sleep(0.15)
        self.assertIsNone(short_store.get_room(room.room_id))


if __name__ == "__main__":
    unittest.main()

