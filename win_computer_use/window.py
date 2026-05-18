"""Window / app: launch, focus, open file."""
from __future__ import annotations
import os
import shutil
import subprocess
from typing import Optional

import pygetwindow as gw

from . import permission
from .announce import announced

APP_ALIASES = {
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "calc": "calc.exe",
    "calculator": "calc.exe",
    "edge": "msedge.exe",
    "msedge": "msedge.exe",
    "browser": "msedge.exe",
    "notepad": "notepad.exe",
    "explorer": "explorer.exe",
    "files": "explorer.exe",
    "snippingtool": "SnippingTool.exe",
}

# Apps that don't live on PATH — resolve to absolute paths if discoverable.
KNOWN_PATHS = {
    "msedge.exe": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
}


def _absolutize(target: str) -> str:
    base = os.path.basename(target).lower()
    for candidate in KNOWN_PATHS.get(base, []):
        if os.path.exists(candidate):
            return candidate
    return target


def _resolve(name_or_path: str) -> str:
    n = name_or_path.strip()
    low = n.lower()
    if low in APP_ALIASES:
        return APP_ALIASES[low]
    # if a full path or .exe given, keep as-is
    if os.path.isabs(n) or n.lower().endswith(".exe"):
        return n
    return n


@announced("launch_app")
def launch_app(name_or_path: str, args: Optional[list[str]] = None, cwd: Optional[str] = None) -> dict:
    target = _resolve(name_or_path)
    allowed, reason = permission.check("launch_app", target=target)
    if not allowed:
        return {"ok": False, "needs_permission": True, "reason": reason, "target": target}

    args = args or []
    resolved = _absolutize(target)
    try:
        if os.path.isabs(resolved) and os.path.exists(resolved):
            subprocess.Popen([resolved] + args, cwd=cwd, shell=False)
        elif resolved.lower().endswith(".exe"):
            # Bare exe name like mspaint.exe / calc.exe — let the shell resolve App Paths.
            subprocess.Popen([resolved] + args, cwd=cwd, shell=True)
        else:
            subprocess.Popen([resolved] + args, cwd=cwd, shell=True)
        return {"ok": True, "target": resolved, "args": args}
    except Exception as e:
        # Final fallback: use 'start' to leverage the shell's full resolution.
        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "", resolved, *args],
                cwd=cwd,
                shell=False,
            )
            return {"ok": True, "target": resolved, "args": args, "note": "via cmd start"}
        except Exception as e2:
            return {"ok": False, "error": f"{e}; fallback: {e2}", "target": resolved}


@announced("focus_window", gated=False)
def focus_window(title_substring: str) -> dict:
    matches = [w for w in gw.getAllWindows() if title_substring.lower() in (w.title or "").lower() and w.title]
    if not matches:
        return {"ok": False, "error": f"no window matching '{title_substring}'"}
    w = matches[0]
    try:
        if w.isMinimized:
            w.restore()
        w.activate()
        return {
            "ok": True,
            "title": w.title,
            "x": w.left,
            "y": w.top,
            "w": w.width,
            "h": w.height,
        }
    except Exception as e:
        # activate() sometimes fails on first try due to focus stealing prevention.
        try:
            import pyautogui
            pyautogui.press("alt")  # bump foreground lock
            w.activate()
            return {
                "ok": True,
                "title": w.title,
                "x": w.left,
                "y": w.top,
                "w": w.width,
                "h": w.height,
                "note": "activated after alt-bump",
            }
        except Exception as e2:
            return {"ok": False, "error": f"{e}; retry: {e2}", "title": w.title}


@announced("open_file")
def open_file(path: str) -> dict:
    if not os.path.exists(path):
        return {"ok": False, "error": f"path does not exist: {path}"}
    try:
        os.startfile(path)  # type: ignore[attr-defined]
        return {"ok": True, "path": path}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": path}
