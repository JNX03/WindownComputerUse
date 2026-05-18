"""Permission system: allowlist + bypass."""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path(os.environ["USERPROFILE"]) / ".win_computer_use"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "bypass": False,
    "allowed_apps": [
        "mspaint.exe",
        "msedge.exe",
        "calc.exe",
        "calculator.exe",
        "explorer.exe",
        "notepad.exe",
        "SnippingTool.exe",
    ],
    "blocked_apps": [],
    "max_screenshot_dim": 1920,
    "mouse_move_duration_s": 0.25,
    "fail_safe": True,
    # Phase 2 — visibility & UX
    "agent_name": "Claude",
    "cursor_color": "#FE6E58",
    "cursor_label_text_color": "#FFFFFF",
    "overlay_enabled": True,
    "showcase_mode": True,
    "emergency_hotkey": "ctrl+shift+x",
    # Phase 4 — polish
    # Two-stage fade:
    # - Chip ("Claude" label) starts fading after `label_hide_after_s` seconds
    #   of stillness, finishes hiding `fade_duration_s` later.
    # - The arrow itself starts shrinking + fading after
    #   `cursor_auto_hide_after_s` seconds, finishes `fade_duration_s` later.
    # - On any AI cursor motion both elements wake back up.
    "label_hide_after_s": 5.0,
    "cursor_auto_hide_after_s": 15.0,
    "cursor_fade_duration_s": 1.5,
    "cursor_wake_duration_s": 0.4,
    "app_theme": "dark",
    "app_default_page": "setup",
}


def _ensure_config() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
        return dict(DEFAULT_CONFIG)
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        cfg = dict(DEFAULT_CONFIG)
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    return merged


def load_config() -> dict:
    return _ensure_config()


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def set_bypass(enabled: bool) -> dict:
    cfg = load_config()
    cfg["bypass"] = bool(enabled)
    save_config(cfg)
    return cfg


def add_allowed_app(name: str) -> dict:
    cfg = load_config()
    name = name.lower()
    if name not in [a.lower() for a in cfg["allowed_apps"]]:
        cfg["allowed_apps"].append(name)
        save_config(cfg)
    return cfg


def check(tool_name: str, target: Optional[str] = None) -> tuple[bool, str]:
    """Return (allowed, reason).

    target is optional — typically an app exe name for launch_app, otherwise None.
    """
    cfg = load_config()
    if cfg.get("bypass"):
        return True, "bypass-enabled"
    if target is None:
        # Pure input/screenshot tools are always allowed; gating is at app level.
        return True, "no-target"
    t = target.lower()
    blocked = [b.lower() for b in cfg.get("blocked_apps", [])]
    allowed = [a.lower() for a in cfg.get("allowed_apps", [])]
    base = os.path.basename(t)
    if base in blocked or t in blocked:
        return False, f"app '{target}' is in blocked_apps"
    if base in allowed or t in allowed:
        return True, "app-allowed"
    return False, (
        f"app '{target}' not in allowed_apps. Either ask user to approve, "
        f"call permission.add_allowed_app('{base}'), or enable bypass mode."
    )
