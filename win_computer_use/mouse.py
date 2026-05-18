"""Mouse: move, click, drag, scroll — with a fully independent virtual AI cursor.

Behavior:
- mouse_move animates a virtual cursor (stored in state.json) along a Bezier
  curve with subtle jitter. The real Windows cursor is NEVER touched.
- mouse_click / mouse_drag / mouse_scroll send WM_LBUTTONDOWN/UP etc. via
  PostMessage to the window at the target point. The real cursor stays where
  the user left it. Works in standard Win32 apps.
- For apps that ignore synthetic input (Chromium, games, DirectX), each tool
  takes an optional `use_real_cursor=True` to fall back to brief snap-restore
  via pyautogui.
"""
from __future__ import annotations
import math
import random
import time
from typing import Iterable, Optional

import pyautogui

from . import permission, state, winapi
from .announce import announced

pyautogui.MINIMUM_DURATION = 0
pyautogui.MINIMUM_SLEEP = 0
pyautogui.PAUSE = 0.02


def _duration(d: Optional[float]) -> float:
    if d is not None:
        return max(0.0, float(d))
    return float(permission.load_config().get("mouse_move_duration_s", 0.6))


# ---- Human-like path generation -------------------------------------------

def _ease_out_cubic(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


def _bezier_path(
    sx: float, sy: float, ex: float, ey: float, *, n_points: int = 60, curviness: float = 0.18
) -> list[tuple[int, int]]:
    """Generate a cubic Bezier path from (sx,sy) to (ex,ey) with randomized control points
    offset perpendicular to the line, plus subtle jitter on each sample.

    curviness ~ 0.1–0.3 produces natural-looking arcs.
    """
    dx = ex - sx
    dy = ey - sy
    dist = math.hypot(dx, dy)
    if dist < 1.0:
        return [(int(ex), int(ey))]

    # Perpendicular unit vector
    px = -dy / dist
    py = dx / dist

    # Two control points at ~1/3 and ~2/3 along the line, offset perpendicularly
    # in opposite directions by a random fraction of the total distance.
    off1 = random.uniform(0.08, curviness) * dist * random.choice([-1.0, 1.0])
    off2 = random.uniform(0.05, curviness) * dist * random.choice([-1.0, 1.0])
    c1x = sx + dx * (1.0 / 3.0) + px * off1
    c1y = sy + dy * (1.0 / 3.0) + py * off1
    c2x = sx + dx * (2.0 / 3.0) + px * off2
    c2y = sy + dy * (2.0 / 3.0) + py * off2

    pts: list[tuple[int, int]] = []
    for i in range(1, n_points + 1):
        # Ease-out: spend more time finishing precisely on target.
        t = _ease_out_cubic(i / n_points)
        u = 1.0 - t
        bx = (u ** 3) * sx + 3 * (u ** 2) * t * c1x + 3 * u * (t ** 2) * c2x + (t ** 3) * ex
        by = (u ** 3) * sy + 3 * (u ** 2) * t * c1y + 3 * u * (t ** 2) * c2y + (t ** 3) * ey
        # Tiny jitter — proportional to distance, never overshoots.
        jx = random.uniform(-1.0, 1.0) * min(1.5, dist * 0.003)
        jy = random.uniform(-1.0, 1.0) * min(1.5, dist * 0.003)
        # Decay jitter near the end so we land exactly on target.
        jx *= (1.0 - t) ** 2
        jy *= (1.0 - t) ** 2
        pts.append((int(round(bx + jx)), int(round(by + jy))))
    # Snap final point exactly on target.
    pts[-1] = (int(round(ex)), int(round(ey)))
    return pts


def _animate_virtual(x: int, y: int, duration_s: float, fps: int = 60) -> None:
    """Animate the VIRTUAL cursor only. Real cursor untouched."""
    sx, sy = state.get_virtual_cursor()
    if duration_s <= 0 or (sx, sy) == (int(x), int(y)):
        state.set_virtual_cursor(int(x), int(y))
        return
    steps = max(8, int(duration_s * fps))
    path = _bezier_path(sx, sy, x, y, n_points=steps)
    dt = duration_s / len(path)
    for px, py in path:
        state.set_virtual_cursor(px, py)
        time.sleep(dt)
    state.set_virtual_cursor(int(x), int(y))


def _animate_real_and_virtual(x: int, y: int, duration_s: float, fps: int = 60) -> None:
    """Animate BOTH virtual and real cursor along a Bezier path. Used for drag."""
    sx, sy = state.get_virtual_cursor()
    if duration_s <= 0 or (sx, sy) == (int(x), int(y)):
        pyautogui.moveTo(int(x), int(y), duration=0)
        state.set_virtual_cursor(int(x), int(y))
        return
    steps = max(8, int(duration_s * fps))
    path = _bezier_path(sx, sy, x, y, n_points=steps)
    dt = duration_s / len(path)
    for px, py in path:
        pyautogui.moveTo(px, py, duration=0)
        state.set_virtual_cursor(px, py)
        time.sleep(dt)
    pyautogui.moveTo(int(x), int(y), duration=0)
    state.set_virtual_cursor(int(x), int(y))


def _save_real_pos() -> tuple[int, int]:
    p = pyautogui.position()
    return int(p.x), int(p.y)


def _snap_real(x: int, y: int) -> None:
    # Fastest possible move so the flicker is invisible.
    pyautogui.moveTo(int(x), int(y), duration=0)


def _restore_real(sx: int, sy: int) -> None:
    pyautogui.moveTo(int(sx), int(sy), duration=0)


@announced("mouse_move")
def mouse_move(x: int, y: int, duration_s: Optional[float] = None) -> dict:
    """Animate the AI's virtual cursor to (x, y). User's real cursor untouched."""
    _animate_virtual(int(x), int(y), _duration(duration_s))
    return {"x": int(x), "y": int(y), "virtual": True, "ok": True}


def _real_click_fallback(x: int, y: int, button: str, clicks: int, interval_s: float) -> dict:
    user_pos = _save_real_pos()
    try:
        _snap_real(int(x), int(y))
        pyautogui.click(button=button, clicks=clicks, interval=interval_s)
    finally:
        _restore_real(*user_pos)
    return {"x": int(x), "y": int(y), "button": button, "clicks": clicks, "method": "real-cursor-snap", "ok": True}


@announced("mouse_click")
def mouse_click(
    x: Optional[int] = None,
    y: Optional[int] = None,
    button: str = "left",
    clicks: int = 1,
    interval_s: float = 0.05,
    duration_s: Optional[float] = None,
    use_real_cursor: bool = False,
) -> dict:
    """Click at (x, y) or at the AI cursor's current position.

    By default sends WM_LBUTTONDOWN/UP via PostMessage so the real cursor never
    moves. If the target app ignores synthetic clicks (Chromium, games),
    pass use_real_cursor=True to briefly snap the real cursor instead.
    """
    if x is None or y is None:
        vx, vy = state.get_virtual_cursor()
        x = x if x is not None else vx
        y = y if y is not None else vy
    else:
        _animate_virtual(int(x), int(y), _duration(duration_s))

    state.set_pressed(True)
    try:
        if use_real_cursor:
            r = _real_click_fallback(int(x), int(y), button, clicks, interval_s)
        else:
            r = winapi.post_click(int(x), int(y), button=button, clicks=clicks)
            if not r.get("ok"):
                # Auto-fallback if PostMessage couldn't find a window.
                r = _real_click_fallback(int(x), int(y), button, clicks, interval_s)
                r["method"] = "real-cursor-fallback"
            else:
                r["method"] = "postmessage"
                r["x"] = int(x); r["y"] = int(y)
    finally:
        state.set_pressed(False)
    return r


@announced("mouse_double_click")
def mouse_double_click(x: int, y: int, button: str = "left", use_real_cursor: bool = False) -> dict:
    return mouse_click.__wrapped__(
        x=x, y=y, button=button, clicks=2, interval_s=0.08, use_real_cursor=use_real_cursor
    )


@announced("mouse_drag")
def mouse_drag(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    button: str = "left",
    duration_s: Optional[float] = None,
    hold_after_s: float = 0.05,
    use_real_cursor: bool = False,
) -> dict:
    """Drag from (x1,y1) to (x2,y2). By default uses PostMessage drag so the
    real cursor never moves. Pass use_real_cursor=True for apps that need
    real synthetic input (Paint, games, drawing apps)."""
    d = _duration(duration_s)
    # Animate virtual cursor to start so the user sees it position before pressing.
    _animate_virtual(int(x1), int(y1), max(d, 0.15))

    state.set_pressed(True)
    try:
        if use_real_cursor:
            user_pos = _save_real_pos()
            try:
                _snap_real(int(x1), int(y1))
                pyautogui.mouseDown(button=button)
                _animate_real_and_virtual(int(x2), int(y2), max(d, 0.25))
                if hold_after_s > 0:
                    time.sleep(hold_after_s)
            finally:
                try:
                    pyautogui.mouseUp(button=button)
                except Exception:
                    pass
                _restore_real(*user_pos)
            return {"from": [int(x1), int(y1)], "to": [int(x2), int(y2)], "button": button, "method": "real-cursor", "ok": True}
        else:
            # PostMessage drag: also drive the virtual cursor along the same path for visibility.
            import threading

            def animate_virtual_only():
                _animate_virtual(int(x2), int(y2), max(d, 0.25))

            t = threading.Thread(target=animate_virtual_only, daemon=True)
            t.start()
            r = winapi.post_drag(int(x1), int(y1), int(x2), int(y2), button=button, duration_s=max(d, 0.25))
            t.join(timeout=max(d, 0.25) + 0.5)
            r["method"] = "postmessage"
            return r
    finally:
        state.set_pressed(False)


@announced("mouse_scroll")
def mouse_scroll(clicks: int, x: Optional[int] = None, y: Optional[int] = None, use_real_cursor: bool = False) -> dict:
    if x is not None and y is not None:
        _animate_virtual(int(x), int(y), _duration(None))
    vx, vy = state.get_virtual_cursor()
    if use_real_cursor:
        user_pos = _save_real_pos()
        try:
            _snap_real(vx, vy)
            pyautogui.scroll(int(clicks))
        finally:
            _restore_real(*user_pos)
        return {"clicks": int(clicks), "method": "real-cursor", "ok": True}
    r = winapi.post_scroll(int(vx), int(vy), int(clicks))
    r["method"] = "postmessage"
    return r
