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

from . import state


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
WINDOW_W = 360
WINDOW_H = 80
TRAIL_LENGTH = 10
TRAIL_DOT_R = 4
# Position of the arrow tip inside the overlay window.
TIP_X = 14
TIP_Y = 14

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
        self._cursor_color = "#3B82F6"
        self._text_color = "#FFFFFF"
        self._visible = True
        self._pressed = False
        self._last_x: Optional[int] = None
        self._last_y: Optional[int] = None
        # Trail of recent (x, y) positions, oldest first.
        self._trail: deque[tuple[int, int]] = deque(maxlen=TRAIL_LENGTH)

        self.root.after_idle(self._enable_click_through)
        self._redraw()

        # Position tick is fast so motion looks smooth; state tick is slower.
        self.root.after(40, self._tick_position)
        self.root.after(200, self._tick_state)

    # ------------------------------------------------------------------ render
    def _redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        if not self._visible:
            return

        # ---- trail dots behind the arrow (so motion is unmistakable) -------
        if self._last_x is not None and len(self._trail) > 1:
            for idx, (tx, ty) in enumerate(list(self._trail)[:-1]):
                local_x = tx - self._last_x + TIP_X
                local_y = ty - self._last_y + TIP_Y
                if not (0 <= local_x <= WINDOW_W and 0 <= local_y <= WINDOW_H):
                    continue
                age = (len(self._trail) - idx) / len(self._trail)
                rr = TRAIL_DOT_R * (1.0 - age * 0.65)
                c.create_oval(
                    local_x - rr, local_y - rr, local_x + rr, local_y + rr,
                    fill=self._cursor_color, outline="",
                )

        # ---- arrow cursor --------------------------------------------------
        # Build the polygon translated so the tip sits at (TIP_X, TIP_Y).
        verts: list[float] = []
        for vx, vy in ARROW:
            verts.extend([TIP_X + vx, TIP_Y + vy])

        # 1) White halo for contrast on dark backgrounds — drawn slightly
        #    fatter than the colored arrow on top.
        c.create_polygon(
            verts,
            fill="#FFFFFF",
            outline="#FFFFFF",
            width=ARROW_OUTLINE_WIDTH + 3,
            smooth=False,
            joinstyle="round",
        )

        # 2) The arrow itself — colored fill + dark outline so it pops on
        #    any background.
        c.create_polygon(
            verts,
            fill=self._cursor_color,
            outline=ARROW_OUTLINE,
            width=ARROW_OUTLINE_WIDTH,
            smooth=False,
            joinstyle="round",
        )

        # 3) Pressed ripple — small expanding ring around the tip when clicking.
        if self._pressed:
            for i, rad in enumerate((10, 16, 22)):
                c.create_oval(
                    TIP_X - rad, TIP_Y - rad,
                    TIP_X + rad, TIP_Y + rad,
                    outline=self._cursor_color,
                    width=2 - i // 2 if i < 2 else 1,
                )

        # ---- label chip ----------------------------------------------------
        text = self._agent_name or "Agent"
        tmp = c.create_text(0, 0, text=text, font=LABEL_FONT, anchor="nw")
        bbox = c.bbox(tmp)
        c.delete(tmp)
        if bbox:
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        else:
            tw, th = 80, 16

        chip_x = TIP_X + 30  # to the right of the arrow's right edge
        chip_y = TIP_Y + 6
        chip_w = tw + LABEL_PADDING_X * 2
        chip_h = th + LABEL_PADDING_Y * 2
        radius = chip_h // 2
        # Chip with rounded ends
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
        c.create_text(
            chip_x + chip_w / 2, chip_y + chip_h / 2,
            text=text, fill=self._text_color, font=LABEL_FONT,
        )

    # ---------------------------------------------------------------- ticking
    def _tick_position(self) -> None:
        try:
            s = state.load()
            x = int(s.get("virtual_cursor_x", 0))
            y = int(s.get("virtual_cursor_y", 0))
            moved = (self._last_x is None) or (x != self._last_x) or (y != self._last_y)
            self._last_x, self._last_y = x, y

            # Move window so the arrow tip (TIP_X, TIP_Y) sits exactly at (x, y).
            self.root.geometry(f"+{x - TIP_X}+{y - TIP_Y}")

            if moved:
                self._trail.append((x, y))

            pressed = bool(s.get("virtual_cursor_pressed", False))
            if pressed != self._pressed:
                self._pressed = pressed
                self._redraw()
            elif moved:
                # Redraw only when trail changed enough to matter (every other frame).
                # Cheap to redraw the small canvas.
                self._redraw()
        except Exception:
            pass
        self.root.after(40, self._tick_position)

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

        # Apply visuals
        name = s.get("agent_name") or "Agent"
        color = s.get("cursor_color") or "#3B82F6"
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
