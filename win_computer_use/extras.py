"""Phase 3 additions: pixel inspection, waits, window mgmt, files, HTTP, TTS."""
from __future__ import annotations
import os
import time
import urllib.request
from pathlib import Path
from typing import Optional

import mss
import pyautogui
import pygetwindow as gw

from . import state
from .announce import announced
from . import ocr as ocr_tools
from . import vision


# ---- Pixel / color --------------------------------------------------------

@announced("pixel_color", gated=False)
def pixel_color(x: int, y: int) -> dict:
    """Return the RGB color at (x, y) on the virtual desktop."""
    with mss.mss() as sct:
        raw = sct.grab({"left": int(x), "top": int(y), "width": 1, "height": 1})
        b, g, r, _ = raw.raw[0], raw.raw[1], raw.raw[2], raw.raw[3]
    return {
        "x": int(x),
        "y": int(y),
        "r": int(r),
        "g": int(g),
        "b": int(b),
        "hex": f"#{int(r):02X}{int(g):02X}{int(b):02X}",
        "ok": True,
    }


# ---- Cursor introspection -------------------------------------------------

@announced("get_virtual_cursor", gated=False)
def get_virtual_cursor() -> dict:
    """Return the AI's virtual cursor position and pressed state."""
    s = state.load()
    return {
        "x": int(s.get("virtual_cursor_x", 0)),
        "y": int(s.get("virtual_cursor_y", 0)),
        "pressed": bool(s.get("virtual_cursor_pressed", False)),
        "ok": True,
    }


# ---- Wait helpers ---------------------------------------------------------

def _hex_to_rgb(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


@announced("wait_for_pixel_color", gated=False)
def wait_for_pixel_color(x: int, y: int, hex_color: str, timeout_s: float = 10.0, tolerance: int = 6) -> dict:
    """Block until pixel (x,y) is within tolerance of hex_color, or timeout."""
    target = _hex_to_rgb(hex_color)
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        c = pixel_color.__wrapped__(x, y)
        if (
            abs(c["r"] - target[0]) <= tolerance
            and abs(c["g"] - target[1]) <= tolerance
            and abs(c["b"] - target[2]) <= tolerance
        ):
            return {"ok": True, "found_after_s": round(time.time() - t0, 2), "actual": c["hex"]}
        time.sleep(0.1)
    return {"ok": False, "error": "timeout", "actual": pixel_color.__wrapped__(x, y)["hex"]}


@announced("wait_for_window", gated=False)
def wait_for_window(title_substring: str, timeout_s: float = 10.0) -> dict:
    """Block until a window whose title contains the substring exists."""
    needle = title_substring.lower()
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        for w in gw.getAllWindows():
            if needle in (w.title or "").lower() and w.title:
                return {
                    "ok": True,
                    "found_after_s": round(time.time() - t0, 2),
                    "title": w.title,
                    "x": w.left, "y": w.top, "w": w.width, "h": w.height,
                }
        time.sleep(0.2)
    return {"ok": False, "error": "timeout"}


@announced("wait_for_text", gated=False)
def wait_for_text(text: str, timeout_s: float = 10.0, region: Optional[dict] = None) -> dict:
    """Block until OCR finds `text` on screen (in optional region)."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        r = ocr_tools.find_text_on_screen.__wrapped__(text, region=region)
        if r.get("ok") and r.get("count", 0) > 0:
            r["found_after_s"] = round(time.time() - t0, 2)
            return r
        time.sleep(0.4)
    return {"ok": False, "error": "timeout"}


# ---- Window management ----------------------------------------------------

def _find_window(title_substring: str):
    needle = title_substring.lower()
    for w in gw.getAllWindows():
        if w.title and needle in w.title.lower():
            return w
    return None


@announced("get_active_window", gated=False)
def get_active_window() -> dict:
    w = gw.getActiveWindow()
    if not w:
        return {"ok": False, "error": "no active window"}
    return {"ok": True, "title": w.title, "x": w.left, "y": w.top, "w": w.width, "h": w.height}


@announced("close_window")
def close_window(title_substring: str) -> dict:
    w = _find_window(title_substring)
    if not w:
        return {"ok": False, "error": f"no window matching '{title_substring}'"}
    try:
        w.close()
        return {"ok": True, "closed": w.title}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@announced("move_window")
def move_window(title_substring: str, x: int, y: int, w: int, h: int) -> dict:
    win = _find_window(title_substring)
    if not win:
        return {"ok": False, "error": f"no window matching '{title_substring}'"}
    try:
        win.moveTo(int(x), int(y))
        win.resizeTo(int(w), int(h))
        return {"ok": True, "title": win.title, "x": int(x), "y": int(y), "w": int(w), "h": int(h)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@announced("minimize_window")
def minimize_window(title_substring: str) -> dict:
    win = _find_window(title_substring)
    if not win:
        return {"ok": False, "error": f"no window matching '{title_substring}'"}
    try:
        win.minimize()
        return {"ok": True, "title": win.title}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@announced("maximize_window")
def maximize_window(title_substring: str) -> dict:
    win = _find_window(title_substring)
    if not win:
        return {"ok": False, "error": f"no window matching '{title_substring}'"}
    try:
        win.maximize()
        return {"ok": True, "title": win.title}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@announced("restore_window")
def restore_window(title_substring: str) -> dict:
    win = _find_window(title_substring)
    if not win:
        return {"ok": False, "error": f"no window matching '{title_substring}'"}
    try:
        win.restore()
        return {"ok": True, "title": win.title}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---- Process management ---------------------------------------------------

@announced("list_processes", gated=False)
def list_processes(name_contains: Optional[str] = None) -> list[dict]:
    import psutil  # type: ignore
    needle = (name_contains or "").lower()
    out: list[dict] = []
    for p in psutil.process_iter(["pid", "name", "exe", "cpu_percent", "memory_info"]):
        try:
            info = p.info
            if needle and needle not in (info.get("name") or "").lower():
                continue
            mem = info.get("memory_info")
            out.append({
                "pid": info["pid"],
                "name": info.get("name"),
                "exe": info.get("exe"),
                "cpu_percent": info.get("cpu_percent"),
                "rss_mb": int((mem.rss if mem else 0) / (1024 * 1024)),
            })
        except Exception:
            continue
    return out


@announced("kill_process")
def kill_process(pid_or_name: str | int) -> dict:
    import psutil  # type: ignore
    try:
        if isinstance(pid_or_name, int) or (isinstance(pid_or_name, str) and pid_or_name.isdigit()):
            p = psutil.Process(int(pid_or_name))
            name = p.name()
            p.terminate()
            try:
                p.wait(timeout=3)
            except psutil.TimeoutExpired:
                p.kill()
            return {"ok": True, "killed": [{"pid": int(pid_or_name), "name": name}]}
        # by name
        killed: list[dict] = []
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if (p.info.get("name") or "").lower() == str(pid_or_name).lower():
                    p.terminate()
                    killed.append({"pid": p.info["pid"], "name": p.info["name"]})
            except Exception:
                continue
        return {"ok": True, "killed": killed}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---- File I/O -------------------------------------------------------------

@announced("read_text_file", gated=False)
def read_text_file(path: str, max_bytes: int = 200_000) -> dict:
    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": "file does not exist"}
    try:
        size = p.stat().st_size
        with p.open("rb") as f:
            data = f.read(int(max_bytes))
        return {
            "ok": True,
            "path": str(p),
            "size_bytes": size,
            "returned_bytes": len(data),
            "truncated": size > len(data),
            "text": data.decode("utf-8", errors="replace"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@announced("write_text_file")
def write_text_file(path: str, content: str, append: bool = False) -> dict:
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with p.open(mode, encoding="utf-8") as f:
            f.write(content)
        return {"ok": True, "path": str(p), "bytes_written": len(content.encode("utf-8")), "append": append}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@announced("list_directory", gated=False)
def list_directory(path: str, include_hidden: bool = False) -> dict:
    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": "directory does not exist"}
    if not p.is_dir():
        return {"ok": False, "error": "not a directory"}
    entries: list[dict] = []
    try:
        for child in sorted(p.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower())):
            if not include_hidden and child.name.startswith("."):
                continue
            try:
                st = child.stat()
                entries.append({
                    "name": child.name,
                    "is_dir": child.is_dir(),
                    "size_bytes": st.st_size if not child.is_dir() else None,
                    "modified": int(st.st_mtime),
                })
            except Exception:
                continue
        return {"ok": True, "path": str(p), "count": len(entries), "entries": entries}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@announced("delete_path")
def delete_path(path: str, recursive: bool = False) -> dict:
    import shutil

    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": "does not exist"}
    try:
        if p.is_dir():
            if recursive:
                shutil.rmtree(p)
            else:
                p.rmdir()
        else:
            p.unlink()
        return {"ok": True, "deleted": str(p)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---- HTTP -----------------------------------------------------------------

@announced("http_get", gated=False)
def http_get(url: str, timeout_s: float = 15.0, max_bytes: int = 200_000) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "win-computer-use/0.3"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            data = r.read(int(max_bytes))
            return {
                "ok": True,
                "url": url,
                "status": r.status,
                "content_type": r.headers.get("Content-Type"),
                "bytes": len(data),
                "text": data.decode("utf-8", errors="replace"),
            }
    except Exception as e:
        return {"ok": False, "error": str(e), "url": url}


@announced("download_file")
def download_file(url: str, dest_path: str, timeout_s: float = 60.0) -> dict:
    p = Path(dest_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "win-computer-use/0.3"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r, p.open("wb") as f:
            total = 0
            while True:
                chunk = r.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                total += len(chunk)
        return {"ok": True, "url": url, "path": str(p), "bytes": total}
    except Exception as e:
        return {"ok": False, "error": str(e), "url": url}


# ---- TTS via Windows SAPI -------------------------------------------------

@announced("text_to_speech")
def text_to_speech(text: str, rate: int = 0) -> dict:
    """Speak the text out loud using the Windows SAPI voice."""
    try:
        import comtypes.client  # type: ignore
        sapi = comtypes.client.CreateObject("SAPI.SpVoice")
        sapi.Rate = int(rate)
        sapi.Speak(text)
        return {"ok": True, "chars": len(text)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---- Convenience: save screenshot to file --------------------------------

@announced("screenshot_to_file", gated=False)
def screenshot_to_file(path: str, monitor_index: int = 0) -> dict:
    import base64

    shot = vision.screenshot.__wrapped__(monitor_index=monitor_index)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(base64.b64decode(shot["image_base64"]))
    return {
        "ok": True,
        "path": str(p),
        "full_width": shot["full_width"],
        "full_height": shot["full_height"],
    }


# ---- System -----------------------------------------------------

@announced("lock_workstation")
def lock_workstation() -> dict:
    """Lock the Windows session (LockWorkStation API)."""
    import ctypes

    ok = ctypes.windll.user32.LockWorkStation()
    return {"ok": bool(ok)}


@announced("get_battery", gated=False)
def get_battery() -> dict:
    try:
        import psutil  # type: ignore
        b = psutil.sensors_battery()
        if not b:
            return {"ok": False, "error": "no battery (desktop?)"}
        return {
            "ok": True,
            "percent": int(b.percent),
            "plugged_in": bool(b.power_plugged),
            "seconds_left": b.secsleft if b.secsleft >= 0 else None,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
