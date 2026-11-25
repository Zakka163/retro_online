# Spesifikasi Produk & Teknis

## Arcade Online Launcher — One-Click Multiplayer untuk RetroArch

**Versi:** 1.1  
**Status:** Implementasi Aktif (Uji Lapangan & Operasional)  
**Target game:** Katalog ROM lokal (`roms/`), termasuk Street Fighter II dan game arcade/konsol lainnya  
**Platform:** EmuELEC 4.8 (Amlogic aarch64), Batocera, Linux, macOS, Windows dengan RetroArch  
**Core utama:** `fbneo` (FinalBurn Neo), serta dukungan MAME, `snes9x`, `genesis_plus_gx`, `fceumm`  
**Prinsip utama:** Pemain cukup memilih game, membuat atau mencari room, lalu bermain (atau memilih Main Offline). Seluruh konfigurasi jaringan, validasi, dan proses teknis ditangani launcher secara otomatis.

---

## 1. Ringkasan Eksekutif

Arcade Online Launcher adalah aplikasi antarmuka TUI (`curses`) dan CLI untuk menghubungkan dua mesin arcade yang berada di jaringan lokal maupun internet berbeda. Pemain tidak perlu memahami IP address, port, NAT, konfigurasi RetroArch Netplay, ataupun perintah terminal.

Alur penggunaan:

1. Pemain menyalakan perangkat (di EmuELEC mode `boot`, launcher langsung terbuka otomatis).
2. Di menu utama, pemain memilih **Main Offline**, **Main Online**, atau **Cek Mapping Joystick**.
3. Pada **Main Online**, pemain memilih game → **Buat Room** atau **Cari Room**.
4. Jika membuat room, launcher mendaftarkan room ke server matchmaking dan menunggu lawan.
5. Pemain kedua memilih room tersebut lalu menekan **Gabung**.
6. Launcher memeriksa kompatibilitas ROM/core, membangun koneksi (Direct P2P atau Relay fallback), lalu menjalankan RetroArch secara otomatis.
7. Setelah permainan selesai, launcher kembali ke menu dan mengunggah log diagnostik (jika diaktifkan).

### Sasaran pengalaman pengguna

> Pilih game → Cari/Buat Room → Main.

Pemain tidak perlu:
- Mengisi alamat IP atau port secara manual.
- Mengatur port forwarding router.
- Memilih core RetroArch secara manual.
- Mengetik perintah SSH atau terminal.
- Mengatur relay server atau menyalin file konfigurasi secara manual.

---

## 2. Tujuan dan Batasan

### 2.1 Tujuan utama

- Menyediakan launcher multiplayer yang mudah dikendalikan dengan joystick/D-Pad maupun keyboard.
- Menyediakan mode **Main Offline** dan **Main Online** dalam satu antarmuka.
- Menyediakan daftar room aktif berdasarkan game.
- Mengotomatiskan pemeriksaan game, ROM (`sha1`, `md5`, `crc32`), core (nama, versi, `sha256`), dan binary RetroArch.
- Mengutamakan koneksi langsung antarpemain (Direct P2P TCP) jika memungkinkan.
- Menggunakan TCP Relay di VPS sebagai fallback ketika koneksi langsung gagal (CGNAT/firewall/AP isolation).
- Menyediakan indikator jaringan/WiFi dan ping server, serta menu **Cek Mapping Joystick**.
- Mengunggah log sesi otomatis ke VPS via SSH key untuk memudahkan troubleshooting.

### 2.2 Di luar cakupan

- Membuat emulator atau core libretro baru.
- Memodifikasi ROM game atau mendistribusikan ROM berhak cipta ke publik.
- Membuat sistem rollback netcode sendiri (menggunakan netcode bawaan RetroArch).
- Matchmaking berbasis ranking, turnamen, atau leaderboard.
- VPN penuh untuk seluruh trafik perangkat.

### 2.3 Asumsi operasional

- Satu room berisi maksimal dua pemain (1 Host + 1 Client).
- Kedua mesin memiliki file ROM dan core yang identik.
- Koneksi internet tersedia pada kedua mesin untuk mode Online.
- Server publik VPS menjalankan Matchmaking API, Signaling polling, dan TCP Relay (`server/app.py`).

---

## 3. Prinsip Desain Produk

### 3.1 Antarmuka bersih & sederhana

Launcher menjalankan pemeriksaan teknis di belakang layar. Tampilan TUI dibuat bersih dengan teks polos (minim simbol/ikon), menampilkan informasi penting seperti indikator WiFi/jaringan, IP lokal, ping server, serta status koneksi yang mudah dipahami.

### 3.2 Konfigurasi RetroArch terisolasi

Launcher **tidak menimpa** `retroarch.cfg` pengguna. Parameter Netplay dan layar penuh ditulis ke file konfigurasi sementara (`--appendconfig`) dan dihapus setelah sesi berakhir. Pada EmuELEC, launcher tetap menyertakan `-c /storage/.config/retroarch/retroarch.cfg` saat file tersebut ada agar profil autoconfig joystick (`/tmp/joypads`) selalu terbaca.

### 3.3 Direct-first, relay-fallback

Urutan koneksi yang dijalankan `launcher/connection_manager.py`:

1. Negosiasi informasi sesi melalui HTTP Signaling (`/api/rooms/{id}/signal` & `/poll`).
2. Mencoba koneksi Direct P2P TCP ke endpoint IP:port host (default port `55435`) dengan timeout terukur (`direct_connection_timeout`, default `5.0` detik).
3. Jika koneksi langsung gagal, host dan client beralih ke jalur **TCP Relay** melalui `LocalRelayBridge` yang terhubung ke `RelayServer` di VPS (port `55436`).
4. RetroArch Client diarahkan ke `127.0.0.1` pada port lokal bridge sehingga tetap transparan bagi RetroArch.

---

## 4. Pengalaman Pengguna (UX) & Struktur Menu

### 4.1 Layar utama

Komponen yang tampil pada `launcher/main.py` + `launcher/ui.py`:
- Header **ARCADE ONLINE** beserta nama kabinet (`player_name`) dan status koneksi/sinyal jaringan (mis. `[WiFi 85% | 10.233.214.109 | Ping 32ms]` atau `[LAN | IP]`).
- Pilihan menu utama:
  1. **Main Online** — Masuk ke alur pilih game → Buat/Cari Room.
  2. **Main Offline** — Pilih game dan langsung jalankan RetroArch tanpa server.
  3. **Cek Mapping Joystick** — Melihat device `/dev/input/js*` aktif, input tombol real-time, dan label tombol yang terbaca dari `retroarch.cfg`.
  4. **Keluar** — Menutup launcher (pada mode boot EmuELEC, dapat kembali ke EmulationStation).

### 4.2 Alur Main Online

1. **Pilih Game:** Menampilkan daftar game yang lolos validasi ROM dan core.
2. **Pilih Aksi:** **Buat Room** atau **Cari Room**.
3. **Buat Room:**
   - Launcher memvalidasi core & hash ROM lokal.
   - Mengirim `POST /api/rooms` ke server.
   - Menampilkan status menunggu lawan sembari melakukan polling/heartbeat.
4. **Cari Room:**
   - Mengambil daftar room via `GET /api/rooms`.
   - Pemain memilih room dan menekan **Gabung** (`POST /api/rooms/{id}/join`).
5. **Negosiasi & Peluncuran:**
   - Launcher menampilkan progres bertahap (mencari room, validasi, koneksi langsung / jalur alternatif, menjalankan game).
   - RetroArch dijalankan sebagai `--host` atau `--connect`.

### 4.3 Kontrol & Hotplug Joystick

- Di Linux/EmuELEC, `launcher/gamepad.py` membaca `/dev/input/js*` dengan dukungan **hotplug standby** dan **auto-reconnect**: jika joystick baru dicolokkan atau dipindah port USB saat launcher berjalan, device baru otomatis terdeteksi.
- `launcher/retroarch_config.py` membaca mapping tombol (`hotkey_btn`, `exit_btn`, dan nama tombol yang ramah manusia) dari `retroarch.cfg`.
- Saat RetroArch berjalan di console EmuELEC, `launcher/retroarch_controller.py` membekukan `fbterm`/`gptokeyb` sementara (`SIGSTOP`) dan mengembalikannya (`SIGCONT`) setelah game ditutup agar layar tidak saling menimpa.

---

## 5. Arsitektur Sistem

### 5.1 Struktur Modul Aktual

```text
online_netplay/
├── catalog/
│   ├── manifest.json            # Metadata game (opsional)
│   ├── scanner.py               # Pemindai core libretro & ROM
│   └── validator.py             # Validasi binary RetroArch, core, dan hash ROM
├── launcher/
│   ├── main.py                  # Entrypoint TUI/CLI & alur menu utama
│   ├── ui.py                    # Antarmuka TUI curses & CLI fallback
│   ├── gamepad.py               # Input joystick (/dev/input/js* + hotplug)
│   ├── retroarch_config.py      # Pembaca mapping tombol & label manusiawi
│   ├── retroarch_controller.py  # Builder --appendconfig & supervisor proses RetroArch
│   ├── connection_manager.py    # Direct P2P TCP + LocalRelayBridge + indikator jaringan
│   ├── session_supervisor.py    # Pemantau heartbeat & status sesi
│   ├── client_api.py            # Klien HTTP REST ke server matchmaking/signaling
│   ├── logger.py                # Logging lokal ke arcade_launcher.log
│   ├── system_info.py           # Deteksi OS, hardware, versi RetroArch & core SHA-256
│   └── log_uploader.py          # Auto-upload log ke VPS via SSH/SCP key
├── server/
│   ├── app.py                   # Entrypoint server (API + Signaling + Relay)
│   ├── api.py                   # HTTP REST handler matchmaking & signaling
│   ├── models.py                # Model Room, Player, Signal
│   ├── room_store.py            # Penyimpanan room in-memory dengan TTL
│   ├── signaling.py             # Antrean event signaling per room
│   └── relay.py                 # TCP Netplay RelayServer (framing 24-byte)
├── deploy/
│   ├── Dockerfile               # Image server
│   ├── docker-compose.yml       # Docker Compose server
│   ├── arcade-server.service    # Unit systemd VPS
│   ├── batocera_install.sh      # Installer Batocera
│   └── emuelec_install.sh       # Installer EmuELEC (mode boot / ports / remove)
├── roms/                        # Folder ROM lokal (.zip / .7z)
├── config.json                  # Konfigurasi utama (mendukung komentar //)
├── diagnose.py                  # Preflight diagnostic lokal
├── sync_to_emuelec.sh           # Sinkronisasi kode + ROM + config ke EmuELEC
├── sync_replace.sh              # Mirror penuh ke EmuELEC (menghapus file lama)
├── set_emuelec_config.sh        # Pengubah nama & config EmuELEC via SSH dari Mac
├── setup_log_ssh.{sh,py,bat,ps1}# Setup SSH key untuk auto-upload log ke VPS
└── download_log.sh              # Unduh log dari VPS ke lokal
```

### 5.2 Diagram Alur Koneksi

```text
                    VPS (217.216.146.15)
             +---------------+---------------+
             |                               |
    HTTP API & Signaling (:8080)    TCP Relay Server (:55436)
    - /api/rooms*                   - Handshake & room pairing
    - /api/rooms/{id}/signal        - Framing header 24-byte
    - /api/rooms/{id}/poll          - Fallback jika P2P gagal
             |                               |
             +---------------+---------------+
                             |
             +---------------+---------------+
             |                               |
     MESIN A (Host)                  MESIN B (Client)
     Launcher + RetroArch            Launcher + RetroArch
     Direct TCP (:55435)  <------->  Direct TCP (:55435)
     (atau via LocalRelayBridge 127.0.0.1 <-> VPS :55436)
```

---

## 6. Strategi Koneksi & Anti-Desync

### 6.1 Urutan Koneksi

1. **Service check:** Memeriksa `GET /api/health` pada server.
2. **Compatibility check:** Validasi core dan hash ROM sebelum membuat/bergabung ke room.
3. **Signaling exchange:** Host dan client bertukar endpoint lokal/publik melalui `/signal` dan `/poll`.
4. **Direct attempt:** Client menguji koneksi TCP langsung ke host (`direct_connection_timeout`, default `5.0` detik).
5. **Relay fallback:** Jika direct gagal, kedua sisi terhubung melalui `LocalRelayBridge` ke `RelayServer` VPS (`55436`).
6. **Session launch & monitoring:** RetroArch dijalankan, sementara `SessionSupervisor` menjaga heartbeat dan mendeteksi bila lawan keluar.

### 6.2 Pengaturan Anti-Desync (`config.json`)

Untuk menjaga stabilitas Netplay (terutama FBNeo via WiFi dan lintas OS), pengaturan default di `config.json`:
- `preferred_arcade_core`: `"fbneo"`
- `stateless_mode`: `true` (mengirim input tanpa memaksa sinkronisasi savestate lintas OS)
- `check_frames`: `0`
- `input_latency_frames`: `5` (~83 ms buffer untuk meredam jitter WiFi)
- `sync_sram`: `false`
- `run_ahead_enabled`, `rewind_enable`, `cheats_enable`: dipaksa `"false"` di `--appendconfig`
- `savefile_directory` & `savestate_directory`: diarahkan ke folder temp agar kedua pemain memulai dari state RAM yang bersih.

---

## 7. Kompatibilitas Game, Core, dan ROM

- **Format ROM:** `.zip`, `.7z`
- **Lokasi pemindaian:** Default `scan_local_roms_only: true` hanya memindai `roms/` proyek agar cepat dan identik di semua kabinet. Opsi `--all-rom-dirs` memindai folder sistem EmuELEC/Batocera/RetroPie dan disk eksternal.
- **Validasi:** `catalog/validator.py` menghitung hash ROM (`crc32`, `md5`, `sha1`) dan hash core (`sha256`) untuk memastikan kedua mesin memakai aset yang kompatibel.

---

## 8. Desain API Server (`server/api.py`)

Server berjalan di port HTTP `8080` (default) dengan penyimpanan room in-memory (`server/room_store.py`) dan polling signaling (`server/signaling.py`).

| Method | Endpoint | Fungsi |
|---|---|---|
| `GET` | `/api/health` | Cek status server & layanan relay |
| `GET` | `/api/rooms` | Daftar room aktif |
| `GET` | `/api/rooms/{id}` | Detail room |
| `GET` | `/api/rooms/{id}/poll?player_id=...&since=...` | Mengambil event signaling terbaru |
| `POST` | `/api/rooms` | Membuat room baru |
| `POST` | `/api/rooms/{id}/join` | Bergabung ke room |
| `POST` | `/api/rooms/{id}/leave` | Keluar dari room |
| `POST` | `/api/rooms/{id}/heartbeat` | Memperbarui TTL / status aktif |
| `POST` | `/api/rooms/{id}/signal` | Mengirim pesan signaling ke lawan |
| `POST` | `/api/rooms/{id}/relay` | Meminta/mengonfirmasi sesi jalur relay |

---

## 9. Observabilitas, Logging, dan Diagnostik

- **Log lokal:** Ditulis ke `arcade_launcher.log`, mencakup info OS/perangkat (`launcher/system_info.py`), versi RetroArch, core SHA-256, ROM CRC32, jalur koneksi (Direct/Relay), dan exit code.
- **Auto-upload ke VPS:** Jika `logging.auto_upload: true`, `launcher/log_uploader.py` mengirim log ke VPS (`/root/log_testing/arcade_launcher_<NamaMesin>_<YYYYMMDD_HHMMSS>.log`) menggunakan SSH key (tanpa password di kode).
- **Diagnostik preflight:** `python3 diagnose.py` memeriksa keberadaan RetroArch, core, ROM, konektivitas server, dan ketersediaan port `55435`/`55436`.

---

## 10. Deployment & Operasional

### 10.1 Server VPS

Dapat dijalankan langsung (`python3 -m server.app`), dengan Docker (`deploy/docker-compose.yml`), atau systemd (`deploy/arcade-server.service`). Port yang perlu dibuka di firewall VPS:
- **8080/tcp** (Matchmaking API & Signaling)
- **55436/tcp** (TCP Netplay Relay)

### 10.2 Perangkat EmuELEC

Instalasi menggunakan `deploy/emuelec_install.sh`:
- **Mode `boot`:** Menulis `/storage/.config/arcade_boot.sh` dan `/storage/.config/custom_start.sh`. Launcher dijalankan melalui `systemd-run --no-block --unit=arcade-launcher` dengan `fbterm -s 20` serta environment `HOME=/storage` dan `XDG_CONFIG_HOME=/storage/.config` agar `emuelec-autostart.service` tidak tertahan dan autoconfig RetroArch (`/tmp/joypads`) tetap terbaca.
- **Mode `ports`:** Menambahkan entri `Arcade_Online.sh` di `/storage/roms/ports/` agar launcher dibuka dari menu Ports EmulationStation.
- **Mode `remove`:** Menghapus skrip boot dan entri ports.

### 10.3 Manajemen Jarak Jauh dari Mac

- `./sync_to_emuelec.sh <IP>` — Sinkronisasi kode, ROM, setup SSH key log, dan setel config kabinet.
- `./sync_replace.sh <IP>` — Mirror penuh folder proyek ke EmuELEC (menghapus file lama yang tidak ada di Mac).
- `./set_emuelec_config.sh <IP>` — Mengubah `player_name` atau parameter `config.json` di EmuELEC secara interaktif atau lewat flag CLI (`--name`, `--server`, `--restart`, dll.).
- `./download_log.sh` — Mengunduh seluruh log pengujian dari VPS ke folder lokal.

---

## 11. Status Implementasi Saat Ini

| Komponen | Status | Keterangan |
|---|---|---|
| Launcher TUI & CLI (`launcher/`) | Selesai | Mendukung offline, online, cek mapping joystick, indikator jaringan |
| Katalog & Validator (`catalog/`) | Selesai | Scan ROM/core lokal & verifikasi hash |
| Server Matchmaking & Signaling (`server/`) | Selesai | Berjalan via `arcade-server.service` di VPS |
| TCP Relay & `LocalRelayBridge` | Selesai | Framing 24-byte & penanganan coalesced handshake |
| Auto-upload Log SSH & Diagnostik | Selesai | SSH key setup lintas OS + `diagnose.py` |
| Installer & Sinkronisasi EmuELEC | Selesai | Mode `boot`/`ports`, `sync_*`, dan `set_emuelec_config.sh` |
| Uji Lapangan & Perluasan Katalog | Berjalan | Pengujian multi-kabinet & penambahan ROM terverifikasi |
