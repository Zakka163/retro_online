# Arcade Online Launcher

Launcher multiplayer untuk RetroArch dengan alur **Pilih Game -> Buat/Cari Room -> Main**.
Pengaturan jaringan (IP, port, NAT traversal, signaling, TCP relay fallback, dan parameter netplay RetroArch) ditangani otomatis di balik antarmuka arcade yang mendukung joystick/D-Pad maupun keyboard.

## Fitur Utama

1. **One-Click Netplay**: Pilih game, buat atau gabung room, lalu langsung bermain.
2. **Pemindaian Otomatis**: Mendeteksi core libretro terpasang (`fbneo`, `mame`, `snes9x`, dll.) dan ROM pada folder `roms/`.
3. **Direct-First, Relay-Fallback**: Mencoba koneksi langsung (P2P TCP) terlebih dahulu; jika gagal akibat CGNAT/firewall/AP isolation, otomatis beralih ke TCP relay di server.
4. **Validasi Kompatibilitas**: Memeriksa binary RetroArch, core, dan hash ROM (`sha1`, `md5`, `crc32`) sebelum sesi dimulai.
5. **Konfigurasi RetroArch Terisolasi**: `retroarch.cfg` tidak pernah ditimpa; parameter netplay disuntikkan melalui file sementara (`--appendconfig`) dan dihapus saat sesi berakhir.
6. **Manajemen Terpusat & Auto-Update**: Mendukung pelaporan status perangkat (`device_reporter.py`), pembaruan launcher otomatis (`updater.py`), dan dashboard monitoring web di server.
7. **Log Diagnostik & Upload Otomatis**: Mencatat versi RetroArch, core (SHA-256), ROM (CRC32), dan parameter netplay, lalu mengirim log ke VPS via SSH key.

## Struktur Proyek

```text
online_netplay/
├── catalog/
│   ├── manifest.json             # Katalog game tambahan (opsional)
│   ├── scanner.py                # Pemindai core libretro & ROM
│   └── validator.py              # Validasi ROM, core, dan binary RetroArch
├── launcher/
│   ├── main.py                   # Entrypoint utama launcher (TUI & CLI)
│   ├── ui.py                     # Antarmuka TUI curses & fallback CLI
│   ├── gamepad.py                # Input joystick/D-Pad untuk menu
│   ├── retroarch_controller.py   # Peluncur & supervisor proses RetroArch
│   ├── retroarch_config.py       # Pembaca konfigurasi kontrol RetroArch
│   ├── connection_manager.py     # Negosiasi Direct P2P & Relay fallback
│   ├── session_supervisor.py     # Pemantau sesi & heartbeat
│   ├── client_api.py             # Klien HTTP ke server matchmaking
│   ├── device_reporter.py        # Pelaporan status perangkat & remote config
│   ├── updater.py                # Auto-updater launcher via HTTP bundle
│   ├── system_info.py            # Deteksi mesin, OS, versi RetroArch/core
│   ├── logger.py                 # Setup logging lokal
│   └── log_uploader.py           # Upload log sesi ke VPS via SSH/SCP
├── server/
│   ├── app.py                    # Entrypoint server (API + Signaling + Relay + Dashboard)
│   ├── api.py                    # REST API matchmaking, signaling, device & OTA
│   ├── dashboard.py              # Router dashboard admin web
│   ├── dashboard_views/          # Halaman dashboard (overview, devices, rooms, games, logs, updates)
│   ├── models.py                 # Model data Room, Player, Signal
│   ├── room_store.py             # Penyimpanan room in-memory dengan TTL
│   ├── device_store.py           # Penyimpanan status perangkat kabinet
│   ├── rom_store.py              # Pengelola repositori & manifest ROM
│   ├── signaling.py              # Hub signaling
│   └── relay.py                  # TCP Netplay Relay
├── deploy/
│   ├── Dockerfile                # Image Docker server
│   ├── docker-compose.yml        # Konfigurasi Docker Compose
│   ├── arcade-server.service     # Unit systemd server
│   ├── batocera_install.sh       # Instalasi pada Batocera
│   └── emuelec_install.sh        # Instalasi pada EmuELEC
├── scripts/
│   ├── diagnose.py               # Preflight diagnostic
│   ├── publish_update.sh         # Rilis bundle update launcher ke VPS
│   ├── sync_to_emuelec.sh        # Sinkronisasi kode + ROM ke perangkat EmuELEC
│   ├── sync_replace.sh           # Mirror penuh proyek ke perangkat EmuELEC
│   ├── set_emuelec_config.sh     # Ubah config.json perangkat EmuELEC via SSH
│   ├── setup_log_ssh.py          # Setup SSH key untuk upload log (lintas OS)
│   ├── setup_log_ssh.sh          # Setup SSH key (Linux/macOS)
│   ├── setup_log_ssh.bat         # Setup SSH key (Windows CMD)
│   ├── setup_log_ssh.ps1         # Setup SSH key (Windows PowerShell)
│   ├── download_log.sh           # Unduh log dari VPS ke lokal
│   └── hapus_log.sh              # Bersihkan log testing di VPS
├── roms/                         # Direktori ROM lokal (.zip/.7z, diabaikan git)
├── roms_repo/                    # Manifest repositori ROM server
├── config.json                   # Konfigurasi utama launcher
└── .gitignore
```

## Menjalankan Launcher

### Mode TUI (Antarmuka Arcade)

```bash
python3 -m launcher.main
```

Pengaturan default dibaca dari `config.json`. Untuk menimpa server atau nama kabinet sementara:

```bash
python3 -m launcher.main --server "http://217.216.146.15:8080" --name ArcadeCab2
```

**Kontrol Menu:**
- `UP` / `DOWN` (`W` / `S`): Navigasi menu, game, atau room
- `ENTER` (`Spasi` / Tombol 1): Konfirmasi / Buat / Gabung
- `ESC` (`Q` / Tombol 2): Kembali / Batal

### Mode CLI

```bash
python3 -m launcher.main --scan
python3 -m launcher.main --show-logs
python3 -m launcher.main --play sf2
python3 -m launcher.main --list
python3 -m launcher.main --create --game sf2 --room-name "Dojo SF2"
python3 -m launcher.main --join <ROOM_ID>
python3 -m launcher.main --dry-run
python3 -m launcher.main --upload-logs
```

## Konfigurasi (`config.json`)

`config.json` mendukung komentar `//`. Parameter utama:

| Bagian | Kunci | Keterangan |
|---|---|---|
| `server` | `url` | Alamat server matchmaking & relay |
| `client` | `player_name` | Nama kabinet/mesin (harus unik per perangkat) |
| `client` | `direct_connection_timeout` | Timeout uji koneksi P2P langsung (detik) |
| `retroarch` | `check_frames` | Interval cek savestate netplay (`0` untuk mode stateless lintas OS) |
| `retroarch` | `input_latency_frames` | Buffer input frame untuk meredam jitter WiFi (disarankan `5`) |
| `retroarch` | `stateless_mode` | `true` untuk sinkronisasi input murni lintas OS |
| `retroarch` | `preferred_arcade_core` | Core arcade utama (mis. `fbneo`) |
| `logging` | `auto_upload` | Aktifkan upload log otomatis ke VPS |
| `logging` | `remote_host` / `remote_port` / `remote_path` | Target upload log SSH |
| `logging` | `ssh_key_path` | Path private key (`null` = kunci default sistem) |

## Menjalankan Server

### Python

```bash
python3 -m server.app --host 0.0.0.0 --port 8080 --relay-port 55436 --public-relay-host 217.216.146.15
```

Pastikan port **8080** (HTTP API & Dashboard) dan **55436** (TCP Relay) terbuka pada firewall VPS.

### Docker Compose

```bash
cd deploy
PUBLIC_IP="217.216.146.15" docker compose up -d
```

### systemd

```bash
sudo cp deploy/arcade-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now arcade-server
```

## Deployment & Pemeliharaan Perangkat EmuELEC

1. Sinkronkan kode dan ROM ke perangkat EmuELEC:
   ```bash
   ./scripts/sync_to_emuelec.sh <IP_EMUELEC>
   ```
2. Atur nama unik kabinet bila diperlukan:
   ```bash
   ./scripts/set_emuelec_config.sh <IP_EMUELEC> --name ArcadeCab3 --restart
   ```
3. Pasang mode autostart boot atau menu Ports:
   ```bash
   ssh root@<IP_EMUELEC> "bash /storage/online_netplay/deploy/emuelec_install.sh boot && reboot"
   # atau mode Ports:
   ssh root@<IP_EMUELEC> "bash /storage/online_netplay/deploy/emuelec_install.sh ports"
   ```
4. Rilis update launcher ke seluruh perangkat melalui server OTA:
   ```bash
   ./scripts/publish_update.sh --version 1.2.1 --notes "Catatan rilis"
   ```

## Diagnostik & Log

Jalankan pemeriksaan pra-terbang (RetroArch, core, ROM, koneksi server, port):

```bash
python3 scripts/diagnose.py
```

Setup SSH key untuk upload log otomatis ke VPS:

```bash
python3 scripts/setup_log_ssh.py
```

Mengunduh atau membersihkan log testing dari VPS:

```bash
./scripts/download_log.sh
./scripts/hapus_log.sh
```
