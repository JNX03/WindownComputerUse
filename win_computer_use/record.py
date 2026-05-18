"""Screen recording via mss + imageio-ffmpeg.

A worker thread grabs frames at the requested fps and pipes them to ffmpeg.
record_screen_start() returns immediately; record_screen_stop() finalizes the mp4.
"""
from __future__ import annotations
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

import mss
from PIL import Image

from .announce import announced
from . import permission


_state: dict = {"thread": None, "stop": False, "proc": None, "path": None, "started_at": None}
_lock = threading.Lock()


def _ffmpeg_bin() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def _worker(path: str, fps: int, monitor_index: int) -> None:
    with mss.mss() as sct:
        mon = sct.monitors[monitor_index]
        w, h = mon["width"], mon["height"]
        # ffmpeg cmdline: read rawvideo from stdin, write mp4.
        ffmpeg = _ffmpeg_bin()
        cmd = [
            ffmpeg,
            "-y",
            "-loglevel", "error",
            "-f", "rawvideo",
            "-pix_fmt", "bgra",
            "-s", f"{w}x{h}",
            "-r", str(fps),
            "-i", "-",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "veryfast",
            path,
        ]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _state["proc"] = proc
        interval = 1.0 / max(1, fps)
        t_next = time.time()
        try:
            while not _state["stop"]:
                t_next += interval
                raw = sct.grab(mon)
                # raw.bgra is bytes in BGRA order which matches ffmpeg bgra pix_fmt.
                try:
                    proc.stdin.write(raw.bgra)
                except BrokenPipeError:
                    break
                sleep_left = t_next - time.time()
                if sleep_left > 0:
                    time.sleep(sleep_left)
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()


@announced("record_screen_start", gated=False)
def record_screen_start(path: Optional[str] = None, fps: int = 10, monitor_index: int = 1) -> dict:
    with _lock:
        if _state["thread"] and _state["thread"].is_alive():
            return {"ok": False, "error": "already recording", "path": _state["path"]}
        if not path:
            ts = time.strftime("%Y%m%d-%H%M%S")
            target_dir = permission.CONFIG_DIR / "recordings"
            target_dir.mkdir(parents=True, exist_ok=True)
            path = str(target_dir / f"capture-{ts}.mp4")
        else:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        _state.update({"stop": False, "path": path, "started_at": time.time()})
        t = threading.Thread(target=_worker, args=(path, fps, monitor_index), daemon=True)
        _state["thread"] = t
        t.start()
        return {"ok": True, "path": path, "fps": fps, "monitor_index": monitor_index}


@announced("record_screen_stop", gated=False)
def record_screen_stop() -> dict:
    with _lock:
        t = _state.get("thread")
        if not t or not t.is_alive():
            return {"ok": False, "error": "not recording"}
        _state["stop"] = True
    t.join(timeout=15)
    return {
        "ok": True,
        "path": _state.get("path"),
        "elapsed_s": round(time.time() - (_state.get("started_at") or time.time()), 2),
    }
