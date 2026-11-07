# Arcade Online Launcher — One-Click Multiplayer untuk RetroArch

Aplikasi antarmuka dan penghubung multiplayer arcade untuk RetroArch dengan prinsip **"Pilih Game → Cari/Buat Room → Main"**.

Sistem menyembunyikan seluruh kompleksitas jaringan (IP address, port forwarding, NAT traversal, STUN, signaling, relay fallback, dan parameter RetroArch Netplay) di balik antarmuka ramah arcade yang dapat dikendalikan dengan joystick.

---

## 🚀 Fitur Utama

1. **Pengalaman Satu Klik (One-Click Netplay)**:
   - Pemain hanya memilih game (default: **Street Fighter II: The World Warrior**), memilih Buat Room atau Cari Room, lalu langsung bermain.
2. **Pemindaian Otomatis Dinamis (Dynamic Auto-Scan)**:
   - Sistem **secara otomatis memindai** core RetroArch yang terpasang (MAME, FBNeo, dll.) dan seluruh folder ROM lokal (termasuk partisi Batocera, flashdisk USB, dan subdirektori).
   - Mengidentifikasi judul game arcade secara otomatis (Street Fighter, Metal Slug, King of Fighters, dll.) atau memberi nama otomatis untuk ROM lainnya.
   - Menu launcher menyertakan opsi **`[ 🔄 PINDAI ULANG DISK / RESCAN ]`** langsung dari antarmuka.
3. **Koneksi Direct-First, Relay-Fallback**:
   - Sistem secara otomatis mengutamakan koneksi langsung (P2P direct) jika dimungkinkan oleh jaringan.
   - Jika kedua mesin berada di balik CGNAT / firewall simetris, sistem secara transparan beralih ke Netplay Relay Tunnel berkecepatan tinggi dengan `TCP_NODELAY`.
4. **Pemeriksaan Kompatibilitas Otomatis**:
   - Memeriksa executable RetroArch, ketersediaan core MAME / FBNeo, dan hash ROM (`sha1`, `md5`, `crc32`) sebelum room dapat dimasuki. Mencegah desinkronisasi netplay.
5. **Isolasi Konfigurasi RetroArch yang Aman**:
   - Launcher tidak pernah menimpa file `retroarch.cfg` pengguna secara permanen. Konfigurasi netplay dibuat dalam temporary file terisolasi (`--appendconfig`) dan dibersihkan otomatis begitu game ditutup.
6. **Antarmuka Ganda (TUI & CLI)**:
   - Antarmuka retro bergaya arcade berbasis `curses` yang dinavigasi via D-Pad / Joystick.
   - Mode CLI non-interaktif untuk pengujian, SSH, atau integrasi otomatis.

---

## 📁 Struktur Proyek

```text
online_netplay/
├── catalog/
│   ├── manifest.json                  # Katalog game, spesifikasi core, dan hash ROM
│   └── validator.py                   # Pemeriksa ROM, core libretro, dan binary RetroArch
├── server/
│   ├── app.py                         # Runner server mandiri (API + Signaling + Relay)
│   ├── api.py                         # REST API Matchmaking & Signaling Handler
│   ├── models.py                      # Data models Room, Player, Signaling
│   ├── room_store.py                  # In-memory room store dengan TTL & slot locking
│   ├── signaling.py                   # Hub signaling real-time
│   └── relay.py                       # TCP Netplay Relay berkecepatan tinggi
├── launcher/
│   ├── main.py                        # Entrypoint utama Arcade Launcher
│   ├── retroarch_controller.py        # Pengendali & supervisor proses RetroArch
│   ├── connection_manager.py          # Strategi negosiasi Direct & Relay Fallback
│   ├── client_api.py                  # Klien HTTP & Signaling
│   └── ui.py                          # TUI Curses arcade & CLI fallback
├── deploy/
│   ├── Dockerfile                     # Image container server VPS
│   ├── docker-compose.yml             # Orkestrasi Docker Compose
│   ├── arcade-server.service          # Unit systemd untuk Linux Server
│   └── batocera_install.sh            # Skrip instalasi Batocera / EmuELEC
├── tests/
│   ├── test_validator.py              # Uji verifikasi ROM dan core
│   ├── test_retroarch_controller.py   # Uji command generator & appendconfig
│   ├── test_room_store.py             # Uji siklus hidup room dan TTL
│   ├── test_server_api.py             # Uji REST API Matchmaking
│   ├── test_relay.py                  # Uji bidirectional TCP Relay
│   └── test_e2e_flow.py               # Uji simulasi alur lengkap Host & Client
├── config.json                        # Konfigurasi default
└── arcade_online_launcher_spec.md     # Dokumen spesifikasi produk & teknis
```

---

## 🕹️ Panduan Penggunaan Launcher

### 1. Menjalankan TUI Interaktif (Mode Arcade Cabinet)

```bash
python3 -m launcher.main
```

**Kontrol Navigasi:**
- **UP / DOWN** (atau W / S): Memilih menu / game / room
- **ENTER** (atau Spasi / Tombol 1): Konfirmasi / Gabung / Buat Room
- **ESC** (atau Q / Tombol 2): Kembali / Batal

### 2. Menjalankan via Command Line (CLI)

```bash
# Memindai otomatis semua core dan ROM di sistem
python3 -m launcher.main --scan

# Menampilkan 50 baris log terakhir launcher
python3 -m launcher.main --show-logs

# Menjalankan dengan mode verbose log di terminal
python3 -m launcher.main --verbose

# Menampilkan daftar room aktif
python3 -m launcher.main --list --server http://ip-server:8080

# Membuat room sebagai Host
python3 -m launcher.main --create --game street-fighter-ii --name "Dojo SF2" --server http://ip-server:8080

# Bergabung ke room tertentu sebagai Client
python3 -m launcher.main --join <ROOM_ID> --server http://ip-server:8080

# Mode simulasi (dry-run tanpa emulator fisik)
python3 -m launcher.main --dry-run

# Menjalankan dalam mode jendela (ideal untuk menguji 2 pemain di 1 laptop)
python3 -m launcher.main --windowed
```

---

## 🌐 Menghubungkan Game Lewat Internet

Agar Anda dan teman Anda di jaringan berbeda dapat bermain bersama, Anda dapat memilih salah satu metode:

### Cara 1: Menggunakan Tailscale / ZeroTier (*Gratis & P2P Langsung Tanpa Sewa VPS*)
1. Install [Tailscale](https://tailscale.com/) di laptop Anda dan laptop teman Anda.
2. Login akun yang sama atau bagikan node koneksi.
3. Dapatkan IP virtual Tailscale (misal: `100.80.20.10`).
4. Jalankan server di laptop Anda:
   ```bash
   python3 -m server.app
   ```
5. Teman Anda menjalankan launcher mengarah ke IP Tailscale Anda:
   ```bash
   python3 -m launcher.main --server "http://100.80.20.10:8080"
   ```

### Cara 2: Deploy di Cloud Server / VPS
1. Jalankan server di VPS dengan IP Publik (misal: `217.216.146.15`):
   ```bash
   python3 -m server.app --host 0.0.0.0 --port 8080 --relay-port 55436 --public-relay-host 217.216.146.15
   ```
   *(Buka port `8080` dan `55436` pada firewall / security group / port forwarding panel VPS Anda)*.
2. Semua pemain cukup mengarahkan launcher ke VPS di `config.json` atau via CLI:
   ```bash
   python3 -m launcher.main --server "http://217.216.146.15:8080"
   ```

---

## 🖥️ Menjalankan Server Mandiri (VPS & Docker)

Server bertugas sebagai perantara pencarian room (*matchmaking*), pertukaran informasi koneksi (*signaling*), dan jalur cadangan (*relay tunnel*) jika koneksi langsung diblokir CGNAT/firewall.

### Menggunakan Python Mandiri:
```bash
# Cukup jalankan perintah ini (IP publik otomatis terdeteksi):
python3 -m server.app

# Atau jika ingin menentukan IP/domain publik secara manual:
python3 -m server.app --host 0.0.0.0 --port 8080 --relay-port 55436 --public-relay-host 103.145.22.88
```

> **Penjelasan Parameter:**
> - `--host 0.0.0.0`: Mendengarkan koneksi dari seluruh internet (bukan hanya localhost).
> - `--port 8080`: Port HTTP untuk API Matchmaking & Signaling (daftar room, buat room, join).
> - `--relay-port 55436`: Port TCP khusus jalur data game Netplay berkecepatan tinggi.
> - `--public-relay-host`: Alamat IP publik internet atau domain server VPS Anda (misal `103.145.22.88`). Parameter ini otomatis terdeteksi jika dibiarkan default (`auto`).

### Menggunakan Docker Compose:
```bash
cd deploy
PUBLIC_IP="203.0.113.10" docker compose up -d
```

### Menggunakan systemd:
```bash
sudo cp deploy/arcade-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now arcade-server
```

---

## ⚙️ Kompatibilitas Game & ROM Dinamis

Sistem **tidak lagi menggunakan daftar game statis**. Katalog game dibuat secara otomatis berdasarkan file ROM yang terdeteksi di mesin Anda.

- **Format ROM yang Didukung:** `.zip` dan `.7z`
- **Sistem yang Didukung:** Arcade (MAME / FBNeo), SNES (`snes9x`), Genesis (`genesis_plus_gx`), NES (`fceumm`).
- **Lokasi Pemindaian Bawaan:**
  - Batocera / EmuELEC: `/userdata/roms/mame`, `/userdata/roms/fbneo`, `/userdata/roms/arcade`, `/userdata/roms/neogeo`
  - RetroPie: `/home/pi/RetroPie/roms/arcade`, `/home/pi/RetroPie/roms/mame-libretro`
  - Linux / PC: `~/roms/mame`, `~/roms/arcade`, `~/roms/fbneo`
  - macOS: `~/RetroArch/roms`, `~/roms/mame`, `~/Downloads/roms`
  - Flashdisk / USB Eksternal: Otomatis mendeteksi partisi di `/media/*`, `/run/media/*`, dan `/Volumes/*`
- **Pemasangan Core Otomatis:** Sistem mendeteksi core libretro yang terpasang di sistem (`fbneo`, `mame2003_plus`, `snes9x`, dll.) dan memilih core terbaik untuk ROM yang dipindai.
- **Folder Kustom:** Tambahkan folder ROM kustom via flag `--rom-dir /path/ke/roms` atau di `config.json`.

---

## 🧪 Menjalankan Automated Test Suite

Seluruh komponen telah dilengkapi dengan automated unit tests dan integration tests:

```bash
# Menjalankan 25 automated unit tests
python3 -m unittest discover tests

# Menjalankan preflight system diagnostics
python3 diagnose.py

# Menjalankan simulasi pertandingan lengkap end-to-end
python3 simulate_match.py
```

Output unit test:
```text
Ran 25 tests in ~0.48s
OK
```