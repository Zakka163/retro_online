#!/bin/bash
# Script Pengubah Nama & Pengaturan EmuELEC dari Mac lewat SSH
# Mengedit /storage/online_netplay/config.json di EmuELEC tanpa perlu edit manual.

set -e

TARGET_DIR="/storage/online_netplay"
CFG_PATH="${TARGET_DIR}/config.json"
EMUELEC_USER="root"
EMUELEC_IP=""
SHOW_ONLY=false
RESTART_LAUNCHER=false

declare -a UPDATES=()

print_usage() {
    cat << 'EOF'
Pemakaian:
  ./set_emuelec_config.sh <IP_EMUELEC>                     (Mode interaktif)
  ./set_emuelec_config.sh <IP_EMUELEC> --show              (Lihat config saat ini)
  ./set_emuelec_config.sh <IP_EMUELEC> [opsi...]

Opsi cepat:
  --name <NAMA>           Ubah client.player_name (mis. ArcadeCab2, ArcadeCab3)
  --server <URL>          Ubah server.url (mis. http://217.216.146.15:8080)
  --core <CORE>           Ubah retroarch.preferred_arcade_core (mis. fbneo)
  --fullscreen <true|false> Ubah retroarch.fullscreen
  --latency <ANGKA>       Ubah retroarch.input_latency_frames (mis. 5)
  --check-frames <ANGKA>  Ubah retroarch.check_frames (mis. 0)
  --stateless <true|false>  Ubah retroarch.stateless_mode
  --auto-upload <true|false> Ubah logging.auto_upload
  --set <bagian.kunci=nilai> Ubah kunci bebas (mis. client.direct_connection_timeout=5.0)
  --user <USER>           User SSH (default: root)
  --restart               Restart service arcade-launcher setelah simpan
  -h, --help              Tampilkan bantuan ini

Contoh:
  ./set_emuelec_config.sh 10.233.214.109 --name ArcadeCab3
  ./set_emuelec_config.sh 10.233.214.109 --name ArcadeCab3 --fullscreen true --latency 5 --restart
EOF
}

if [ $# -eq 0 ]; then
    print_usage
    exit 1
fi

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            print_usage
            exit 0
            ;;
        --show)
            SHOW_ONLY=true
            shift
            ;;
        --restart)
            RESTART_LAUNCHER=true
            shift
            ;;
        --user)
            EMUELEC_USER="$2"
            shift 2
            ;;
        --name)
            UPDATES+=("client.player_name=$2")
            shift 2
            ;;
        --server)
            UPDATES+=("server.url=$2")
            shift 2
            ;;
        --core)
            UPDATES+=("retroarch.preferred_arcade_core=$2")
            shift 2
            ;;
        --fullscreen)
            UPDATES+=("retroarch.fullscreen=$2")
            shift 2
            ;;
        --latency)
            UPDATES+=("retroarch.input_latency_frames=$2")
            shift 2
            ;;
        --check-frames)
            UPDATES+=("retroarch.check_frames=$2")
            shift 2
            ;;
        --stateless)
            UPDATES+=("retroarch.stateless_mode=$2")
            shift 2
            ;;
        --auto-upload)
            UPDATES+=("logging.auto_upload=$2")
            shift 2
            ;;
        --set)
            UPDATES+=("$2")
            shift 2
            ;;
        -*)
            echo "[!] Opsi tidak dikenal: $1"
            print_usage
            exit 1
            ;;
        *)
            if [ -z "$EMUELEC_IP" ]; then
                EMUELEC_IP="$1"
            else
                echo "[!] Argumen berlebih: $1"
                exit 1
            fi
            shift
            ;;
    esac
done

if [ -z "$EMUELEC_IP" ]; then
    echo "[!] IP EmuELEC wajib diisi."
    print_usage
    exit 1
fi

SSH_OPTS="-o ConnectTimeout=8 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"
REMOTE="${EMUELEC_USER}@${EMUELEC_IP}"

run_remote_python() {
    local mode="$1"
    shift
    ssh ${SSH_OPTS} "${REMOTE}" python3 - "$CFG_PATH" "$mode" "$@" << 'PYEOF'
import json, os, re, sys

cfg_path = sys.argv[1]
mode = sys.argv[2]
pairs = sys.argv[3:]

if not os.path.exists(cfg_path):
    print(f"[!] File tidak ditemukan: {cfg_path}", file=sys.stderr)
    sys.exit(2)

with open(cfg_path, "r", encoding="utf-8") as f:
    content = f.read()

pat = re.compile(r'(?:/\*.*?\*/|//[^\r\n]*|#[^\r\n]*)|("(?:\\.|[^"\\])*")', re.DOTALL)
clean = pat.sub(lambda m: m.group(1) if m.group(1) is not None else "", content)
cfg = json.loads(clean)

def parse_val(raw):
    low = raw.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low == "null":
        return None
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw

if mode == "apply":
    for item in pairs:
        if "=" not in item:
            print(f"[!] Format salah (harus bagian.kunci=nilai): {item}", file=sys.stderr)
            sys.exit(1)
        key_path, raw_val = item.split("=", 1)
        parts = key_path.split(".")
        target = cfg
        for p in parts[:-1]:
            if p not in target or not isinstance(target[p], dict):
                target[p] = {}
            target = target[p]
        target[parts[-1]] = parse_val(raw_val)

    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")

client = cfg.get("client", {})
server = cfg.get("server", {})
ra = cfg.get("retroarch", {})
lg = cfg.get("logging", {})

print("---------------------------------------------")
print(f"player_name          : {client.get('player_name')}")
print(f"server.url           : {server.get('url')}")
print(f"preferred_core       : {ra.get('preferred_arcade_core')}")
print(f"fullscreen           : {ra.get('fullscreen')}")
print(f"input_latency_frames : {ra.get('input_latency_frames')}")
print(f"check_frames         : {ra.get('check_frames')}")
print(f"stateless_mode       : {ra.get('stateless_mode')}")
print(f"auto_upload          : {lg.get('auto_upload')}")
print("---------------------------------------------")
PYEOF
}

if [ "$SHOW_ONLY" = true ]; then
    echo "Membaca konfigurasi di ${REMOTE}..."
    run_remote_python "show"
    exit 0
fi

# Mode interaktif jika tidak ada flag perubahan yang diberikan
if [ ${#UPDATES[@]} -eq 0 ]; then
    echo "Membaca konfigurasi saat ini dari ${REMOTE}..."
    run_remote_python "show"
    echo ""
    echo "Kosongkan (tekan Enter) jika tidak ingin mengubah nilai tersebut:"
    read -r -p "1. Nama kabinet (player_name)       : " in_name
    read -r -p "2. URL Server (server.url)          : " in_server
    read -r -p "3. Core utama (fbneo/mame/dll)      : " in_core
    read -r -p "4. Fullscreen (true/false)          : " in_full
    read -r -p "5. Input latency frames (angka)     : " in_lat
    read -r -p "6. Check frames (angka, mis. 0)     : " in_chk
    read -r -p "7. Stateless mode (true/false)      : " in_stateless
    read -r -p "8. Auto upload log (true/false)     : " in_upload

    [ -n "$in_name" ] && UPDATES+=("client.player_name=${in_name}")
    [ -n "$in_server" ] && UPDATES+=("server.url=${in_server}")
    [ -n "$in_core" ] && UPDATES+=("retroarch.preferred_arcade_core=${in_core}")
    [ -n "$in_full" ] && UPDATES+=("retroarch.fullscreen=${in_full}")
    [ -n "$in_lat" ] && UPDATES+=("retroarch.input_latency_frames=${in_lat}")
    [ -n "$in_chk" ] && UPDATES+=("retroarch.check_frames=${in_chk}")
    [ -n "$in_stateless" ] && UPDATES+=("retroarch.stateless_mode=${in_stateless}")
    [ -n "$in_upload" ] && UPDATES+=("logging.auto_upload=${in_upload}")

    if [ ${#UPDATES[@]} -eq 0 ]; then
        echo "Tidak ada perubahan."
        exit 0
    fi

    read -r -p "Restart launcher di EmuELEC setelah simpan? (y/N): " in_restart
    if [[ "$in_restart" =~ ^[Yy]$ ]]; then
        RESTART_LAUNCHER=true
    fi
fi

echo "Menyimpan perubahan ke ${REMOTE}:${CFG_PATH}..."
run_remote_python "apply" "${UPDATES[@]}"
echo "[✓] Konfigurasi berhasil diperbarui."

if [ "$RESTART_LAUNCHER" = true ]; then
    echo "Merestart launcher di ${REMOTE}..."
    ssh ${SSH_OPTS} "${REMOTE}" "systemctl restart arcade-launcher >/dev/null 2>&1 || (pkill -f 'launcher.main' >/dev/null 2>&1; systemd-run --no-block --unit=arcade-launcher /storage/.config/arcade_boot.sh >/dev/null 2>&1)"
    echo "[✓] Launcher direstart."
fi

