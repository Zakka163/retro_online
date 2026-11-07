#!/usr/bin/env bash
# Arcade Online Multiplayer Launcher for Linux & macOS

set -e

# Detect python3 binary
if command -v python3 >/dev/null 2>&1; then
    PY_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PY_BIN="python"
else
    echo "[ERROR] Python 3 tidak ditemukan! Pastikan Python 3 sudah terpasang."
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

exec "$PY_BIN" -m launcher.main "$@"

