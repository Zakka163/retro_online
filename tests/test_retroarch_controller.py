"""Unit tests for RetroArch Controller."""

import os
import unittest
from unittest.mock import MagicMock, patch
from launcher.retroarch_controller import (
    RetroArchController,
    RetroArchLaunchConfig,
)


class TestRetroArchController(unittest.TestCase):

    def setUp(self):
        self.controller = RetroArchController(retroarch_bin="/usr/bin/retroarch")

    def tearDown(self):
        self.controller.cleanup()

    def test_build_host_command(self):
        cfg = RetroArchLaunchConfig(
            mode="host",
            core_path="/usr/lib/libretro/mame2003_plus_libretro.so",
            rom_path="/roms/sf2.zip",
            port=55435,
            nickname="Player1",
            session_id="test1234"
        )
        temp_cfg = self.controller.create_session_config(cfg)
        self.assertTrue(os.path.exists(temp_cfg))

        with open(temp_cfg, "r") as f:
            content = f.read()
            self.assertIn('netplay_mode = "false"', content)
            self.assertIn('netplay_ip_port = "55435"', content)
            self.assertIn('netplay_nickname = "Player1"', content)

        cmd = self.controller.build_command(cfg, temp_cfg)
        self.assertEqual(cmd[0], "/usr/bin/retroarch")
        self.assertIn("-v", cmd)
        self.assertIn("-L", cmd)
        self.assertIn("/usr/lib/libretro/mame2003_plus_libretro.so", cmd)
        self.assertIn("/roms/sf2.zip", cmd)
        self.assertIn("--host", cmd)
        self.assertIn("--port", cmd)
        self.assertIn("55435", cmd)
        self.assertIn("--nick", cmd)
        self.assertIn("Player1", cmd)
        self.assertIn("--appendconfig", cmd)

        self.controller.cleanup()
        self.assertFalse(os.path.exists(temp_cfg))

    def test_build_client_command(self):
        cfg = RetroArchLaunchConfig(
            mode="client",
            core_path="/usr/lib/libretro/mame2003_plus_libretro.so",
            rom_path="/roms/sf2.zip",
            port=55435,
            connect_ip="192.168.1.100",
            nickname="Player2",
            session_id="test5678"
        )
        temp_cfg = self.controller.create_session_config(cfg)
        with open(temp_cfg, "r") as f:
            content = f.read()
            self.assertIn('netplay_mode = "true"', content)
            self.assertIn('netplay_ip_address = "192.168.1.100"', content)

        cmd = self.controller.build_command(cfg, temp_cfg)

        self.assertIn("-v", cmd)
        self.assertIn("--connect", cmd)
        self.assertIn("192.168.1.100", cmd)
        self.assertNotIn("--host", cmd)

        self.controller.cleanup()

    def test_client_missing_connect_ip_raises(self):
        cfg = RetroArchLaunchConfig(
            mode="client",
            core_path="/core.so",
            rom_path="/sf2.zip",
            connect_ip=None
        )
        temp_cfg = self.controller.create_session_config(cfg)
        with self.assertRaises(ValueError):
            self.controller.build_command(cfg, temp_cfg)
        self.controller.cleanup()

    def test_mock_launch(self):
        cfg = RetroArchLaunchConfig(
            mode="host",
            core_path="/core.so",
            rom_path="/sf2.zip",
            session_id="mock"
        )
        started = []
        result = self.controller.launch(
            cfg,
            on_started=lambda: started.append(True),
            dry_run=True
        )
        self.assertEqual(result.status, "MOCK_SUCCESS")
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(len(started) == 1)

    def test_auto_resolve_retroarch_bin(self):
        # When retroarch_bin is None, controller automatically resolves or falls back
        controller = RetroArchController(retroarch_bin=None)
        cfg = RetroArchLaunchConfig(
            mode="host",
            core_path="/core.so",
            rom_path="/sf2.zip"
        )
        temp_cfg = controller.create_session_config(cfg)
        cmd = controller.build_command(cfg, temp_cfg)
        self.assertTrue(len(cmd[0]) > 0)
        controller.cleanup()

    def test_override_retroarch_bin_in_launch_config(self):
        cfg = RetroArchLaunchConfig(
            mode="host",
            core_path="/core.so",
            rom_path="/sf2.zip",
            retroarch_bin="/custom/path/to/retroarch"
        )
        temp_cfg = self.controller.create_session_config(cfg)
        cmd = self.controller.build_command(cfg, temp_cfg)
        self.assertEqual(cmd[0], "/custom/path/to/retroarch")
        self.controller.cleanup()

    def test_launch_nonexistent_binary_returns_failed(self):
        cfg = RetroArchLaunchConfig(
            mode="host",
            core_path="/core.so",
            rom_path="/sf2.zip",
            retroarch_bin="/non/existent/path/retroarch_never_exists_12345"
        )
        result = self.controller.launch(cfg, dry_run=False)
        self.assertEqual(result.status, "FAILED")
        self.assertEqual(result.exit_code, -1)
        self.assertIn("Executable RetroArch tidak ditemukan", result.error_message)

    @patch("subprocess.Popen")
    @patch("os.path.isfile", return_value=True)
    def test_terminated_process_returns_completed_status(self, mock_isfile, mock_popen):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("", "")
        mock_proc.returncode = 1  # Exit code 1 as in Windows TerminateProcess
        mock_popen.return_value = mock_proc

        cfg = RetroArchLaunchConfig(
            mode="host",
            core_path="/core.so",
            rom_path="/sf2.zip",
            retroarch_bin="/usr/bin/retroarch"
        )
        # Simulate supervisor calling terminate while process was running
        self.controller.active_process = mock_proc
        self.controller.terminate()
        self.assertTrue(self.controller._was_terminated)

        # Force _was_terminated to remain True for this test run
        def set_proc():
            self.controller.active_process = mock_proc
            self.controller._was_terminated = True

        result = self.controller.launch(cfg, on_started=set_proc)
        self.assertEqual(result.status, "COMPLETED")
        self.assertEqual(result.exit_code, 1)
        self.assertIsNone(result.error_message)


if __name__ == "__main__":
    unittest.main()

