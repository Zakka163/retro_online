"""Arcade Gamepad & USB Encoder Driver for Linux / Batocera.

Reads native Linux joystick events from /dev/input/js* without external dependencies.
Translates arcade joystick inputs (D-Pad, Stick, Buttons) into virtual key events
so the launcher can be navigated 100% using physical arcade controls.
"""

import os
import sys
import glob
import struct
import select
import threading
import logging
from typing import Optional, Callable

logger = logging.getLogger("Arcade.Gamepad")

# Linux joystick event struct format:
# uint32 time, int16 value, uint8 type, uint8 number (total 8 bytes)
JS_EVENT_FORMAT = "IhBB"
JS_EVENT_SIZE = struct.calcsize(JS_EVENT_FORMAT)

JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80


class ArcadeGamepadListener:
    """Listens for hardware arcade joystick and button presses on Linux."""

    def __init__(self, on_action: Optional[Callable[[str], None]] = None, device_path: Optional[str] = None):
        self.on_action = on_action
        self.device_path = device_path
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._js_file = None

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
        """Start listening in background thread if a joystick device is available."""
        if sys.platform != "linux":
            # On non-Linux (e.g. macOS testing), joystick via /dev/input is not available
            return False

        path = self.device_path or self.find_first_joystick()
        if not path:
            return False

        try:
            self._js_file = open(path, "rb")
            self._running = True
            self._thread = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()
            logger.info(f"Arcade gamepad listener attached to {path}")
            return True
        except Exception as e:
            logger.debug(f"Could not open joystick {path}: {e}")
            return False

    def stop(self) -> None:
        """Stop listening and close device file."""
        self._running = False
        if self._js_file:
            try:
                self._js_file.close()
            except Exception:
                pass
            self._js_file = None
            logger.info("Arcade gamepad listener dimatikan.")

    def _trigger(self, action: str) -> None:
        logger.debug(f"Aksi gamepad hardware: {action}")
        if self.on_action:
            try:
                self.on_action(action)
            except Exception:
                pass

    def _read_loop(self) -> None:
        """Process incoming 8-byte joystick event packets."""
        while self._running and self._js_file:
            try:
                rlist, _, _ = select.select([self._js_file], [], [], 0.5)
                if not rlist:
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
                        if number in (0, 1, 6):  # Button 1 / Start / A
                            self._trigger("ENTER")
                        elif number in (2, 3, 7, 8):  # Button 2 / B / Coin / Back
                            self._trigger("BACK")

                elif event_type & JS_EVENT_AXIS:
                    # Axis 1 = Vertical (Y), Axis 0 = Horizontal (X)
                    # Standard axes: -32767 is UP/LEFT, +32767 is DOWN/RIGHT
                    if number in (1, 5, 7):  # Y-axis (D-Pad or Stick)
                        if value < -16000 and self._axis_y_state != -1:
                            self._axis_y_state = -1
                            self._trigger("UP")
                        elif value > 16000 and self._axis_y_state != 1:
                            self._axis_y_state = 1
                            self._trigger("DOWN")
                        elif -8000 <= value <= 8000:
                            self._axis_y_state = 0

                    elif number in (0, 4, 6):  # X-axis
                        if value < -16000 and self._axis_x_state != -1:
                            self._axis_x_state = -1
                            self._trigger("LEFT")
                        elif value > 16000 and self._axis_x_state != 1:
                            self._axis_x_state = 1
                            self._trigger("RIGHT")
                        elif -8000 <= value <= 8000:
                            self._axis_x_state = 0

            except Exception:
                break

