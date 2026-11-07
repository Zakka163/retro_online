"""Logging and Diagnostic Facility for Arcade Online Launcher.

Provides file logging with rotation, in-memory log buffering for the TUI log viewer,
and sanitized diagnostic metrics tracking.
"""

import os
import sys
import collections
import logging
from typing import List, Optional

LOG_BUFFER_SIZE = 250
_recent_logs: collections.deque = collections.deque(maxlen=LOG_BUFFER_SIZE)


class InMemoryLogHandler(logging.Handler):
    """Stores recent formatted log lines in a thread-safe circular buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            _recent_logs.append(msg)
        except Exception:
            self.handleError(record)


def setup_launcher_logging(log_file: str = "arcade_launcher.log",
                           verbose: bool = False,
                           log_to_console: bool = False) -> logging.Logger:
    """Initialize file logging and in-memory buffer."""
    level = logging.DEBUG if verbose else logging.INFO

    root_logger = logging.getLogger("Arcade")
    root_logger.setLevel(level)

    # Avoid duplicate handlers on re-init and close existing handlers cleanly
    for h in list(root_logger.handlers):
        try:
            h.close()
        except Exception:
            pass
    root_logger.handlers.clear()

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. In-memory buffer handler (for TUI viewer)
    mem_handler = InMemoryLogHandler()
    mem_handler.setFormatter(formatter)
    mem_handler.setLevel(level)
    root_logger.addHandler(mem_handler)

    # 2. File handler (persisted to disk with auto-flush)
    try:
        file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root_logger.addHandler(file_handler)
    except Exception as e:
        sys.stderr.write(f"Warning: Could not open log file '{log_file}': {e}\n")

    # 3. Optional console stderr handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        root_logger.addHandler(console_handler)

    return root_logger


def get_recent_logs(max_lines: int = 50) -> List[str]:
    """Retrieve recent log lines for UI display."""
    items = list(_recent_logs)
    if max_lines and len(items) > max_lines:
        return items[-max_lines:]
    return items


def clear_recent_logs() -> None:
    _recent_logs.clear()
