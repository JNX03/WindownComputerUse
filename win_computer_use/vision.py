"""Vision: screenshots, window enumeration, cursor position."""
from __future__ import annotations
import base64
import io
from typing import Optional

import mss
from PIL import Image
import pyautogui
import pygetwindow as gw

from . import permission
from .announce import announced


def _downscale(img: Image.Image, max_dim: int) -> tuple[Image.Image, float]:
    w, h = img.size
    longest = max(w, h)
    if longest <= max_dim:
        return img, 1.0
    scale = max_dim / longest
    new_size = (int(w * scale), int(h * scale))
    return img.resize(new_size, Image.LANCZOS), scale


def _encode_png(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


@announced("screenshot", gated=False)
def screenshot(monitor_index: int = 0) -> dict:
    """Full-screen capture. monitor_index 0 = full virtual desktop."""
    cfg = permission.load_config()
    with mss.mss() as sct:
        mon = sct.monitors[monitor_index]
        raw = sct.grab(mon)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    full_w, full_h = img.size
    img_small, scale = _downscale(img, cfg["max_screenshot_dim"])
    return {
        "image_base64": _encode_png(img_small),
        "mime_type": "image/png",
        "full_width": full_w,
        "full_height": full_h,
        "scaled_width": img_small.size[0],
        "scaled_height": img_small.size[1],
        "scale": scale,
        "monitor_origin": {"x": mon["left"], "y": mon["top"]},
        "monitor_index": monitor_index,
    }


@announced("screenshot_region", gated=False)
def screenshot_region(x: int, y: int, w: int, h: int) -> dict:
    cfg = permission.load_config()
    with mss.mss() as sct:
        raw = sct.grab({"left": x, "top": y, "width": w, "height": h})
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    img_small, scale = _downscale(img, cfg["max_screenshot_dim"])
    return {
        "image_base64": _encode_png(img_small),
        "mime_type": "image/png",
        "full_width": w,
        "full_height": h,
        "scaled_width": img_small.size[0],
        "scaled_height": img_small.size[1],
        "scale": scale,
        "region": {"x": x, "y": y, "w": w, "h": h},
    }


@announced("list_monitors", gated=False)
def list_monitors() -> list[dict]:
    with mss.mss() as sct:
        return [
            {
                "index": i,
                "left": m["left"],
                "top": m["top"],
                "width": m["width"],
                "height": m["height"],
                "is_virtual": i == 0,
            }
            for i, m in enumerate(sct.monitors)
        ]


@announced("list_windows", gated=False)
def list_windows(only_visible: bool = True) -> list[dict]:
    out = []
    for w in gw.getAllWindows():
        if not w.title:
            continue
        if only_visible and (w.width <= 0 or w.height <= 0):
            continue
        try:
            out.append(
                {
                    "title": w.title,
                    "x": w.left,
                    "y": w.top,
                    "w": w.width,
                    "h": w.height,
                    "minimized": w.isMinimized,
                    "maximized": w.isMaximized,
                    "active": w.isActive,
                }
            )
        except Exception:
            continue
    return out


@announced("get_cursor_position", gated=False)
def get_cursor_position() -> dict:
    p = pyautogui.position()
    return {"x": int(p.x), "y": int(p.y)}
