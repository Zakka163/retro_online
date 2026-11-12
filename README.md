# Arcade Online Launcher — One-Click Multiplayer untuk RetroArch

Launcher multiplayer arcade untuk RetroArch dengan alur **"Pilih Game → Buat/Cari Room → Main"**.

Semua urusan jaringan (IP, port forwarding, NAT, signaling, relay fallback, dan parameter RetroArch Netplay) diurus otomatis di balik antarmuka bergaya arcade yang bisa dikendalikan dengan joystick.

---

## 🚀 Fitur Utama

1. **One-Click Netplay** — pilih game, pilih *Buat Room* atau *Cari Room*, langsung main.
2. **Pemindaian Otomatis** — mendeteksi core RetroArch yang terpasang (FBNeo, MAME, snes9x, dll.) dan ROM di folder `roms/` proyek (atau seluruh disk dengan `--all-rom-dirs`).
3. **Direct-First, Relay-Fallback** — mencoba koneksi langsung (P2P) dulu; jika gagal (CGNAT/firewall/AP isolation), otomatis beralih ke TCP relay di VPS.
4. **Pemeriksaan Kompatibilitas** — memeriksa binary RetroArch, core, dan hash ROM (`sha1`, `md5`, `crc32`) sebelum masuk room.
5. **Konfigurasi RetroArch Terisolasi** — `retroarch.cfg` tidak pernah ditimpa. Pengaturan netplay ditulis ke file sementara (`--appendconfig`) dan dihapus saat game ditutup.
6. **Log Diagnostik Lengkap** — mencatat nama mesin, hardware/OS, versi RetroArch, core (versi + SHA-256), ROM (ukuran + CRC32), dan parameter netplay.
7. **Upload Log Otomatis ke VPS** — log tiap mesin dikirim ke server via SSH key setelah setiap sesi.
8. **Antarmuka Ganda** — TUI `curses` untuk joystick/D-Pad, dan mode CLI untuk SSH/otomasi.

---

## 📁 Struktur Proyek

```text
online_netplay/
├── catalog/
│   ├── manifest.json            # Katalog game tambahan (opsional)
│   ├── scanner.py               # Pemindai core libretro & ROM
│   └── validator.py             # Validasi ROM, core, dan binary RetroArch
├── launcher/
│   ├── main.py                  # Entrypoint utama launcher
│   ├── retroarch_controller.py  # Peluncur & supervisor proses RetroArch
│   ├── retroarch_config.py      # Pembaca konfigurasi kontrol RetroArch
│   ├── connection_manager.py    # Negosiasi Direct P2P & Relay fallback
│   ├── session_supervisor.py    # Pemantau sesi (heartbeat, deteksi lawan putus)
│   ├── client_api.py            # Klien HTTP ke server matchmaking
│   ├── gamepad.py               # Input joystick untuk menu
│   ├── ui.py                    # TUI curses & CLI fallback
│   ├── logger.py                # Setup logging file & buffer
│   ├── system_info.py           # Deteksi mesin, OS, versi RetroArch/core
│   └── log_uploader.py          # Upload log ke VPS via SSH/SCP
├── server/
│   ├── app.py                   # Runner server (API + Signaling + Relay)
│   ├── api.py                   # REST API matchmaking & signaling
│   ├── models.py                # Model Room, Player, Signal
│   ├── room_store.py            # Penyimpanan room in-memory dengan TTL
│   ├── signaling.py             # Hub signaling
│   └── relay.py                 # TCP Netplay Relay
├── deploy/
│   ├── Dockerfile               # Image server
│   ├── docker-compose.yml       # Docker Compose
│   ├── arcade-server.service    # Unit systemd
│   ├── batocera_install.sh      # Instalasi di Batocera
│   └── emuelec_install.sh       # Instalasi di EmuELEC
├── roms/                        # Letakkan ROM (.zip) di sini
├── config.json                  # Konfigurasi utama
├── diagnose.py                  # Preflight diagnostic
├── sync_to_emuelec.sh           # Sinkronisasi kode + ROM ke kabinet EmuELEC
├── sync_replace.sh              # Mirror penuh folder proyek ke EmuELEC (hapus file lama)
├── setup_log_ssh.sh             # Setup SSH key untuk upload log ke VPS (Linux/macOS)
├── setup_log_ssh.bat            # Setup SSH key untuk Windows (CMD / Double-click)
├── setup_log_ssh.ps1            # Setup SSH key untuk Windows (PowerShell)
├── download_log.sh              # Unduh semua log dari VPS ke lokal
└── arcade_online_launcher_spec.md
```

---

## 🕹️ Menjalankan Launcher

### Mode TUI (antarmuka arcade)

```bash
python3 -m launcher.main
```

Alamat server, nama mesin, dan pengaturan lainnya dibaca dari `config.json`. Untuk menimpa sementara:

```bash
python3 -m launcher.main --server "http://217.216.146.15:8080" --name ArcadeCab2
```

**Kontrol:**

| Tombol | Fungsi |
|---|---|
| UP / DOWN (W / S) | Pilih menu / game / room |
| ENTER (Spasi / Tombol 1) | Konfirmasi / Buat / Gabung |
| ESC (Q / Tombol 2) | Kembali / Batal |

### Mode CLI

```bash
# Pindai core & ROM
python3 -m launcher.main --scan

# Tampilkan 50 baris log terakhir
python3 -m launcher.main --show-logs

# Main offline langsung
python3 -m launcher.main --play sf2

# Daftar room aktif
python3 -m launcher.main --list

# Buat room sebagai Host
python3 -m launcher.main --create --game sf2 --room-name "Dojo SF2"

# Gabung ke room sebagai Client
python3 -m launcher.main --join <ROOM_ID>

# Simulasi tanpa membuka emulator
python3 -m launcher.main --dry-run

# Kirim log ke VPS sekarang juga
python3 -m launcher.main --upload-logs
```

Tampilan fullscreen/windowed diatur lewat `"fullscreen"` di `config.json`.

---

## ⚙️ Konfigurasi (`config.json`)

`config.json` mendukung komentar `//`. Bagian penting:

| Bagian | Kunci | Keterangan |
|---|---|---|
| `server` | `url` | Alamat server matchmaking (mis. `http://217.216.146.15:8080`) |
| `client` | `player_name` | Nama mesin, **harus berbeda di tiap kabinet** (mis. `ArcadeCab1`, `ArcadeCab2`) |
| `client` | `direct_connection_timeout` | Batas waktu uji P2P langsung (disarankan `5.0` untuk WiFi) |
| `retroarch` | `check_frames` | Interval cek sinkronisasi netplay. Disarankan `600` (~10 detik) |
| `retroarch` | `input_latency_frames` | Buffer input. `5` (~83 ms) untuk meredam jitter WiFi |
| `retroarch` | `stateless_mode` | `true` = mode lockstep |
| `retroarch` | `preferred_arcade_core` | Core arcade utama, mis. `fbneo` |
| `logging` | `auto_upload` | `true` = kirim log ke VPS otomatis |
| `logging` | `remote_host` / `remote_port` / `remote_path` | Tujuan upload log |
| `logging` | `ssh_key_path` | Path private key (`null` = pakai `~/.ssh/id_ed25519` / `id_rsa`) |

---

## 📶 Tips Netplay Stabil (FBNeo via WiFi)

Savestate FBNeo jauh lebih besar dibanding SNES, sehingga lebih sensitif terhadap jitter WiFi. Error `Netplay state load out of order!` di log biasanya muncul karena hal ini.

1. Gunakan `check_frames: 600` dan `input_latency_frames: 5`.
2. **Pastikan core FBNeo identik di kedua mesin.** Bandingkan nilai `SHA256` core di log. Jangan sampai satu mesin memakai `/tmp/cores/` dan mesin lain `/usr/lib/libretro/` dengan versi berbeda.
3. **Pastikan ROM identik.** Bandingkan `CRC32` di log, atau sinkronkan dengan `sync_to_emuelec.sh`.
4. Gunakan WiFi **5 GHz** bila tersedia.
5. Matikan **AP / Client Isolation** di router agar mesin dapat terhubung langsung (P2P) dan tidak dipaksa lewat relay VPS.

---

## 🌐 Server Matchmaking & Relay

Server menangani pencarian room, signaling, dan relay cadangan.

### Python

```bash
# IP publik relay otomatis terdeteksi
python3 -m server.app

# Atau tentukan manual
python3 -m server.app --host 0.0.0.0 --port 8080 --relay-port 55436 --public-relay-host 217.216.146.15
```

| Parameter | Keterangan |
|---|---|
| `--host` | Alamat bind API (default `0.0.0.0`) |
| `--port` | Port API HTTP (default `8080`) |
| `--relay-port` | Port TCP relay netplay (default `55436`) |
| `--public-relay-host` | IP/domain publik relay (default: otomatis) |
| `--no-relay` | Matikan relay bawaan |

Buka port **8080** dan **55436** di firewall VPS.

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

### Alternatif tanpa VPS: Tailscale / ZeroTier

1. Pasang [Tailscale](https://tailscale.com/) di kedua mesin dan hubungkan ke jaringan yang sama.
2. Jalankan `python3 -m server.app` di salah satu mesin.
3. Arahkan launcher ke IP Tailscale mesin tersebut, mis. `--server "http://100.80.20.10:8080"`.

---

## 📦 Sinkronisasi ke Kabinet EmuELEC

```bash
# Kirim kode launcher + ROM, dan setel config kabinet (ArcadeCab2)
./sync_to_emuelec.sh <IP_EMUELEC>

# Atau mirror penuh (menghapus file yang tidak ada di Mac)
./sync_replace.sh <IP_EMUELEC>
```

---

## 📝 Log & Upload ke VPS

Log lokal ditulis ke `arcade_launcher.log`. Jika `logging.auto_upload` aktif, log dikirim ke VPS setelah setiap sesi (host, client, offline) dan saat launcher ditutup, dengan nama file unik:

```text
/root/log_testing/arcade_launcher_<NamaMesin>_<YYYYMMDD_HHMMSS>.log
```

Autentikasi **hanya memakai SSH key**. Kata sandi VPS tidak disimpan di kode maupun konfigurasi.

### 1. Setup SSH key (sekali per mesin)

**Semua OS (Windows / macOS / Linux) - Paling Mudah:**
```bash
python setup_log_ssh.py
```

**Atau lewat skrip sistem:**
- **Windows:** Klik dua kali `setup_log_ssh.bat` atau jalankan `powershell -ExecutionPolicy Bypass -File .\setup_log_ssh.ps1`
- **Linux / macOS:** `./setup_log_ssh.sh`

Skrip ini membuat SSH key (jika belum ada), mendaftarkannya ke VPS (kata sandi VPS diminta **satu kali**), dan menguji login tanpa kata sandi.

Untuk EmuELEC, salin skripnya dulu:

```bash
scp setup_log_ssh.sh root@<IP_EMUELEC>:/storage/online_netplay/
ssh root@<IP_EMUELEC> "cd /storage/online_netplay && ./setup_log_ssh.sh"
```

### 2. Uji kirim

```bash
python3 -m launcher.main --upload-logs
```

### 3. Periksa log di server

```bash
ssh -p 20157 root@217.216.146.15
ls -lht /root/log_testing/                       # terbaru di atas
ls /root/log_testing/*ArcadeCab2*                # log satu mesin
grep -l "out of order" /root/log_testing/*.log   # cari error netplay
```

Atau unduh semuanya ke lokal:

```bash
./download_log.sh
```

---

## 🩺 Diagnostik

```bash
python3 diagnose.py
```

Memeriksa RetroArch, core libretro (versi + SHA-256), folder ROM, konektivitas server, dan ketersediaan port 55435/55436.

---

## 🎮 Kompatibilitas Game & ROM

- **Format ROM:** `.zip`, `.7z`
- **Sistem:** Arcade (FBNeo / MAME), SNES (`snes9x`), Genesis (`genesis_plus_gx`), NES (`fceumm`)
- **Lokasi pemindaian:**
  - Default (`scan_local_roms_only: true`): folder `roms/` di proyek
  - Dengan `--all-rom-dirs`: folder sistem Batocera/EmuELEC (`/userdata/roms/...`), RetroPie, `~/roms/...`, dan disk eksternal (`/media/*`, `/run/media/*`, `/Volumes/*`)
- **Folder tambahan:** `--rom-dir /path/ke/roms` atau `custom_roms_dir` di `config.json`
- **Core tambahan:** `--core-dir /path/ke/cores` atau `custom_cores_dir` di `config.json`


### 3. Periksa log di server

```bash
ssh -p 20157 root@217.216.146.15
ls -lht /root/log_testing/                       # terbaru di atas
ls /root/log_testing/*ArcadeCab2*                # log satu mesin
grep -l "out of order" /root/log_testing/*.log   # cari error netplay
```

Atau unduh semuanya ke lokal:

```bash
./download_log.sh
```

---

## 🩺 Diagnostik

```bash
python3 diagnose.py
```

Memeriksa RetroArch, core libretro (versi + SHA-256), folder ROM, konektivitas server, dan ketersediaan port 55435/55436.

---

## 🎮 Kompatibilitas Game & ROM

- **Format ROM:** `.zip`, `.7z`
- **Sistem:** Arcade (FBNeo / MAME), SNES (`snes9x`), Genesis (`genesis_plus_gx`), NES (`fceumm`)
- **Lokasi pemindaian:**
  - Default (`scan_local_roms_only: true`): folder `roms/` di proyek
  - Dengan `--all-rom-dirs`: folder sistem Batocera/EmuELEC (`/userdata/roms/...`), RetroPie, `~/roms/...`, dan disk eksternal (`/media/*`, `/run/media/*`, `/Volumes/*`)
- **Folder tambahan:** `--rom-dir /path/ke/roms` atau `custom_roms_dir` di `config.json`
- **Core tambahan:** `--core-dir /path/ke/cores` atau `custom_cores_dir` di `config.json`