"""RetroArch Controller and Supervisor.

Responsible for building temporary session configurations, constructing command
arguments for Host and Client Netplay modes, supervising process execution,
and safely cleaning up temporary resources upon session termination.
"""

import os
import sys
import time
import signal
import tempfile
import subprocess
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable

logger = logging.getLogger("Arcade.RetroArch")


@dataclass
class RetroArchLaunchConfig:
    """Configuration parameters for launching a RetroArch Netplay session."""
    mode: str                       # 'host', 'client', or 'offline'
    core_path: str                  # Absolute path to libretro core (.so / .dylib)
    rom_path: str                   # Absolute path to ROM file
    port: int = 55435               # Netplay port
    connect_ip: Optional[str] = None# Target IP/hostname (client mode only)
    nickname: str = "ArcadePlayer"  # Netplay nickname
    check_frames: int = 30          # Netplay sync check frames (30 = checks every 0.5s)
    input_latency_frames: int = 2   # Netplay input delay frames (2 = 33ms buffer to prevent rollback desync)
    stateless_mode: bool = False    # True = 100% lockstep determinism; False = rollback
    sync_sram: bool = True          # True = sync host save RAM to client on connect
    session_id: str = "default"     # Unique session ID
    fullscreen: bool = True         # Run fullscreen
    retroarch_bin: Optional[str] = None # Path to RetroArch executable
    extra_args: List[str] = field(default_factory=list)


@dataclass
class RetroArchProcessResult:
    """Result and metrics of a finished RetroArch session."""
    exit_code: int
    duration_seconds: float
    status: str                     # 'COMPLETED', 'FAILED', 'KILLED', 'MOCK_SUCCESS'
    error_message: Optional[str] = None


class RetroArchController:
    """Manages RetroArch lifecycle without modifying permanent user settings."""

    def __init__(self, retroarch_bin: Optional[str] = None):
        if retroarch_bin:
            self.retroarch_bin = retroarch_bin
        else:
            try:
                from catalog.validator import find_retroarch_binary
                self.retroarch_bin = find_retroarch_binary()
            except Exception:
                self.retroarch_bin = None
        self.active_process: Optional[subprocess.Popen] = None
        self.temp_config_paths: set = set()
        self._was_terminated: bool = False

    @property
    def temp_config_path(self) -> Optional[str]:
        return next(iter(self.temp_config_paths), None)

    @temp_config_path.setter
    def temp_config_path(self, val: Optional[str]) -> None:
        if val:
            self.temp_config_paths.add(val)
        else:
            self.temp_config_paths.clear()

    def create_session_config(self, config: RetroArchLaunchConfig) -> str:
        """Create an isolated temporary append-config file for the Netplay session."""
        if config.mode == "offline":
            lines = [
                "# Auto-generated Arcade Offline temporary session config",
                "# Automatically removed upon session exit",
            ]
            if config.fullscreen:
                lines.append('video_fullscreen = "true"')
            else:
                lines.append('video_fullscreen = "false"')

            fd, temp_path = tempfile.mkstemp(
                prefix=f"arcade_offline_{config.session_id}_",
                suffix=".cfg"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")

            self.temp_config_paths.add(temp_path)
            logger.debug(f"File config offline sementara dibuat: {temp_path}")
            return temp_path

        mode_val = "false" if config.mode == "host" else "true"
        lines = [
            "# Auto-generated Arcade Netplay temporary session config",
            "# Automatically removed upon session exit",
            f'netplay_mode = "{mode_val}"',
            f'netplay_ip_port = "{config.port}"',
            f'netplay_nickname = "{config.nickname}"',
            f'netplay_check_frames = "{config.check_frames}"',
            f'netplay_input_latency_frames_min = "{config.input_latency_frames}"',
            'netplay_input_latency_frames_range = "2"',
            'netplay_ping_timeout = "30"',
            'netplay_max_ping = "0"',
            f'netplay_stateless_mode = "{"true" if config.stateless_mode else "false"}"',
            f'netplay_sync_sram = "{"true" if config.sync_sram else "false"}"',
            'netplay_public_announce = "false"',
            'netplay_require_slang = "false"',
            'netplay_use_mitm_server = "false"',
            # Anti-desync safeguards: disable features that alter frame execution
            'run_ahead_enabled = "false"',
            'run_ahead_secondary_instance = "false"',
            'rewind_enable = "false"',
            'cheats_enable = "false"',
            # Isolate savefile directory so both players boot from an identical clean RAM state
            f'savefile_directory = "{tempfile.gettempdir()}"',
            f'savestate_directory = "{tempfile.gettempdir()}"',
        ]

        if config.mode == "client" and config.connect_ip:
            lines.append(f'netplay_ip_address = "{config.connect_ip}"')

        if config.fullscreen:
            lines.append('video_fullscreen = "true"')
        else:
            lines.append('video_fullscreen = "false"')

        fd, temp_path = tempfile.mkstemp(
            prefix=f"arcade_netplay_{config.session_id}_",
            suffix=".cfg"
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        self.temp_config_paths.add(temp_path)
        logger.debug(f"File config sementara dibuat: {temp_path} (mode={config.mode}, port={config.port})")
        return temp_path

    def build_command(self, config: RetroArchLaunchConfig, temp_cfg_path: str) -> List[str]:
        """Construct the CLI command line for RetroArch."""
        binary = config.retroarch_bin or self.retroarch_bin
        if not binary:
            try:
                from catalog.validator import find_retroarch_binary
                binary = find_retroarch_binary()
            except Exception:
                pass
        binary = binary or "retroarch"

        if config.mode == "offline":
            cmd = [
                binary,
                "-v",
                "-L", config.core_path,
                config.rom_path,
                "--appendconfig", temp_cfg_path,
            ]
        else:
            cmd = [
                binary,
                "-v",
                "-L", config.core_path,
                config.rom_path,
                "--port", str(config.port),
                "--nick", config.nickname,
                "--appendconfig", temp_cfg_path,
            ]

            if config.mode == "host":
                cmd.append("--host")
            elif config.mode == "client":
                if not config.connect_ip:
                    raise ValueError("connect_ip must be provided for client mode")
                cmd.extend(["--connect", config.connect_ip])
            else:
                raise ValueError(f"Unknown launch mode: {config.mode}")

        if config.extra_args:
            cmd.extend(config.extra_args)

        return cmd

    def cleanup(self) -> None:
        """Clean up temporary configuration files."""
        for path in list(self.temp_config_paths):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        self.temp_config_paths.clear()

    def launch(self, config: RetroArchLaunchConfig,
               on_started: Optional[Callable[[], None]] = None,
               dry_run: bool = False) -> RetroArchProcessResult:
        """Launch RetroArch process, supervise its execution, and clean up afterwards."""
        self._was_terminated = False
        # 1. Check for mock execution environment
        is_mock = dry_run or bool(os.environ.get("ARCADE_MOCK_RETROARCH"))

        temp_cfg = self.create_session_config(config)
        cmd = self.build_command(config, temp_cfg)

        start_time = time.time()
        mode_str = config.mode.upper()
        lat_ms = int(round(config.input_latency_frames * (1000.0 / 60.0)))
        logger.info(f"Mempersiapkan RetroArch ({mode_str}) untuk game: {os.path.basename(config.rom_path)}")
        if config.mode != "offline":
            target_str = f"Target IP: {config.connect_ip}:{config.port}" if config.mode == "client" else f"Port Listening: {config.port}"
            logger.info(
                f"  -> Sesi Netplay   : Mode={mode_str} | Pemain='{config.nickname}' | {target_str} | "
                f"Buffer={config.input_latency_frames} frame (~{lat_ms}ms) | CheckFrames={config.check_frames} | "
                f"Stateless={'Aktif' if config.stateless_mode else 'Nonaktif'}"
            )
        logger.info(f"  -> Core Lib       : {config.core_path}")
        logger.info(f"  -> Perintah Exec  : {' '.join(cmd)}")

        if not is_mock:
            # Check executable exists before invoking subprocess
            binary = cmd[0]
            import shutil
            is_valid_bin = os.path.isfile(binary) or bool(shutil.which(binary))
            if not is_valid_bin:
                self.cleanup()
                err_msg = (
                    f"Executable RetroArch tidak ditemukan ({binary}). "
                    "Pastikan RetroArch terpasang di sistem atau gunakan opsi --retroarch-bin."
                )
                logger.error(err_msg)
                return RetroArchProcessResult(
                    exit_code=-1,
                    duration_seconds=0.0,
                    status="FAILED",
                    error_message=err_msg
                )

        if is_mock:
            # Simulate launch in test / headless environment
            if on_started:
                on_started()
            time.sleep(0.05)
            self.cleanup()
            logger.info("RetroArch berjalan dalam mode MOCK (simulasi).")
            return RetroArchProcessResult(
                exit_code=0,
                duration_seconds=time.time() - start_time,
                status="MOCK_SUCCESS",
                error_message=None
            )

        # Silence terminal echoing, freeze background terminal (fbterm/gptokeyb), reset framebuffer offset, and clear screen on Linux / EmuELEC
        is_linux = sys.platform.startswith("linux")
        if is_linux:
            try:
                subprocess.run(["fbfix", "0"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.5)
            except Exception:
                pass
            try:
                subprocess.run(["stty", "-echo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.5)
            except Exception:
                pass
            try:
                subprocess.run(["setterm", "-cursor", "off"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.5)
            except Exception:
                pass
            try:
                # Clear screen, scrollback buffer, and hide cursor
                sys.stdout.write("\033[H\033[2J\033[3J\033[?25l")
                sys.stdout.flush()
            except Exception:
                pass
            try:
                # Freeze fbterm & gptokeyb on EmuELEC so the terminal is completely hidden
                # and gamepad presses are not translated into console keystrokes during gameplay
                subprocess.run(["killall", "-STOP", "fbterm", "gptokeyb"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.5)
            except Exception:
                pass

        try:
            self.active_process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            logger.info(f"Proses RetroArch berhasil diluncurkan (PID: {self.active_process.pid})")

            if on_started:
                on_started()

            stdout, stderr = self.active_process.communicate()
            exit_code = self.active_process.returncode
            duration = time.time() - start_time

            # Log any RetroArch [ERROR] or netplay diagnostic messages found in stdout or stderr
            combined_output = (stdout or "") + "\n" + (stderr or "")
            log_errors = [
                l.strip() for l in combined_output.splitlines()
                if "[ERROR]" in l
                or "[netplay]" in l.lower()
                or "failed to" in l.lower()
                or "mismatch" in l.lower()
                or "failed to open" in l.lower()
            ]
            if log_errors:
                logger.warning("Log diagnosa / kesalahan dari RetroArch:")
                for le in log_errors[:10]:
                    logger.warning(f"  -> {le}")

            # Detect premature shutdown (< 2.0s) where core failed to load content
            is_premature = (duration < 2.0)
            is_windows = sys.platform.startswith("win")
            # Normal exits: 0 (clean quit), -15 (SIGTERM), 130 (SIGINT / Ctrl+C),
            # or explicitly terminated by supervisor/launcher (self._was_terminated),
            # or exit code 1 on Windows (standard result of TerminateProcess when terminated)
            is_normal_exit = (
                exit_code in (0, -15, 130)
                or self._was_terminated
                or (is_windows and exit_code == 1 and not is_premature)
            )

            if is_normal_exit and is_premature and not self._was_terminated:
                status = "FAILED"
                cname = os.path.basename(config.core_path)
                rname = os.path.basename(config.rom_path)
                err_msg = (
                    f"RetroArch tertutup terlalu cepat ({duration:.1f}s). "
                    f"Kemungkinan ROM '{rname}' tidak kompatibel dengan core '{cname}' "
                    f"(misal: ROM SNES/Console dijalankan dengan core Arcade MAME, atau file ZIP bukan ROM set arcade lengkap)."
                )
            elif is_normal_exit:
                status = "COMPLETED"
                err_msg = None
            else:
                status = "FAILED"
                err_msg = stderr.strip() if stderr else f"Kode keluar: {exit_code}"

            logger.info(f"RetroArch selesai: {status} (Exit Code: {exit_code}, Durasi: {duration:.1f}s)")
            if err_msg:
                logger.warning(f"Keterangan: {err_msg[:250]}")

            return RetroArchProcessResult(
                exit_code=exit_code,
                duration_seconds=duration,
                status=status,
                error_message=err_msg
            )

        except FileNotFoundError as e:
            duration = time.time() - start_time
            err_msg = f"File tidak ditemukan: {e}. Periksa path RetroArch ({cmd[0]})."
            logger.error(err_msg)
            return RetroArchProcessResult(
                exit_code=-1,
                duration_seconds=duration,
                status="CRASHED",
                error_message=err_msg
            )
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Error saat mengeksekusi RetroArch: {e}")
            return RetroArchProcessResult(
                exit_code=-1,
                duration_seconds=duration,
                status="CRASHED",
                error_message=str(e)
            )
        finally:
            self.active_process = None
            if is_linux:
                try:
                    # Unfreeze fbterm & gptokeyb on EmuELEC
                    subprocess.run(["killall", "-CONT", "fbterm", "gptokeyb"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.5)
                except Exception:
                    pass
                try:
                    subprocess.run(["fbfix", "0"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.5)
                except Exception:
                    pass
                try:
                    subprocess.run(["stty", "echo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.5)
                except Exception:
                    pass
                try:
                    subprocess.run(["setterm", "-cursor", "on"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.5)
                except Exception:
                    pass
                try:
                    sys.stdout.write("\033[?25h")
                    sys.stdout.flush()
                except Exception:
                    pass
            self.cleanup()

    def terminate(self) -> None:
        """Terminate active RetroArch process if currently running."""
        self._was_terminated = True
        if self.active_process and self.active_process.poll() is None:
            try:
                self.active_process.terminate()
                try:
                    self.active_process.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    self.active_process.kill()
            except Exception:
                pass
        self.cleanup()
