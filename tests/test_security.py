import pytest
from auth import create_access_token
from routers import security as security_module


@pytest.mark.anyio
async def test_security_actions_and_history(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})

    def fake_run_command(cmd, timeout=10):
        if cmd[:2] == ["loginctl", "lock-sessions"]:
            return "", "", 0
        if cmd[:2] == ["loginctl", "terminate-user"]:
            return "", "", 0
        if cmd[:2] == ["modprobe", "-r"]:
            return "", "", 0
        if cmd[:2] == ["modprobe", "uvcvideo"]:
            return "", "", 0
        if cmd[:2] == ["pactl", "set-source-mute"]:
            return "", "", 0
        if cmd[:2] == ["last", "-n"]:
            return "user1 pts/0 192.168.1.5 Mon May 10 10:00 - 10:10 (00:10)", "", 0
        if cmd[:1] == ["who"]:
            return "user1 pts/0 2026-05-10 10:00 (192.168.1.5)", "", 0
        return "", "", 0

    def fake_run_command_bytes(cmd, timeout=10):
        return b"PNGDATA", "", 0

    monkeypatch.setattr(security_module, "_run_command", fake_run_command)
    monkeypatch.setattr(security_module, "_run_command_bytes", fake_run_command_bytes)

    lock_resp = await async_client.post(
        "/security/lock",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert lock_resp.status_code == 200
    assert lock_resp.json()["success"] is True

    logout_resp = await async_client.post(
        "/security/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_resp.status_code == 200
    assert logout_resp.json()["success"] is True

    snapshot_resp = await async_client.post(
        "/security/webcam/snapshot",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert snapshot_resp.status_code == 200
    assert snapshot_resp.json()["image_base64"] == "UE5HREFUQQ=="

    mic_disable_resp = await async_client.post(
        "/security/mic/disable",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert mic_disable_resp.status_code == 200
    assert mic_disable_resp.json()["success"] is True

    login_history_resp = await async_client.get(
        "/security/login-history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert login_history_resp.status_code == 200
    assert login_history_resp.json()["events"]

    ssh_sessions_resp = await async_client.get(
        "/security/ssh-sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ssh_sessions_resp.status_code == 200
    assert ssh_sessions_resp.json()["sessions"][0]["user"] == "user1"


@pytest.mark.anyio
async def test_security_lock_falls_back_to_user_session(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})
    username = security_module.getpass.getuser()

    def fake_run_command(cmd, timeout=10):
        if cmd[:2] == ["loginctl", "lock-sessions"]:
            return "", "Access denied", 1
        if cmd[:2] == ["loginctl", "show-user"]:
            return "c1 c2", "", 0
        if cmd[:2] == ["loginctl", "lock-session"]:
            return "", "", 0
        return "", "", 0

    monkeypatch.setattr(security_module, "_run_command", fake_run_command)

    lock_resp = await async_client.post(
        "/security/lock",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert lock_resp.status_code == 200
    assert "Screen locked via loginctl lock-session" in lock_resp.json()["message"]
