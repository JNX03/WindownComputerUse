"""Single-shot diagnostic for the win-computer-use MCP server.

Run via:
    py -3.12 scripts/startup_check.py

Reads the live state files written by the running MCP server (does NOT
spawn a new server). Useful for an agent to call via Bash before deciding
how to operate.

Exit codes:
    0  - everything healthy
    1  - server appears down (no state.json or heartbeat too old)
    2  - server up, but at least one warning (emergency hotkey not armed,
         OCR backend missing, overlay process dead, etc.)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

CONFIG_DIR = Path(os.path.expanduser("~/.win_computer_use"))
STATE_PATH = CONFIG_DIR / "state.json"
CONFIG_PATH = CONFIG_DIR / "config.json"
ACTIVITY_PATH = CONFIG_DIR / "activity.log"

HEARTBEAT_STALE_S = 30  # heartbeat older than this -> server probably dead


def load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def check_winrt_ocr() -> tuple[bool, str]:
    """Try to import the winrt OCR chain. Returns (ok, message)."""
    try:
        import winrt.windows.media.ocr  # noqa: F401
        import winrt.windows.globalization  # noqa: F401
        return True, "winrt OCR backend importable"
    except ImportError as e:
        return False, f"winrt OCR missing: {e}. Try: py -3.12 -m pip install winrt-Windows.Globalization"


def fmt_age(ts_ms: float) -> str:
    age = time.time() - ts_ms
    if age < 0:
        return f"in the future by {-age:.1f}s (clock skew?)"
    if age < 60:
        return f"{age:.1f}s ago"
    if age < 3600:
        return f"{age / 60:.1f}m ago"
    return f"{age / 3600:.1f}h ago"


def main() -> int:
    print(f"Config dir: {CONFIG_DIR}")
    print()

    warnings: list[str] = []
    fatal: list[str] = []

    # ---- state.json ----
    state = load_json(STATE_PATH)
    if state is None:
        fatal.append(f"state.json missing or unreadable at {STATE_PATH}. Is the MCP server running?")
    else:
        print("STATE")
        print(f"  agent_name           = {state.get('agent_name')!r}")
        print(f"  cursor_color         = {state.get('cursor_color')!r}")
        print(f"  overlay_enabled      = {state.get('overlay_enabled')}")
        print(f"  server_pid           = {state.get('server_pid')}")
        print(f"  overlay_subprocess   = {state.get('overlay_subprocess_pid')}")
        print(f"  virtual_cursor       = ({state.get('virtual_cursor_x')}, {state.get('virtual_cursor_y')})")
        print(f"  emergency_stopped    = {state.get('emergency_stopped')}")

        # heartbeat freshness
        hb = state.get("heartbeat_at")
        if hb:
            # heartbeat_at is ISO8601, convert to epoch
            try:
                import datetime as dt
                hb_dt = dt.datetime.fromisoformat(hb.replace("Z", "+00:00"))
                hb_epoch = hb_dt.timestamp()
                age = time.time() - hb_epoch
                print(f"  heartbeat_at         = {hb}  ({fmt_age(hb_epoch)})")
                if age > HEARTBEAT_STALE_S:
                    warnings.append(f"heartbeat is {age:.0f}s old (threshold {HEARTBEAT_STALE_S}s). Server may be hung.")
            except Exception as e:
                warnings.append(f"could not parse heartbeat_at: {e}")
        else:
            warnings.append("heartbeat_at missing from state.json")

        if state.get("emergency_stopped"):
            warnings.append("emergency_stopped=true. User stopped the agent. Do NOT auto-resume; confirm first.")

    # ---- config.json ----
    cfg = load_json(CONFIG_PATH)
    print()
    print("CONFIG")
    if cfg is None:
        warnings.append("config.json missing. Server will use defaults.")
    else:
        print(f"  bypass               = {cfg.get('bypass')}")
        print(f"  allowed_apps         = {cfg.get('allowed_apps')}")
        print(f"  blocked_apps         = {cfg.get('blocked_apps')}")
        print(f"  fail_safe            = {cfg.get('fail_safe')}")
        print(f"  emergency_hotkey     = {cfg.get('emergency_hotkey')}")
        print(f"  mouse_move_duration  = {cfg.get('mouse_move_duration_s')}")

    # ---- activity log ----
    print()
    print("ACTIVITY LOG")
    if ACTIVITY_PATH.exists():
        size = ACTIVITY_PATH.stat().st_size
        mtime = ACTIVITY_PATH.stat().st_mtime
        print(f"  path                 = {ACTIVITY_PATH}")
        print(f"  size                 = {size} bytes")
        print(f"  last write           = {fmt_age(mtime)}")
    else:
        print(f"  not present at {ACTIVITY_PATH}")

    # ---- OCR backend probe ----
    print()
    print("OCR BACKEND")
    ok, msg = check_winrt_ocr()
    print(f"  {'OK' if ok else 'BROKEN'}: {msg}")
    if not ok:
        warnings.append(msg)

    # ---- recordings dir ----
    rec_dir = CONFIG_DIR / "recordings"
    print()
    print("RECORDINGS")
    if rec_dir.exists():
        files = sorted(rec_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        print(f"  path                 = {rec_dir}")
        print(f"  mp4 count            = {len(files)}")
        if files:
            print(f"  most recent          = {files[0].name} ({fmt_age(files[0].stat().st_mtime)})")
    else:
        print(f"  no recordings dir at {rec_dir}")

    # ---- summary ----
    print()
    print("=" * 60)
    if fatal:
        print("FATAL:")
        for w in fatal:
            print(f"  - {w}")
        return 1
    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"  - {w}")
        print()
        print("Server is up but operating with caveats. See references/ for guidance.")
        return 2
    print("All checks passed. Server is healthy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
