"""Keyboard: type text, press keys, hotkeys."""
from __future__ import annotations
from typing import Iterable

import pyautogui
import pyperclip

from .announce import announced


def _is_ascii(text: str) -> bool:
    try:
        text.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


@announced("keyboard_type")
def keyboard_type(text: str, interval_s: float = 0.02) -> dict:
    if not text:
        return {"chars": 0, "method": "noop", "ok": True}
    if _is_ascii(text):
        pyautogui.write(text, interval=interval_s)
        return {"chars": len(text), "method": "write", "ok": True}
    # Unicode fallback: use clipboard + Ctrl+V to preserve characters.
    prev = ""
    try:
        prev = pyperclip.paste()
    except Exception:
        pass
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v")
    pyautogui.sleep(0.05)
    try:
        pyperclip.copy(prev)
    except Exception:
        pass
    return {"chars": len(text), "method": "paste", "ok": True}


@announced("keyboard_press")
def keyboard_press(key: str) -> dict:
    pyautogui.press(key)
    return {"key": key, "ok": True}


@announced("keyboard_hotkey")
def keyboard_hotkey(keys: Iterable[str]) -> dict:
    ks = list(keys)
    if not ks:
        return {"ok": False, "error": "no keys"}
    pyautogui.hotkey(*ks)
    return {"keys": ks, "ok": True}


@announced("keyboard_key_down")
def keyboard_key_down(key: str) -> dict:
    pyautogui.keyDown(key)
    return {"key": key, "down": True, "ok": True}


@announced("keyboard_key_up")
def keyboard_key_up(key: str) -> dict:
    pyautogui.keyUp(key)
    return {"key": key, "up": True, "ok": True}
