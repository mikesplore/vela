"""Prepare image payloads for assistant clients and relay delivery."""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any

from PIL import Image

# Keep assistant image JSON under the agent tunnel's single-frame relay limit.
RELAY_SAFE_BASE64_LEN = 240_000


def compress_png_for_transmission(
        png_bytes: bytes,
        *,
        max_base64_len: int = RELAY_SAFE_BASE64_LEN,
) -> tuple[bytes, str]:
    """Return JPEG bytes sized for single-frame relay delivery."""
    img = Image.open(BytesIO(png_bytes))
    if img.mode in {"RGBA", "P"}:
        background = Image.new("RGB", img.size, (255, 255, 255))
        foreground = img.convert("RGBA") if img.mode == "P" else img
        background.paste(foreground, mask=foreground.split()[3])
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    def _fits(data: bytes) -> bool:
        return len(base64.b64encode(data)) <= max_base64_len

    def _encode_jpeg(source: Image.Image, quality: int) -> bytes:
        buf = BytesIO()
        source.save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue()

    for quality in range(85, 34, -10):
        data = _encode_jpeg(img, quality)
        if _fits(data):
            return data, "image/jpeg"

    scale = 0.85
    while scale >= 0.25:
        resized = img.resize(
            (max(1, int(img.width * scale)), max(1, int(img.height * scale))),
            Image.Resampling.LANCZOS,
        )
        for quality in range(70, 29, -5):
            data = _encode_jpeg(resized, quality)
            if _fits(data):
                return data, "image/jpeg"
        scale -= 0.15

    thumb = img.resize((960, 540), Image.Resampling.LANCZOS)
    for quality in range(55, 24, -5):
        data = _encode_jpeg(thumb, quality)
        if _fits(data):
            return data, "image/jpeg"

    data = _encode_jpeg(thumb, 35)
    return data, "image/jpeg"


def prepare_client_image_base64(image_base64: str) -> tuple[str, str]:
    """Return relay-safe base64 and content type for client delivery."""
    if len(image_base64) <= RELAY_SAFE_BASE64_LEN:
        return image_base64, "image/png"

    raw = base64.b64decode(image_base64)
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        compressed, content_type = compress_png_for_transmission(raw)
        return base64.b64encode(compressed).decode("ascii"), content_type
    return image_base64, "application/octet-stream"


def _image_from_result(tool: str, result: dict[str, Any]) -> str | None:
    if tool == "download_file":
        if result.get("is_image") and result.get("image_base64"):
            return str(result["image_base64"])
        return None
    if tool in {"display_screenshot", "display_record", "webcam_snapshot"}:
        value = result.get("image_base64")
        return str(value) if value else None
    return None


def extract_image_payload(tool_results: list[dict[str, Any]]) -> tuple[str, str, str] | None:
    """Return (label, image_base64, content_type) from the first successful image tool."""
    for entry in tool_results:
        if entry.get("error"):
            continue
        tool = str(entry.get("tool") or "")
        result = entry.get("result") or {}
        if not isinstance(result, dict):
            continue
        image_base64 = _image_from_result(tool, result)
        if not image_base64:
            continue

        label = "Screenshot"
        if tool == "download_file":
            path = str(result.get("path") or "image")
            label = path.rsplit("/", 1)[-1] or "image"
        elif tool == "webcam_snapshot":
            label = "Webcam snapshot"

        prepared, content_type = prepare_client_image_base64(image_base64)
        return label, prepared, content_type
    return None
