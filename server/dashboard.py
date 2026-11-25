"""Admin Web Dashboard UI and VPS Log/Update Inspection Helpers."""

import json
import os
from typing import Any, Dict, List, Optional

from .dashboard_views import build_dashboard_html


def list_vps_logs(logs_dir: str, limit: int = 100) -> List[Dict[str, Any]]:
    """List recent .log files from the VPS log directory."""
    if not logs_dir or not os.path.isdir(logs_dir):
        return []
    items: List[Dict[str, Any]] = []
    for name in os.listdir(logs_dir):
        if not name.endswith(".log"):
            continue
        full = os.path.join(logs_dir, name)
        if not os.path.isfile(full):
            continue
        try:
            st = os.stat(full)
            items.append({
                "filename": name,
                "size": st.st_size,
                "mtime": st.st_mtime,
            })
        except OSError:
            continue
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items[:limit]


def read_vps_log(
    logs_dir: str,
    filename: str,
    tail_lines: int = 300,
    errors_only: bool = False,
) -> Optional[Dict[str, Any]]:
    """Safely read tail lines from a specific VPS log file."""
    safe_name = os.path.basename(filename)
    if not safe_name or not safe_name.endswith(".log"):
        return None
    full = os.path.join(logs_dir, safe_name)
    if not os.path.isfile(full):
        return None
    with open(full, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    if errors_only:
        keywords = ("[ERROR]", "[WARNING]", "out of order", "FAILED", "CRASHED")
        lines = [ln for ln in lines if any(k in ln for k in keywords)]
    if tail_lines > 0 and len(lines) > tail_lines:
        lines = lines[-tail_lines:]
    return {
        "filename": safe_name,
        "line_count": len(lines),
        "content": "\n".join(lines),
    }


def read_update_manifest(updates_dir: str) -> Dict[str, Any]:
    """Read manifest.json from updates_dir if present."""
    manifest_path = os.path.join(updates_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        return {"update_available": False}
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("update_available", True)
        return data
    except Exception:
        return {"update_available": False}


DASHBOARD_HTML = build_dashboard_html()
