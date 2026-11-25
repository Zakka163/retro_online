"""Cross-platform SSH Key Setup for VPS Log Upload.

Sets up passwordless SSH public key authentication to the arcade VPS server
so log uploading works seamlessly in the background without passwords.
Works on Windows, macOS, and Linux / EmuELEC.
"""

import os
import sys
import shutil
import socket
import subprocess

VPS_HOST = "217.216.146.15"
VPS_PORT = 20157
VPS_USER = "root"
REMOTE_DIR = "/root/log_testing"


def main():
    print("=" * 60)
    print("   SETUP SSH KEY OTOMATIS KE SERVER VPS ARCADE")
    print(f"   Target: {VPS_USER}@{VPS_HOST}:{VPS_PORT}")
    print("=" * 60)

    # 1. Pastikan OpenSSH tersedia
    ssh_bin = shutil.which("ssh")
    keygen_bin = shutil.which("ssh-keygen")
    if not ssh_bin or not keygen_bin:
        print("\n[X] Error: OpenSSH Client ('ssh' / 'ssh-keygen') tidak ditemukan di sistem.")
        if sys.platform == "win32":
            print("    Di Windows 10/11: Buka Settings -> Apps -> Optional Features -> Tambahkan 'OpenSSH Client'.")
        sys.exit(1)

    # 2. Periksa / buat SSH key lokal
    ssh_dir = os.path.expanduser("~/.ssh")
    os.makedirs(ssh_dir, exist_ok=True)
    try:
        os.chmod(ssh_dir, 0o700)
    except Exception:
        pass

    key_ed = os.path.join(ssh_dir, "id_ed25519")
    key_rsa = os.path.join(ssh_dir, "id_rsa")

    pub_key_path = None
    if os.path.isfile(key_ed + ".pub"):
        pub_key_path = key_ed + ".pub"
        print(f"\n[1/3] SSH Key ditemukan: {key_ed}")
    elif os.path.isfile(key_rsa + ".pub"):
        pub_key_path = key_rsa + ".pub"
        print(f"\n[1/3] SSH Key ditemukan: {key_rsa}")
    else:
        print(f"\n[1/3] Membuat SSH Key baru: {key_ed}...")
        hostname = socket.gethostname()
        res = subprocess.run([
            keygen_bin, "-t", "ed25519", "-N", "", "-C", f"arcade-{hostname}", "-f", key_ed
        ])
        if res.returncode != 0:
            print("[!] Mencoba algoritma RSA...")
            res = subprocess.run([
                keygen_bin, "-t", "rsa", "-b", "4096", "-N", "", "-C", f"arcade-{hostname}", "-f", key_rsa
            ])
            if res.returncode == 0:
                pub_key_path = key_rsa + ".pub"
        else:
            pub_key_path = key_ed + ".pub"

    if not pub_key_path or not os.path.isfile(pub_key_path):
        print("\n[X] Gagal membuat atau menemukan SSH public key.")
        sys.exit(1)

    with open(pub_key_path, "r", encoding="utf-8") as f:
        pub_key_content = f.read().strip()

    # 3. Daftarkan public key ke VPS
    print(f"\n[2/3] Mendaftarkan public key ke {VPS_USER}@{VPS_HOST}:{VPS_PORT}")
    print("      (Masukkan kata sandi root VPS SATU KALI saat diminta di bawah):")

    remote_cmd = (
        f"mkdir -p ~/.ssh '{REMOTE_DIR}' && chmod 700 ~/.ssh && "
        f"touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && "
        f"grep -qxF '{pub_key_content}' ~/.ssh/authorized_keys || echo '{pub_key_content}' >> ~/.ssh/authorized_keys"
    )

    res = subprocess.run([
        ssh_bin, "-p", str(VPS_PORT),
        "-o", "StrictHostKeyChecking=accept-new",
        f"{VPS_USER}@{VPS_HOST}",
        remote_cmd
    ])

    if res.returncode != 0:
        print(f"\n[X] Gagal mendaftarkan SSH key ke server (Exit code: {res.returncode}).")
        print("    Pastikan password VPS yang dimasukkan benar.")
        sys.exit(1)

    # 4. Uji login tanpa password
    print(f"\n[3/3] Menguji koneksi tanpa kata sandi...")
    test_res = subprocess.run([
        ssh_bin, "-p", str(VPS_PORT),
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=6",
        f"{VPS_USER}@{VPS_HOST}",
        f"test -d '{REMOTE_DIR}' && echo OK"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if test_res.returncode == 0 and "OK" in test_res.stdout:
        print("\n" + "=" * 60)
        print(" [✓] BERHASIL! Autentikasi SSH Key telah aktif.")
        print(f" Mesin ini siap mengirim file log otomatis ke:")
        print(f" {VPS_USER}@{VPS_HOST}:{VPS_PORT} ({REMOTE_DIR})")
        print("=" * 60)
    else:
        print(f"\n[X] Pengujian login tanpa password gagal: {test_res.stderr.strip()}")
        sys.exit(1)


if __name__ == "__main__":
    main()

