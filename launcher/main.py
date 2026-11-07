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

logger = logging.getLogger("Arcade.Launcher")


class ArcadeLauncherApp:
    """Manages the interactive launcher lifecycle, dynamic game scanner, and RetroArch execution."""

    def __init__(self, server_url: str = "http://localhost:8080",
                 retroarch_bin: Optional[str] = None,
                 player_name: str = "Arcade1",
                 custom_rom_dirs: Optional[List[str]] = None,
                 custom_core_dirs: Optional[List[str]] = None,
                 dry_run: bool = False,
                 fullscreen: bool = True):
        self.server_url = server_url
        self.player_name = player_name
        self.dry_run = dry_run
        self.fullscreen = fullscreen
        self.custom_rom_dirs = custom_rom_dirs or []
        self.custom_core_dirs = custom_core_dirs or []

        from catalog.scanner import SystemScanner
        self.scanner = SystemScanner(
            custom_rom_dirs=self.custom_rom_dirs,
            custom_core_dirs=self.custom_core_dirs
        )
        self.manifest = GameManifest()
        # Merge dynamically scanned games on startup
        self.manifest.scan_and_merge(self.scanner)

        from catalog.validator import find_retroarch_binary
        self.retroarch_bin = retroarch_bin or find_retroarch_binary()

        self.validator = CatalogValidator(
            manifest=self.manifest,
            rom_dirs=self.custom_rom_dirs,
            core_dirs=self.custom_core_dirs,
            retroarch_bin=self.retroarch_bin
        )
        self.api = ArcadeClientAPI(server_url=self.server_url)
        self.conn_mgr = ConnectionManager(api=self.api)
        self.ra_controller = RetroArchController(retroarch_bin=self.retroarch_bin)
        self.ui = ArcadeTUI()

        logger.info(
            f"Arcade Online Launcher siap. Server: {self.server_url} | "
            f"Pemain: {self.player_name} | RetroArch: {self.retroarch_bin} | "
            f"Tampilan: {'Fullscreen' if self.fullscreen else 'Windowed'}"
        )
        logger.info(f"Katalog game: {len(self.manifest.list_games())} judul game terdaftar.")

    def run_cli_scan(self) -> None:
        """Scan disk and list all discovered arcade ROMs and cores."""
        ArcadeCLI.show_banner()
        print("Memindai sistem untuk emulator RetroArch, core libretro, dan ROM arcade...")
        cores = self.scanner.scan_installed_cores()
        print(f"\n[+] Core Libretro Terdeteksi ({len(cores)}):")
        for cname, cpath in cores.items():
            print(f"  - {cname}: {cpath}")

        rom_dirs = self.scanner.get_system_rom_directories()
        print(f"\n[+] Direktori ROM Dipindai ({len(rom_dirs)}):")
        for d in rom_dirs:
            print(f"  - {d}")

        games = self.scanner.scan_roms()
        ready_games = [g for g in games.values() if g.status == "ready"]
        print(f"\n[+] Game Arcade Ditemukan: {len(games)} (Siap dimainkan: {len(ready_games)}):")
        for g in games.values():
            status_tag = "[READY]" if g.status == "ready" else "[MISSING CORE]"
            print(f"  - {status_tag} {g.display_name} ({g.rom_file}) -> Core: {g.core_name}")

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
                fullscreen=self.fullscreen
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

            try:
                res = self.ra_controller.launch(launch_cfg, dry_run=self.dry_run)
            finally:
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
            fullscreen=self.fullscreen
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

        try:
            res = self.ra_controller.launch(launch_cfg, dry_run=self.dry_run)
        finally:
            supervisor.stop()
            if result.local_bridge:
                result.local_bridge.stop()
            try:
                self.api.send_signal(room_id, client_id, "peer.left", {"reason": f"{self.player_name} keluar dari game"})
            except Exception:
                pass
            self.api.leave_room(room_id, client_id, client_token)

        if supervisor.peer_disconnected:
            print(f"\n[!] Lawan terputus: {supervisor.disconnect_reason}\nPermainan diakhiri.")
        elif res.status in ("FAILED", "CRASHED"):
            print(f"\n[!] Gagal menjalankan game: {res.error_message}")
        print(f"Permainan selesai. Status: {res.status}")

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

    def _run_cli_interactive_menu(self) -> None:
        """Interactive text-based menu when curses is not available (e.g. Windows without windows-curses)."""
        ArcadeCLI.show_banner()
        if sys.platform == "win32":
            print("\n[INFO WINDOWS]")
            print("  Untuk antarmuka grafis terminal (TUI) bergaya arcade di Windows,")
            print("  Anda dapat menginstal: pip install windows-curses\n")

        while True:
            print("\n================= MENU UTAMA =================")
            print(" 1. Buat Room (Host Permainan)")
            print(" 2. Cari & Gabung Room (Client)")
            print(" 3. Pindai Ulang Core & ROM (Rescan)")
            print(" 4. Lihat Log Sistem")
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
                    print("    Letakkan file ROM arcade (.zip) di folder ROM Anda, lalu pilih menu 3 (Rescan).")
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

            elif choice == "2":
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

            elif choice == "3":
                self.run_cli_scan()

            elif choice == "4":
                self.run_show_logs()

            elif choice == "5" or choice.lower() in ("q", "exit"):
                print("Terima kasih telah bermain!")
                break
            else:
                print("Pilihan tidak valid. Silakan pilih 1-5.")

    def _main_menu_loop(self) -> None:
        """Layar 1: Pemilihan Game & Scanner."""
        selected_idx = 0

        while True:
            games = self.manifest.list_games()
            menu_items = []
            if not games:
                menu_items.append(("[ ! ] Tidak ada ROM arcade terdeteksi", "empty_hint"))
            else:
                for g in games:
                    status_icon = "✓" if g.get("status") == "ready" or g.get("scanned_rom_path") else " "
                    menu_items.append((f"[{status_icon}] {g['display_name']}", g))
            menu_items.append(("🔄 PINDAI ULANG DISK / RESCAN", "rescan"))
            menu_items.append(("📋 LIHAT LOG SISTEM", "view_logs"))

            # Check server status
            online, _ = self.api.check_health()
            status_text = "Online" if online else "Offline (Periksa Server)"

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

            key = self.ui.stdscr.getch()
            if key in (27, ord('q'), ord('Q')):  # ESC or q
                break
            elif key in (self.ui.curses.KEY_UP, ord('w'), ord('W')):
                selected_idx = (selected_idx - 1) % len(menu_items)
            elif key in (self.ui.curses.KEY_DOWN, ord('s'), ord('S')):
                selected_idx = (selected_idx + 1) % len(menu_items)
            elif key in (10, 13, self.ui.curses.KEY_ENTER, ord(' ')):
                _, selected_data = menu_items[selected_idx]
                if selected_data == "rescan":
                    # Trigger dynamic re-scan
                    logger.info("Menu Utama: Memulai pemindaian ulang disk (RESCAN)...")
                    self.ui.show_message("MEMINDAI...", "Sedang memindai direktori ROM dan core...", wait_seconds=0.5)
                    self.manifest.scan_and_merge(self.scanner)
                    games_count = len(self.manifest.list_games())
                    logger.info(f"Menu Utama: Pemindaian selesai. Total game terdaftar: {games_count}")
                    self.ui.show_message("SELESAI", f"Ditemukan {games_count} game arcade!", wait_seconds=1.5)
                elif selected_data == "empty_hint":
                    logger.info("Menu Utama: Petunjuk penempatan ROM ditampilkan.")
                    self.ui.show_message("PETUNJUK", "Letakkan file ROM (.zip) di folder roms, lalu pilih RESCAN.", wait_seconds=2.5)
                elif selected_data == "view_logs":
                    logger.info("Menu Utama: Membuka layar penampil log sistem.")
                    self.ui.show_log_viewer(get_recent_logs)
                elif isinstance(selected_data, dict):
                    logger.info(f"Menu Utama: Pengguna memilih game '{selected_data.get('display_name')}' ({selected_data.get('game_id')})")
                    self._game_action_loop(selected_data)

    def _game_action_loop(self, game: Dict[str, Any]) -> None:
        """Layar 2: Cari Room / Buat Room."""
        actions = ["CARI ROOM", "BUAT ROOM", "KEMBALI"]
        selected_idx = 0

        while True:
            # Refresh online players count
            rooms = self.api.list_rooms(game["game_id"])
            total_players = len(rooms) * 2  # Estimate

            lines = [
                f"Game: {game['display_name']}",
                "",
                "PILIHAN MENU:"
            ]
            for idx, act in enumerate(actions):
                prefix = "> [ " if idx == selected_idx else "  [ "
                lines.append(f"{prefix}{act} ]")

            lines.append("")
            lines.append(f"Room Aktif: {len(rooms)}")

            self.ui.draw_box(
                game["display_name"],
                lines,
                "UP/DOWN: Pilih | ENTER: Buka | ESC: Kembali"
            )

            key = self.ui.stdscr.getch()
            if key in (27, ord('q'), ord('Q')):
                break
            elif key in (self.ui.curses.KEY_UP, ord('w'), ord('W')):
                selected_idx = (selected_idx - 1) % len(actions)
            elif key in (self.ui.curses.KEY_DOWN, ord('s'), ord('S')):
                selected_idx = (selected_idx + 1) % len(actions)
            elif key in (10, 13, self.ui.curses.KEY_ENTER, ord(' ')):
                action = actions[selected_idx]
                logger.info(f"Menu Aksi Game '{game.get('display_name')}': Memilih [{action}]")
                if action in ("CARI ROOM", "BUAT ROOM"):
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

    def _browse_rooms_loop(self, game: Dict[str, Any]) -> None:
        """Layar 3: Cari dan Gabung ke Room."""
        selected_idx = 0

        while True:
            rooms = self.api.list_rooms(game["game_id"])
            latency = self.api.measure_latency_ms()
            latency_str = f" ({latency:.0f}ms)" if latency > 0 else ""
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

            key = self.ui.stdscr.getch()
            if key in (27, ord('q'), ord('Q')):
                break
            elif rooms and key in (self.ui.curses.KEY_UP, ord('w'), ord('W')):
                selected_idx = (selected_idx - 1) % len(rooms)
            elif rooms and key in (self.ui.curses.KEY_DOWN, ord('s'), ord('S')):
                selected_idx = (selected_idx + 1) % len(rooms)
            elif rooms and key in (10, 13, self.ui.curses.KEY_ENTER, ord(' ')):
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
        logger.info(f"Room berhasil dibuka! ID: {room_id} | Menunggu penantang...")

        # Waiting screen
        opponent_name = None
        last_poll = time.time()

        try:
            while not opponent_name:
                lines = [
                    f"Room: {room_name}",
                    f"Room ID: {room_id}",
                    "",
                    "Menunggu lawan bergabung...",
                    ""
                ]
                self.ui.draw_box("MENUNGGU LAWAN", lines, "Tekan ESC untuk Batal")

                key = self.ui.stdscr.getch()
                if key in (27, ord('q'), ord('Q')):
                    logger.info(f"Host membatalkan room {room_id}.")
                    return  # Canceled

                self.api.send_heartbeat(room_id, host_id, host_token)
                signals = self.api.poll_signals(room_id, host_id, since=last_poll, timeout=0.5)
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
                fullscreen=self.fullscreen
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

            try:
                res = self.ra_controller.launch(launch_cfg, dry_run=self.dry_run)
            finally:
                supervisor.stop()
                if result.local_bridge:
                    result.local_bridge.stop()
                try:
                    self.api.send_signal(room_id, host_id, "peer.left", {"reason": f"{self.player_name} keluar dari game"})
                except Exception:
                    pass

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
        logger.info(f"Berhasil bergabung ke room! Player ID: {client_id}")

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
            retroarch_bin=ra_bin
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

        try:
            res = self.ra_controller.launch(launch_cfg, dry_run=self.dry_run)
        finally:
            supervisor.stop()
            if result.local_bridge:
                result.local_bridge.stop()
            try:
                self.api.send_signal(room["room_id"], client_id, "peer.left", {"reason": f"{self.player_name} keluar dari game"})
            except Exception:
                pass
            self.api.leave_room(room["room_id"], client_id, client_token)
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

    # Load defaults from config.json if present
    cfg = {}
    if os.path.isfile(args.config):
        try:
            with open(args.config, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass

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

    custom_roms = list(args.rom_dir or [])
    cfg_rom = cfg.get("retroarch", {}).get("custom_roms_dir")
    if cfg_rom and cfg_rom not in custom_roms:
        custom_roms.append(cfg_rom)

    custom_cores = list(args.core_dir or [])
    cfg_core = cfg.get("retroarch", {}).get("custom_cores_dir")
    if cfg_core and cfg_core not in custom_cores:
        custom_cores.append(cfg_core)

    app = ArcadeLauncherApp(
        server_url=server_url,
        retroarch_bin=ra_bin,
        player_name=player_name,
        custom_rom_dirs=custom_roms,
        custom_core_dirs=custom_cores,
        dry_run=args.dry_run
    )

    if args.scan:
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

