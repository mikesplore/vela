import base64

import pytest

from app.services.assistant.images import (
    RELAY_SAFE_BASE64_LEN,
    compress_png_for_transmission,
    extract_image_payload,
    prepare_client_image_base64,
)
from app.services.assistant import tool_exec


def test_prepare_client_image_base64_keeps_small_payload():
    small = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 100).decode("ascii")
    prepared, content_type = prepare_client_image_base64(small)
    assert prepared == small
    assert content_type == "image/png"


def test_compress_png_for_transmission_targets_relay_limit(monkeypatch):
    from io import BytesIO

    from PIL import Image, ImageDraw

    monkeypatch.setattr("app.services.assistant.images.RELAY_SAFE_BASE64_LEN", 50_000)
    base = Image.new("RGB", (400, 400), (10, 20, 30))
    draw = ImageDraw.Draw(base)
    for row in range(400):
        draw.line([(0, row), (399, row)], fill=(row % 256, (row * 2) % 256, (row * 3) % 256))
    big = base.resize((4800, 2700), Image.Resampling.NEAREST)
    buf = BytesIO()
    big.save(buf, format="PNG")
    large = base64.b64encode(buf.getvalue()).decode("ascii")
    assert len(large) > 50_000

    compressed, content_type = compress_png_for_transmission(buf.getvalue(), max_base64_len=50_000)
    assert content_type == "image/jpeg"
    assert len(base64.b64encode(compressed)) <= 50_000
    assert compressed.startswith(b"\xff\xd8")


def test_extract_image_payload_finds_screenshot_among_multiple_tools():
    payload = extract_image_payload([
        {"tool": "get_battery", "result": {"percent": 80}, "error": None},
        {"tool": "display_screenshot", "result": {"image_base64": "UE5HREFUQQ=="}, "error": None},
    ])
    assert payload is not None
    assert payload[0] == "Screenshot"
    assert payload[1] == "UE5HREFUQQ=="


def test_download_image_payload_wrapper():
    payload = tool_exec.download_image_payload([
        {
            "tool": "download_file",
            "result": {"path": "/tmp/x.png", "is_image": True, "image_base64": "UE5H"},
            "error": None,
        }
    ])
    assert payload == ("x.png", "UE5H")
