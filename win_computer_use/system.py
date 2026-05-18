"""System: volume, wait, clipboard."""
from __future__ import annotations
import time
from typing import Optional

import pyperclip

from .announce import announced


def _audio_endpoint():
    # Newer pycaw (>=20240210) exposes EndpointVolume directly on the AudioDevice.
    from pycaw.pycaw import AudioUtilities

    speakers = AudioUtilities.GetSpeakers()
    return speakers.EndpointVolume


@announced("volume_set")
def volume_set(level_0_to_100: int) -> dict:
    lvl = max(0, min(100, int(level_0_to_100)))
    try:
        ep = _audio_endpoint()
        # pycaw uses scalar 0.0–1.0
        ep.SetMasterVolumeLevelScalar(lvl / 100.0, None)
        return {"ok": True, "level": lvl}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@announced("volume_get", gated=False)
def volume_get() -> dict:
    try:
        ep = _audio_endpoint()
        scalar = ep.GetMasterVolumeLevelScalar()
        muted = bool(ep.GetMute())
        return {"ok": True, "level": int(round(scalar * 100)), "muted": muted}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@announced("volume_mute")
def volume_mute(on: Optional[bool] = None) -> dict:
    try:
        ep = _audio_endpoint()
        if on is None:
            on = not bool(ep.GetMute())
        ep.SetMute(1 if on else 0, None)
        return {"ok": True, "muted": bool(on)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@announced("wait", gated=False)
def wait(seconds: float) -> dict:
    s = max(0.0, float(seconds))
    time.sleep(s)
    return {"ok": True, "slept_s": s}


@announced("clipboard_get", gated=False)
def clipboard_get() -> dict:
    try:
        return {"ok": True, "text": pyperclip.paste()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@announced("clipboard_set")
def clipboard_set(text: str) -> dict:
    try:
        pyperclip.copy(text)
        return {"ok": True, "chars": len(text)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
