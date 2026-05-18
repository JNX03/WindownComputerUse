"""Run a list of tool calls sequentially with optional waits.

Step shape:
    { "tool": "mouse_move", "args": {"x": 100, "y": 200}, "wait_ms": 500 }
"""
from __future__ import annotations
import time
from typing import Any

from .announce import announced
from . import (
    keyboard_io,
    mouse,
    system as sys_tools,
    vision,
    window as win_tools,
    ocr,
)


_TOOL_TABLE: dict[str, Any] = {
    "mouse_move": mouse.mouse_move,
    "mouse_click": mouse.mouse_click,
    "mouse_double_click": mouse.mouse_double_click,
    "mouse_drag": mouse.mouse_drag,
    "mouse_scroll": mouse.mouse_scroll,
    "keyboard_type": keyboard_io.keyboard_type,
    "keyboard_press": keyboard_io.keyboard_press,
    "keyboard_hotkey": keyboard_io.keyboard_hotkey,
    "keyboard_key_down": keyboard_io.keyboard_key_down,
    "keyboard_key_up": keyboard_io.keyboard_key_up,
    "launch_app": win_tools.launch_app,
    "focus_window": win_tools.focus_window,
    "open_file": win_tools.open_file,
    "volume_set": sys_tools.volume_set,
    "volume_mute": sys_tools.volume_mute,
    "wait": sys_tools.wait,
    "wait_seconds": sys_tools.wait,
    "clipboard_set": sys_tools.clipboard_set,
    "screenshot": vision.screenshot,
    "find_text_on_screen": ocr.find_text_on_screen,
    "click_text": ocr.click_text,
}


@announced("macro_run", gated=True)
def macro_run(steps: list[dict]) -> dict:
    results: list[dict] = []
    for i, step in enumerate(steps):
        tool = step.get("tool")
        args = step.get("args", {}) or {}
        fn = _TOOL_TABLE.get(tool)
        if not fn:
            results.append({"step": i, "tool": tool, "ok": False, "error": "unknown tool"})
            return {"ok": False, "results": results, "failed_at": i}
        try:
            r = fn(**args) if isinstance(args, dict) else fn(*args)
            results.append({"step": i, "tool": tool, "ok": True, "result": r})
        except Exception as e:
            results.append({"step": i, "tool": tool, "ok": False, "error": str(e)})
            return {"ok": False, "results": results, "failed_at": i}
        wait_ms = int(step.get("wait_ms", 0) or 0)
        if wait_ms > 0:
            time.sleep(wait_ms / 1000.0)
    return {"ok": True, "results": results, "count": len(results)}
