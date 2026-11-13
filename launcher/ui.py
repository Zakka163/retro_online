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
from .gamepad import ArcadeGamepadListener
from .retroarch_config import load_retroarch_mapping, RetroArchInputMapping

logger = logging.getLogger("Arcade.UI")


def clear_terminal_screen() -> None:
    """Clear terminal screen and hide cursor without touching raw framebuffer."""
    try:
        sys.stdout.write("\033[2J\033[H\033[?25l")
        sys.stdout.flush()
    except Exception:
        pass


class ArcadeTUI:
    """Arcade-friendly terminal UI using curses with graceful fallback."""

    def __init__(self, mapping: Optional[RetroArchInputMapping] = None):
        self.stdscr = None
        self.curses_available = False
        self.curses = None
        self.mapping = mapping if isinstance(mapping, RetroArchInputMapping) else load_retroarch_mapping()
        self.gamepad = ArcadeGamepadListener(mapping=self.mapping)

    def init_curses(self) -> bool:
        """Initialize curses display."""
        clear_terminal_screen()
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
            self.stdscr.timeout(25)  # 25ms responsive poll timeout (~40 FPS)

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
            try:
                self.gamepad.start()
            except Exception as e:
                logger.debug(f"Gamepad listener start failed: {e}")
            return True
        except Exception as e:
            self.curses_available = False
            logger.warning(f"Curses tidak tersedia ({e}). Menggunakan mode CLI.")
            return False

    def restore_terminal(self) -> None:
        """Restore normal terminal settings and clear screen for game display."""
        if self.gamepad:
            self.gamepad.stop()

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

        clear_terminal_screen()

    def pause_gamepad(self) -> None:
        """Pause gamepad listener while external emulator is running."""
        if self.gamepad:
            self.gamepad.pause()

    def resume_gamepad(self) -> None:
        """Resume gamepad listener after external emulator finishes."""
        if self.gamepad:
            self.gamepad.resume()

    def get_key(self) -> int:
        """Get next key event from either Gamepad or Keyboard."""
        if not self.curses_available or not self.stdscr:
            return -1

        # 1. Check Gamepad action first
        if self.gamepad:
            act = self.gamepad.get_action()
            if act == "UP":
                return self.curses.KEY_UP
            elif act == "DOWN":
                return self.curses.KEY_DOWN
            elif act == "LEFT":
                return self.curses.KEY_LEFT
            elif act == "RIGHT":
                return self.curses.KEY_RIGHT
            elif act == "ENTER":
                return 10
            elif act == "BACK":
                return 27

        # 2. Check Keyboard input (timeout set to 50ms)
        key = self.stdscr.getch()
        if key != -1:
            return key

        # 3. Check Gamepad again in case an action arrived during wait
        if self.gamepad:
            act = self.gamepad.get_action()
            if act == "UP":
                return self.curses.KEY_UP
            elif act == "DOWN":
                return self.curses.KEY_DOWN
            elif act == "LEFT":
                return self.curses.KEY_LEFT
            elif act == "RIGHT":
                return self.curses.KEY_RIGHT
            elif act == "ENTER":
                return 10
            elif act == "BACK":
                return 27

        return -1

    def is_up(self, key: int) -> bool:
        """Check if key corresponds to UP navigation (RetroArch & Arcade)."""
        if self.curses and key == self.curses.KEY_UP:
            return True
        return key in self.mapping.keys_up

    def is_down(self, key: int) -> bool:
        """Check if key corresponds to DOWN navigation (RetroArch & Arcade)."""
        if self.curses and key == self.curses.KEY_DOWN:
            return True
        return key in self.mapping.keys_down

    def is_left(self, key: int) -> bool:
        """Check if key corresponds to LEFT navigation (RetroArch & Arcade)."""
        if self.curses and key == self.curses.KEY_LEFT:
            return True
        return key in self.mapping.keys_left

    def is_right(self, key: int) -> bool:
        """Check if key corresponds to RIGHT navigation (RetroArch & Arcade)."""
        if self.curses and key == self.curses.KEY_RIGHT:
            return True
        return key in self.mapping.keys_right

    def is_enter(self, key: int) -> bool:
        """Check if key corresponds to ENTER / Confirm (RetroArch A/Start & Arcade P1 Start/Coin)."""
        if self.curses and key == self.curses.KEY_ENTER:
            return True
        return key in self.mapping.keys_enter

    def is_back(self, key: int) -> bool:
        """Check if key corresponds to BACK / Cancel / Exit (RetroArch B/Select & ESC/Coin/Q)."""
        return key in self.mapping.keys_back

    def draw_box(self, title: str, lines: List[str], footer: str = "") -> None:
        """Draw a clean, color-highlighted retro arcade bordered window."""
        if not self.curses_available or not self.stdscr:
            return

        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        if h < 8 or w < 24:
            self.stdscr.refresh()
            return

        box_w = min(w - 4, 74)
        inner_w = box_w - 4
        max_content = max(1, h - 6)
        visible_lines = lines[:max_content]
        box_h = min(h - 2, len(visible_lines) + 6)
        start_y = max(1, (h - box_h) // 2)
        start_x = max(1, (w - box_w) // 2)

        # Top & Bottom borders with '+' corners
        horiz = "+" + "-" * (box_w - 2) + "+"
        try:
            self.stdscr.addstr(start_y, start_x, horiz, self.curses.color_pair(1))
            self.stdscr.addstr(start_y + box_h - 1, start_x, horiz, self.curses.color_pair(1))
        except Exception:
            pass

        # Title centered on top border
        t_str = f" {title.upper()} "[:box_w - 4]
        t_x = start_x + max(1, (box_w - len(t_str)) // 2)
        try:
            self.stdscr.addstr(start_y, t_x, t_str, self.curses.color_pair(1) | self.curses.A_BOLD)
        except Exception:
            pass

        # Side borders + padded content lines
        curr_y = start_y + 2
        for y in range(start_y + 1, start_y + box_h - 1):
            try:
                self.stdscr.addstr(y, start_x, "|", self.curses.color_pair(1))
                self.stdscr.addstr(y, start_x + box_w - 1, "|", self.curses.color_pair(1))
            except Exception:
                pass

        for line in visible_lines:
            if curr_y >= start_y + box_h - 2:
                break
            text = str(line)[:inner_w]
            padded = text.ljust(inner_w)

            attr = self.curses.color_pair(2)
            stripped = text.lstrip()
            if text.startswith("> "):
                attr = self.curses.color_pair(3) | self.curses.A_BOLD
            elif stripped.startswith("---") or stripped.startswith("==="):
                attr = self.curses.color_pair(5)
            elif "Offline" in text or "PERINGATAN" in text or "TERPUTUS" in text:
                attr = self.curses.color_pair(4) | self.curses.A_BOLD
            elif text.startswith("Sinyal") or text.startswith("Layanan") or text.startswith("Room Aktif"):
                attr = self.curses.color_pair(5)

            try:
                self.stdscr.addstr(curr_y, start_x + 2, padded, attr)
            except Exception:
                pass
            curr_y += 1

        # Footer centered on bottom border
        if footer:
            f_str = f" {footer} "[:box_w - 4]
            f_x = start_x + max(1, (box_w - len(f_str)) // 2)
            try:
                self.stdscr.addstr(start_y + box_h - 1, f_x, f_str, self.curses.color_pair(5))
            except Exception:
                pass

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
        """Display an informational dialog with clean word wrapping."""
        import textwrap
        logger.info(f"UI Dialog [{title}]: {message}")
        wrapped: List[str] = [""]
        for para in str(message).splitlines() or [""]:
            wrapped.extend(textwrap.wrap(para, width=64) or [""])
        wrapped.append("")
        if self.curses_available:
            self.draw_box(title, wrapped, "Mohon tunggu...")
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
        needs_redraw = True
        last_logs_count = -1

        while True:
            logs = get_logs_func()
            if len(logs) != last_logs_count:
                needs_redraw = True
                last_logs_count = len(logs)

            if needs_redraw:
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
                needs_redraw = False

            key = self.get_key()
            if self.is_back(key) or self.is_enter(key):
                break
            elif self.is_up(key):
                scroll_offset = min(scroll_offset + 1, max(0, len(logs) - visible_lines_count))
                needs_redraw = True
            elif self.is_down(key):
                scroll_offset = max(0, scroll_offset - 1)
                needs_redraw = True


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

