"""Append-only JSONL activity log for the Electron manager and audits.

File: %USERPROFILE%\\.win_computer_use\\activity.log
Rotates to activity.log.1 when it exceeds 5 MB.
"""
from __future__ import annotations
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import permission

LOG_PATH = permission.CONFIG_DIR / "activity.log"
ROTATED_PATH = permission.CONFIG_DIR / "activity.log.1"
MAX_BYTES = 5 * 1024 * 1024

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _safe_args(args: Optional[dict]) -> dict:
    if not args:
        return {}
    out: dict[str, Any] = {}
    for k, v in args.items():
        if isinstance(v, str) and len(v) > 120:
            out[k] = v[:117] + "..."
        elif isinstance(v, (bytes, bytearray)):
            out[k] = f"<{len(v)} bytes>"
        else:
            out[k] = v
    return out


def _rotate_if_needed() -> None:
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > MAX_BYTES:
            if ROTATED_PATH.exists():
                ROTATED_PATH.unlink()
            os.replace(LOG_PATH, ROTATED_PATH)
    except Exception:
        pass


def append(
    tool: str,
    args: Optional[dict] = None,
    *,
    ok: bool = True,
    elapsed_ms: int = 0,
    error: Optional[str] = None,
) -> None:
    permission.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": _now(),
        "tool": tool,
        "args": _safe_args(args),
        "ok": ok,
        "elapsed_ms": int(elapsed_ms),
    }
    if error:
        entry["error"] = error[:500]
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with _lock:
        _rotate_if_needed()
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line)
