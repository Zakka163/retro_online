"""Arcade Online Launcher: One-Click Multiplayer for RetroArch.

Primary entrypoint executing the complete workflow:
1. Game selection (Street Fighter II default)
2. Create Room or Find Room
3. Resource & Compatibility validation
4. Direct P2P or Relay Fallback connection negotiation
5. RetroArch launch and supervision
6. Safe cleanup and return to launcher
"""

import os
import sys
import json
import re
import time
import argparse
import logging
from typing import Optional, Dict, Any, List

from catalog.validator import CatalogValidator, GameManifest
from .retroarch_controller import RetroArchController, RetroArchLaunchConfig
from .client_api import ArcadeClientAPI
from .connection_manager import ConnectionManager, ConnectionProgressStep, ERROR_MESSAGES
from .ui import ArcadeTUI, ArcadeCLI
from .logger import setup_launcher_logging, get_recent_logs
from .session_supervisor import SessionSupervisor
from datetime import datetime
import platform

log_file = f"scan_{datetime.now():%Y%m%d_%H%M%S}_{platform.node()}.txt"
logger = logging.getLogger("Arcade.Launcher")


class ArcadeLauncherApp:
    """Manages the interactive launcher lifecycle, dynamic game scanner, and RetroArch execution."""

    def __init__(self, server_url: str = "http://localhost:8080",
                 retroarch_bin: Optional[str] = None,
                 player_name: str = "Arcade1",
                 custom_rom_dirs: Optional[List[str]] = None,
                 custom_core_dirs: Optional[List[str]] = None,
                 dry_run: bool = False,
                 fullscreen: bool = True,
                 check_frames: int = 30,
                 input_latency_frames: int = 2,
                 stateless_mode: bool = False,
                 sync_sram: bool = True,
                 preferred_arcade_cores: Optional[List[str]] = None,
                 local_roms_only: bool = False,
                 log_file: str = "arcade_launcher.log",
                 log_uploader_cfg: Optional[Dict[str, Any]] = None):
        self.server_url = server_url
        self.player_name = player_name
        self.dry_run = dry_run
        self.fullscreen = fullscreen
        self.check_frames = check_frames
        self.input_latency_frames = input_latency_frames
        self.stateless_mode = stateless_mode
        self.sync_sram = sync_sram
        self.custom_rom_dirs = custom_rom_dirs or []
        self.custom_core_dirs = custom_core_dirs or []
        self.preferred_arcade_cores = preferred_arcade_cores
        self.local_roms_only = local_roms_only
        self.log_file = log_file

        from launcher.log_uploader import RemoteLogUploader
        lu_cfg = log_uploader_cfg or {}
        self.log_uploader = RemoteLogUploader(
            host=lu_cfg.get("remote_host", "217.216.146.15"),
            port=lu_cfg.get("remote_port", 20157),
            user=lu_cfg.get("remote_user", "root"),
            remote_dir=lu_cfg.get("remote_path", "/root/log_testing"),
            machine_name=self.player_name,
            log_file=self.log_file,
            ssh_key_path=lu_cfg.get("ssh_key_path"),
            timeout_seconds=lu_cfg.get("upload_timeout_seconds", 8.0),
            enabled=lu_cfg.get("auto_upload", True)
        )

        from catalog.scanner import SystemScanner
        self.scanner = SystemScanner(
            custom_rom_dirs=self.custom_rom_dirs,
            custom_core_dirs=self.custom_core_dirs,
            preferred_arcade_cores=self.preferred_arcade_cores,
            local_roms_only=self.local_roms_only
        )
        self.manifest = GameManifest(scanner=self.scanner)

        from catalog.validator import find_retroarch_binary
        self.retroarch_bin = retroarch_bin or find_retroarch_binary()

        self.validator = CatalogValidator(
            manifest=self.manifest,
            rom_dirs=self.custom_rom_dirs,
            core_dirs=self.custom_core_dirs,
            retroarch_bin=self.retroarch_bin,
            local_roms_only=self.local_roms_only
        )
        self.api = ArcadeClientAPI(server_url=self.server_url)
        self.conn_mgr = ConnectionManager(api=self.api)
        self.ra_controller = RetroArchController(retroarch_bin=self.retroarch_bin)
        self.ui = ArcadeTUI()

        import socket
        import platform
        from launcher.system_info import (
            LAUNCHER_VERSION,
            get_machine_hardware,
            get_os_distro,
            get_retroarch_version_string,
        )
        from launcher.connection_manager import get_local_ip, get_all_local_ips

        hostname = socket.gethostname()
        distro = get_os_distro()
        hardware = get_machine_hardware()
        local_ip = get_local_ip()
        candidate_ips = get_all_local_ips()
        ra_ver = get_retroarch_version_string(self.retroarch_bin)
        lat_ms = int(round(self.input_latency_frames * (1000.0 / 60.0)))

        logger.info("=" * 78)
        logger.info(f"ARCADE ONLINE NETPLAY LAUNCHER v{LAUNCHER_VERSION}")
        logger.info(f"  -> Identitas Mesin : {self.player_name} (Hostname: {hostname})")
        logger.info(f"  -> Hardware / OS   : {distro} | {hardware} ({platform.machine()})")
        logger.info(f"  -> IP Jaringan     : {local_ip} (Kandidat: {candidate_ips})")
        logger.info(f"  -> Emulator        : {self.retroarch_bin} [{ra_ver}]")
        logger.info(f"  -> Server Relay    : {self.server_url}")
        logger.info(
            f"  -> Konfig Netplay  : Buffer={self.input_latency_frames} frame (~{lat_ms}ms) | "
            f"CheckFrames={self.check_frames} | Stateless={'Aktif' if self.stateless_mode else 'Nonaktif'} | "
            f"SyncSRAM={'Aktif' if self.sync_sram else 'Nonaktif'} | "
            f"Layar={'Fullscreen' if self.fullscreen else 'Windowed'}"
        )
        logger.info(
            f"  -> Upload Log VPS  : {'Aktif' if self.log_uploader.enabled else 'Nonaktif'} "
            f"({self.log_uploader.user}@{self.log_uploader.host}:{self.log_uploader.port} -> {self.log_uploader.remote_dir})"
        )
        logger.info(f"  -> Katalog Game    : {len(self.manifest.list_games())} judul game terdaftar.")
        logger.info("=" * 78)

    def trigger_log_upload(self, reason: str = "session_end") -> None:
        """Trigger non-blocking background upload of launcher logs to VPS."""
        if hasattr(self, "log_uploader") and self.log_uploader and self.log_uploader.enabled:
            self.log_uploader.upload_async(reason=reason)



    def run_cli_scan(self) -> None:
        """Scan disk and list all discovered arcade ROMs and cores."""
        log = logging.getLogger("arcade_scan")
        log.setLevel(logging.INFO)

        if not log.handlers:
            handler = logging.FileHandler(log_file, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(message)s"))
            log.addHandler(handler)

        def output(message: str = "") -> None:
            print(message)
            log.info(message)

        ArcadeCLI.show_banner()
        output("Memindai sistem untuk emulator RetroArch, core libretro, dan ROM arcade...")
        cores = self.scanner.scan_installed_cores()
        output(f"\n[+] Core Libretro Terdeteksi ({len(cores)}):")
        for cname, cpath in cores.items():
            output(f"  - {cname}: {cpath}")

        rom_dirs = self.scanner.get_system_rom_directories()
        output(f"\n[+] Direktori ROM Dipindai ({len(rom_dirs)}):")
        for d in rom_dirs:
            output(f"  - {d}")

        games = self.scanner.scan_roms()
        ready_games = [g for g in games.values() if g.status == "ready"]
        output(
            f"\n[+] Game Arcade Ditemukan: {len(games)} "
            f"(Siap dimainkan: {len(ready_games)}):"
        )
        for g in games.values():
            status_tag = "[READY]" if g.status == "ready" else "[MISSING CORE]"
            output(
                f"  - {status_tag} {g.display_name} "
                f"({g.rom_file}) -> Core: {g.core_name}"
            )

    def run_cli_list(self, game_id: Optional[str] = None) -> None:
        """List active rooms from command line."""
        ArcadeCLI.show_banner()
        rooms = self.api.list_rooms(game_id)
        if not rooms:
            print("Tidak ada room yang tersedia saat ini.")
            return

        print(f"Daftar Room Tersedia ({len(rooms)}):")
        print("------------------------------------------------------------")
        for r in rooms:
            print(f"[{r['room_id']}] {r['name']} | Game: {r['game_id']} | Host: {r['host_name']} | Status: {r['status']}")
        print("------------------------------------------------------------")

    def run_cli_create(self, game_id: str, room_name: Optional[str] = None) -> None:
        """Create room and wait for opponent via CLI."""
        ArcadeCLI.show_banner()
        game = self.manifest.get_game(game_id)
        if not game:
            print(f"Error: Game '{game_id}' tidak ditemukan di katalog.")
            return

        print(f"Memeriksa aset lokal untuk {game['display_name']}...")
        valid, code, details = self.validator.verify_local_game(game_id, strict_hash=not self.dry_run)
        if not valid and not self.dry_run:
            print(f"Error [{code}]: {details.get('message')}")
            return

        room_name = room_name or f"{self.player_name}'s {game['display_name']}"
        compat = {
            "core": game["retroarch_core"],
            "core_version": game.get("core_version"),
            "rom_hash": list(game.get("rom_hashes", {}).values())[0] if game.get("rom_hashes") else None
        }

        print(f"Membuat room '{room_name}' pada server {self.server_url}...")
        ok, data = self.api.create_room(game_id, room_name, self.player_name, compat)
        if not ok:
            print(f"Gagal membuat room: {data.get('message', 'Server error')}")
            return

        room_id = data["room_id"]
        host_token = data["host_token"]
        host_id = data["player_id"]
        print(f"\n[✓] Room berhasil dibuat! ID: {room_id}")
        print("Menunggu pemain kedua bergabung (tekan Ctrl+C untuk batal)...")

        try:
            # Poll for client joined
            client_joined = False
            last_poll = time.time()
            while not client_joined:
                time.sleep(1.0)
                self.api.send_heartbeat(room_id, host_id, host_token)
                signals = self.api.poll_signals(room_id, host_id, since=last_poll, timeout=2.0)
                last_poll = time.time()
                for s in signals:
                    if s.get("event") == "room.joined":
                        client_joined = True
                        print(f"\n[✓] Lawan bergabung: {s.get('payload', {}).get('client_name', 'Player 2')}")
                        break

            # Negotiate connection
            print("Menghubungkan kedua mesin...")
            result = self.conn_mgr.negotiate_as_host(
                room_id=room_id,
                host_id=host_id,
                host_token=host_token,
                netplay_port=game.get("default_port", 55435),
                on_progress=ArcadeCLI.show_steps
            )

            if not result.success:
                print(f"\nGagal menghubungkan: {result.error_message}")
                return

            print(f"\nKoneksi berhasil ({result.mode.upper()})! Menjalankan RetroArch...")
            ra_bin = details.get("retroarch_bin") or self.ra_controller.retroarch_bin
            if ra_bin:
                self.ra_controller.retroarch_bin = ra_bin
            launch_cfg = RetroArchLaunchConfig(
                mode="host",
                core_path=details.get("core_lib") if details else "/mock/core.so",
                rom_path=details.get("rom_path") if details else "/mock/sf2.zip",
                port=result.target_port,
                nickname=self.player_name,
                session_id=room_id,
                retroarch_bin=ra_bin,
                fullscreen=self.fullscreen,
                check_frames=self.check_frames,
                input_latency_frames=self.input_latency_frames,
                stateless_mode=self.stateless_mode,
                sync_sram=self.sync_sram
            )

            supervisor = SessionSupervisor(
                api=self.api,
                room_id=room_id,
                player_id=host_id,
                token=host_token,
                role="host",
                ra_controller=self.ra_controller,
                local_bridge=result.local_bridge
            )
            supervisor.start()

            self.ui.pause_gamepad()
            try:
                res = self.ra_controller.launch(launch_cfg, dry_run=self.dry_run)
            finally:
                self.ui.resume_gamepad()
                supervisor.stop()
                if result.local_bridge:
                    result.local_bridge.stop()
                try:
                    self.api.send_signal(room_id, host_id, "peer.left", {"reason": f"{self.player_name} keluar dari game"})
                except Exception:
                    pass

            if supervisor.peer_disconnected:
                print(f"\n[!] Lawan terputus: {supervisor.disconnect_reason}\nPermainan diakhiri.")
            elif res.status in ("FAILED", "CRASHED"):
                print(f"\n[!] Gagal menjalankan game: {res.error_message}")
            print(f"Sesi permainan selesai. Status: {res.status} (Durasi: {res.duration_seconds:.1f}s)")

        finally:
            print("Membersihkan sesi room...")
            self.api.close_room(room_id, host_token)
            self.trigger_log_upload("host_session_end")
            print("Selesai.")

    def run_cli_join(self, room_id: str) -> None:
        """Join an existing room by ID via CLI."""
        ArcadeCLI.show_banner()
        print(f"Mencari room {room_id}...")
        room = self.api.get_room(room_id)
        if not room:
            print(f"Room {room_id} tidak ditemukan atau telah kedaluwarsa.")
            return

        game_id = room["game_id"]
        game = self.manifest.get_game(game_id)
        if not game:
            print(f"Game {game_id} tidak didukung di mesin ini.")
            return

        print(f"Memeriksa kompatibilitas untuk {game['display_name']}...")
        valid, code, details = self.validator.verify_local_game(game_id, strict_hash=not self.dry_run)
        if not valid and not self.dry_run:
            print(f"Error [{code}]: {details.get('message')}")
            return

        compat = {
            "core": game["retroarch_core"],
            "core_version": game.get("core_version"),
            "rom_hash": list(game.get("rom_hashes", {}).values())[0] if game.get("rom_hashes") else None
        }

        print("Bergabung ke room...")
        ok, join_data = self.api.join_room(room_id, self.player_name, compat)
        if not ok:
            print(f"Gagal bergabung: {join_data.get('message')}")
            return

        client_id = join_data["player_id"]
        client_token = join_data["client_token"]
        print(f"[✓] Berhasil bergabung! Membangun koneksi ke {room['host_name']}...")

        result = self.conn_mgr.negotiate_as_client(
            room_id=room_id,
            client_id=client_id,
            client_token=client_token,
            on_progress=ArcadeCLI.show_steps
        )

        if not result.success:
            print(f"\nGagal menghubungkan: {result.error_message}")
            self.api.leave_room(room_id, client_id, client_token)
            return

        print(f"\nKoneksi siap ({result.mode.upper()})! Memulai permainan...")
        ra_bin = details.get("retroarch_bin") or self.ra_controller.retroarch_bin
        if ra_bin:
            self.ra_controller.retroarch_bin = ra_bin
        launch_cfg = RetroArchLaunchConfig(
            mode="client",
            core_path=details.get("core_lib") if details else "/mock/core.so",
            rom_path=details.get("rom_path") if details else "/mock/sf2.zip",
            port=result.target_port,
            connect_ip=result.target_ip,
            nickname=self.player_name,
            session_id=room_id,
            retroarch_bin=ra_bin,
            fullscreen=self.fullscreen,
            check_frames=self.check_frames,
            input_latency_frames=self.input_latency_frames,
            stateless_mode=self.stateless_mode,
            sync_sram=self.sync_sram
        )

        supervisor = SessionSupervisor(
            api=self.api,
            room_id=room_id,
            player_id=client_id,
            token=client_token,
            role="client",
            ra_controller=self.ra_controller,
            local_bridge=result.local_bridge
        )
        supervisor.start()

        if result.mode == "direct" and not self.dry_run and not os.environ.get("ARCADE_MOCK_RETROARCH"):
            # Give Host's RetroArch time to boot and start listening on netplay port
            logger.info("Direct P2P: Menunggu 1.5 detik agar Host RetroArch siap menerima koneksi...")
            time.sleep(1.5)

        self.ui.pause_gamepad()
        try:
            res = self.ra_controller.launch(launch_cfg, dry_run=self.dry_run)
        finally:
            self.ui.resume_gamepad()
            supervisor.stop()
            if result.local_bridge:
                result.local_bridge.stop()
            try:
                self.api.send_signal(room_id, client_id, "peer.left", {"reason": f"{self.player_name} keluar dari game"})
            except Exception:
                pass
            self.api.leave_room(room_id, client_id, client_token)
            self.trigger_log_upload("client_session_end")

        if supervisor.peer_disconnected:
            print(f"\n[!] Lawan terputus: {supervisor.disconnect_reason}\nPermainan diakhiri.")
        elif res.status in ("FAILED", "CRASHED"):
            print(f"\n[!] Gagal menjalankan game: {res.error_message}")
        print(f"Permainan selesai. Status: {res.status}")

    def run_cli_play_offline(self, game_id: str) -> None:
        """Launch a game directly in offline RetroArch via CLI."""
        ArcadeCLI.show_banner()
        game = self.manifest.get_game(game_id)
        if not game:
            print(f"Error: Game '{game_id}' tidak ditemukan di katalog.")
            return

        print(f"Memeriksa aset lokal untuk {game['display_name']}...")
        valid, code, details = self.validator.verify_local_game(game_id, strict_hash=not self.dry_run)
        if not valid and not self.dry_run:
            print(f"Error [{code}]: {details.get('message')}")
            return

        core_path = details.get("core_lib") if details else game.get("core_path")
        rom_path = details.get("rom_path") if details else game.get("scanned_rom_path")
        ra_bin = details.get("retroarch_bin") or self.ra_controller.retroarch_bin

        launch_cfg = RetroArchLaunchConfig(
            mode="offline",
            core_path=core_path,
            rom_path=rom_path,
            session_id=game_id,
            retroarch_bin=ra_bin,
            fullscreen=self.fullscreen,
        )

        print(f"\nMembuka {game.get('display_name')} di RetroArch (Offline)...")
        res = self.ra_controller.launch(launch_cfg, dry_run=self.dry_run)
        if res.status in ("FAILED", "CRASHED"):
            print(f"\n[!] Gagal menjalankan game: {res.error_message}")
        print(f"Permainan selesai. Status: {res.status}")
        self.trigger_log_upload("offline_game_end")

    def run_interactive(self) -> None:
        """Run the interactive Arcade Curses frontend, or interactive CLI on platforms without curses."""
        if not self.ui.init_curses():
            logger.info("Curses tidak tersedia pada terminal ini. Mengaktifkan mode interaktif CLI.")
            self._run_cli_interactive_menu()
            return

        try:
            self._main_menu_loop()
        finally:
            self.ui.restore_terminal()
            if hasattr(self, "log_uploader") and self.log_uploader and self.log_uploader.enabled:
                self.log_uploader.upload_sync("launcher_exit")

    def _run_cli_interactive_menu(self) -> None:
        """Interactive text-based menu when curses is not available (e.g. Windows without windows-curses)."""
        ArcadeCLI.show_banner()
        if sys.platform == "win32":
            print("\n[INFO WINDOWS]")
            print("  Untuk antarmuka grafis terminal (TUI) bergaya arcade di Windows,")
            print("  Anda dapat menginstal: pip install windows-curses\n")

        while True:
            print("\n================= MENU UTAMA =================")
            print(" 1. Main Offline (Single / Local Player)")
            print(" 2. Buat Room Online (Host Permainan)")
            print(" 3. Cari & Gabung Room Online (Client)")
            print(" 4. Pindai ROM (Rescan)")
            print(" 5. Keluar")
            print("==============================================")
            try:
                choice = input("Pilih menu [1-5]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nKeluar dari Arcade Launcher.")
                break

            if choice == "1":
                games = self.manifest.list_games()
                ready = [g for g in games if g.get("status") == "ready"]
                if not ready:
                    print("\n[!] Belum ada ROM yang siap dimainkan.")
                    print("    Letakkan file ROM arcade (.zip) di folder ROM Anda, lalu pilih menu 4 (Pindai).")
                    continue

                print("\nPilih Game untuk Main Offline:")
                for i, g in enumerate(ready, 1):
                    print(f"  {i}. {g.get('display_name')} ({g.get('rom_file')}) -> Core: {g.get('retroarch_core')}")
                try:
                    g_choice = input(f"Pilih game [1-{len(ready)}] (Enter untuk 1): ").strip()
                except (EOFError, KeyboardInterrupt):
                    continue
                idx = int(g_choice) - 1 if g_choice.isdigit() and 1 <= int(g_choice) <= len(ready) else 0
                selected_game = ready[idx]
                self.run_cli_play_offline(selected_game["game_id"])

            elif choice == "2":
                games = self.manifest.list_games()
                ready = [g for g in games if g.get("status") == "ready"]
                if not ready:
                    print("\n[!] Belum ada ROM yang siap dimainkan.")
                    print("    Letakkan file ROM arcade (.zip) di folder ROM Anda, lalu pilih menu 4 (Pindai).")
                    continue

                print("\nPilih Game untuk Host:")
                for i, g in enumerate(ready, 1):
                    print(f"  {i}. {g.get('display_name')} ({g.get('rom_file')}) -> Core: {g.get('retroarch_core')}")
                try:
                    g_choice = input(f"Pilih game [1-{len(ready)}] (Enter untuk 1): ").strip()
                except (EOFError, KeyboardInterrupt):
                    continue
                idx = int(g_choice) - 1 if g_choice.isdigit() and 1 <= int(g_choice) <= len(ready) else 0
                selected_game = ready[idx]
                try:
                    r_name = input(f"Nama Room [Room {self.player_name}]: ").strip()
                except (EOFError, KeyboardInterrupt):
                    r_name = ""
                r_name = r_name or f"Room {self.player_name}"
                self.run_cli_create(selected_game["game_id"], r_name)

            elif choice == "3":
                print("\nMencari room online di server...")
                rooms = self.api.list_rooms()
                if not rooms:
                    print("[i] Saat ini belum ada room yang aktif di server.")
                    continue
                print(f"\nDaftar Room Online ({len(rooms)}):")
                for i, r in enumerate(rooms, 1):
                    print(f"  {i}. [{r['room_id']}] {r['name']} | Game: {r['game_id']} | Host: {r['host_name']}")
                try:
                    r_choice = input(f"\nPilih nomor room [1-{len(rooms)}] atau ketik Room ID (Enter untuk batal): ").strip()
                except (EOFError, KeyboardInterrupt):
                    continue
                if not r_choice:
                    continue
                target_room_id = None
                if r_choice.isdigit() and 1 <= int(r_choice) <= len(rooms):
                    target_room_id = rooms[int(r_choice) - 1]["room_id"]
                else:
                    target_room_id = r_choice
                self.run_cli_join(target_room_id)

            elif choice == "4":
                self.run_cli_scan()

            elif choice == "5" or choice.lower() in ("q", "exit"):
                if self.log_uploader.enabled:
                    print("Mengirim log ke server VPS...")
                    ok, msg = self.log_uploader.upload_sync("launcher_exit")
                    print(("[✓] " if ok else "[!] Gagal kirim log: ") + msg)
                print("Terima kasih telah bermain!")
                break
            else:
                print("Pilihan tidak valid. Silakan pilih 1-5.")

    def _main_menu_loop(self) -> None:
        """Layar 1: Pemilihan Game & Scanner."""
        selected_idx = 0
        needs_redraw = True
        last_render_time = 0.0

        # Prime asynchronous health check in background
        self.api.get_cached_health()

        def build_menu_items():
            games = self.manifest.list_games()
            items = []
            if not games:
                items.append(("[ ! ] Tidak ada ROM arcade terdeteksi", "empty_hint"))
            else:
                for g in games:
                    status_icon = "✓" if g.get("status") == "ready" or g.get("scanned_rom_path") else " "
                    items.append((f"[{status_icon}] {g['display_name']}", g))
            items.append(("🔄 PINDAI", "rescan"))
            return items

        menu_items = build_menu_items()

        while True:
            if selected_idx >= len(menu_items):
                selected_idx = max(0, len(menu_items) - 1)

            # Check server status non-blocking
            online, _ = self.api.get_cached_health(max_age=5.0)
            status_text = "Online" if online else "Offline (Periksa Server)"

            now = time.time()
            if needs_redraw or (now - last_render_time >= 1.0):
                lines = ["PILIH GAME (✓ = Siap Main):"]
                for idx, (label, _) in enumerate(menu_items):
                    prefix = "> [ " if idx == selected_idx else "  [ "
                    suffix = " ]"
                    lines.append(f"{prefix}{label}{suffix}")

                lines.append("")
                lines.append(f"Status Layanan: {status_text}")

                self.ui.draw_box(
                    "ARCADE ONLINE",
                    lines,
                    "UP/DOWN: Pilih | ENTER: Buka | ESC: Keluar"
                )
                last_render_time = now
                needs_redraw = False

            key = self.ui.get_key()
            if self.ui.is_back(key):
                break
            elif self.ui.is_up(key):
                selected_idx = (selected_idx - 1) % len(menu_items)
                needs_redraw = True
            elif self.ui.is_down(key):
                selected_idx = (selected_idx + 1) % len(menu_items)
                needs_redraw = True
            elif self.ui.is_enter(key):
                needs_redraw = True
                _, selected_data = menu_items[selected_idx]
                if selected_data == "rescan":
                    # Trigger dynamic re-scan
                    logger.info("Menu Utama: Memulai pemindaian ROM...")
                    self.ui.show_message("MEMINDAI...", "Sedang memindai direktori ROM...", wait_seconds=0.5)
                    self.manifest.scan_and_merge(self.scanner)
                    menu_items = build_menu_items()
                    games_count = len(self.manifest.list_games())
                    logger.info(f"Menu Utama: Pemindaian selesai. Total game terdaftar: {games_count}")
                    self.ui.show_message("SELESAI", f"Ditemukan {games_count} game arcade!", wait_seconds=1.5)
                elif selected_data == "empty_hint":
                    logger.info("Menu Utama: Petunjuk penempatan ROM ditampilkan.")
                    self.ui.show_message("PETUNJUK", "Letakkan file ROM (.zip) di folder roms, lalu pilih PINDAI.", wait_seconds=2.5)
                elif isinstance(selected_data, dict):
                    logger.info(f"Menu Utama: Pengguna memilih game '{selected_data.get('display_name')}' ({selected_data.get('game_id')})")
                    self._game_action_loop(selected_data)

    def _game_action_loop(self, game: Dict[str, Any]) -> None:
        """Layar 2: Pilih Mode Permainan (Offline / Online)."""
        options = [
            ("🕹️  MAIN OFFLINE", "offline"),
            ("🌐 MAIN ONLINE", "online"),
            ("⬅️  KEMBALI", "back"),
        ]
        selected_idx = 0
        needs_redraw = True
        last_render_time = 0.0

        # Prime room cache asynchronously in background
        self.api.get_cached_rooms(game["game_id"])

        while True:
            # Refresh online players count non-blocking
            rooms = self.api.get_cached_rooms(game["game_id"], max_age=3.0)

            now = time.time()
            if needs_redraw or (now - last_render_time >= 1.0):
                lines = [
                    f"Game: {game['display_name']}",
                    "",
                    "PILIH MODE PERMAINAN:"
                ]
                for idx, (label, _) in enumerate(options):
                    prefix = "> [ " if idx == selected_idx else "  [ "
                    lines.append(f"{prefix}{label} ]")

                lines.append("")
                lines.append(f"Room Online Aktif: {len(rooms)}")

                self.ui.draw_box(
                    game["display_name"],
                    lines,
                    "UP/DOWN: Pilih | ENTER: Lanjut | ESC: Kembali"
                )
                last_render_time = now
                needs_redraw = False

            key = self.ui.get_key()
            if self.ui.is_back(key):
                break
            elif self.ui.is_up(key):
                selected_idx = (selected_idx - 1) % len(options)
                needs_redraw = True
            elif self.ui.is_down(key):
                selected_idx = (selected_idx + 1) % len(options)
                needs_redraw = True
            elif self.ui.is_enter(key):
                needs_redraw = True
                _, choice = options[selected_idx]
                if choice == "offline":
                    logger.info(f"Menu Mode: Memilih MAIN OFFLINE untuk '{game.get('display_name')}'")
                    self._launch_offline(game)
                elif choice == "online":
                    logger.info(f"Menu Mode: Memilih MAIN ONLINE untuk '{game.get('display_name')}'")
                    self._online_mode_loop(game)
                elif choice == "back":
                    break

    def _online_mode_loop(self, game: Dict[str, Any]) -> None:
        """Layar 2b: Pilihan Online (Cari Room / Buat Room)."""
        actions = ["CARI ROOM", "BUAT ROOM", "KEMBALI"]
        selected_idx = 0
        needs_redraw = True
        last_render_time = 0.0

        # Prime room cache asynchronously
        self.api.get_cached_rooms(game["game_id"])

        while True:
            # Refresh online players count non-blocking
            rooms = self.api.get_cached_rooms(game["game_id"], max_age=3.0)

            now = time.time()
            if needs_redraw or (now - last_render_time >= 1.0):
                lines = [
                    f"Game: {game['display_name']}",
                    "Mode: ONLINE MULTIPLAYER",
                    "",
                    "PILIHAN MENU:"
                ]
                for idx, act in enumerate(actions):
                    prefix = "> [ " if idx == selected_idx else "  [ "
                    lines.append(f"{prefix}{act} ]")

                lines.append("")
                lines.append(f"Room Aktif: {len(rooms)}")

                self.ui.draw_box(
                    f"{game['display_name']} [ONLINE]",
                    lines,
                    "UP/DOWN: Pilih | ENTER: Buka | ESC: Kembali"
                )
                last_render_time = now
                needs_redraw = False

            key = self.ui.get_key()
            if self.ui.is_back(key):
                break
            elif self.ui.is_up(key):
                selected_idx = (selected_idx - 1) % len(actions)
                needs_redraw = True
            elif self.ui.is_down(key):
                selected_idx = (selected_idx + 1) % len(actions)
                needs_redraw = True
            elif self.ui.is_enter(key):
                needs_redraw = True
                action = actions[selected_idx]
                logger.info(f"Menu Aksi Online '{game.get('display_name')}': Memilih [{action}]")
                if action in ("CARI ROOM", "BUAT ROOM"):
                    online, _ = self.api.get_cached_health(max_age=3.0)
                    if not online:
                        online, _ = self.api.check_health()
                    if not online:
                        logger.warning("Pemeriksaan server sebelum aksi: SERVER OFFLINE.")
                        self.ui.show_message(
                            "SERVER OFFLINE",
                            "Server belum aktif! Buka terminal lain dan ketik: python3 -m server.app",
                            wait_seconds=3.0
                        )
                        continue

                if action == "CARI ROOM":
                    self._browse_rooms_loop(game)
                elif action == "BUAT ROOM":
                    self._create_room_flow(game)
                elif action == "KEMBALI":
                    break

    def _launch_offline(self, game: Dict[str, Any]) -> None:
        """Jalankan game secara lokal / offline di RetroArch biasa."""
        game_id = game["game_id"]
        logger.info(f"Menu Mode: Mempersiapkan peluncuran OFFLINE game '{game.get('display_name')}' ({game_id})")

        self.ui.show_message("MEMERIKSA GAME", f"Memeriksa aset game {game.get('display_name')}...", wait_seconds=0.3)
        valid, code, details = self.validator.verify_local_game(game_id, strict_hash=not self.dry_run)
        if not valid and not self.dry_run:
            logger.error(f"Validasi game offline gagal: {code} - {details.get('message')}")
            self.ui.show_message("ASET TIDAK LENGKAP", details.get("message", "Game tidak siap dimainkan."), wait_seconds=3.0)
            return

        core_path = details.get("core_lib") if details else game.get("core_path")
        rom_path = details.get("rom_path") if details else game.get("scanned_rom_path")
        ra_bin = details.get("retroarch_bin") or self.ra_controller.retroarch_bin

        if not core_path or not rom_path:
            self.ui.show_message("ASET TIDAK LENGKAP", "Core atau file ROM tidak ditemukan.", wait_seconds=3.0)
            return

        if ra_bin:
            self.ra_controller.retroarch_bin = ra_bin

        launch_cfg = RetroArchLaunchConfig(
            mode="offline",
            core_path=core_path,
            rom_path=rom_path,
            session_id=game_id,
            retroarch_bin=ra_bin,
            fullscreen=self.fullscreen,
        )

        logger.info(f"Meluncurkan RetroArch Offline untuk game: {game.get('display_name')}")
        self.ui.show_message("MEMBUKA GAME...", f"Membuka {game.get('display_name')} di RetroArch...", wait_seconds=0.5)
        self.ui.pause_gamepad()
        try:
            res = self.ra_controller.launch(launch_cfg, dry_run=self.dry_run)
        finally:
            self.ui.resume_gamepad()
            self.ui.init_curses()
            self.trigger_log_upload("offline_game_end")

        if res.status == "MOCK_SUCCESS":
            self.ui.show_message("SIMULASI BERHASIL", "Mode simulasi aktif! Game offline selesai dimainkan.", wait_seconds=2.0)
        elif res.exit_code != 0 or res.status in ("FAILED", "CRASHED"):
            err_text = res.error_message or f"Kode keluar: {res.exit_code}"
            self.ui.show_message("RETROARCH GAGAL DIBUKA", f"Gagal menjalankan game:\n{err_text[:250]}", wait_seconds=4.0)

    def _browse_rooms_loop(self, game: Dict[str, Any]) -> None:
        """Layar 3: Cari dan Gabung ke Room."""
        selected_idx = 0
        needs_redraw = True
        last_render_time = 0.0

        # Prime room and latency checks asynchronously
        self.api.get_cached_rooms(game["game_id"])
        self.api.get_cached_latency_ms()

        while True:
            rooms = self.api.get_cached_rooms(game["game_id"], max_age=2.5)
            latency = self.api.get_cached_latency_ms(max_age=5.0)
            latency_str = f" ({latency:.0f}ms)" if latency > 0 else ""

            if rooms and selected_idx >= len(rooms):
                selected_idx = max(0, len(rooms) - 1)

            now = time.time()
            if needs_redraw or (now - last_render_time >= 1.0):
                lines = ["DAFTAR ROOM MENUNGGU LAWAN:", ""]

                if not rooms:
                    lines.append("Belum ada room tersedia.")
                    lines.append("Pilih [BUAT ROOM] untuk menjadi Host!")
                else:
                    for idx, r in enumerate(rooms):
                        prefix = "> " if idx == selected_idx else "  "
                        lines.append(f"{prefix}[{r['name']}] Host: {r['host_name']}{latency_str}")

                self.ui.draw_box(
                    f"CARI ROOM - {game['display_name']}",
                    lines,
                    "UP/DOWN: Pilih | ENTER: Gabung | ESC: Batal"
                )
                last_render_time = now
                needs_redraw = False

            key = self.ui.get_key()
            if self.ui.is_back(key):
                break
            elif rooms and self.ui.is_up(key):
                selected_idx = (selected_idx - 1) % len(rooms)
                needs_redraw = True
            elif rooms and self.ui.is_down(key):
                selected_idx = (selected_idx + 1) % len(rooms)
                needs_redraw = True
            elif rooms and self.ui.is_enter(key):
                selected_room = rooms[selected_idx]
                self._join_room_flow(game, selected_room)
                break

    def _create_room_flow(self, game: Dict[str, Any]) -> None:
        """Layar 4: Buat Room dan Menunggu Lawan."""
        logger.info(f"Memeriksa aset lokal untuk pembuatan room game '{game.get('display_name')}'...")
        valid, code, details = self.validator.verify_local_game(game["game_id"], strict_hash=not self.dry_run)
        if not valid and not self.dry_run:
            logger.error(f"Validasi lokal gagal [{code}]: {details.get('message')}")
            self.ui.show_message("KESALAHAN SISTEM", details.get("message", code))
            return

        compat = {
            "core": game["retroarch_core"],
            "core_version": game.get("core_version"),
            "rom_hash": list(game.get("rom_hashes", {}).values())[0] if game.get("rom_hashes") else None
        }

        room_name = f"{self.player_name}'s {game['display_name']}"
        ok, data = self.api.create_room(game["game_id"], room_name, self.player_name, compat)
        if not ok:
            logger.error(f"Gagal membuat room pada server: {data.get('message')}")
            self.ui.show_message("GAGAL MEMBUAT ROOM", data.get("message", "Server error"))
            return

        room_id = data["room_id"]
        host_token = data["host_token"]
        host_id = data["player_id"]
        logger.info(f"Room berhasil dibuka! ID: {room_id} (Game: '{game['display_name']}' [{game['game_id']}] | Host: '{self.player_name}') | Menunggu penantang...")

        # Waiting screen
        opponent_name = None
        last_poll = time.time()
        last_heartbeat = 0.0
        needs_redraw = True
        last_render_time = 0.0

        try:
            while not opponent_name:
                now = time.time()
                if needs_redraw or (now - last_render_time >= 1.0):
                    lines = [
                        f"Room: {room_name}",
                        f"Room ID: {room_id}",
                        "",
                        "Menunggu lawan bergabung...",
                        ""
                    ]
                    self.ui.draw_box("MENUNGGU LAWAN", lines, "Tekan ESC untuk Batal")
                    last_render_time = now
                    needs_redraw = False

                key = self.ui.get_key()
                if self.ui.is_back(key):
                    logger.info(f"Host membatalkan room {room_id}.")
                    return  # Canceled

                # Send heartbeat every 3.0s (not every tick!)
                if now - last_heartbeat >= 3.0:
                    self.api.send_heartbeat(room_id, host_id, host_token)
                    last_heartbeat = now

                # Poll signals with short timeout (0.2s)
                signals = self.api.poll_signals(room_id, host_id, since=last_poll, timeout=0.2)
                last_poll = time.time()

                for s in signals:
                    if s.get("event") == "room.joined":
                        opponent_name = s.get("payload", {}).get("client_name", "Player 2")
                        logger.info(f"Penantang terdeteksi bergabung: '{opponent_name}'!")
                        break

            # Opponent joined -> Show connection screen
            def update_ui_steps(steps):
                self.ui.show_connection_screen(steps)

            logger.info("Memulai negosiasi koneksi P2P / Relay sebagai Host...")
            result = self.conn_mgr.negotiate_as_host(
                room_id=room_id,
                host_id=host_id,
                host_token=host_token,
                netplay_port=game.get("default_port", 55435),
                on_progress=update_ui_steps
            )

            if not result.success:
                logger.error(f"Koneksi gagal: {result.error_message}")
                self.ui.show_message("KONEKSI GAGAL", result.error_message or "Gagal menghubungkan")
                return

            logger.info(f"Koneksi siap ({result.mode.upper()}). Mempersiapkan jendela RetroArch...")
            time.sleep(0.5)

            # Launch RetroArch
            self.ui.restore_terminal()
            ra_bin = details.get("retroarch_bin") or self.ra_controller.retroarch_bin
            if ra_bin:
                self.ra_controller.retroarch_bin = ra_bin
            launch_cfg = RetroArchLaunchConfig(
                mode="host",
                core_path=details.get("core_lib") if details else "/mock/core.so",
                rom_path=details.get("rom_path") if details else "/mock/sf2.zip",
                port=result.target_port,
                nickname=self.player_name,
                session_id=room_id,
                retroarch_bin=ra_bin,
                fullscreen=self.fullscreen,
                check_frames=self.check_frames,
                input_latency_frames=self.input_latency_frames,
                stateless_mode=self.stateless_mode,
                sync_sram=self.sync_sram
            )
            supervisor = SessionSupervisor(
                api=self.api,
                room_id=room_id,
                player_id=host_id,
                token=host_token,
                role="host",
                ra_controller=self.ra_controller,
                local_bridge=result.local_bridge
            )
            supervisor.start()

            self.ui.pause_gamepad()
            try:
                res = self.ra_controller.launch(launch_cfg, dry_run=self.dry_run)
            finally:
                self.ui.resume_gamepad()
                supervisor.stop()
                if result.local_bridge:
                    result.local_bridge.stop()
                try:
                    self.api.send_signal(room_id, host_id, "peer.left", {"reason": f"{self.player_name} keluar dari game"})
                except Exception:
                    pass
                self.trigger_log_upload("host_session_end")

            self.ui.init_curses()
            if supervisor.peer_disconnected:
                msg = supervisor.disconnect_reason or "Lawan terputus dari permainan."
                logger.warning(f"Sesi netplay diakhiri: {msg}")
                self.ui.show_message("LAWAN TERPUTUS", f"{msg}\nPermainan diakhiri.", wait_seconds=3.0)
            elif res.status == "MOCK_SUCCESS":
                self.ui.show_message("SIMULASI BERHASIL", "Mode --dry-run aktif! Koneksi disimulasikan tanpa membuka game fisik.", wait_seconds=2.5)
            elif res.exit_code != 0 or res.status in ("FAILED", "CRASHED"):
                err_text = res.error_message or f"Kode keluar: {res.exit_code}"
                self.ui.show_message("RETROARCH GAGAL DIBUKA", f"Gagal menjalankan game:\n{err_text[:250]}", wait_seconds=4.0)

        finally:
            self.api.close_room(room_id, host_token)
            self.ui.init_curses()

    def _join_room_flow(self, game: Dict[str, Any], room: Dict[str, Any]) -> None:
        """Layar 5: Gabung ke Room Lawan."""
        logger.info(f"Memeriksa kompatibilitas lokal untuk bergabung ke room '{room.get('name')}' (Game: {game.get('display_name')})...")
        valid, code, details = self.validator.verify_local_game(game["game_id"], strict_hash=not self.dry_run)
        if not valid and not self.dry_run:
            logger.error(f"Validasi lokal gagal [{code}]: {details.get('message')}")
            self.ui.show_message("KESALAHAN SISTEM", details.get("message", code))
            return

        compat = {
            "core": game["retroarch_core"],
            "core_version": game.get("core_version"),
            "rom_hash": list(game.get("rom_hashes", {}).values())[0] if game.get("rom_hashes") else None
        }

        logger.info(f"Mengirim permintaan gabung ke room {room['room_id']}...")
        ok, join_data = self.api.join_room(room["room_id"], self.player_name, compat)
        if not ok:
            err_code = join_data.get("code", "ERROR")
            friendly_msg = ERROR_MESSAGES.get(err_code, join_data.get("message", "Gagal bergabung"))
            logger.warning(f"Gagal bergabung ke room: {friendly_msg}")
            self.ui.show_message("TIDAK DAPAT BERGABUNG", friendly_msg)
            return

        client_id = join_data["player_id"]
        client_token = join_data["client_token"]
        logger.info(f"Berhasil bergabung ke room {room['room_id']}! Player ID: {client_id} (Game: '{game['display_name']}' | Host: '{room.get('host_name', 'Player 1')}')")

        def update_ui_steps(steps):
            self.ui.show_connection_screen(steps)

        logger.info("Memulai negosiasi koneksi P2P / Relay sebagai Client...")
        result = self.conn_mgr.negotiate_as_client(
            room_id=room["room_id"],
            client_id=client_id,
            client_token=client_token,
            on_progress=update_ui_steps
        )

        if not result.success:
            logger.error(f"Koneksi client gagal: {result.error_message}")
            self.ui.show_message("KONEKSI GAGAL", result.error_message or "Gagal menghubungkan")
            self.api.leave_room(room["room_id"], client_id, client_token)
            return

        logger.info(f"Koneksi siap ({result.mode.upper()}). Mempersiapkan jendela RetroArch Client...")
        time.sleep(0.5)

        # Launch RetroArch
        self.ui.restore_terminal()
        ra_bin = details.get("retroarch_bin") or self.ra_controller.retroarch_bin
        if ra_bin:
            self.ra_controller.retroarch_bin = ra_bin
        launch_cfg = RetroArchLaunchConfig(
            mode="client",
            core_path=details.get("core_lib") if details else "/mock/core.so",
            rom_path=details.get("rom_path") if details else "/mock/sf2.zip",
            port=result.target_port,
            connect_ip=result.target_ip,
            nickname=self.player_name,
            session_id=room["room_id"],
            retroarch_bin=ra_bin,
            fullscreen=self.fullscreen,
            check_frames=self.check_frames,
            input_latency_frames=self.input_latency_frames,
            stateless_mode=self.stateless_mode,
            sync_sram=self.sync_sram
        )

        supervisor = SessionSupervisor(
            api=self.api,
            room_id=room["room_id"],
            player_id=client_id,
            token=client_token,
            role="client",
            ra_controller=self.ra_controller,
            local_bridge=result.local_bridge
        )
        supervisor.start()

        if result.mode == "direct" and not self.dry_run and not os.environ.get("ARCADE_MOCK_RETROARCH"):
            # Give Host's RetroArch time to boot and start listening on netplay port
            logger.info("Direct P2P: Menunggu 1.5 detik agar Host RetroArch siap menerima koneksi...")
            time.sleep(1.5)

        self.ui.pause_gamepad()
        try:
            res = self.ra_controller.launch(launch_cfg, dry_run=self.dry_run)
        finally:
            self.ui.resume_gamepad()
            supervisor.stop()
            if result.local_bridge:
                result.local_bridge.stop()
            try:
                self.api.send_signal(room["room_id"], client_id, "peer.left", {"reason": f"{self.player_name} keluar dari game"})
            except Exception:
                pass
            self.api.leave_room(room["room_id"], client_id, client_token)
            self.trigger_log_upload("client_session_end")
            self.ui.init_curses()

        if supervisor.peer_disconnected:
            msg = supervisor.disconnect_reason or "Lawan terputus dari permainan."
            logger.warning(f"Sesi netplay diakhiri: {msg}")
            self.ui.show_message("LAWAN TERPUTUS", f"{msg}\nPermainan diakhiri.", wait_seconds=3.0)
        elif res.status == "MOCK_SUCCESS":
            self.ui.show_message("SIMULASI BERHASIL", "Mode --dry-run aktif! Koneksi disimulasikan tanpa membuka game fisik.", wait_seconds=2.5)
        elif res.exit_code != 0 or res.status in ("FAILED", "CRASHED"):
            err_text = res.error_message or f"Kode keluar: {res.exit_code}"
            self.ui.show_message("RETROARCH GAGAL DIBUKA", f"Gagal menjalankan game:\n{err_text[:250]}", wait_seconds=4.0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Arcade Online Launcher - One-Click RetroArch Multiplayer")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument("--server", help="Matchmaking server URL")
    parser.add_argument("--name", help="Cabinet / player nickname")
    parser.add_argument("--retroarch-bin", help="Path to RetroArch executable")
    parser.add_argument("--rom-dir", action="append", help="Extra ROM directory to scan (can be repeated)")
    parser.add_argument("--core-dir", action="append", help="Extra Core directory to scan (can be repeated)")
    parser.add_argument("--scan", action="store_true", help="Perform dynamic scan of cores & ROMs and print summary")
    parser.add_argument("--log-file", default="arcade_launcher.log", help="Path to log file (default: arcade_launcher.log)")
    parser.add_argument("--show-logs", action="store_true", help="Print recent launcher logs and exit")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging")
    parser.add_argument("--auto-server", action="store_true",
                        help="Auto-start embedded matchmaking server if offline (convenient for 1-machine testing)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulate execution without requiring real emulator or display")
    parser.add_argument("--cli", action="store_true",
                        help="Run in CLI mode without curses TUI")
    parser.add_argument("--list", action="store_true",
                        help="List active rooms and exit")
    parser.add_argument("--create", action="store_true",
                        help="Create a room via CLI")
    parser.add_argument("--game", default="sf2",
                        help="Game ID for room creation (default: sf2)")
    parser.add_argument("--room-name", help="Custom room name")
    parser.add_argument("--join", help="Join room by Room ID via CLI")
    parser.add_argument("--play", "--offline", dest="play_offline", metavar="GAME_ID",
                        help="Launch a game directly in offline/local RetroArch mode")
    parser.add_argument("--check-frames", type=int, help="Netplay sync check interval in frames (e.g. 30)")
    parser.add_argument("--input-latency", type=int, help="Netplay input delay buffer in frames (e.g. 2)")
    parser.add_argument("--stateless", action="store_true", default=None, help="Force stateless/lockstep mode")
    parser.add_argument("--local-roms-only", action="store_true", default=None,
                        help="Only scan the single project 'roms' folder (exclude system directories)")
    parser.add_argument("--all-rom-dirs", action="store_true",
                        help="Scan all system ROM directories across internal and external disks")

    parser.add_argument("--upload-logs", action="store_true",
                        help="Upload log file to VPS log server immediately and exit")

    args = parser.parse_args()

    # Configure logger
    setup_launcher_logging(
        log_file=args.log_file,
        verbose=args.verbose,
        log_to_console=(args.cli or args.show_logs or args.scan)
    )
    logger.info("Arcade Online Launcher diinisialisasi.")

    if args.show_logs:
        logs = []
        if os.path.isfile(args.log_file):
            try:
                with open(args.log_file, "r", encoding="utf-8") as f:
                    logs = [line.rstrip() for line in f.readlines()[-50:]]
            except Exception:
                pass
        if not logs:
            logs = get_recent_logs(50)

        print(f"\n=== LOG SISTEM TERAKHIR ({args.log_file}) ===")
        for l in logs:
            print(l)
        print("============================================\n")
        return

    # Load defaults from config.json if present (supports // and # comments)
    cfg = {}
    if os.path.isfile(args.config):
        try:
            with open(args.config, "r", encoding="utf-8") as f:
                content = f.read()
            import re
            pattern = re.compile(r"(?:/\*.*?\*/|//[^\r\n]*|#[^\r\n]*)|(\"(?:\\.|[^\"\\])*\")", re.DOTALL)
            clean_json = pattern.sub(lambda m: m.group(1) if m.group(1) is not None else "", content)
            cfg = json.loads(clean_json)
        except Exception as e:
            logger.warning(f"Peringatan saat memuat konfigurasi {args.config}: {e}")

    server_url = (
        args.server
        or os.environ.get("ARCADE_SERVER_URL")
        or cfg.get("server", {}).get("url")
        or "http://localhost:8080"
    )
    player_name = (
        args.name
        or os.environ.get("ARCADE_PLAYER_NAME")
        or cfg.get("client", {}).get("player_name")
        or "ArcadeCab1"
    )
    from catalog.validator import find_retroarch_binary
    ra_bin = (
        args.retroarch_bin
        or os.environ.get("ARCADE_RETROARCH_BIN")
        or cfg.get("retroarch", {}).get("binary_path")
        or find_retroarch_binary()
    )

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    local_roms = os.path.join(base_dir, "roms")
    cwd_roms = os.path.abspath("roms")

    custom_roms = []
    # Highest priority: local project roms folder
    if os.path.isdir(local_roms):
        custom_roms.append(local_roms)
    elif os.path.isdir(cwd_roms):
        custom_roms.append(cwd_roms)

    # Then CLI arguments or user configuration
    if args.rom_dir:
        for r in args.rom_dir:
            r_abs = os.path.abspath(r) if not os.path.isabs(r) else r
            if r_abs not in custom_roms:
                custom_roms.append(r_abs)

    cfg_rom = cfg.get("retroarch", {}).get("custom_roms_dir")
    if cfg_rom:
        cfg_rom_abs = os.path.abspath(cfg_rom) if not os.path.isabs(cfg_rom) else cfg_rom
        if cfg_rom_abs not in custom_roms and os.path.isdir(cfg_rom_abs):
            custom_roms.append(cfg_rom_abs)

    custom_cores = list(args.core_dir or [])
    cfg_core = cfg.get("retroarch", {}).get("custom_cores_dir")
    if cfg_core and cfg_core not in custom_cores:
        custom_cores.append(cfg_core)

    check_frames = args.check_frames if args.check_frames is not None else cfg.get("retroarch", {}).get("check_frames", 600)
    input_latency = args.input_latency if args.input_latency is not None else cfg.get("retroarch", {}).get("input_latency_frames", 5)
    stateless = args.stateless if args.stateless is not None else cfg.get("retroarch", {}).get("stateless_mode", False)
    sync_sram = cfg.get("retroarch", {}).get("sync_sram", True)
    pref_arcade = cfg.get("retroarch", {}).get("preferred_arcade_core")
    pref_cores = [pref_arcade] if pref_arcade else None

    local_roms_only = cfg.get("retroarch", {}).get("scan_local_roms_only", True)
    if args.local_roms_only is not None:
        local_roms_only = args.local_roms_only
    if args.all_rom_dirs:
        local_roms_only = False

    app = ArcadeLauncherApp(
        server_url=server_url,
        retroarch_bin=ra_bin,
        player_name=player_name,
        custom_rom_dirs=custom_roms,
        custom_core_dirs=custom_cores,
        dry_run=args.dry_run,
        check_frames=check_frames,
        input_latency_frames=input_latency,
        stateless_mode=stateless,
        sync_sram=sync_sram,
        preferred_arcade_cores=pref_cores,
        local_roms_only=local_roms_only,
        log_file=args.log_file,
        log_uploader_cfg=cfg.get("logging", {})
    )

    if args.upload_logs:
        ok, msg = app.log_uploader.upload_sync("manual_cli")
        print(("[✓] " if ok else "[X] GAGAL: ") + msg)
        sys.exit(0 if ok else 1)

    if args.play_offline:
        app.run_cli_play_offline(args.play_offline)
    elif args.scan:
        app.run_cli_scan()
    elif args.list:
        app.run_cli_list(args.game)
    elif args.create:
        app.run_cli_create(args.game, args.room_name)
    elif args.join:
        app.run_cli_join(args.join)
    elif args.cli:
        app.run_cli_list()
    else:
        app.run_interactive()


if __name__ == "__main__":
    main()

