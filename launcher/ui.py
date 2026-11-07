"""Arcade Cabinet User Interface (Curses & CLI Fallback).

Implements Section 4 UX:
1. Main Screen: Game Selection (Street Fighter II default)
2. Game Action Screen: [ CARI ROOM ], [ BUAT ROOM ]
3. Cari Room Screen: Room browser with live status and 1-click join
4. Buat Room Screen: Waiting for challenger with cancel option
5. Connection Screen: Step-by-step friendly checklist (Section 4.6)
6. Error & Notification overlays
Designed for arcade joysticks and d-pads (UP, DOWN, ENTER/BTN1, ESC/BTN2).
"""

import os
import sys
import time
import logging
import subprocess
from typing import List, Optional, Callable, Dict, Any
from .connection_manager import ConnectionProgressStep

logger = logging.getLogger("Arcade.UI")


def blank_system_framebuffer() -> None:
    """Clear framebuffer and hide terminal cursor on Linux / EmuELEC."""
    try:
        sys.stdout.write("\033[2J\033[H\033[?25l")
        sys.stdout.flush()
    except Exception:
        pass

    if sys.platform.startswith("linux"):
        import shutil
        if shutil.which("emuelec-utils"):
            try:
                subprocess.run(["emuelec-utils", "blank_buffer"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1.0)
            except Exception:
                pass
        for dev in ("/dev/tty0", "/dev/tty1", "/dev/console"):
            if os.path.exists(dev) and os.access(dev, os.W_OK):
                try:
                    subprocess.run(["reset"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1.0)
                    break
                except Exception:
                    pass


class ArcadeTUI:
    """Arcade-friendly terminal UI using curses with graceful fallback."""

    def __init__(self):
        self.stdscr = None
        self.curses_available = False
        self.curses = None

    def init_curses(self) -> bool:
        """Initialize curses display."""
        blank_system_framebuffer()
        try:
            import curses
            self.curses = curses
            self.stdscr = curses.initscr()
            curses.noecho()
            curses.cbreak()
            try:
                curses.curs_set(0)
            except Exception:
                pass
            self.stdscr.keypad(True)
            self.stdscr.timeout(500)  # 500ms poll timeout

            if curses.has_colors():
                curses.start_color()
                curses.init_pair(1, curses.COLOR_YELLOW, curses.COLOR_BLUE)   # Header
                curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLACK)   # Normal
                curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_GREEN)   # Highlight
                curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)     # Error
                curses.init_pair(5, curses.COLOR_CYAN, curses.COLOR_BLACK)    # Info
                curses.init_pair(6, curses.COLOR_GREEN, curses.COLOR_BLACK)   # Success

            self.curses_available = True
            logger.debug("TUI Curses berhasil diinisialisasi.")
            return True
        except Exception as e:
            self.curses_available = False
            logger.warning(f"Curses tidak tersedia ({e}). Menggunakan mode CLI.")
            return False

    def restore_terminal(self) -> None:
        """Restore normal terminal settings and blank framebuffer for game display."""
        if self.curses_available and self.stdscr:
            try:
                self.stdscr.clear()
                self.stdscr.refresh()
            except Exception:
                pass
            try:
                import curses
                curses.nocbreak()
                self.stdscr.keypad(False)
                curses.echo()
                try:
                    curses.curs_set(0)
                except Exception:
                    pass
                curses.endwin()
                logger.debug("Terminal curses direstore ke mode standar.")
            except Exception:
                pass
            self.curses_available = False

        blank_system_framebuffer()

    def draw_box(self, title: str, lines: List[str], footer: str = "") -> None:
        """Draw a retro arcade bordered window."""
        if not self.curses_available or not self.stdscr:
            return

        self.stdscr.clear()
        h, w = self.stdscr.getmaxyx()
        box_w = min(w - 4, 60)
        box_h = min(h - 4, len(lines) + 8)
        start_y = max(1, (h - box_h) // 2)
        start_x = max(1, (w - box_w) // 2)

        # Draw border
        border = "+" + "-" * (box_w - 2) + "+"
        self.stdscr.addstr(start_y, start_x, border, self.curses.color_pair(1))

        # Title
        t_str = f" {title.upper()} "
        t_x = start_x + (box_w - len(t_str)) // 2
        self.stdscr.addstr(start_y, t_x, t_str, self.curses.color_pair(1))

        # Content lines
        curr_y = start_y + 2
        for line in lines:
            if curr_y >= start_y + box_h - 2:
                break
            padding = " " * max(0, box_w - 4 - len(line))
            self.stdscr.addstr(curr_y, start_x + 2, f"{line}{padding}"[:box_w - 4])
            curr_y += 1

        # Footer
        if footer:
            f_str = f" {footer} "
            f_x = start_x + (box_w - len(f_str)) // 2
            self.stdscr.addstr(start_y + box_h - 1, f_x, f_str, self.curses.color_pair(5))
        else:
            self.stdscr.addstr(start_y + box_h - 1, start_x, border, self.curses.color_pair(1))

        self.stdscr.refresh()

    def show_connection_screen(self, steps: List[ConnectionProgressStep],
                               error_msg: Optional[str] = None) -> None:
        """Render Section 4.6 Connection Screen checklist."""
        lines = [
            "Menghubungkan ke pemain...",
            ""
        ]

        for step in steps:
            if step.status == "completed":
                icon = "[✓]"
            elif step.status == "active":
                icon = "[..]"
            elif step.status == "failed":
                icon = "[X]"
            else:
                icon = "[ ]"
            lines.append(f" {icon} {step.label}")

        if error_msg:
            lines.append("")
            lines.append(f"PERINGATAN: {error_msg}")

        self.draw_box("KONEKSI NETPLAY", lines, "Menyiapkan pertandingan...")

    def show_message(self, title: str, message: str, wait_seconds: float = 2.0) -> None:
        """Display an informational dialog."""
        logger.info(f"UI Dialog [{title}]: {message}")
        lines = ["", message, ""]
        if self.curses_available:
            self.draw_box(title, lines, "Tekan Sembarang Tombol")
            time.sleep(wait_seconds)
        else:
            print(f"\n[{title.upper()}] {message}")
            time.sleep(wait_seconds)

    def show_log_viewer(self, get_logs_func: Callable[[], List[str]]) -> None:
        """Interactive scrollable log viewer for arcade screens."""
        if not self.curses_available or not self.stdscr:
            logs = get_logs_func()
            print("\n=== LOG SISTEM TERAKHIR ===")
            for l in logs[-30:]:
                print(l)
            print("===========================\n")
            return

        scroll_offset = 0

        while True:
            logs = get_logs_func()
            h, w = self.stdscr.getmaxyx()
            visible_lines_count = max(4, h - 8)

            total_logs = len(logs)
            if not logs:
                display_lines = ["Belum ada log tercatat."]
            else:
                max_scroll = max(0, total_logs - visible_lines_count)
                scroll_offset = min(scroll_offset, max_scroll)
                start_idx = max(0, total_logs - visible_lines_count - scroll_offset)
                end_idx = start_idx + visible_lines_count
                display_lines = logs[start_idx:end_idx]

            self.draw_box(
                "LOG SISTEM LAUNCHER",
                display_lines,
                "UP/DOWN: Gulir | ENTER/ESC: Tutup"
            )

            key = self.stdscr.getch()
            if key in (27, 10, 13, ord('q'), ord('Q'), ord(' ')):
                break
            elif key in (self.curses.KEY_UP, ord('w'), ord('W')):
                scroll_offset = min(scroll_offset + 1, max(0, len(logs) - visible_lines_count))
            elif key in (self.curses.KEY_DOWN, ord('s'), ord('S')):
                scroll_offset = max(0, scroll_offset - 1)


class ArcadeCLI:
    """Non-interactive and headless fallback UI."""

    @staticmethod
    def show_banner():
        if sys.platform == "win32":
            import os
            os.system("")  # Enable ANSI VT100 colors in Windows Command Prompt and PowerShell
        print("========================================")
        print("             ARCADE ONLINE              ")
        print("   One-Click Multiplayer RetroArch     ")
        print("========================================")

    @staticmethod
    def show_steps(steps: List[ConnectionProgressStep]):
        print("\n--- Status Koneksi ---")
        for s in steps:
            icon = "[✓]" if s.status == "completed" else ("[..]" if s.status == "active" else ("[X]" if s.status == "failed" else "[ ]"))
            print(f" {icon} {s.label}")
        print("----------------------\n")

