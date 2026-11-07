"""Unit tests for Launcher Logging and In-Memory Buffer."""

import os
import tempfile
import unittest
import logging

from launcher.logger import setup_launcher_logging, get_recent_logs, clear_recent_logs


class TestLauncherLogger(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_path = os.path.join(self.temp_dir.name, "test_launcher.log")
        clear_recent_logs()

    def tearDown(self):
        arcade_logger = logging.getLogger("Arcade")
        for h in list(arcade_logger.handlers):
            try:
                h.close()
            except Exception:
                pass
        arcade_logger.handlers.clear()
        self.temp_dir.cleanup()

    def test_setup_logging_and_file_write(self):
        logger = setup_launcher_logging(log_file=self.log_path, verbose=True)
        logger.info("Test arcade log line 1")
        logger.warning("Test arcade warning 2")

        self.assertTrue(os.path.exists(self.log_path))
        with open(self.log_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Test arcade log line 1", content)
            self.assertIn("Test arcade warning 2", content)

    def test_in_memory_log_buffer(self):
        logger = setup_launcher_logging(log_file=self.log_path)
        logger.info("Buffer entry alpha")
        logger.info("Buffer entry beta")

        recent = get_recent_logs(10)
        self.assertTrue(any("Buffer entry alpha" in l for l in recent))
        self.assertTrue(any("Buffer entry beta" in l for l in recent))


if __name__ == "__main__":
    unittest.main()

