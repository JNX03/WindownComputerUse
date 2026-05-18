"""Native Win32 helpers — no pywin32 dependency.

PostMessage-based input lets us click and drag without ever moving the user's
real Windows cursor. RegisterHotKey gives us a reliable emergency-stop hotkey
without needing the `keyboard` package's low-level hooks.
"""
from __future__ import annotations
import ctypes
import threading
import time
from ctypes import wintypes
from typing import Optional

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# ----- message constants ---------------------------------------------------

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONDBLCLK = 0x0206
WM_MOUSEWHEEL = 0x020A
WM_HOTKEY = 0x0312
WHEEL_DELTA = 120

MK_LBUTTON = 0x0001
MK_RBUTTON = 0x0002
MK_MBUTTON = 0x0010

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

# ----- function prototypes -------------------------------------------------

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


user32.WindowFromPoint.restype = wintypes.HWND
user32.WindowFromPoint.argtypes = [POINT]
user32.ScreenToClient.restype = wintypes.BOOL
user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
user32.PostMessageW.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_long
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL


# ----- helpers -------------------------------------------------------------

def _lparam(x: int, y: int) -> int:
    return (int(y) << 16) | (int(x) & 0xFFFF)


def window_at(x: int, y: int) -> int:
    """Return the HWND of the deepest child window at the given screen point."""
    pt = POINT(int(x), int(y))
    hwnd = user32.WindowFromPoint(pt)
    return int(hwnd or 0)


def screen_to_client(hwnd: int, x: int, y: int) -> tuple[int, int]:
    pt = POINT(int(x), int(y))
    user32.ScreenToClient(wintypes.HWND(hwnd), ctypes.byref(pt))
    return pt.x, pt.y


# ----- PostMessage-based mouse input --------------------------------------

def post_click(x: int, y: int, button: str = "left", clicks: int = 1) -> dict:
    """Click at screen (x, y) by posting WM messages — real cursor untouched.

    Returns {"ok": True, "hwnd": ..., "client_x": cx, "client_y": cy} or
    {"ok": False, "error": "..."}.
    """
    hwnd = window_at(x, y)
    if not hwnd:
        return {"ok": False, "error": f"no window at ({x},{y})"}
    cx, cy = screen_to_client(hwnd, x, y)
    lp = _lparam(cx, cy)
    if button == "left":
        down, up, mk = WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON
        dbl = WM_LBUTTONDBLCLK
    elif button == "right":
        down, up, mk = WM_RBUTTONDOWN, WM_RBUTTONUP, MK_RBUTTON
        dbl = WM_RBUTTONDBLCLK
    elif button == "middle":
        down, up, mk = WM_MBUTTONDOWN, WM_MBUTTONUP, MK_MBUTTON
        dbl = WM_MBUTTONDOWN  # no dedicated dbl; just re-down
    else:
        return {"ok": False, "error": f"unknown button {button}"}

    # Quick mousemove sets cursor focus for the receiving window.
    user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lp)
    for i in range(max(1, int(clicks))):
        user32.PostMessageW(hwnd, down, mk, lp)
        time.sleep(0.02)
        user32.PostMessageW(hwnd, up, 0, lp)
        if clicks > 1 and i < clicks - 1:
            time.sleep(0.05)
    return {"ok": True, "hwnd": hwnd, "client_x": cx, "client_y": cy, "button": button, "clicks": clicks}


def post_drag(x1: int, y1: int, x2: int, y2: int, button: str = "left", duration_s: float = 0.4) -> dict:
    """Drag via posted WM messages along a curved path.

    Caveats: many Chromium / DirectX / fullscreen apps ignore synthetic mouse
    messages. For those, fall back to a real-cursor snap-and-restore via
    mouse_drag(use_real_cursor=True).
    """
    import math
    import random

    hwnd_a = window_at(x1, y1)
    hwnd_b = window_at(x2, y2)
    if not hwnd_a:
        return {"ok": False, "error": f"no window at start ({x1},{y1})"}
    # We use the START window for the whole drag — releasing on a different
    # window is rare and PostMessage-drag generally doesn't cross windows anyway.
    hwnd = hwnd_a

    if button == "left":
        down, up, mk = WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON
    elif button == "right":
        down, up, mk = WM_RBUTTONDOWN, WM_RBUTTONUP, MK_RBUTTON
    else:
        return {"ok": False, "error": f"unknown button {button}"}

    cx1, cy1 = screen_to_client(hwnd, x1, y1)
    cx2, cy2 = screen_to_client(hwnd, x2, y2)

    # Press
    user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, _lparam(cx1, cy1))
    user32.PostMessageW(hwnd, down, mk, _lparam(cx1, cy1))

    # Curve via bezier with one randomized control point.
    dx = cx2 - cx1
    dy = cy2 - cy1
    dist = math.hypot(dx, dy)
    if dist < 1.0:
        steps = 2
    else:
        steps = max(8, int(duration_s * 90))
    if dist >= 1.0:
        # perpendicular offset
        px = -dy / dist
        py = dx / dist
        off = random.uniform(0.06, 0.18) * dist * random.choice([-1.0, 1.0])
        ccx = cx1 + dx * 0.5 + px * off
        ccy = cy1 + dy * 0.5 + py * off
    else:
        ccx = cx1
        ccy = cy1
    dt = duration_s / max(1, steps)
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        bx = (u * u) * cx1 + 2 * u * t * ccx + (t * t) * cx2
        by = (u * u) * cy1 + 2 * u * t * ccy + (t * t) * cy2
        user32.PostMessageW(hwnd, WM_MOUSEMOVE, mk, _lparam(int(bx), int(by)))
        time.sleep(dt)

    user32.PostMessageW(hwnd, WM_MOUSEMOVE, mk, _lparam(cx2, cy2))
    user32.PostMessageW(hwnd, up, 0, _lparam(cx2, cy2))
    return {"ok": True, "hwnd": hwnd, "from": [x1, y1], "to": [x2, y2], "button": button}


def post_scroll(x: int, y: int, clicks: int) -> dict:
    """Scroll via WM_MOUSEWHEEL."""
    hwnd = window_at(x, y)
    if not hwnd:
        return {"ok": False, "error": f"no window at ({x},{y})"}
    # WM_MOUSEWHEEL uses SCREEN coords in lParam (yes — different from buttons).
    lp = _lparam(int(x), int(y))
    delta = int(clicks) * WHEEL_DELTA
    wp = (delta & 0xFFFF) << 16
    user32.PostMessageW(hwnd, WM_MOUSEWHEEL, wp, lp)
    return {"ok": True, "hwnd": hwnd, "wheel_delta": delta}


# ----- Native emergency hotkey (RegisterHotKey) ---------------------------

_hotkey_thread: Optional[threading.Thread] = None
_hotkey_started = False


def start_emergency_hotkey(callback) -> dict:
    """Register Ctrl+Shift+X globally and call `callback()` when pressed.

    Uses a dedicated thread running a Win32 message loop, since RegisterHotKey
    delivers WM_HOTKEY to the calling thread's queue.
    """
    global _hotkey_thread, _hotkey_started
    if _hotkey_started:
        return {"ok": True, "already_started": True}

    def _loop() -> None:
        # Register on this thread.
        if not user32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, 0x58):  # 0x58 = 'X'
            return
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    try:
                        callback()
                    except Exception:
                        pass
        finally:
            user32.UnregisterHotKey(None, 1)

    _hotkey_thread = threading.Thread(target=_loop, daemon=True)
    _hotkey_thread.start()
    _hotkey_started = True
    return {"ok": True}


def hotkey_is_running() -> bool:
    return _hotkey_started and (_hotkey_thread is not None) and _hotkey_thread.is_alive()
