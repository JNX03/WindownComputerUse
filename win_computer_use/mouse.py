"""Mouse: move, click, drag, scroll — with a fully independent virtual AI cursor.

Behavior:
- mouse_move animates a virtual cursor along a curved Bezier path with spring
  acceleration/deceleration, micro-tremor, and rotation that follows motion
  direction. The cursor position streams through a lightweight side-file
  (cursor_pos.txt) so the overlay can render at high fps without contending
  with the rest of the state.json blob. The real Windows cursor is NEVER
  touched on the default path.
- mouse_click / mouse_drag / mouse_scroll send WM_LBUTTONDOWN/UP etc. via
  PostMessage to the window at the target point. The real cursor stays where
  the user left it. Works in standard Win32 apps.
- For apps that ignore synthetic input (Chromium, games, DirectX), each tool
  takes an optional `use_real_cursor=True` to fall back to brief snap-restore
  via pyautogui.

The animation algorithm is a direct port of `testing/mouse-simulation.html`:
cubic Bezier from current position to the target, with the time parameter t
driven by under-damped spring physics (so the cursor accelerates, very slightly
overshoots, and settles). Tremor + lateral wobble decay near arrival, like a
human hand. The cursor sprite is rotated to face its velocity vector during
travel and eased back to a resting NW orientation once stopped.
"""
from __future__ import annotations
import ctypes
import math
import random
import time
from typing import Optional

import pyautogui

from . import permission, state, winapi
from .announce import announced

# Windows' default timer resolution is ~15.6 ms, so `time.sleep(0.011)`
# actually sleeps 15-50 ms. That drops our animation from ~90 fps to ~20 fps
# and the overlay (polling at 60 Hz) only sees a couple of samples per move,
# producing visible "teleports". timeBeginPeriod(1) bumps the granularity to
# 1 ms for as long as the call is in effect; we pair it with timeEndPeriod(1)
# around each animation.
try:
    _winmm = ctypes.windll.winmm
except Exception:  # pragma: no cover — non-Windows
    _winmm = None


class _HighResTimer:
    def __enter__(self):
        if _winmm is not None:
            try:
                _winmm.timeBeginPeriod(1)
            except Exception:
                pass
        return self

    def __exit__(self, *exc):
        if _winmm is not None:
            try:
                _winmm.timeEndPeriod(1)
            except Exception:
                pass

pyautogui.MINIMUM_DURATION = 0
pyautogui.MINIMUM_SLEEP = 0
# Don't pause after every pyautogui call — we manage timing ourselves.
pyautogui.PAUSE = 0


def _duration(d: Optional[float]) -> float:
    if d is not None:
        return max(0.0, float(d))
    return float(permission.load_config().get("mouse_move_duration_s", 0.25))


# ---- Human-like path generation -------------------------------------------
# HTML simulation defaults (start=0.40, end=0.20, size=0.45, flow=0.60,
# spring=0.55). Curved Bezier + spring time-driver = the look the user wants.
S_START = 0.40
S_END = 0.20
S_SIZE = 0.45
S_FLOW = 0.60
S_SPRING_DEFAULT = 0.55

# The arrow in overlay.py is drawn with its tip pointing up-left (NW).
# Forward direction in screen space = atan2(-1, -1) = -3π/4. Rotation
# applied to the sprite = motion_angle - RESTING_FORWARD.
RESTING_FORWARD = -math.pi * 3.0 / 4.0


def _bezier_handles(sx: float, sy: float, ex: float, ey: float) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float], float]:
    dx, dy = ex - sx, ey - sy
    dist = math.hypot(dx, dy) or 1.0
    ux, uy = dx / dist, dy / dist
    perp_x, perp_y = -uy, ux

    jitter_start = (random.random() - 0.5) * 0.12
    jitter_end = (random.random() - 0.5) * 0.12
    size_mul = 0.65 + random.random() * 0.75
    flow_mul = 0.7 + random.random() * 0.6
    flow_sign = 1.0 if S_FLOW >= 0 else -1.0
    flow_abs = abs(S_FLOW)

    arc = S_SIZE * dist * 0.9 * size_mul
    a1x = sx + ux * dist * max(0.05, S_START + jitter_start)
    a1y = sy + uy * dist * max(0.05, S_START + jitter_start)
    a2x = sx + ux * dist * min(0.95, (1 - S_END) + jitter_end)
    a2y = sy + uy * dist * min(0.95, (1 - S_END) + jitter_end)
    off1 = arc * flow_abs * flow_mul * flow_sign
    off2 = arc * flow_abs * flow_mul * flow_sign * (0.4 + random.random() * 0.5)

    P0 = (sx, sy)
    P1 = (a1x + perp_x * off1, a1y + perp_y * off1)
    P2 = (a2x + perp_x * off2, a2y + perp_y * off2)
    P3 = (ex, ey)
    return P0, P1, P2, P3, dist


def _bezier(P0, P1, P2, P3, t):
    it = 1.0 - t
    b0 = it * it * it
    b1 = 3 * it * it * t
    b2 = 3 * it * t * t
    b3 = t * t * t
    return (
        P0[0] * b0 + P1[0] * b1 + P2[0] * b2 + P3[0] * b3,
        P0[1] * b0 + P1[1] * b1 + P2[1] * b2 + P3[1] * b3,
    )


def _bezier_deriv(P0, P1, P2, P3, t):
    it = 1.0 - t
    return (
        3 * it * it * (P1[0] - P0[0]) + 6 * it * t * (P2[0] - P1[0]) + 3 * t * t * (P3[0] - P2[0]),
        3 * it * it * (P1[1] - P0[1]) + 6 * it * t * (P2[1] - P1[1]) + 3 * t * t * (P3[1] - P2[1]),
    )


def _spring_animate(
    target_x: int,
    target_y: int,
    duration_s: float,
    *,
    on_step,
    fps: int = 60,
) -> tuple[int, int, float]:
    """Spring-driven Bezier animation. Calls on_step(x, y, angle) per frame.

    duration_s scales the spring stiffness — short = snappy, long = leisurely.
    The physics is driven by wall-clock dt from perf_counter so the cursor
    settles in the requested duration regardless of OS sleep granularity. The
    high-resolution-timer context manager bumps Windows' timer to 1 ms so
    we can actually hit our frame interval.
    """
    sx, sy = state.get_virtual_cursor()
    if (sx, sy) == (int(target_x), int(target_y)):
        on_step(int(target_x), int(target_y), 0.0)
        return int(target_x), int(target_y), 0.0

    P0, P1, P2, P3, dist = _bezier_handles(sx, sy, target_x, target_y)

    # Pick spring constants so the *settling time* roughly matches duration_s.
    # For an under-damped 2nd-order system with damping ratio ζ, the 2% settling
    # time is ≈ 4 / (ζ ω). With ζ = 0.80 (mild overshoot, fast settle), that
    # gives ω ≈ 5 / settle_time. We use 5.5 as a small fudge so the cursor
    # arrives just before the requested duration rather than just after,
    # leaving the deadline-cap as a true safety net.
    omega = 5.5 / max(0.10, float(duration_s))
    k = omega * omega
    d = 2.0 * omega * 0.80

    t = 0.0
    t_vel = 0.0
    frame_dt = 1.0 / fps
    last_angle = 0.0
    deadline_s = max(0.3, duration_s * 1.6)

    with _HighResTimer():
        loop_start = time.perf_counter()
        last_ts = loop_start
        while True:
            now = time.perf_counter()
            real_dt = now - last_ts
            # Clamp so a stalled scheduler can't drive a giant single step.
            if real_dt > 0.05:
                real_dt = 0.05
            elif real_dt <= 0:
                real_dt = frame_dt
            last_ts = now
            elapsed = now - loop_start

            a = k * (1.0 - t) - d * t_vel
            t_vel += a * real_dt
            t += t_vel * real_dt
            t_eval = max(0.0, min(1.04, t))

            bx, by = _bezier(P0, P1, P2, P3, t_eval)
            tan_x, tan_y = _bezier_deriv(P0, P1, P2, P3, min(1.0, t_eval))

            remaining = max(0.0, 1.0 - t)
            speed = math.hypot(tan_x, tan_y)
            tremor_amp = min(2.0, 0.4 + speed * 0.0035) * min(1.0, remaining * 1.6)
            wobble = math.sin(elapsed * 22.0) * 0.6 * remaining
            if speed > 1e-4:
                tsx, tsy = -tan_y / speed, tan_x / speed
                last_angle = math.atan2(tan_y, tan_x)
            else:
                tsx, tsy = 0.0, 0.0
            jx = (random.random() - 0.5) * tremor_amp + tsx * wobble
            jy = (random.random() - 0.5) * tremor_amp + tsy * wobble

            sprite_angle = last_angle - RESTING_FORWARD
            on_step(int(round(bx + jx)), int(round(by + jy)), sprite_angle)

            if t >= 0.998 and abs(t_vel) < 0.06:
                break
            if elapsed >= deadline_s:
                break

            # Sleep until the next frame boundary, but respect what we've
            # already burned computing this frame.
            spent = time.perf_counter() - now
            remaining_frame = frame_dt - spent
            if remaining_frame > 0:
                time.sleep(remaining_frame)

    on_step(int(target_x), int(target_y), 0.0)
    return int(target_x), int(target_y), 0.0


def _animate_virtual(x: int, y: int, duration_s: float) -> None:
    """Spring-Bezier animate VIRTUAL cursor only — real cursor untouched."""
    if duration_s <= 0:
        state.set_virtual_cursor(int(x), int(y), angle_rad=0.0)
        return

    def step(px, py, ang):
        state.write_cursor_pos(px, py, ang, False)

    fx, fy, fang = _spring_animate(int(x), int(y), float(duration_s), on_step=step)
    # One canonical write into state.json so the slow path stays coherent.
    state.set_virtual_cursor(fx, fy, angle_rad=fang)


def _animate_real_and_virtual(x: int, y: int, duration_s: float) -> None:
    """Spring-Bezier animate BOTH virtual and real (used for drag)."""
    if duration_s <= 0:
        pyautogui.moveTo(int(x), int(y), duration=0)
        state.set_virtual_cursor(int(x), int(y), angle_rad=0.0)
        return

    def step(px, py, ang):
        pyautogui.moveTo(px, py, duration=0)
        state.write_cursor_pos(px, py, ang, True)

    fx, fy, fang = _spring_animate(int(x), int(y), float(duration_s), on_step=step)
    state.set_virtual_cursor(fx, fy, angle_rad=fang)


def _save_real_pos() -> tuple[int, int]:
    p = pyautogui.position()
    return int(p.x), int(p.y)


def _snap_real(x: int, y: int) -> None:
    pyautogui.moveTo(int(x), int(y), duration=0)


def _restore_real(sx: int, sy: int) -> None:
    pyautogui.moveTo(int(sx), int(sy), duration=0)


# ---- Public API -----------------------------------------------------------

@announced("mouse_move")
def mouse_move(x: int, y: int, duration_s: Optional[float] = None) -> dict:
    """Animate the AI's virtual cursor to (x, y). User's real cursor untouched."""
    _animate_virtual(int(x), int(y), _duration(duration_s))
    return {"x": int(x), "y": int(y), "virtual": True, "ok": True}


@announced("mouse_move_path")
def mouse_move_path(
    points: list,
    duration_s_per_segment: Optional[float] = None,
) -> dict:
    """Animate through a list of waypoints in one call.

    points: a list of [x, y] pairs. Each segment uses the same spring/Bezier
    animation as mouse_move, so a 3-point path produces two smooth arcs.
    """
    if not points:
        return {"ok": False, "error": "no points provided"}
    d = _duration(duration_s_per_segment)
    timings = []
    for pt in points:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            return {"ok": False, "error": f"invalid waypoint: {pt!r}"}
        t0 = time.time()
        _animate_virtual(int(pt[0]), int(pt[1]), d)
        timings.append(int((time.time() - t0) * 1000))
    last = points[-1]
    return {
        "ok": True,
        "segments": len(points),
        "segment_ms": timings,
        "final": [int(last[0]), int(last[1])],
    }


@announced("mouse_hover")
def mouse_hover(
    x: int,
    y: int,
    dwell_ms: int = 400,
    duration_s: Optional[float] = None,
) -> dict:
    """Move to (x, y) then dwell for dwell_ms — useful for triggering tooltips."""
    _animate_virtual(int(x), int(y), _duration(duration_s))
    if dwell_ms > 0:
        time.sleep(max(0, int(dwell_ms)) / 1000.0)
    return {"x": int(x), "y": int(y), "dwell_ms": int(dwell_ms), "ok": True}


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
    # Call the wrapped function so the announced decorator still fires.
    return mouse_click(
        x=x, y=y, button=button, clicks=2, interval_s=0.08, use_real_cursor=use_real_cursor
    )


@announced("mouse_down")
def mouse_down(
    x: Optional[int] = None,
    y: Optional[int] = None,
    button: str = "left",
    duration_s: Optional[float] = None,
    use_real_cursor: bool = False,
) -> dict:
    """Press the mouse button without releasing it. Pair with mouse_up."""
    if x is not None and y is not None:
        _animate_virtual(int(x), int(y), _duration(duration_s))
    vx, vy = state.get_virtual_cursor()
    state.set_pressed(True)
    if use_real_cursor:
        user_pos = _save_real_pos()
        _snap_real(vx, vy)
        try:
            pyautogui.mouseDown(button=button)
        except Exception as e:
            state.set_pressed(False)
            _restore_real(*user_pos)
            return {"ok": False, "error": str(e)}
        # Note: real cursor is NOT restored here — a real button is held down
        # and restoring would drag. mouse_up restores it.
        return {"x": vx, "y": vy, "button": button, "method": "real-cursor", "real_pos_before": user_pos, "ok": True}
    if button == "left":
        down, _, mk = winapi.WM_LBUTTONDOWN, winapi.WM_LBUTTONUP, winapi.MK_LBUTTON
    elif button == "right":
        down, _, mk = winapi.WM_RBUTTONDOWN, winapi.WM_RBUTTONUP, winapi.MK_RBUTTON
    elif button == "middle":
        down, _, mk = winapi.WM_MBUTTONDOWN, winapi.WM_MBUTTONUP, winapi.MK_MBUTTON
    else:
        state.set_pressed(False)
        return {"ok": False, "error": f"unknown button {button}"}
    hwnd = winapi.window_at(vx, vy)
    if not hwnd:
        state.set_pressed(False)
        return {"ok": False, "error": f"no window at ({vx},{vy})"}
    cx, cy = winapi.screen_to_client(hwnd, vx, vy)
    lp = winapi._lparam(cx, cy)
    winapi.user32.PostMessageW(hwnd, winapi.WM_MOUSEMOVE, 0, lp)
    winapi.user32.PostMessageW(hwnd, down, mk, lp)
    return {"x": vx, "y": vy, "button": button, "method": "postmessage", "hwnd": hwnd, "ok": True}


@announced("mouse_up")
def mouse_up(
    x: Optional[int] = None,
    y: Optional[int] = None,
    button: str = "left",
    use_real_cursor: bool = False,
    real_pos_before: Optional[list] = None,
) -> dict:
    """Release a previously pressed mouse button."""
    if x is not None and y is not None:
        _animate_virtual(int(x), int(y), _duration(None))
    vx, vy = state.get_virtual_cursor()
    try:
        if use_real_cursor:
            try:
                pyautogui.mouseUp(button=button)
            except Exception:
                pass
            if real_pos_before and len(real_pos_before) == 2:
                _restore_real(int(real_pos_before[0]), int(real_pos_before[1]))
            return {"x": vx, "y": vy, "button": button, "method": "real-cursor", "ok": True}
        if button == "left":
            up, mk = winapi.WM_LBUTTONUP, 0
        elif button == "right":
            up, mk = winapi.WM_RBUTTONUP, 0
        elif button == "middle":
            up, mk = winapi.WM_MBUTTONUP, 0
        else:
            return {"ok": False, "error": f"unknown button {button}"}
        hwnd = winapi.window_at(vx, vy)
        if not hwnd:
            return {"ok": False, "error": f"no window at ({vx},{vy})"}
        cx, cy = winapi.screen_to_client(hwnd, vx, vy)
        lp = winapi._lparam(cx, cy)
        winapi.user32.PostMessageW(hwnd, up, mk, lp)
        return {"x": vx, "y": vy, "button": button, "method": "postmessage", "hwnd": hwnd, "ok": True}
    finally:
        state.set_pressed(False)


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
    # Travel to the start point first so the user sees the cursor arrive.
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
        # PostMessage drag — animate the virtual cursor along the same path
        # synchronously so the overlay tracks it. winapi.post_drag synthesises
        # the WM_MOUSEMOVE stream at the OS level for the target window.
        _animate_virtual(int(x2), int(y2), max(d, 0.25))
        r = winapi.post_drag(int(x1), int(y1), int(x2), int(y2), button=button, duration_s=max(d, 0.25))
        r["method"] = "postmessage"
        return r
    finally:
        state.set_pressed(False)


@announced("mouse_scroll")
def mouse_scroll(
    clicks: int,
    x: Optional[int] = None,
    y: Optional[int] = None,
    duration_s: Optional[float] = None,
    use_real_cursor: bool = False,
) -> dict:
    """Scroll the wheel. Positive = up, negative = down.

    If duration_s is provided, the requested clicks are spread over that
    duration in single-tick increments — a "smooth" scroll. Default is the
    classic instant scroll for backwards compatibility.
    """
    if x is not None and y is not None:
        _animate_virtual(int(x), int(y), _duration(None))
    vx, vy = state.get_virtual_cursor()
    total = int(clicks)

    if duration_s is not None and duration_s > 0 and abs(total) > 1:
        step_sign = 1 if total > 0 else -1
        n = abs(total)
        per_step = duration_s / n
        if use_real_cursor:
            user_pos = _save_real_pos()
            try:
                _snap_real(vx, vy)
                for _ in range(n):
                    pyautogui.scroll(step_sign)
                    time.sleep(per_step)
            finally:
                _restore_real(*user_pos)
            return {"clicks": total, "method": "real-cursor", "smooth": True, "ok": True}
        last = None
        for _ in range(n):
            last = winapi.post_scroll(vx, vy, step_sign)
            time.sleep(per_step)
        r = last or {"ok": True}
        r["clicks"] = total
        r["method"] = "postmessage"
        r["smooth"] = True
        return r

    if use_real_cursor:
        user_pos = _save_real_pos()
        try:
            _snap_real(vx, vy)
            pyautogui.scroll(total)
        finally:
            _restore_real(*user_pos)
        return {"clicks": total, "method": "real-cursor", "ok": True}
    r = winapi.post_scroll(vx, vy, total)
    r["method"] = "postmessage"
    return r
