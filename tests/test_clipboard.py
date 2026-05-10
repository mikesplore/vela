import pytest

from auth import create_access_token
from routers import clipboard as clipboard_module


@pytest.mark.anyio
async def test_clipboard_read_write_clear(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    clipboard_state = {"text": ""}

    def fake_copy(text):
        clipboard_state["text"] = text

    def fake_paste():
        return clipboard_state["text"]

    monkeypatch.setattr(clipboard_module.pyperclip, "copy", fake_copy)
    monkeypatch.setattr(clipboard_module.pyperclip, "paste", fake_paste)

    write_response = await async_client.post(
        "/clipboard/write",
        json={"text": "test text"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert write_response.status_code == 200
    assert write_response.json()["success"] is True

    read_response = await async_client.get(
        "/clipboard/read",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert read_response.status_code == 200
    assert read_response.json()["text"] == "test text"

    clear_response = await async_client.post(
        "/clipboard/clear",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["success"] is True
    assert clipboard_state["text"] == ""
