"""Arcade Gamepad & USB Encoder Driver for Windows & Linux.

Reads hardware joystick events without external dependencies:
- On Linux: reads native joystick events from /dev/input/js*
- On Windows: reads DirectInput & XInput via native ctypes (winmm.dll / xinput*.dll)

Translates arcade joystick inputs (D-Pad, Stick, Buttons) into virtual actions
(UP, DOWN, LEFT, RIGHT, ENTER, BACK) so the launcher can be navigated 100%
using physical arcade controls.
"""

import os
import sys
import glob
import time
import queue
import struct
import select
import threading
import logging
from typing import Optional, Callable, Any

logger = logging.getLogger("Arcade.Gamepad")

# Linux joystick event struct format:
# uint32 time, int16 value, uint8 type, uint8 number (total 8 bytes)
JS_EVENT_FORMAT = "IhBB"
JS_EVENT_SIZE = struct.calcsize(JS_EVENT_FORMAT)

JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80


class ArcadeGamepadListener:
    """Listens for hardware arcade joystick and button presses on Windows and Linux."""

    def __init__(self, on_action: Optional[Callable[[str], None]] = None,
                 device_path: Optional[str] = None,
                 mapping: Optional[Any] = None):
        self.on_action = on_action
        self.device_path = device_path
        self._running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._js_file = None
        self._queue = queue.Queue()

        from .retroarch_config import load_retroarch_mapping, RetroArchInputMapping
        self.mapping = mapping if isinstance(mapping, RetroArchInputMapping) else load_retroarch_mapping()

        # State tracking to prevent repeated triggers
        self._axis_y_state = 0  # -1 = UP, 0 = CENTER, 1 = DOWN
        self._axis_x_state = 0  # -1 = LEFT, 0 = CENTER, 1 = RIGHT

    @staticmethod
    def find_first_joystick() -> Optional[str]:
        """Detect the first connected joystick device on Linux."""
        devices = sorted(glob.glob("/dev/input/js*"))
        if devices and os.path.exists(devices[0]) and os.access(devices[0], os.R_OK):
            return devices[0]
        return None

    def start(self) -> bool:
        """Start listening in background thread if a joystick device or API is available."""
        if self._running:
            return True

        self._running = True
        self._paused = False

        if sys.platform.startswith("win"):
            self._thread = threading.Thread(target=self._windows_read_loop, daemon=True)
            self._thread.start()
            logger.info("Arcade gamepad listener aktif (Windows DirectInput / XInput).")
            return True

        elif sys.platform.startswith("linux"):
            path = self.device_path or self.find_first_joystick()
            if not path:
                logger.debug("Tidak ada perangkat joystick /dev/input/js* ditemukan di Linux.")
                self._running = False
                return False

            try:
                self._js_file = open(path, "rb")
                self._thread = threading.Thread(target=self._linux_read_loop, daemon=True)
                self._thread.start()
                logger.info(f"Arcade gamepad listener attached to {path}")
                return True
            except Exception as e:
                logger.debug(f"Could not open joystick {path}: {e}")
                self._running = False
                return False
        else:
            logger.debug(f"Arcade gamepad listener tidak aktif pada OS: {sys.platform}")
            self._running = False
            return False

    def stop(self) -> None:
        """Stop listening and close device handles."""
        self._running = False
        if self._js_file:
            try:
                self._js_file.close()
            except Exception:
                pass
            self._js_file = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        logger.info("Arcade gamepad listener dimatikan.")

    def pause(self) -> None:
        """Temporarily pause capturing input (e.g. while RetroArch is running)."""
        self._paused = True

    def resume(self) -> None:
        """Resume capturing input and discard stale queue events."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._axis_y_state = 0
        self._axis_x_state = 0
        self._paused = False

    def get_action(self, timeout: Optional[float] = None) -> Optional[str]:
        """Retrieve next pending action ('UP', 'DOWN', 'LEFT', 'RIGHT', 'ENTER', 'BACK')."""
        try:
            return self._queue.get(block=(timeout is not None and timeout > 0), timeout=timeout)
        except queue.Empty:
            return None

    def _trigger(self, action: str) -> None:
        """Dispatch gamepad action to queue and optional callback."""
        if self._paused:
            return
        logger.debug(f"Aksi gamepad hardware: {action}")
        self._queue.put(action)
        if self.on_action:
            try:
                self.on_action(action)
            except Exception:
                pass

    def _linux_read_loop(self) -> None:
        """Process incoming 8-byte joystick event packets on Linux."""
        last_y_time = 0.0
        last_x_time = 0.0

        while self._running and self._js_file:
            if self._paused:
                time.sleep(0.1)
                continue

            try:
                rlist, _, _ = select.select([self._js_file], [], [], 0.1)
                if not rlist:
                    # Check repeat if direction is held
                    now = time.time()
                    if self._axis_y_state == -1 and (now - last_y_time > 0.35):
                        last_y_time = now - 0.20
                        self._trigger("UP")
                    elif self._axis_y_state == 1 and (now - last_y_time > 0.35):
                        last_y_time = now - 0.20
                        self._trigger("DOWN")
                    continue

                event_data = self._js_file.read(JS_EVENT_SIZE)
                if not event_data or len(event_data) < JS_EVENT_SIZE:
                    break

                _, value, event_type, number = struct.unpack(JS_EVENT_FORMAT, event_data)

                # Ignore synthetic driver init events
                if event_type & JS_EVENT_INIT:
                    continue

                if event_type & JS_EVENT_BUTTON:
                    # value: 1 = pressed, 0 = released
                    if value == 1:
                        if number in self.mapping.buttons_enter:
                            self._trigger("ENTER")
                        elif number in self.mapping.buttons_back:
                            self._trigger("BACK")
                        elif number in self.mapping.buttons_up or number in (13, 544):
                            self._trigger("UP")
                        elif number in self.mapping.buttons_down or number in (14, 545):
                            self._trigger("DOWN")
                        elif number in self.mapping.buttons_left or number in (15, 546):
                            self._trigger("LEFT")
                        elif number in self.mapping.buttons_right or number in (16, 547):
                            self._trigger("RIGHT")

                elif event_type & JS_EVENT_AXIS:
                    now = time.time()
                    matched_up = any(num == number and (sign == -1 and value < -16000 or sign == 1 and value > 16000) for num, sign in self.mapping.axes_up)
                    matched_down = any(num == number and (sign == 1 and value > 16000 or sign == -1 and value < -16000) for num, sign in self.mapping.axes_down)
                    matched_left = any(num == number and (sign == -1 and value < -16000 or sign == 1 and value > 16000) for num, sign in self.mapping.axes_left)
                    matched_right = any(num == number and (sign == 1 and value > 16000 or sign == -1 and value < -16000) for num, sign in self.mapping.axes_right)

                    if matched_up and self._axis_y_state != -1:
                        self._axis_y_state = -1
                        last_y_time = now
                        self._trigger("UP")
                    elif matched_down and self._axis_y_state != 1:
                        self._axis_y_state = 1
                        last_y_time = now
                        self._trigger("DOWN")
                    elif not matched_up and not matched_down and -8000 <= value <= 8000:
                        if number in [num for num, _ in self.mapping.axes_up + self.mapping.axes_down]:
                            self._axis_y_state = 0

                    if matched_left and self._axis_x_state != -1:
                        self._axis_x_state = -1
                        last_x_time = now
                        self._trigger("LEFT")
                    elif matched_right and self._axis_x_state != 1:
                        self._axis_x_state = 1
                        last_x_time = now
                        self._trigger("RIGHT")
                    elif not matched_left and not matched_right and -8000 <= value <= 8000:
                        if number in [num for num, _ in self.mapping.axes_left + self.mapping.axes_right]:
                            self._axis_x_state = 0

            except Exception:
                break

    def _windows_read_loop(self) -> None:
        """Poll Windows Gamepads (XInput & WinMM DirectInput) using standard ctypes."""
        import ctypes
        from ctypes import wintypes

        class JOYINFOEX(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("dwXpos", wintypes.DWORD),
                ("dwYpos", wintypes.DWORD),
                ("dwZpos", wintypes.DWORD),
                ("dwRpos", wintypes.DWORD),
                ("dwUpos", wintypes.DWORD),
                ("dwVpos", wintypes.DWORD),
                ("dwButtons", wintypes.DWORD),
                ("dwButtonNumber", wintypes.DWORD),
                ("dwPOV", wintypes.DWORD),
                ("dwReserved1", wintypes.DWORD),
                ("dwReserved2", wintypes.DWORD),
            ]

        class XINPUT_GAMEPAD(ctypes.Structure):
            _fields_ = [
                ("wButtons", wintypes.WORD),
                ("bLeftTrigger", wintypes.BYTE),
                ("bRightTrigger", wintypes.BYTE),
                ("sThumbLX", wintypes.SHORT),
                ("sThumbLY", wintypes.SHORT),
                ("sThumbRX", wintypes.SHORT),
                ("sThumbRY", wintypes.SHORT),
            ]

        class XINPUT_STATE(ctypes.Structure):
            _fields_ = [
                ("dwPacketNumber", wintypes.DWORD),
                ("Gamepad", XINPUT_GAMEPAD),
            ]

        winmm = None
        try:
            winmm = ctypes.windll.winmm
        except Exception:
            pass

        xinput = None
        for dll_name in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
            try:
                xinput = ctypes.windll.LoadLibrary(dll_name)
                break
            except Exception:
                pass

        joy_info = JOYINFOEX()
        joy_info.dwSize = ctypes.sizeof(JOYINFOEX)
        joy_info.dwFlags = 0xFF  # JOY_RETURNALL

        xinput_state = XINPUT_STATE()

        btn_enter_prev = False
        btn_back_prev = False
        last_y_time = 0.0
        last_x_time = 0.0

        while self._running:
            if self._paused:
                time.sleep(0.1)
                continue

            try:
                is_up = False
                is_down = False
                is_left = False
                is_right = False
                btn_enter = False
                btn_back = False

                # 1. Try XInput first (Xbox 360, Xbox One, modern gamepads)
                xinput_active = False
                if xinput:
                    try:
                        res = xinput.XInputGetState(0, ctypes.byref(xinput_state))
                        if res == 0:  # ERROR_SUCCESS
                            xinput_active = True
                            pad = xinput_state.Gamepad
                            wb = pad.wButtons
                            # D-Pad
                            if wb & 0x0001: is_up = True
                            if wb & 0x0002: is_down = True
                            if wb & 0x0004: is_left = True
                            if wb & 0x0008: is_right = True
                            # Left Thumbstick (threshold ~16000)
                            if pad.sThumbLY > 16000: is_up = True
                            elif pad.sThumbLY < -16000: is_down = True
                            if pad.sThumbLX < -16000: is_left = True
                            elif pad.sThumbLX > 16000: is_right = True
                            # Buttons: A (0x1000) or Start (0x0010) -> ENTER
                            if wb & 0x1010: btn_enter = True
                            # Buttons: B (0x2000) or Back (0x0020) -> BACK
                            if wb & 0x2020: btn_back = True
                    except Exception:
                        pass

                # 2. Try WinMM DirectInput (Arcade USB Encoders, Zero Delay, DragonRise, Sanwa, Xin-Mo)
                if not xinput_active and winmm:
                    try:
                        for joy_id in (0, 1):
                            if winmm.joyGetPosEx(joy_id, ctypes.byref(joy_info)) == 0:
                                # Y Axis (Center ~32767)
                                if joy_info.dwYpos < 16384: is_up = True
                                elif joy_info.dwYpos > 49152: is_down = True
                                # X Axis
                                if joy_info.dwXpos < 16384: is_left = True
                                elif joy_info.dwXpos > 49152: is_right = True

                                # POV Hat / D-Pad
                                pov = joy_info.dwPOV
                                if pov != 65535 and pov != 0xFFFF:
                                    if pov >= 31500 or pov <= 4500: is_up = True
                                    elif 13500 <= pov <= 22500: is_down = True
                                    elif 4500 < pov < 13500: is_right = True
                                    elif 22500 < pov < 31500: is_left = True

                                # Check button mapping from RetroArch or arcade standards
                                btns = joy_info.dwButtons
                                if self.mapping and self.mapping.buttons_enter:
                                    if any((btns & (1 << b)) for b in self.mapping.buttons_enter if b < 32):
                                        btn_enter = True
                                elif btns & 0x05 or btns & (1 << 6) or btns & (1 << 8):
                                    btn_enter = True

                                if self.mapping and self.mapping.buttons_back:
                                    if any((btns & (1 << b)) for b in self.mapping.buttons_back if b < 32):
                                        btn_back = True
                                elif btns & 0x0A or btns & (1 << 7) or btns & (1 << 9):
                                    btn_back = True

                                # Stick mapped to buttons
                                if self.mapping and self.mapping.buttons_up:
                                    if any((btns & (1 << b)) for b in self.mapping.buttons_up if b < 32):
                                        is_up = True
                                if self.mapping and self.mapping.buttons_down:
                                    if any((btns & (1 << b)) for b in self.mapping.buttons_down if b < 32):
                                        is_down = True
                                if self.mapping and self.mapping.buttons_left:
                                    if any((btns & (1 << b)) for b in self.mapping.buttons_left if b < 32):
                                        is_left = True
                                if self.mapping and self.mapping.buttons_right:
                                    if any((btns & (1 << b)) for b in self.mapping.buttons_right if b < 32):
                                        is_right = True

                                # Fallback checks for common arcade buttons (Button 0, 1, 2, 7, 8, 9)
                                if btns & 0x01 or btns & (1 << 6) or btns & (1 << 8):
                                    btn_enter = True
                                if btns & 0x02 or btns & (1 << 7) or btns & (1 << 9):
                                    btn_back = True
                                break
                    except Exception:
                        pass

                # Button transitions (edge triggered)
                if btn_enter and not btn_enter_prev:
                    self._trigger("ENTER")
                btn_enter_prev = btn_enter

                if btn_back and not btn_back_prev:
                    self._trigger("BACK")
                btn_back_prev = btn_back

                # Direction navigation (with auto-repeat on hold)
                now = time.time()
                if is_up:
                    if self._axis_y_state != -1:
                        self._axis_y_state = -1
                        last_y_time = now
                        self._trigger("UP")
                    elif now - last_y_time > 0.35:
                        last_y_time = now - 0.20
                        self._trigger("UP")
                elif is_down:
                    if self._axis_y_state != 1:
                        self._axis_y_state = 1
                        last_y_time = now
                        self._trigger("DOWN")
                    elif now - last_y_time > 0.35:
                        last_y_time = now - 0.20
                        self._trigger("DOWN")
                else:
                    self._axis_y_state = 0

                if is_left:
                    if self._axis_x_state != -1:
                        self._axis_x_state = -1
                        last_x_time = now
                        self._trigger("LEFT")
                    elif now - last_x_time > 0.35:
                        last_x_time = now - 0.20
                        self._trigger("LEFT")
                elif is_right:
                    if self._axis_x_state != 1:
                        self._axis_x_state = 1
                        last_x_time = now
                        self._trigger("RIGHT")
                    elif now - last_x_time > 0.35:
                        last_x_time = now - 0.20
                        self._trigger("RIGHT")
                else:
                    self._axis_x_state = 0

            except Exception:
                pass

            time.sleep(0.02)  # 50 Hz responsive polling
