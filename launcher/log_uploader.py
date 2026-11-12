"""Remote Log Uploader for Arcade Online Launcher.

Transfers session logs securely to a remote VPS server using SSH/SCP with
publickey authentication, unique machine-timestamped filenames, and non-blocking
background uploads.
"""

import os
import sys
import re
import shutil
import logging
import threading
import subprocess
import tempfile
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger("Arcade.LogUploader")


def find_default_ssh_key() -> Optional[str]:
    """Search for common SSH private key locations across Linux, EmuELEC, and macOS."""
    candidates = [
        os.path.expanduser("~/.ssh/id_ed25519"),
        os.path.expanduser("~/.ssh/id_rsa"),
        os.path.expanduser("~/.ssh/id_ecdsa"),
        "/storage/.ssh/id_ed25519",
        "/storage/.ssh/id_rsa",
        "/storage/.ssh/id_ecdsa",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


class RemoteLogUploader:
    """Manages secure SSH/SCP log uploads to remote server."""

    def __init__(self,
                 host: str = "217.216.146.15",
                 port: int = 20157,
                 user: str = "root",
                 remote_dir: str = "/root/log_testing",
                 machine_name: str = "ArcadeCab",
                 log_file: str = "arcade_launcher.log",
                 ssh_key_path: Optional[str] = None,
                 timeout_seconds: float = 8.0,
                 enabled: bool = True):
        self.host = host
        self.port = port
        self.user = user
        self.remote_dir = remote_dir.rstrip("/")
        self.machine_name = machine_name
        self.log_file = log_file
        self.ssh_key_path = ssh_key_path or os.environ.get("ARCADE_SSH_KEY") or find_default_ssh_key()
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled
        self._lock = threading.Lock()
        self._last_upload_time = 0.0

    def generate_remote_filename(self) -> str:
        """Generate unique log filename containing sanitized machine name and timestamp."""
        # Sanitize machine name to alphanumeric, underscores, and dashes
        clean_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", self.machine_name.strip()) or "ArcadeCab"
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(os.path.basename(self.log_file))[0]
        return f"{base_name}_{clean_name}_{now_str}.log"

    def _flush_log_handlers(self) -> None:
        """Flush root and arcade loggers to ensure latest entries are flushed to disk."""
        try:
            for name in ("Arcade", "root", ""):
                log = logging.getLogger(name)
                for h in log.handlers:
                    try:
                        h.flush()
                    except Exception:
                        pass
        except Exception:
            pass

    def _build_ssh_base_cmd(self, binary: str) -> Tuple[list, Optional[str]]:
        """Build base command line for ssh or scp with security options."""
        bin_path = shutil.which(binary)
        if not bin_path:
            return [], f"Executable '{binary}' tidak ditemukan di sistem."

        cmd = [bin_path]
        if binary == "scp":
            cmd.extend(["-P", str(self.port)])
        else:
            cmd.extend(["-p", str(self.port)])

        # Security and non-interactive safeguard flags
        cmd.extend([
            "-o", "BatchMode=yes",                        # Never prompt for interactive password
            "-o", f"ConnectTimeout={int(self.timeout_seconds)}",
            "-o", "StrictHostKeyChecking=accept-new",      # Auto-accept new host key securely
            "-o", "ServerAliveInterval=3",
            "-o", "ServerAliveCountMax=2",
        ])

        if self.ssh_key_path and os.path.isfile(self.ssh_key_path):
            cmd.extend(["-i", self.ssh_key_path])

        return cmd, None

    def ensure_remote_directory(self) -> Tuple[bool, Optional[str]]:
        """Verify or create remote storage directory on VPS via SSH."""
        base_cmd, err = self._build_ssh_base_cmd("ssh")
        if err:
            return False, err

        cmd = base_cmd + [
            f"{self.user}@{self.host}",
            f"mkdir -p '{self.remote_dir}'"
        ]

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.timeout_seconds
            )
            if proc.returncode == 0:
                return True, None

            stderr = (proc.stderr or "").strip()
            if "Permission denied" in stderr:
                return False, f"Autentikasi ditolak (publickey). Kunci SSH belum terdaftar di VPS {self.host}:{self.port}."
            if "timed out" in stderr.lower() or "timeout" in stderr.lower():
                return False, f"Waktu koneksi habis (timeout) saat menghubungi VPS {self.host}:{self.port}."
            return False, stderr or f"Gagal membuat direktori remote (Exit code: {proc.returncode})"
        except subprocess.TimeoutExpired:
            return False, f"Koneksi SSH ke {self.host}:{self.port} melebihi batas waktu {self.timeout_seconds}s."
        except Exception as e:
            return False, f"Pengecualian saat menghubungi VPS: {e}"

    def upload_sync(self, reason: str = "manual") -> Tuple[bool, str]:
        """Execute synchronous upload of current log file to remote VPS."""
        if not self.enabled:
            return False, "Pengunggahan log dinonaktifkan di konfigurasi."

        if not os.path.isfile(self.log_file):
            return False, f"File log lokal '{self.log_file}' tidak ditemukan."

        self._flush_log_handlers()

        try:
            log_size = os.path.getsize(self.log_file)
            if log_size == 0:
                return False, "File log lokal kosong (0 bytes)."
        except OSError as e:
            return False, f"Gagal membaca ukuran file log lokal: {e}"

        with self._lock:
            # 1. Pastikan direktori remote siap
            ok, err = self.ensure_remote_directory()
            if not ok:
                msg = f"Gagal menyiapkan folder remote di VPS: {err}"
                logger.warning(f"[LogUploader] {msg}")
                return False, msg

            # 2. Buat snapshot lokal sementara agar pembacaan scp tidak terganggu oleh log baru
            temp_copy = None
            try:
                fd, temp_copy = tempfile.mkstemp(prefix="arcade_log_upload_", suffix=".log")
                os.close(fd)
                shutil.copyfile(self.log_file, temp_copy)
            except Exception as e:
                if temp_copy and os.path.exists(temp_copy):
                    try:
                        os.remove(temp_copy)
                    except Exception:
                        pass
                temp_copy = self.log_file

            remote_filename = self.generate_remote_filename()
            remote_target = f"{self.remote_dir}/{remote_filename}"

            logger.info(
                f"[LogUploader] Mengunggah log ke VPS {self.host}:{self.port} "
                f"({remote_target}) [Pemicu: {reason}]..."
            )

            # 3. Jalankan perintah SCP
            base_scp, err_scp = self._build_ssh_base_cmd("scp")
            if err_scp:
                if temp_copy != self.log_file and os.path.exists(temp_copy):
                    try:
                        os.remove(temp_copy)
                    except Exception:
                        pass
                logger.warning(f"[LogUploader] {err_scp}")
                return False, err_scp

            cmd_scp = base_scp + [
                temp_copy,
                f"{self.user}@{self.host}:{remote_target}"
            ]

            try:
                proc = subprocess.run(
                    cmd_scp,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=self.timeout_seconds * 1.5
                )

                if proc.returncode == 0:
                    self._last_upload_time = datetime.now().timestamp()
                    size_fmt = f"{log_size / 1024:.1f} KB" if log_size < 1048576 else f"{log_size / 1048576:.2f} MB"
                    success_msg = (
                        f"Log berhasil diunggah ke VPS: {self.host}:{self.port} -> {remote_target} "
                        f"(Ukuran: {size_fmt})"
                    )
                    logger.info(f"[LogUploader] [✓] {success_msg}")
                    return True, success_msg

                stderr = (proc.stderr or "").strip()
                if "Permission denied" in stderr:
                    err_msg = f"Autentikasi ditolak (publickey). Kunci SSH belum terdaftar di VPS {self.host}:{self.port}."
                elif "timed out" in stderr.lower() or "timeout" in stderr.lower():
                    err_msg = f"Koneksi SCP timeout saat mengirim log ke {self.host}:{self.port}."
                else:
                    err_msg = stderr or f"SCP gagal dengan exit code {proc.returncode}."

                logger.warning(f"[LogUploader] [!] Gagal mengunggah log ke VPS: {err_msg}")
                return False, err_msg
            except subprocess.TimeoutExpired:
                err_msg = f"Transfer SCP ke {self.host}:{self.port} melebihi batas waktu timeout."
                logger.warning(f"[LogUploader] [!] {err_msg}")
                return False, err_msg
            except Exception as e:
                err_msg = f"Pengecualian saat mengunggah log: {e}"
                logger.warning(f"[LogUploader] [!] {err_msg}")
                return False, err_msg
            finally:
                if temp_copy != self.log_file and os.path.exists(temp_copy):
                    try:
                        os.remove(temp_copy)
                    except Exception:
                        pass

    def upload_async(self, reason: str = "session_end") -> threading.Thread:
        """Trigger background log upload in daemon thread to avoid blocking UI/controls."""
        t = threading.Thread(
            target=self.upload_sync,
            kwargs={"reason": reason},
            name="ArcadeLogUploadThread",
            daemon=True
        )
        t.start()
        return t

