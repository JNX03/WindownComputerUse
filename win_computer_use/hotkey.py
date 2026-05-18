"""Global emergency-stop hotkey via Win32 RegisterHotKey.

Pressing Ctrl+Shift+X flips state.emergency_stopped to true. Input-tool wrappers
consult announce.is_emergency() and refuse to run.
"""
from __future__ import annotations

from . import permission, state, winapi


def _on_pressed() -> None:
    state.set_emergency(True)


def start() -> dict:
    r = winapi.start_emergency_hotkey(_on_pressed)
    combo = permission.load_config().get("emergency_hotkey", "ctrl+shift+x")
    return {"ok": bool(r.get("ok")), "combo": combo, **r}


def status() -> dict:
    return {
        "started": winapi.hotkey_is_running(),
        "stopped": state.is_emergency(),
        "combo": permission.load_config().get("emergency_hotkey", "ctrl+shift+x"),
    }


def resume() -> dict:
    state.set_emergency(False)
    return {"ok": True, "stopped": False}
