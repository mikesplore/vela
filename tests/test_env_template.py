from pathlib import Path

from app.utils.env_template import parse_env_values, render_env_file, sync_env_file


def test_render_env_file_includes_all_template_keys():
    text = render_env_file()
    values = parse_env_values(text)
    assert "VELA_FCM_SERVICE_ACCOUNT_PATH" in values
    assert "VELA_ALERT_TIMEZONE" in values
    assert values["VELA_NETWORK_PUBLIC_IP_CACHE_SECONDS"] == "120"


def test_sync_env_file_preserves_existing_values(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("USERNAME=alice\nPASSWORD=secret\n", encoding="utf-8")

    added = sync_env_file(env_path)

    values = parse_env_values(env_path.read_text(encoding="utf-8"))
    assert values["USERNAME"] == "alice"
    assert values["PASSWORD"] == "secret"
    assert "VELA_FCM_SERVICE_ACCOUNT_PATH" in values
    assert values["VELA_FCM_SERVICE_ACCOUNT_PATH"] == ""
    assert "VELA_FCM_SERVICE_ACCOUNT_PATH" in added
