"""Labeled cursor overlay — runs as its own process.

A click-through, always-on-top tkinter window that draws a colored ring around
the AI's *virtual* cursor and shows the agent's name. Reads
%USERPROFILE%/.win_computer_use/state.json every 50ms.

Default lifecycle: stay alive as long as the heartbeat in state.json is fresh
(<5 minutes old). Pass --watch-parent-pid <pid> to bind lifetime to a parent
process instead.

Run standalone:
    py -3.12 -m win_computer_use.overlay
    py -3.12 -m win_computer_use.overlay --watch-parent-pid 12345
"""
from __future__ import annotations
import argparse
import math
import os
import sys
import time
import tkinter as tk
from collections import deque
from pathlib import Path
from typing import Optional

# DPI awareness must be set BEFORE Tk() so widget coords match cursor coords.
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import pyautogui  # noqa  (after DPI set)

from . import permission, state


TRANSPARENT_KEY = "magenta"

# Arrow polygon — vertices in canvas pixels with the tip at (0,0), pointing NW.
# Scaled up ~1.8x from the classic Windows arrow proportions for visibility.
ARROW = [
    (0, 0),      # tip
    (0, 30),     # left edge going down
    (8, 24),     # bend
    (13, 36),   # bottom-right of stem
    (19, 33),   # stem bottom inner
    (13, 22),   # stem top inner
    (24, 22),   # right edge of head
]
ARROW_OUTLINE = "#0F172A"
ARROW_OUTLINE_WIDTH = 2.5
LABEL_PADDING_X = 12
LABEL_PADDING_Y = 5
LABEL_FONT = ("Segoe UI", 11, "bold")
WINDOW_W = 320
WINDOW_H = 96
# Arrow tip sits near the top-left corner — like a real OS cursor — with the
# label chip extending to the right.
TIP_X = 18
TIP_Y = 18
# Trail tracking is retained for diagnostics but nothing is rendered.
TRAIL_LENGTH = 8

# How long since the last heartbeat before we consider the server gone, in seconds.
HEARTBEAT_GRACE_S = 300


def _make_click_through(hwnd: int) -> None:
    import ctypes
    from ctypes import wintypes

    GWL_EXSTYLE = -20
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_NOACTIVATE = 0x08000000

    user32 = ctypes.windll.user32
    GetWindowLongW = user32.GetWindowLongW
    SetWindowLongW = user32.SetWindowLongW
    GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    GetWindowLongW.restype = ctypes.c_long
    SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    SetWindowLongW.restype = ctypes.c_long

    style = GetWindowLongW(hwnd, GWL_EXSTYLE) or 0
    style |= WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
    SetWindowLongW(hwnd, GWL_EXSTYLE, style)


def _pid_alive(pid: int) -> bool:
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not h:
        return False
    exit_code = ctypes.c_ulong(0)
    ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
    ctypes.windll.kernel32.CloseHandle(h)
    if not ok:
        return False
    return exit_code.value == 259  # STILL_ACTIVE


def _toplevel_hwnd(tk_root: tk.Tk) -> int:
    import ctypes
    h = tk_root.winfo_id()
    return ctypes.windll.user32.GetAncestor(h, 2)  # GA_ROOT


def _parse_iso(ts: str) -> Optional[float]:
    if not ts:
        return None
    # Accept "...Z" by replacing with +00:00
    s = ts.replace("Z", "+00:00")
    try:
        from datetime import datetime, timezone
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return None


class CursorOverlay:
    def __init__(self, watch_pid: Optional[int] = None) -> None:
        self.watch_pid = watch_pid

        self.root = tk.Tk()
        self.root.title("WinCU Overlay")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.root.geometry(f"{WINDOW_W}x{WINDOW_H}+0+0")
        self.root.configure(bg=TRANSPARENT_KEY)

        self.canvas = tk.Canvas(
            self.root,
            width=WINDOW_W,
            height=WINDOW_H,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill="both", expand=True)

        self._agent_name = "Claude"
        self._cursor_color = "#FE6E58"
        self._text_color = "#FFFFFF"
        self._visible = True
        self._pressed = False
        self._last_x: Optional[int] = None
        self._last_y: Optional[int] = None
        self._trail: deque[tuple[int, int]] = deque(maxlen=TRAIL_LENGTH)
        # Cursor sprite rotation. Target comes from the position file; rendered
        # angle eases toward it (HTML-style shortest-arc interpolation).
        self._target_angle = 0.0
        self._current_angle = 0.0
        self._last_tick_ts = time.time()
        # Two-stage fade / wake state.
        self._last_motion_ts = time.time()
        # Window alpha — smoothly approaches target.
        self._current_alpha = 1.0
        self._target_alpha = 1.0
        # Cursor scale (1.0 = full size; shrinks during cursor stage of fade).
        self._current_scale = 1.0
        self._target_scale = 1.0
        # Label visibility 0..1 — also drives chip width and arrow.
        self._current_label = 1.0
        self._target_label = 1.0
        # Configurable thresholds.
        self._label_hide_after_s = 5.0
        self._cursor_hide_after_s = 15.0
        self._fade_duration_s = 1.5
        self._wake_duration_s = 0.4

        self.root.after_idle(self._enable_click_through)
        self._redraw()

        # Position tick at ~60 Hz so a 250ms animation produces ~15 visible
        # frames instead of 6. State tick (config / heartbeat / agent name)
        # is much slower because it almost never changes.
        self.root.after(16, self._tick_position)
        self.root.after(200, self._tick_state)

    # ------------------------------------------------------------------ render
    def _redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        if not self._visible:
            return

        # ---- no trail ------------------------------------------------------
        # The previous polyline trail has been removed at the user's request.
        # The trail buffer still records recent points for potential future use
        # but nothing is rendered.

        # ---- arrow cursor --------------------------------------------------
        # Scale polygon vertices toward the tip so the cursor visually shrinks
        # during the second fade stage, then rotate them around the tip by the
        # current sprite angle so the arrow tilts with motion direction.
        scale = max(0.0, self._current_scale)
        cos_a = math.cos(self._current_angle)
        sin_a = math.sin(self._current_angle)
        verts: list[float] = []
        for vx, vy in ARROW:
            sx, sy = vx * scale, vy * scale
            rx = sx * cos_a - sy * sin_a
            ry = sx * sin_a + sy * cos_a
            verts.extend([TIP_X + rx, TIP_Y + ry])

        # Hide the arrow entirely once it's essentially gone.
        draw_arrow = scale > 0.05
        if draw_arrow:
            # White halo for contrast.
            c.create_polygon(
                verts,
                fill="#FFFFFF",
                outline="#FFFFFF",
                width=max(1.0, (ARROW_OUTLINE_WIDTH + 3) * scale),
                smooth=False,
                joinstyle="round",
            )
            # The arrow itself.
            c.create_polygon(
                verts,
                fill=self._cursor_color,
                outline=ARROW_OUTLINE,
                width=max(0.6, ARROW_OUTLINE_WIDTH * scale),
                smooth=False,
                joinstyle="round",
            )

        # Pressed ripple — only when pressed and visible.
        if self._pressed and draw_arrow:
            for i, rad in enumerate((10, 16, 22)):
                r = rad * scale
                c.create_oval(
                    TIP_X - r, TIP_Y - r,
                    TIP_X + r, TIP_Y + r,
                    outline=self._cursor_color,
                    width=2 - i // 2 if i < 2 else 1,
                )

        # ---- label chip ----------------------------------------------------
        # Only draw chip if its visibility is meaningful AND the arrow is still
        # visible enough to attach to.
        label_vis = max(0.0, min(1.0, self._current_label))
        if label_vis > 0.05 and draw_arrow:
            text = self._agent_name or "Agent"
            tmp = c.create_text(0, 0, text=text, font=LABEL_FONT, anchor="nw")
            bbox = c.bbox(tmp)
            c.delete(tmp)
            if bbox:
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
            else:
                tw, th = 80, 16

            # Chip shrinks horizontally as label_vis decreases (fade-by-collapse).
            # We keep height stable so it still looks like a pill mid-fade.
            chip_x = TIP_X + int(30 * scale)
            chip_y = TIP_Y + int(6 * scale)
            full_chip_w = tw + LABEL_PADDING_X * 2
            chip_w = max(int(th * 1.2), int(full_chip_w * label_vis))
            chip_h = th + LABEL_PADDING_Y * 2
            radius = chip_h // 2

            # Rounded pill background (clipped width as we shrink).
            c.create_oval(chip_x, chip_y, chip_x + chip_h, chip_y + chip_h, fill=self._cursor_color, outline="")
            c.create_oval(
                chip_x + chip_w - chip_h, chip_y,
                chip_x + chip_w, chip_y + chip_h,
                fill=self._cursor_color, outline="",
            )
            c.create_rectangle(
                chip_x + radius, chip_y,
                chip_x + chip_w - radius, chip_y + chip_h,
                fill=self._cursor_color, outline="",
            )
            # Text drawn only while pill still wider than text — otherwise the
            # collapsing pill swallows the letters cleanly.
            if chip_w > tw + 4:
                c.create_text(
                    chip_x + chip_w / 2, chip_y + chip_h / 2,
                    text=text, fill=self._text_color, font=LABEL_FONT,
                )

    # ---------------------------------------------------------------- ticking
    def _tick_position(self) -> None:
        try:
            # Prefer the lightweight cursor_pos.txt — written by the server's
            # animation loop without the JSON overhead. If this transient read
            # fails (writer holds the file for ~0.4 ms during a write), reuse
            # the previous tick's value instead of falling back to state.json
            # — falling back would snap to the stale post-animation position
            # and produce the visual "teleport" the user saw.
            pos = state.read_cursor_pos()
            if pos is not None:
                x, y, target_angle, pressed = pos
            elif self._last_x is not None:
                x, y = self._last_x, self._last_y
                target_angle, pressed = self._target_angle, self._pressed
            else:
                s = state.load()
                x = int(s.get("virtual_cursor_x", 0))
                y = int(s.get("virtual_cursor_y", 0))
                target_angle = float(s.get("virtual_cursor_angle_rad", 0.0))
                pressed = bool(s.get("virtual_cursor_pressed", False))
            self._target_angle = float(target_angle)
            moved = (self._last_x is None) or (x != self._last_x) or (y != self._last_y)
            self._last_x, self._last_y = x, y

            self.root.geometry(f"+{x - TIP_X}+{y - TIP_Y}")

            if moved:
                self._trail.append((x, y))
                self._last_motion_ts = time.time()
                self._target_alpha = 1.0
                self._target_scale = 1.0
                self._target_label = 1.0
            else:
                if self._trail and (time.time() - self._last_motion_ts) > 0.15:
                    n = 2 if len(self._trail) > 30 else 1
                    for _ in range(n):
                        if self._trail:
                            self._trail.popleft()

            if pressed != self._pressed:
                self._pressed = pressed

            # ---- Two-stage hide targets ---------------------------------
            # Hide phases (driven by idle time since last cursor motion):
            #   1. Label chip fades + collapses to a dot.
            #   2. The cursor *blooms* briefly to ~115% scale ("attention
            #      grab") then shrinks to 0 while window alpha fades to 0.
            # Both the bloom and the shrink/alpha curve use a cubic ease-in-
            # out for a more polished feel than the previous linear ramp.
            now = time.time()
            idle = now - self._last_motion_ts
            fade = max(0.1, self._fade_duration_s)
            bloom_dur = min(0.25, fade * 0.20)  # brief — ~20% of the fade

            def ease_in_out(p: float) -> float:
                # Smootherstep: 6p^5 - 15p^4 + 10p^3. Zero first and second
                # derivatives at endpoints — visually softer than cubic.
                p = max(0.0, min(1.0, p))
                return p * p * p * (p * (p * 6 - 15) + 10)

            # Stage 1 — label/chip
            t1 = self._label_hide_after_s
            if t1 > 0 and not pressed:
                if idle < t1:
                    self._target_label = 1.0
                elif idle < t1 + fade:
                    self._target_label = 1.0 - ease_in_out((idle - t1) / fade)
                else:
                    self._target_label = 0.0
            else:
                self._target_label = 1.0

            # Stage 2 — cursor bloom + shrink + alpha
            t2 = self._cursor_hide_after_s
            if t2 > 0 and not pressed:
                if idle < t2:
                    self._target_scale = 1.0
                    self._target_alpha = 1.0
                elif idle < t2 + bloom_dur:
                    # Brief bloom up to 1.15x — small "I'm going away" cue.
                    b = ease_in_out((idle - t2) / bloom_dur)
                    self._target_scale = 1.0 + 0.15 * b
                    self._target_alpha = 1.0
                elif idle < t2 + bloom_dur + fade:
                    # Shrink fully to 0 and fade window alpha to 0.
                    p = ease_in_out((idle - t2 - bloom_dur) / fade)
                    self._target_scale = 1.15 - 1.15 * p
                    self._target_alpha = 1.0 - p
                else:
                    self._target_scale = 0.0
                    self._target_alpha = 0.0
            else:
                self._target_scale = 1.0
                self._target_alpha = 1.0

            # ---- Smooth-easing the *rendered* values toward their targets.
            # Critically-damped 1st-order filter: cur += (tgt-cur) * (1-exp(-dt/τ)).
            # Wake (τ_up) is short so the cursor pops back fast; fade settle
            # (τ_dn) is longer for a graceful hide.
            dt = 0.016  # matches the 16ms position tick below
            wake = max(0.05, self._wake_duration_s)
            tau_up = wake * 0.35
            tau_dn = fade * 0.35
            ease_up = 1.0 - math.exp(-dt / tau_up) if tau_up > 0 else 1.0
            ease_dn = 1.0 - math.exp(-dt / tau_dn) if tau_dn > 0 else 1.0

            def approach(cur: float, tgt: float) -> float:
                if abs(cur - tgt) < 0.002:
                    return tgt
                k = ease_up if tgt > cur else ease_dn
                return cur + (tgt - cur) * k

            new_alpha = approach(self._current_alpha, self._target_alpha)
            new_scale = approach(self._current_scale, self._target_scale)
            new_label = approach(self._current_label, self._target_label)

            # Shortest-arc rotation easing. Use a faster rate while actively
            # moving (snappy follow), slower when idle (gentle settle to rest).
            now = time.time()
            tick_dt = max(0.001, now - self._last_tick_ts)
            self._last_tick_ts = now
            rate = 18.0 if moved else 6.0
            diff = self._target_angle - self._current_angle
            while diff > math.pi:
                diff -= 2.0 * math.pi
            while diff < -math.pi:
                diff += 2.0 * math.pi
            self._current_angle = self._current_angle + diff * min(1.0, tick_dt * rate)

            self._current_alpha = new_alpha
            self._current_scale = new_scale
            self._current_label = new_label

            try:
                self.root.attributes("-alpha", new_alpha)
            except Exception:
                pass

            # Cheap redraw — needed every tick so trail decay and scale/label
            # transitions remain smooth.
            self._redraw()
        except Exception:
            pass
        self.root.after(16, self._tick_position)

    def _tick_state(self) -> None:
        try:
            s = state.load()
        except Exception:
            s = {}

        # Lifecycle: either watch a specific parent PID or watch the heartbeat freshness.
        if self.watch_pid is not None:
            if not _pid_alive(self.watch_pid):
                self.root.after(50, self.root.destroy)
                return
        else:
            hb = _parse_iso(s.get("heartbeat_at") or "")
            if hb is not None and (time.time() - hb) > HEARTBEAT_GRACE_S:
                self.root.after(50, self.root.destroy)
                return

        # Refresh fade-stage config (so Settings can tweak it live).
        try:
            cfg = permission.load_config()
            self._label_hide_after_s = float(cfg.get("label_hide_after_s", 5.0))
            self._cursor_hide_after_s = float(cfg.get("cursor_auto_hide_after_s", 15.0))
            self._fade_duration_s = float(cfg.get("cursor_fade_duration_s", 1.5))
            self._wake_duration_s = float(cfg.get("cursor_wake_duration_s", 0.4))
        except Exception:
            pass

        # Apply visuals
        name = s.get("agent_name") or "Agent"
        color = s.get("cursor_color") or "#FE6E58"
        enabled = bool(s.get("overlay_enabled", True))

        if (name != self._agent_name) or (color != self._cursor_color) or (enabled != self._visible):
            self._agent_name = name
            self._cursor_color = color
            self._visible = enabled
            if enabled:
                self.root.deiconify()
            else:
                self.root.withdraw()
            self._redraw()

        self.root.after(200, self._tick_state)

    def _enable_click_through(self) -> None:
        try:
            hwnd = _toplevel_hwnd(self.root)
            _make_click_through(hwnd)
        except Exception as e:
            print(f"[overlay] click-through setup failed: {e}", file=sys.stderr)

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--watch-parent-pid",
        type=int,
        default=None,
        help="If set, exit when this PID disappears. Otherwise watch heartbeat freshness.",
    )
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="Synonym for not setting --watch-parent-pid.",
    )
    args = parser.parse_args()

    state.patch(overlay_subprocess_pid=os.getpid())
    pid = args.watch_parent_pid if not args.standalone else None
    CursorOverlay(watch_pid=pid).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
