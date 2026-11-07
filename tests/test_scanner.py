"""Unit tests for Dynamic Core and ROM Auto-Scanner."""

import os
import tempfile
import unittest
from catalog.scanner import SystemScanner, ARCADE_DATABASE
from catalog.validator import GameManifest


class TestSystemScanner(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cores_dir = os.path.join(self.temp_dir.name, "cores")
        self.roms_dir = os.path.join(self.temp_dir.name, "roms")
        os.makedirs(self.cores_dir, exist_ok=True)
        os.makedirs(self.roms_dir, exist_ok=True)

        # Create dummy core libraries
        for cname in ["mame2003_plus_libretro.so", "fbneo_libretro.so"]:
            with open(os.path.join(self.cores_dir, cname), "wb") as f:
                f.write(b"\x7fELF MOCK CORE")

        # Create dummy ROM files
        for rname in ["sf2.zip", "mslug.zip", "custom_game.zip"]:
            with open(os.path.join(self.roms_dir, rname), "wb") as f:
                f.write(b"PK MOCK ROM ARCHIVE")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_scan_installed_cores(self):
        scanner = SystemScanner(
            custom_core_dirs=[self.cores_dir],
            custom_rom_dirs=[self.roms_dir]
        )
        cores = scanner.scan_installed_cores()
        self.assertIn("mame2003_plus", cores)
        self.assertIn("fbneo", cores)

    def test_scan_and_identify_roms(self):
        scanner = SystemScanner(
            custom_core_dirs=[self.cores_dir],
            custom_rom_dirs=[self.roms_dir]
        )
        games = scanner.scan_roms()

        # Check sf2 identified
        self.assertIn("sf2", games)
        self.assertEqual(games["sf2"].display_name, ARCADE_DATABASE["sf2"])
        self.assertEqual(games["sf2"].status, "ready")

        # Check mslug identified
        self.assertIn("mslug", games)
        self.assertEqual(games["mslug"].display_name, ARCADE_DATABASE["mslug"])
        self.assertEqual(games["mslug"].status, "ready")

        # Check unlisted custom arcade game auto-named
        self.assertIn("custom_game", games)
        self.assertIn("CUSTOM_GAME", games["custom_game"].display_name)
        self.assertEqual(games["custom_game"].status, "ready")

    def test_manifest_scan_and_merge(self):
        manifest = GameManifest(auto_scan=False)
        initial_count = len(manifest.list_games())

        scanner = SystemScanner(
            custom_core_dirs=[self.cores_dir],
            custom_rom_dirs=[self.roms_dir]
        )
        manifest.scan_and_merge(scanner)

        # After merge, mslug and custom_game should now be part of manifest
        self.assertIsNotNone(manifest.get_game("mslug"))
        self.assertIsNotNone(manifest.get_game("custom_game"))
        self.assertGreater(len(manifest.list_games()), initial_count)


if __name__ == "__main__":
    unittest.main()

