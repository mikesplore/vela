import base64

import pytest
from app.auth import create_access_token
from app.main import app
from app.services.assistant import tool_exec
from app.utils.config import get_config


def _auth_header() -> str:
    return f"Bearer {create_access_token({'sub': 'admin'})}"


def _allow_tmp(monkeypatch, tmp_path):
    cfg = get_config()
    monkeypatch.setattr(cfg, "allowed_base_dirs", [str(tmp_path)])


@pytest.mark.anyio
async def test_download_file_small_text_returns_content_base64(tmp_path, monkeypatch):
    _allow_tmp(monkeypatch, tmp_path)
    sample = tmp_path / "note.txt"
    sample.write_text("hello world")

    result = await tool_exec._execute_tool(
        app, "download_file", {"path": str(sample)}, _auth_header()
    )

    assert result["is_image"] is False
    assert result["size_bytes"] == 11
    assert "content_base64" in result
    assert "image_base64" not in result
    assert base64.b64decode(result["content_base64"]) == b"hello world"


@pytest.mark.anyio
async def test_download_file_image_returns_image_base64(tmp_path, monkeypatch):
    _allow_tmp(monkeypatch, tmp_path)
    png = tmp_path / "photo.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)

    result = await tool_exec._execute_tool(
        app, "download_file", {"path": str(png)}, _auth_header()
    )

    assert result["is_image"] is True
    assert result["content_type"] == "image/png"
    assert "image_base64" in result
    assert "content_base64" not in result
    assert base64.b64decode(result["image_base64"]).startswith(b"\x89PNG")


@pytest.mark.anyio
async def test_download_file_rejects_large_file(tmp_path, monkeypatch):
    _allow_tmp(monkeypatch, tmp_path)
    big = tmp_path / "big.bin"
    big.write_bytes(b"x" * 1024)

    cfg = get_config()
    monkeypatch.setattr(cfg, "assistant_max_download_bytes", 100)

    result = await tool_exec._execute_tool(
        app, "download_file", {"path": str(big)}, _auth_header()
    )

    assert result["too_large"] is True
    assert result["size_bytes"] == 1024
    assert result["max_bytes"] == 100
    assert "content_base64" not in result
    assert "image_base64" not in result
    assert "too large" in result["message"].lower()


def test_sanitize_tool_result_strips_binary():
    sanitized = tool_exec.sanitize_tool_result_for_llm(
        {
            "path": "/tmp/a.png",
            "image_base64": "AAAA",
            "content_base64": "BBBB",
            "size_bytes": 4,
        }
    )
    assert "image_base64" not in sanitized
    assert "content_base64" not in sanitized
    assert sanitized["content_omitted"] is True
    assert sanitized["size_bytes"] == 4


def test_download_image_payload_fast_path():
    payload = tool_exec.download_image_payload(
        [
            {
                "tool": "download_file",
                "result": {
                    "path": "/home/u/pic.jpg",
                    "is_image": True,
                    "image_base64": "UE5H",
                },
                "error": None,
            }
        ]
    )
    assert payload == ("pic.jpg", "UE5H")
    assert tool_exec.download_image_payload([{"tool": "list_files", "result": {}, "error": None}]) is None


@pytest.mark.anyio
async def test_assistant_returns_downloaded_image_directly(monkeypatch, async_client):
    from app.routers import assistant as assistant_router
    from app.services.assistant import helpers as assistant_helpers

    monkeypatch.setattr(assistant_router, "get_api_key", lambda: "test-key")
    monkeypatch.setattr(assistant_helpers, "get_api_key", lambda: "test-key")

    async def fake_plan(message, history=None):
        return [{"tool": "download_file", "tool_input": {"path": "/tmp/x.png"}}]

    async def fake_execute_tool_safe(app_, tool_name, tool_input, auth_header, confirmed=False):
        return {
            "tool": "download_file",
            "result": {
                "path": "/tmp/x.png",
                "is_image": True,
                "image_base64": "UE5HREFUQQ==",
                "size_bytes": 8,
            },
            "error": None,
        }

    async def boom_compose(user_message, results):
        raise AssertionError("compose_final_reply should not run for image downloads")

    monkeypatch.setattr(assistant_router, "plan_tool_calls", fake_plan)
    monkeypatch.setattr(tool_exec, "execute_tool_safe", fake_execute_tool_safe)
    monkeypatch.setattr(assistant_helpers, "compose_final_reply", boom_compose)

    response = await async_client.post(
        "/assistant/chat",
        json={"message": "download that png"},
        headers={
            "Authorization": _auth_header(),
            "X-Session-ID": "test-download-session",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"] == "Here's x.png."
    assert payload["image_base64"] == "UE5HREFUQQ=="
