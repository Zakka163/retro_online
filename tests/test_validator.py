"""Unit tests for Game Catalog and Dynamic Resource Validator."""

import os
import tempfile
import unittest
from catalog.validator import (
    GameManifest,
    CatalogValidator,
    calculate_file_hashes,
    find_retroarch_binary,
    find_core_library,
)
from catalog.scanner import SystemScanner


class TestCatalogValidator(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.roms_dir = os.path.join(self.temp_dir.name, "roms")
        os.makedirs(self.roms_dir, exist_ok=True)

        # Create a sample ROM on disk
        self.sf2_path = os.path.join(self.roms_dir, "sf2.zip")
        with open(self.sf2_path, "wb") as f:
            f.write(b"MOCK_SF2_ROM_DATA_HADOUKEN")

        self.scanner = SystemScanner(custom_rom_dirs=[self.roms_dir])
        self.manifest = GameManifest(auto_scan=False)
        self.manifest.scan_and_merge(self.scanner)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_dynamic_scan_populates_game(self):
        # Verify sf2 was discovered dynamically from disk, not hardcoded
        sf2 = self.manifest.get_game("sf2")
        self.assertIsNotNone(sf2)
        self.assertEqual(sf2["rom_file"], "sf2.zip")
        self.assertEqual(sf2["rom_path"], self.sf2_path)
        self.assertIn("Street Fighter II", sf2["display_name"])

    def test_calculate_file_hashes(self):
        hashes = calculate_file_hashes(self.sf2_path)
        self.assertIn("sha1", hashes)
        self.assertIn("md5", hashes)
        self.assertIn("crc32", hashes)
        self.assertEqual(len(hashes["sha1"]), 40)
        self.assertEqual(len(hashes["md5"]), 32)
        self.assertEqual(len(hashes["crc32"]), 8)

    def test_mock_environment_verification(self):
        os.environ["ARCADE_MOCK_RETROARCH"] = "1"
        try:
            ra_bin = find_retroarch_binary()
            self.assertIsNotNone(ra_bin)

            core = find_core_library("mame2003_plus")
            self.assertIsNotNone(core)

            validator = CatalogValidator(
                manifest=self.manifest,
                rom_dirs=[self.roms_dir]
            )

            valid, code, details = validator.verify_local_game("sf2", strict_hash=False)
            self.assertTrue(valid)
            self.assertEqual(code, "OK")
            self.assertEqual(details["rom_path"], self.sf2_path)

            # Test peer compatibility check
            compat_valid, err = validator.check_peer_compatibility(
                "sf2",
                {
                    "core": "mame2003_plus",
                    "core_version": "auto"
                }
            )
            self.assertTrue(compat_valid)

            # Core mismatch test
            mismatch_valid, err = validator.check_peer_compatibility(
                "sf2",
                {
                    "core": "snes9x",
                    "core_version": "1.60"
                }
            )
            self.assertFalse(mismatch_valid)
            self.assertEqual(err, "CORE_MISMATCH")

        finally:
            os.environ.pop("ARCADE_MOCK_RETROARCH", None)


if __name__ == "__main__":
    unittest.main()
