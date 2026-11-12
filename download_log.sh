#!/usr/bin/env bash
set -euo pipefail

REMOTE="root@217.216.146.15"
PORT="20157"
REMOTE_PATH="~/log_testing"
DEST_DIR="${1:-.}"

if ! command -v scp >/dev/null 2>&1; then
  echo "Error: scp tidak ditemukan. Pasang OpenSSH Client terlebih dahulu." >&2
  exit 1
fi

mkdir -p "$DEST_DIR"
echo "Mengunduh $REMOTE_PATH dari $REMOTE ke $DEST_DIR"
echo "Masukkan kata sandi SSH saat diminta."
scp -r -P "$PORT" "$REMOTE:$REMOTE_PATH" "$DEST_DIR/"
echo "Selesai: $DEST_DIR/log_testing"
