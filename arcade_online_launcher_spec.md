# Spesifikasi Produk & Teknis

## Arcade Online Launcher --- One-Click Multiplayer untuk RetroArch

**Versi:** 1.0\
**Status:** Rancangan MVP\
**Target game awal:** Street Fighter II\
**Platform awal:** Mesin arcade berbasis Batocera / EmuELEC / Linux
dengan RetroArch\
**Core awal:** MAME (versi/core harus diseragamkan dan diuji)\
**Prinsip utama:** Pemain cukup memilih game, membuat atau mencari room,
lalu bermain. Seluruh konfigurasi jaringan dan proses teknis ditangani
launcher secara otomatis.

------------------------------------------------------------------------

## 1. Ringkasan Eksekutif

Arcade Online Launcher adalah aplikasi antarmuka sederhana untuk
menghubungkan dua mesin arcade yang berada di lokasi dan jaringan
internet berbeda. Pemain tidak perlu memahami IP address, port, NAT,
konfigurasi RetroArch Netplay, ataupun perintah terminal.

Alur yang diharapkan:

1.  Pemain membuka launcher.
2.  Pemain memilih game, misalnya **Street Fighter II**.
3.  Pemain memilih **Buat Room** atau **Cari Room**.
4.  Jika membuat room, launcher menyiapkan sesi dan menampilkan room di
    daftar.
5.  Pemain kedua memilih room tersebut lalu menekan **Gabung**.
6.  Launcher memeriksa kompatibilitas, membangun koneksi, menjalankan
    RetroArch, dan membuka game.
7.  Kedua pemain langsung bermain.

Tujuan produk bukan sekadar menyediakan server relay. Tujuan utamanya
adalah menyembunyikan kompleksitas jaringan di balik pengalaman
penggunaan yang sederhana.

### Sasaran pengalaman pengguna

> Pilih game → Cari/Buat Room → Main.

Tidak boleh ada keharusan bagi pemain untuk: - Mengisi alamat IP atau
port. - Mengatur port forwarding router. - Memilih core RetroArch secara
manual. - Mengetik perintah SSH atau terminal. - Mengatur relay
server. - Menyalin file konfigurasi dari pemain lain. - Memahami istilah
NAT, STUN, P2P, TCP, atau tunnel.

------------------------------------------------------------------------

## 2. Tujuan dan Batasan

### 2.1 Tujuan utama

-   Menyediakan launcher multiplayer yang mudah digunakan pada mesin
    arcade.
-   Menyediakan daftar room berdasarkan game.
-   Memungkinkan pemain membuat room dan pemain lain bergabung.
-   Mengotomatiskan pemeriksaan game, ROM, core, versi, dan konfigurasi.
-   Mengutamakan koneksi langsung antarpemain jika memungkinkan.
-   Menggunakan relay sebagai fallback ketika koneksi langsung tidak
    berhasil.
-   Menyediakan status koneksi dan pesan kesalahan yang mudah dipahami.
-   Memungkinkan sistem berkembang dari satu game menjadi katalog game
    arcade.

### 2.2 Bukan tujuan MVP

-   Membuat emulator atau core MAME baru.
-   Memodifikasi ROM game.
-   Membuat sistem rollback netcode sendiri.
-   Menjamin semua ROM atau semua versi MAME kompatibel.
-   Menyediakan matchmaking berbasis ranking, turnamen, atau
    leaderboard.
-   Mendukung banyak pemain dalam satu sesi jika core/game belum
    mendukungnya.
-   Membuat jaringan VPN penuh untuk seluruh perangkat.

### 2.3 Asumsi MVP

-   Satu room berisi dua pemain.
-   Satu pemain bertindak sebagai host Netplay RetroArch.
-   Satu pemain bertindak sebagai client.
-   Kedua mesin memiliki game dan core yang kompatibel.
-   Koneksi internet tersedia pada kedua mesin.
-   Server publik digunakan untuk room management/signaling dan, bila
    diperlukan, relay.
-   Versi RetroArch, core, dan ROM ditetapkan pada konfigurasi katalog
    game.

------------------------------------------------------------------------

## 3. Prinsip Desain Produk

### 3.1 Sederhanakan antarmuka, bukan menghilangkan pemeriksaan teknis

Launcher harus menjalankan pemeriksaan teknis di belakang layar. Pemain
hanya melihat status sederhana, misalnya:

-   Memeriksa game...
-   Mencari lawan...
-   Menghubungkan pemain...
-   Menyiapkan permainan...
-   Siap bermain.
-   Koneksi tidak tersedia. Mencoba jalur alternatif...

### 3.2 Otomatisasi dengan kontrol yang jelas

Launcher boleh mengatur RetroArch secara otomatis, tetapi tidak boleh
mengubah konfigurasi global secara permanen tanpa kebutuhan. Gunakan
konfigurasi sesi sementara atau parameter peluncuran khusus bila
memungkinkan.

### 3.3 Direct-first, relay-fallback

Urutan koneksi yang diinginkan:

1.  Temukan dan autentikasi kedua pemain melalui layanan signaling.
2.  Coba koneksi langsung antarpemain dengan mekanisme yang benar-benar
    didukung oleh protokol Netplay yang digunakan.
3.  Jika koneksi langsung gagal atau tidak stabil, coba tunnel/relay
    yang kompatibel.
4.  Jika keduanya gagal, tampilkan alasan dan langkah pemulihan yang
    sederhana.

**Penting:** Server matchmaking/signaling tidak sama dengan relay
trafik. Signaling hanya bertukar informasi sesi. Relay meneruskan data
permainan. Keberhasilan bertukar alamat melalui signaling tidak menjamin
koneksi langsung dapat dibangun, terutama pada jaringan CGNAT atau NAT
simetris.

### 3.4 Jangan mengasumsikan protokol RetroArch

RetroArch Netplay memiliki mekanisme dan persyaratan protokolnya
sendiri. Sebelum implementasi, verifikasi versi RetroArch, core,
transport, port, serta dukungan relay pada versi yang dipilih. Jangan
menganggap semua trafik Netplay menggunakan UDP atau bahwa relay TCP
generik otomatis kompatibel.

------------------------------------------------------------------------

## 4. Pengalaman Pengguna (UX)

### 4.1 Layar utama

Komponen: - Logo/nama Arcade Online. - Daftar game yang tersedia. -
Status internet dan layanan. - Tombol pengaturan terbatas untuk
operator/admin. - Indikator versi launcher.

Contoh tampilan:

``` text
+--------------------------------------+
|             ARCADE ONLINE            |
|                                      |
|  PILIH GAME                          |
|  [ Street Fighter II             ]   |
|  [ Metal Slug                    ]   |
|                                      |
|  Status: Online                      |
+--------------------------------------+
```

Untuk MVP, hanya Street Fighter II yang ditampilkan.

### 4.2 Layar game

Setelah memilih game:

``` text
+--------------------------------------+
| STREET FIGHTER II                    |
|                                      |
|  [ CARI ROOM ]                       |
|  [ BUAT ROOM ]                       |
|                                      |
|  Pemain online: 3                    |
+--------------------------------------+
```

### 4.3 Cari Room

Daftar room menampilkan: - Nama room. - Nama host/pemain. - Game. -
Status: menunggu / penuh / menghubungkan. - Kualitas koneksi perkiraan
jika tersedia. - Tombol Gabung.

Filter minimum: - Game yang dipilih. - Room yang masih menunggu
pemain. - Versi game/core yang kompatibel.

Jangan menampilkan room yang tidak kompatibel sebagai room yang bisa
langsung digabung. Jika perlu, tampilkan alasan ketidakcocokan secara
informatif.

### 4.4 Buat Room

Pemain cukup memilih: - Nama room (opsional; dapat dibuat otomatis). -
Privasi: publik atau privat (opsional untuk MVP). - Buat Room.

Launcher kemudian: 1. Memeriksa game dan core lokal. 2. Memeriksa
layanan online. 3. Menyiapkan RetroArch sebagai host. 4. Membuat room
pada matchmaking server. 5. Menunggu pemain kedua. 6. Saat pemain
bergabung, memulai negosiasi koneksi.

Room otomatis kedaluwarsa jika host keluar atau tidak aktif dalam batas
waktu yang ditetapkan.

### 4.5 Bergabung ke Room

Pemain memilih room dan menekan **Gabung**. Launcher: 1. Memvalidasi
room. 2. Memeriksa kompatibilitas lokal. 3. Meminta slot pemain. 4.
Melakukan signaling dan koneksi. 5. Menjalankan RetroArch sebagai
client. 6. Menampilkan status siap bermain.

Tidak perlu memasukkan IP, port, atau kode teknis. Untuk room privat,
gunakan kode undangan singkat sebagai opsi, bukan sebagai kewajiban
untuk room publik.

### 4.6 Layar koneksi

Tampilkan tahapan dengan bahasa nonteknis:

``` text
Menghubungkan ke pemain...
[✓] Menemukan room
[✓] Memeriksa game
[✓] Memeriksa kompatibilitas
[..] Membangun koneksi langsung
[ ] Menyiapkan jalur alternatif
[ ] Menjalankan permainan
```

Jangan menampilkan detail jaringan yang membingungkan pemain. Sediakan
tombol **Coba Lagi** dan **Kembali**.

### 4.7 Saat permainan berlangsung

-   RetroArch mengambil alih layar.
-   Launcher tidak mengganggu input game.
-   Pemain dapat keluar melalui mekanisme exit yang telah ditentukan.
-   Setelah RetroArch ditutup, launcher kembali ke layar game.
-   Room dan status sesi dibersihkan dengan aman.

------------------------------------------------------------------------

## 5. Arsitektur Sistem

### 5.1 Komponen

1.  **Arcade Launcher**
    -   UI pemain.
    -   Katalog game.
    -   Room browser.
    -   Pemeriksaan lokal.
    -   Pengendali proses RetroArch.
    -   Pelaporan status koneksi.
2.  **Matchmaking API**
    -   Membuat room.
    -   Menampilkan room.
    -   Meminta bergabung.
    -   Mengelola slot pemain.
    -   Mengakhiri room.
3.  **Signaling Service**
    -   Mempertemukan host dan client.
    -   Menukar informasi koneksi yang diperlukan.
    -   Mengirim status negosiasi.
    -   Tidak meneruskan trafik game pada mode direct.
4.  **Connection Manager**
    -   Menentukan strategi koneksi.
    -   Memeriksa keberhasilan koneksi langsung.
    -   Memulai relay fallback bila tersedia dan kompatibel.
    -   Mengawasi timeout dan kegagalan.
5.  **Relay Service**
    -   Meneruskan trafik sesi bila direct connection gagal.
    -   Hanya digunakan bila jalur relay yang dipilih kompatibel dengan
        Netplay.
    -   Memiliki batas kapasitas, timeout, dan autentikasi sesi.
6.  **RetroArch**
    -   Menjalankan core yang ditetapkan.
    -   Menjadi host atau client Netplay.
    -   Menjalankan emulasi game.

### 5.2 Diagram tingkat tinggi

``` text
                    PUBLIC INTERNET
                           |
             +-------------+-------------+
             |                           |
      MATCHMAKING API              SIGNALING SERVICE
      - create room                - exchange session data
      - list rooms                 - connection negotiation
      - join room                  - player status
             |                           |
             +-------------+-------------+
                           |
                 CONNECTION MANAGER
                           |
              +------------+------------+
              |                         |
        DIRECT CONNECTION         RELAY FALLBACK
        (preferred path)          (if required)
              |                         |
              +------------+------------+
                           |
                  GAME SESSION
                           |
             +-------------+-------------+
             |                           |
       ARCADE MACHINE A            ARCADE MACHINE B
       Launcher                    Launcher
       RetroArch Host              RetroArch Client
       MAME Core                   MAME Core
```

Diagram ini menunjukkan tanggung jawab layanan. Implementasi aktual
harus mengikuti protokol Netplay yang telah diverifikasi, bukan
mengasumsikan semua komponen dapat saling menggantikan.

### 5.3 Pemisahan signaling dan relay

**Signaling server** - Mengelola identitas sementara pemain dan room. -
Mengirim informasi yang diperlukan untuk negosiasi koneksi. - Tidak
membawa paket input/game. - Dapat tetap aktif selama sesi untuk
heartbeat dan status.

**Relay server** - Berada pada jalur data permainan. - Menerima data
dari satu sisi dan meneruskannya ke sisi lain. - Mengonsumsi bandwidth
sesuai trafik sesi. - Digunakan hanya jika direct connection tidak
tersedia atau tidak memenuhi kebijakan kualitas.

------------------------------------------------------------------------

## 6. Strategi Koneksi

### 6.1 Urutan koneksi yang diharapkan

1.  **Service check:** launcher memastikan API dan signaling tersedia.
2.  **Session check:** kedua pemain berada di room dan slot telah
    dikunci.
3.  **Compatibility check:** game, ROM, core, dan versi cocok.
4.  **Direct attempt:** sistem mencoba koneksi langsung menggunakan
    metode yang didukung protokol.
5.  **Direct verification:** koneksi harus benar-benar terbukti
    berfungsi, bukan hanya berhasil bertukar alamat.
6.  **Relay fallback:** jika direct gagal, sistem menggunakan relay yang
    kompatibel.
7.  **Session launch:** RetroArch menjalankan sesi.
8.  **Monitoring:** sistem memantau heartbeat, disconnect, dan durasi
    sesi.

### 6.2 Catatan NAT traversal

STUN dapat membantu mengetahui alamat pemetaan NAT, tetapi STUN saja
tidak menjamin koneksi langsung. Beberapa jaringan CGNAT atau symmetric
NAT memerlukan teknik lain atau relay.

Untuk TCP Netplay, teknik traversal harus diuji terhadap protokol dan
implementasi RetroArch yang digunakan. Jangan menerapkan UDP hole
punching sebagai solusi universal.

### 6.3 Relay fallback dan kompatibilitas

Pilihan pertama adalah menggunakan relay/tunnel resmi atau yang
kompatibel dengan ekosistem RetroArch Netplay. Jangan mengganti jalur
sesi yang sedang berjalan secara transparan kecuali protokol mendukung
perpindahan tersebut.

Jika direct gagal: - Hentikan percobaan direct dengan timeout yang
terukur. - Negosiasikan sesi relay. - Mulai ulang pembentukan sesi
melalui jalur relay. - Beri tahu pemain bahwa koneksi sedang disiapkan
ulang.

### 6.4 Kriteria keberhasilan koneksi

Direct dianggap berhasil jika: - Kedua sisi telah terhubung ke endpoint
yang benar. - Protokol Netplay berhasil melakukan handshake. - Sesi game
dapat dimulai. - Koneksi bertahan melewati periode uji. - Tidak ada
kegagalan sinkronisasi yang berulang.

------------------------------------------------------------------------

## 7. Kompatibilitas Game dan ROM

Netplay sangat sensitif terhadap perbedaan lingkungan emulasi. Launcher
harus memeriksa:

-   Identitas game.
-   Hash ROM atau identitas konten yang dapat diverifikasi.
-   Versi core.
-   Nama core.
-   Versi RetroArch.
-   Konfigurasi Netplay yang relevan.
-   Pengaturan emulasi yang memengaruhi determinisme.

### 7.1 Game manifest

Setiap game memiliki metadata terpusat. Contoh konseptual:

``` json
{
  "game_id": "street-fighter-ii",
  "display_name": "Street Fighter II",
  "platform": "arcade",
  "retroarch_core": "mame",
  "core_version": "PINNED_VERSION",
  "rom_hash": "EXPECTED_HASH",
  "players": 2,
  "netplay_enabled": true
}
```

Nilai `core_version`, `rom_hash`, dan nama file harus diisi berdasarkan
aset legal dan build yang benar-benar diuji. Jangan menggunakan nilai
contoh sebagai konfigurasi produksi.

### 7.2 Kebijakan kompatibilitas

-   Jangan mengizinkan join jika ROM berbeda dari versi yang
    disyaratkan.
-   Jangan mengunduh atau mendistribusikan ROM berhak cipta tanpa izin.
-   Sediakan pesan "Versi game tidak cocok" dan petunjuk operator.
-   Gunakan paket core yang sama atau versi yang telah diuji pada kedua
    mesin.

------------------------------------------------------------------------

## 8. Desain API

API berikut adalah rancangan awal, bukan kontrak final.

### 8.1 Matchmaking

  Method   Endpoint                      Fungsi
  -------- ----------------------------- ------------------------
  POST     `/api/rooms`                  Membuat room
  GET      `/api/rooms?game_id=...`      Daftar room
  POST     `/api/rooms/{id}/join`        Bergabung
  POST     `/api/rooms/{id}/leave`       Keluar
  GET      `/api/rooms/{id}`             Detail room
  POST     `/api/rooms/{id}/heartbeat`   Memperbarui status
  DELETE   `/api/rooms/{id}`             Menutup room oleh host

### 8.2 Contoh create room

Request:

``` json
{
  "game_id": "street-fighter-ii",
  "visibility": "public",
  "client_version": "1.0.0",
  "compatibility": {
    "core": "mame",
    "core_version": "PINNED_VERSION",
    "rom_hash": "EXPECTED_HASH"
  }
}
```

Response konseptual:

``` json
{
  "room_id": "ROOM_ID",
  "status": "waiting",
  "expires_at": "ISO-8601-TIMESTAMP"
}
```

### 8.3 Contoh join room

Request:

``` json
{
  "client_version": "1.0.0",
  "compatibility": {
    "core": "mame",
    "core_version": "PINNED_VERSION",
    "rom_hash": "EXPECTED_HASH"
  }
}
```

Server memeriksa: - Room masih aktif. - Slot tersedia. - Game cocok. -
Versi core dan ROM cocok. - Pemain belum memiliki sesi aktif lain.

### 8.4 Signaling event

Gunakan WebSocket atau mekanisme signaling lain yang sesuai.

Contoh event konseptual: - `room.created` - `room.joined` -
`peer.ready` - `connection.offer` - `connection.answer` -
`connection.candidate` (hanya jika teknik traversal yang dipilih memang
menggunakannya) - `connection.direct_failed` -
`connection.relay_required` - `session.started` - `session.closed`

Jangan mengirim token rahasia atau informasi sensitif melalui event yang
dapat diakses pemain lain.

------------------------------------------------------------------------

## 9. Pengendali RetroArch

Launcher bertugas mengatur RetroArch, bukan meminta pemain mengatur
sendiri.

### 9.1 Tanggung jawab

-   Menemukan executable RetroArch.
-   Menemukan core yang dibutuhkan.
-   Memastikan ROM tersedia.
-   Memastikan konfigurasi Netplay sesuai.
-   Menyiapkan mode host/client.
-   Menjalankan proses RetroArch.
-   Memantau proses dan exit code.
-   Membersihkan konfigurasi sesi sementara.

### 9.2 Host dan client

**Host** - Membuka sesi Netplay sebagai host. - Menggunakan core dan
konten yang telah divalidasi. - Menunggu client bergabung.

**Client** - Menerima informasi sesi dari connection manager. -
Menjalankan Netplay client dengan parameter yang sesuai. - Terhubung ke
host atau tunnel relay.

Parameter CLI dan konfigurasi harus diverifikasi pada versi RetroArch
yang dipakai. Jangan menyalin contoh command dari versi berbeda tanpa
pengujian.

### 9.3 Konfigurasi aman

-   Simpan konfigurasi dasar yang dikelola operator.
-   Buat konfigurasi sesi sementara.
-   Jangan menimpa file konfigurasi pengguna tanpa backup.
-   Jangan menyimpan password atau token sesi di file log.
-   Pulihkan pengaturan setelah sesi berakhir.

### 9.4 Integrasi launcher dengan RetroArch

Launcher dapat dibuat menggunakan Python dan Pygame jika itu sesuai
dengan launcher yang sudah ada. Alternatifnya, UI dapat menggunakan
teknologi lain, tetapi pengendali proses RetroArch harus terpisah dari
UI agar mudah diuji.

------------------------------------------------------------------------

## 10. Keamanan

### 10.1 Room dan sesi

-   Room ID harus sulit ditebak atau dilindungi token sesi.
-   Token sesi memiliki masa berlaku.
-   Satu slot tidak boleh diklaim oleh beberapa pemain.
-   Host dapat menutup room.
-   Room otomatis dihapus setelah timeout.
-   Batasi pembuatan room untuk mencegah spam.

### 10.2 Jaringan

-   Gunakan TLS untuk API dan signaling.
-   Validasi seluruh input API.
-   Terapkan rate limiting.
-   Jangan menerima alamat/port arbitrer tanpa validasi.
-   Batasi relay hanya untuk sesi yang terautentikasi.
-   Batasi durasi dan bandwidth relay.
-   Jangan membuka port administrasi ke publik.
-   Gunakan firewall dan update keamanan VPS.

### 10.3 Privasi

-   Jangan menampilkan alamat IP publik pemain pada UI.
-   Jangan menyimpan data jaringan lebih lama dari kebutuhan
    operasional.
-   Log hanya informasi diagnostik yang diperlukan.
-   Sediakan kebijakan privasi yang menjelaskan data koneksi yang
    diproses.

------------------------------------------------------------------------

## 11. Observabilitas dan Pengukuran Kualitas

Untuk menentukan apakah direct atau relay lebih baik, catat metrik
berikut:

-   Waktu menemukan room.
-   Waktu negosiasi koneksi.
-   Waktu handshake Netplay.
-   Jalur yang digunakan: direct atau relay.
-   Round-trip time (RTT) jika dapat diukur dengan metode yang sesuai.
-   Packet loss jika metrik tersedia.
-   Disconnect dan reconnect.
-   Durasi sesi.
-   Kegagalan berdasarkan kategori.

Jangan menyimpulkan kualitas Netplay hanya dari ping ICMP. Uji juga
latency aplikasi dan kestabilan sesi.

### Contoh kategori error

  ----------------------------------------------------------------------------
  Kode                         Makna untuk operator    Pesan untuk pemain
  ---------------------------- ----------------------- -----------------------
  `SERVICE_UNAVAILABLE`        API/signaling tidak     Layanan online sedang
                               aktif                   tidak tersedia

  `ROOM_FULL`                  Slot sudah terisi       Room sudah penuh

  `GAME_MISMATCH`              Game/ROM berbeda        Versi game tidak cocok

  `CORE_MISMATCH`              Core berbeda            Sistem game belum
                                                       kompatibel

  `DIRECT_TIMEOUT`             Direct gagal timeout    Menyiapkan jalur
                                                       koneksi alternatif

  `RELAY_UNAVAILABLE`          Relay gagal             Koneksi online belum
                                                       tersedia

  `NETPLAY_HANDSHAKE_FAILED`   Handshake gagal         Gagal memulai permainan

  `PEER_DISCONNECTED`          Lawan terputus          Lawan terputus dari
                                                       permainan
  ----------------------------------------------------------------------------

------------------------------------------------------------------------

## 12. Deployment

### 12.1 Komponen server

Untuk MVP: - Ubuntu Server LTS. - Reverse proxy untuk HTTPS. -
Matchmaking API. - Signaling service. - Database ringan untuk room dan
status. - Relay service terpisah jika dibutuhkan. - Monitoring dan log.

### 12.2 Pemisahan layanan

Sebaiknya layanan dijalankan terpisah agar kegagalan satu komponen tidak
merusak seluruh sistem:

``` text
VPS
├── reverse-proxy
├── matchmaking-api
├── signaling-service
├── room-store
├── relay-service
└── monitoring
```

Room sementara dapat disimpan di Redis atau penyimpanan in-memory untuk
MVP, dengan TTL. Data akun dan statistik permanen belum diperlukan.

### 12.3 Operasional

-   Jalankan layanan sebagai systemd service atau container.
-   Terapkan restart policy.
-   Gunakan firewall allowlist port yang diperlukan.
-   Simpan secret di environment/config server yang terlindungi.
-   Buat backup konfigurasi.
-   Pantau CPU, RAM, bandwidth, jumlah room, dan sesi relay.

------------------------------------------------------------------------

## 13. Rencana Implementasi Bertahap

### Tahap 0 --- Validasi teknis

Tujuan: memastikan Netplay game target memang bekerja.

-   Tetapkan satu versi RetroArch.
-   Tetapkan satu core MAME dan versinya.
-   Tetapkan ROM legal yang sama untuk kedua mesin.
-   Uji host dan client pada satu jaringan lokal.
-   Uji host dan client pada dua jaringan berbeda.
-   Catat port, protokol, dan konfigurasi aktual.
-   Verifikasi metode relay resmi yang kompatibel.

**Kriteria selesai:** dua mesin dapat memainkan game target secara
konsisten melalui Netplay lokal dan internet.

### Tahap 1 --- Launcher lokal

-   Buat layar pemilihan game.
-   Buat tombol Buat Room dan Cari Room.
-   Jalankan RetroArch host/client secara otomatis untuk pengujian
    lokal.
-   Tampilkan status proses dan error yang ramah pengguna.

**Kriteria selesai:** pemain tidak perlu membuka menu konfigurasi
RetroArch secara manual.

### Tahap 2 --- Matchmaking

-   Buat API room.
-   Buat daftar room.
-   Buat join/leave.
-   Buat heartbeat dan timeout.
-   Batasi satu room untuk dua pemain.

**Kriteria selesai:** dua launcher di internet dapat menemukan room yang
sama.

### Tahap 3 --- Signaling dan koneksi

-   Hubungkan kedua pemain melalui signaling.
-   Implementasikan strategi direct connection yang kompatibel dengan
    protokol.
-   Verifikasi handshake.
-   Tambahkan timeout dan error handling.

**Kriteria selesai:** direct connection berhasil pada jaringan yang
mendukungnya.

### Tahap 4 --- Relay fallback

-   Integrasikan tunnel/relay yang kompatibel dengan RetroArch.
-   Jalankan relay hanya ketika direct gagal.
-   Ukur latency dan bandwidth.
-   Pastikan sesi relay memiliki autentikasi dan batas waktu.

**Kriteria selesai:** pemain tetap dapat bermain pada jaringan yang
tidak mendukung direct, selama relay tersedia dan kualitas koneksi
memadai.

### Tahap 5 --- Uji lapangan

Uji minimal skenario: - Dua mesin pada satu router. - Dua router rumah
berbeda. - Salah satu pemain menggunakan hotspot seluler. - Kedua pemain
menggunakan jaringan CGNAT jika tersedia. - VPS relay tersedia. - VPS
relay tidak tersedia. - Salah satu pemain menutup launcher saat sesi
berjalan. - Internet terputus lalu kembali.

**Kriteria selesai:** sistem memberikan hasil yang konsisten dan pesan
kegagalan yang dapat dipahami.

### Tahap 6 --- Perluasan katalog

Setelah Street Fighter II stabil: - Tambahkan game satu per satu. -
Verifikasi core dan ROM tiap game. - Buat manifest kompatibilitas. -
Jalankan pengujian regresi sebelum game dipublikasikan.

------------------------------------------------------------------------

## 14. Definisi MVP yang Dapat Diterima

MVP dianggap berhasil jika:

1.  Pemain dapat membuka launcher tanpa memahami RetroArch.
2.  Pemain dapat memilih Street Fighter II.
3.  Pemain dapat membuat room.
4.  Pemain lain dapat menemukan dan bergabung.
5.  Launcher memeriksa kompatibilitas secara otomatis.
6.  Launcher mencoba direct connection terlebih dahulu.
7.  Launcher memakai relay fallback jika direct tidak tersedia dan jalur
    relay kompatibel.
8.  RetroArch terbuka otomatis sebagai host/client.
9.  Kedua pemain dapat bermain.
10. Pemain dapat keluar dan kembali ke launcher.
11. Room dibersihkan setelah sesi berakhir.
12. Kesalahan koneksi ditampilkan dalam bahasa sederhana.

------------------------------------------------------------------------

## 15. Risiko dan Keputusan Teknis yang Harus Dibuktikan

  --------------------------------------------------------------------------
  Risiko                  Dampak                     Mitigasi
  ----------------------- -------------------------- -----------------------
  Netplay core tidak      Game gagal sinkron         Pin versi core dan ROM
  kompatibel                                         

  NAT/CGNAT               Direct gagal               Relay fallback

  Protokol relay tidak    Sesi tidak dapat dibuat    Gunakan tunnel yang
  cocok                                              kompatibel

  Latency tinggi          Gameplay tidak nyaman      Pilih lokasi VPS yang
                                                     baik dan ukur RTT

  Versi RetroArch berbeda Handshake/kompatibilitas   Standarkan build
                          gagal                      

  Launcher gagal menutup  UI tidak kembali           Process supervision
  emulator                                           

  Room tertinggal         Room palsu/stale           Heartbeat dan TTL

  Paket/ROM berbeda       Desinkronisasi             Hash dan manifest
  --------------------------------------------------------------------------

### Keputusan arsitektur yang disarankan

-   Jangan membangun protokol Netplay sendiri.
-   Gunakan RetroArch sebagai engine permainan.
-   Gunakan layanan matchmaking/signaling buatan sendiri.
-   Gunakan metode direct hanya jika protokol Netplay benar-benar
    mendukungnya.
-   Gunakan relay resmi/kompatibel sebagai fallback.
-   Jangan menjanjikan perpindahan direct ke relay tanpa memulai ulang
    sesi, kecuali telah dibuktikan protokol mendukung migrasi.
-   Jadikan kompatibilitas game sebagai data terkelola, bukan pilihan
    manual pemain.

------------------------------------------------------------------------

## 16. Prioritas Pekerjaan Pertama

Urutan kerja paling aman dan hemat waktu:

1.  **Buktikan Netplay Street Fighter II** pada dua mesin dan dua
    jaringan berbeda.
2.  Dokumentasikan command, konfigurasi, port, dan versi yang
    benar-benar bekerja.
3.  Buat launcher sederhana yang dapat menjalankan host/client secara
    otomatis.
4.  Tambahkan matchmaking dan room browser.
5.  Tambahkan signaling.
6.  Uji direct connection dan tentukan batas keberhasilannya.
7.  Integrasikan relay fallback yang kompatibel.
8.  Rapikan UX sehingga pemain hanya memilih game, mencari/membuat room,
    dan bermain.

**Prinsip keputusan:** jangan membangun matchmaking, NAT traversal, dan
relay secara bersamaan sebelum Netplay dasar terbukti berjalan. Validasi
engine permainan terlebih dahulu agar kompleksitas proyek tetap
terkendali.

------------------------------------------------------------------------

## 17. Gambaran Akhir Produk

Dari sudut pandang pemain, seluruh sistem idealnya hanya terlihat
seperti ini:

``` text
ARCADE ONLINE

Pilih Game
    |
    v
Street Fighter II
    |
    +---- Cari Room
    |        |
    |        v
    |    Pilih Room
    |        |
    |        v
    |      Gabung
    |
    +---- Buat Room
             |
             v
         Menunggu Lawan
             |
             v
      Lawan Bergabung
             |
             v
     Menghubungkan Pemain
             |
             v
       Menyiapkan Game
             |
             v
          MAIN!
```

**Ukuran keberhasilan produk bukan banyaknya teknologi yang digunakan,
melainkan seberapa sedikit keputusan teknis yang harus dilakukan
pemain.**
