"""OCR via Windows.Media.Ocr (WinRT). Returns screen-space coordinates."""
from __future__ import annotations
import asyncio
import io
from typing import Optional

from PIL import Image

from .announce import announced
from . import vision


def _get_engine():
    from winrt.windows.globalization import Language
    from winrt.windows.media.ocr import OcrEngine

    eng = OcrEngine.try_create_from_user_profile_languages()
    if eng is None:
        # Force English if no user-profile recognizer is installed.
        eng = OcrEngine.try_create_from_language(Language("en-US"))
    return eng


async def _ocr_pil_image(img: Image.Image) -> list[dict]:
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.storage.streams import (
        DataWriter,
        InMemoryRandomAccessStream,
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream.get_output_stream_at(0))
    writer.write_bytes(data)
    await writer.store_async()
    await writer.flush_async()
    writer.detach_stream()
    stream.seek(0)

    decoder = await BitmapDecoder.create_async(stream)
    bmp = await decoder.get_software_bitmap_async()

    eng = _get_engine()
    if eng is None:
        raise RuntimeError("Windows OCR engine not available")
    result = await eng.recognize_async(bmp)

    out: list[dict] = []
    for line in result.lines:
        for word in line.words:
            r = word.bounding_rect
            out.append(
                {
                    "text": word.text,
                    "x": int(r.x),
                    "y": int(r.y),
                    "w": int(r.width),
                    "h": int(r.height),
                }
            )
        # also push the full-line text with combined bbox
        if line.words:
            xs = [w.bounding_rect.x for w in line.words]
            ys = [w.bounding_rect.y for w in line.words]
            xe = [w.bounding_rect.x + w.bounding_rect.width for w in line.words]
            ye = [w.bounding_rect.y + w.bounding_rect.height for w in line.words]
            out.append(
                {
                    "text": line.text,
                    "x": int(min(xs)),
                    "y": int(min(ys)),
                    "w": int(max(xe) - min(xs)),
                    "h": int(max(ye) - min(ys)),
                    "is_line": True,
                }
            )
    return out


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # In rare cases (Jupyter, server eventloop), run nested.
            import nest_asyncio  # type: ignore

            nest_asyncio.apply()
            return loop.run_until_complete(coro)
    except RuntimeError:
        pass
    return asyncio.run(coro)


def _capture_region(region: Optional[dict]) -> tuple[Image.Image, tuple[int, int]]:
    """Returns (PIL image, (origin_x, origin_y))."""
    if region:
        x = int(region["x"])
        y = int(region["y"])
        w = int(region["w"])
        h = int(region["h"])
        shot = vision.screenshot_region(x, y, w, h)
        origin = (x, y)
    else:
        shot = vision.screenshot(0)
        origin = (shot["monitor_origin"]["x"], shot["monitor_origin"]["y"])
    import base64

    raw = base64.b64decode(shot["image_base64"])
    img = Image.open(io.BytesIO(raw))
    # If the screenshot was downscaled we need to scale OCR boxes back; record scale.
    scale = float(shot.get("scale", 1.0))
    return img, origin, scale  # type: ignore[return-value]


@announced("find_text_on_screen", gated=False)
def find_text_on_screen(text: str, region: Optional[dict] = None) -> dict:
    """Return all OCR matches for `text` (case-insensitive substring)."""
    img, origin, scale = _capture_region(region)  # type: ignore[misc]
    try:
        words = _run_async(_ocr_pil_image(img))
    except Exception as e:
        return {"ok": False, "error": f"OCR failed: {e}"}
    needle = (text or "").strip().lower()
    matches = []
    for w in words:
        if needle and needle in w["text"].lower():
            # Scale boxes back to screen coords
            sx = int(w["x"] / scale) + origin[0]
            sy = int(w["y"] / scale) + origin[1]
            sw = int(w["w"] / scale)
            sh = int(w["h"] / scale)
            matches.append({
                "text": w["text"],
                "x": sx,
                "y": sy,
                "w": sw,
                "h": sh,
                "is_line": w.get("is_line", False),
            })
    return {"ok": True, "query": text, "count": len(matches), "matches": matches}


@announced("click_text")
def click_text(text: str, button: str = "left", region: Optional[dict] = None) -> dict:
    """Find `text` via OCR and click the first match's center."""
    from . import mouse

    res = find_text_on_screen(text, region=region)
    if not res.get("ok"):
        return res
    matches = res.get("matches", [])
    if not matches:
        return {"ok": False, "error": f"text '{text}' not found on screen"}
    # Prefer word matches over line matches for cleaner targets.
    word_matches = [m for m in matches if not m.get("is_line")]
    m = (word_matches or matches)[0]
    cx = m["x"] + m["w"] // 2
    cy = m["y"] + m["h"] // 2
    mouse.mouse_click(cx, cy, button=button)
    return {"ok": True, "clicked": {"x": cx, "y": cy}, "match": m}
