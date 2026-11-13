"""RetroArch Configuration & Input Mapping Parser.

Extracts user keyboard bindings and joystick configurations from retroarch.cfg
and autoconfig profiles so the launcher shares the exact same control scheme
as the in-game RetroArch experience.
"""

import os
import sys
import glob
import logging
import platform
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Set

logger = logging.getLogger("Arcade.Input")


def find_retroarch_cfg(retroarch_bin: Optional[str] = None) -> Optional[str]:
    """Find user's active retroarch.cfg across platforms."""
    # 1. Environment variable override
    env_cfg = os.environ.get("ARCADE_RETROARCH_CFG") or os.environ.get("RETROARCH_CFG")
    if env_cfg and os.path.isfile(env_cfg):
        return env_cfg

    # 2. Next to retroarch binary
    if retroarch_bin and os.path.isfile(retroarch_bin):
        bin_dir = os.path.dirname(retroarch_bin)
        candidate = os.path.join(bin_dir, "retroarch.cfg")
        if os.path.isfile(candidate):
            return candidate

    system = platform.system()
    candidates = []

    if system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        localappdata = os.environ.get("LOCALAPPDATA", "")
        userprofile = os.environ.get("USERPROFILE", "")
        prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        prog_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        candidates = [
            r"C:\RetroArch-Win64\retroarch.cfg",
            r"C:\RetroArch\retroarch.cfg",
            r"D:\RetroArch-Win64\retroarch.cfg",
            r"D:\RetroArch\retroarch.cfg",
            os.path.join(appdata, "RetroArch", "retroarch.cfg"),
            os.path.join(localappdata, "RetroArch", "retroarch.cfg"),
            os.path.join(prog_files, "RetroArch", "retroarch.cfg"),
            os.path.join(prog_files_x86, "RetroArch", "retroarch.cfg"),
            os.path.join(userprofile, "RetroArch", "retroarch.cfg"),
        ]
    elif system == "Darwin":
        candidates = [
            os.path.expanduser("~/Library/Application Support/RetroArch/config/retroarch.cfg"),
            os.path.expanduser("~/Library/Application Support/RetroArch/retroarch.cfg"),
            os.path.expanduser("~/.config/retroarch/retroarch.cfg"),
        ]
    elif system == "Linux":
        candidates = [
            "/userdata/system/configs/retroarch/retroarch.cfg",  # Batocera
            "/storage/.config/retroarch/retroarch.cfg",          # EmuELEC
            "/opt/retropie/configs/all/retroarch.cfg",           # RetroPie
            os.path.expanduser("~/.config/retroarch/retroarch.cfg"),
            os.path.expanduser("~/.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg"),
        ]

    for c in candidates:
        if c and os.path.isfile(c):
            return c

    return None


def parse_retroarch_cfg(cfg_path: str) -> Dict[str, str]:
    """Parse retroarch.cfg into key-value map."""
    cfg = {}
    if not cfg_path or not os.path.isfile(cfg_path):
        return cfg

    try:
        with open(cfg_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip()
                    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
                        v = v[1:-1]
                    cfg[k] = v
    except Exception as e:
        logger.debug(f"Error parsing retroarch.cfg ({cfg_path}): {e}")

    return cfg


def retroarch_key_to_codes(key_name: str) -> List[int]:
    """Map RetroArch key identifier to integer keycodes."""
    if not key_name or key_name in ("nul", "null", "none"):
        return []

    k = key_name.lower().strip()
    codes = []

    # Arrow keys & D-pad
    if k in ("up", "kp_up", "keypad_up", "kp8", "num8"):
        codes.extend([259, 450])
    elif k in ("down", "kp_down", "keypad_down", "kp2", "num2"):
        codes.extend([258, 449])
    elif k in ("left", "kp_left", "keypad_left", "kp4", "num4"):
        codes.extend([260, 452])
    elif k in ("right", "kp_right", "keypad_right", "kp6", "num6"):
        codes.extend([261, 451])
    # Action keys
    elif k in ("enter", "return", "kp_enter", "keypad_enter"):
        codes.extend([10, 13])
    elif k in ("escape", "esc"):
        codes.append(27)
    elif k == "space":
        codes.append(ord(" "))
    elif k == "tab":
        codes.append(9)
    elif k in ("backspace", "bksp"):
        codes.extend([8, 127])
    # Single character: e.g. "z", "x", "w", "s", "1", "5"
    elif len(k) == 1:
        codes.extend([ord(k.lower()), ord(k.upper())])

    return codes


def _parse_axis_str(axis_str: str) -> Optional[Tuple[int, int]]:
    """Parse RetroArch axis string like '+1', '-1', '+0', '-0' into (axis_num, sign)."""
    if not axis_str:
        return None
    s = axis_str.strip()
    sign = 1
    if s.startswith("-"):
        sign = -1
        s = s[1:]
    elif s.startswith("+"):
        sign = 1
        s = s[1:]
    try:
        axis_num = int(s)
        return (axis_num, sign)
    except ValueError:
        return None


@dataclass
class RetroArchInputMapping:
    """Active input mapping from RetroArch or arcade cabinet defaults."""
    cfg_file_used: Optional[str] = None

    # Keycodes for UI navigation
    keys_up: Set[int] = field(default_factory=set)
    keys_down: Set[int] = field(default_factory=set)
    keys_left: Set[int] = field(default_factory=set)
    keys_right: Set[int] = field(default_factory=set)
    keys_enter: Set[int] = field(default_factory=set)
    keys_back: Set[int] = field(default_factory=set)

    # Gamepad Button indices (0-based)
    buttons_enter: Set[int] = field(default_factory=set)
    buttons_back: Set[int] = field(default_factory=set)
    buttons_up: Set[int] = field(default_factory=set)
    buttons_down: Set[int] = field(default_factory=set)
    buttons_left: Set[int] = field(default_factory=set)
    buttons_right: Set[int] = field(default_factory=set)

    # Gamepad Axes as (axis_idx, sign)
    axes_up: List[Tuple[int, int]] = field(default_factory=list)
    axes_down: List[Tuple[int, int]] = field(default_factory=list)
    axes_left: List[Tuple[int, int]] = field(default_factory=list)
    axes_right: List[Tuple[int, int]] = field(default_factory=list)

    # RetroArch Hotkey & Exit buttons (for display/diagnostics)
    hotkey_btn: Optional[str] = None
    exit_btn: Optional[str] = None
    button_names: Dict[int, str] = field(default_factory=dict)

    def get_button_name(self, btn_idx: int) -> str:
        """Return a human-readable label for a hardware button index."""
        if btn_idx in self.button_names:
            return self.button_names[btn_idx]
        defaults = {
            0: "A", 1: "B", 2: "X", 3: "Y",
            4: "L1", 5: "R1", 6: "L2", 7: "R2",
            8: "SELECT", 9: "START", 10: "L3", 11: "R3",
            12: "HOME", 13: "ATAS", 14: "BAWAH", 15: "KIRI", 16: "KANAN",
        }
        return defaults.get(btn_idx, f"Tombol {chr(65 + (btn_idx % 26))}")


def load_retroarch_mapping(retroarch_bin: Optional[str] = None,
                           custom_cfg_path: Optional[str] = None) -> RetroArchInputMapping:
    """Load and merge user RetroArch control bindings with arcade cabinet standards."""
    mapping = RetroArchInputMapping()

    # 1. Populate comprehensive Arcade & Keyboard defaults first
    # Up: Arrow Up (259/450), W, K, Numpad 8
    mapping.keys_up.update([259, 450, ord('w'), ord('W'), ord('k'), ord('K'), ord('8')])
    # Down: Arrow Down (258/449), S, J, Numpad 2
    mapping.keys_down.update([258, 449, ord('s'), ord('S'), ord('j'), ord('J'), ord('2')])
    # Left: Arrow Left (260/452), A, H, Numpad 4
    mapping.keys_left.update([260, 452, ord('a'), ord('A'), ord('h'), ord('H'), ord('4')])
    # Right: Arrow Right (261/451), D, L, Numpad 6
    mapping.keys_right.update([261, 451, ord('d'), ord('D'), ord('l'), ord('L'), ord('6')])

    # Enter / Confirm:
    # 10, 13 (Enter), Space, '1' (Player 1 Start - Arcade cabinet standard!), 'z', 'Z', 'c', 'C'
    mapping.keys_enter.update([10, 13, ord(' '), ord('1'), ord('z'), ord('Z'), ord('c'), ord('C')])

    # Back / Cancel:
    # 27 (ESC), 'q', 'Q', '5' (Coin 1 - Arcade cabinet standard!), 'x', 'X', 'b', 'B'
    mapping.keys_back.update([27, ord('q'), ord('Q'), ord('5'), ord('x'), ord('X'), ord('b'), ord('B')])

    # Default Gamepad buttons
    # Button 0 (A), 1 (B), 2 (X), 6 (Select), 7 (Start), 8 (Coin), 9 (P1 Start)
    mapping.buttons_enter.update([0, 1, 2, 6, 8, 9])
    mapping.buttons_back.update([1, 2, 3, 7, 8, 10])

    # Default Gamepad axes
    mapping.axes_up.extend([(1, -1), (5, -1), (7, -1)])
    mapping.axes_down.extend([(1, 1), (5, 1), (7, 1)])
    mapping.axes_left.extend([(0, -1), (4, -1), (6, -1)])
    mapping.axes_right.extend([(0, 1), (4, 1), (6, 1)])

    # 2. Search for user's retroarch.cfg
    cfg_path = custom_cfg_path or find_retroarch_cfg(retroarch_bin)
    if cfg_path and os.path.isfile(cfg_path):
        logger.info(f"Memuat konfigurasi kontrol dari RetroArch: {cfg_path}")
        mapping.cfg_file_used = cfg_path
        cfg_data = parse_retroarch_cfg(cfg_path)

        # Parse Keyboard Bindings
        p1_up = cfg_data.get("input_player1_up")
        if p1_up:
            mapping.keys_up.update(retroarch_key_to_codes(p1_up))

        p1_down = cfg_data.get("input_player1_down")
        if p1_down:
            mapping.keys_down.update(retroarch_key_to_codes(p1_down))

        p1_left = cfg_data.get("input_player1_left")
        if p1_left:
            mapping.keys_left.update(retroarch_key_to_codes(p1_left))

        p1_right = cfg_data.get("input_player1_right")
        if p1_right:
            mapping.keys_right.update(retroarch_key_to_codes(p1_right))

        p1_a = cfg_data.get("input_player1_a")
        if p1_a:
            mapping.keys_enter.update(retroarch_key_to_codes(p1_a))

        p1_start = cfg_data.get("input_player1_start")
        if p1_start:
            mapping.keys_enter.update(retroarch_key_to_codes(p1_start))

        p1_b = cfg_data.get("input_player1_b")
        if p1_b:
            mapping.keys_back.update(retroarch_key_to_codes(p1_b))

        p1_select = cfg_data.get("input_player1_select")
        if p1_select:
            mapping.keys_back.update(retroarch_key_to_codes(p1_select))

        # Parse Joypad Buttons
        for key, btn_set in [
            ("input_player1_a_btn", mapping.buttons_enter),
            ("input_player1_start_btn", mapping.buttons_enter),
            ("input_player1_b_btn", mapping.buttons_back),
            ("input_player1_select_btn", mapping.buttons_back),
            ("input_player1_up_btn", mapping.buttons_up),
            ("input_player1_down_btn", mapping.buttons_down),
            ("input_player1_left_btn", mapping.buttons_left),
            ("input_player1_right_btn", mapping.buttons_right),
        ]:
            val = cfg_data.get(key)
            if val and val.isdigit():
                btn_set.add(int(val))

        # Parse Joypad Axes
        for key, axis_list in [
            ("input_player1_up_axis", mapping.axes_up),
            ("input_player1_down_axis", mapping.axes_down),
            ("input_player1_left_axis", mapping.axes_left),
            ("input_player1_right_axis", mapping.axes_right),
        ]:
            val = cfg_data.get(key)
            if val:
                parsed_ax = _parse_axis_str(val)
                if parsed_ax and parsed_ax not in axis_list:
                    axis_list.insert(0, parsed_ax)

        # Map human-readable button labels from retroarch.cfg
        for cfg_key, label in [
            ("input_player1_a_btn", "A"),
            ("input_player1_b_btn", "B"),
            ("input_player1_x_btn", "X"),
            ("input_player1_y_btn", "Y"),
            ("input_player1_l_btn", "L1"),
            ("input_player1_r_btn", "R1"),
            ("input_player1_l2_btn", "L2"),
            ("input_player1_r2_btn", "R2"),
            ("input_player1_l3_btn", "L3"),
            ("input_player1_r3_btn", "R3"),
            ("input_player1_select_btn", "SELECT"),
            ("input_player1_start_btn", "START"),
            ("input_player1_up_btn", "ATAS"),
            ("input_player1_down_btn", "BAWAH"),
            ("input_player1_left_btn", "KIRI"),
            ("input_player1_right_btn", "KANAN"),
        ]:
            val = cfg_data.get(cfg_key)
            if val and val.isdigit():
                mapping.button_names[int(val)] = label

        mapping.hotkey_btn = cfg_data.get("input_enable_hotkey_btn")
        mapping.exit_btn = cfg_data.get("input_exit_emulator_btn")

    return mapping

