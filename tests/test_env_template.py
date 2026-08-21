from pathlib import Path
import re

from app.setup.writers import write_env_file
from app.utils.env_template import ENV_TEMPLATE, parse_env_values, render_env_file, sync_env_file


def test_env_example_matches_template_keys():
    example_path = Path(__file__).parents[1] / ".env.example"
    example_text = example_path.read_text(encoding="utf-8")
    example_keys = {
        match.group(1)
        for match in re.finditer(r"^\s*#?\s*([A-Za-z_][A-Za-z0-9_]*)=", example_text, re.MULTILINE)
    }
    template_keys = {key for key, _ in ENV_TEMPLATE}

    assert example_keys == template_keys


def test_render_env_file_includes_all_template_keys():
    text = render_env_file()
    values = parse_env_values(text)
    assert "VPS_URL" in values
    assert "RELAY_SECRET" in values
    assert "VELA_ALERT_TIMEZONE" in values
    assert values["VELA_NETWORK_PUBLIC_IP_CACHE_SECONDS"] == "120"


def test_sync_env_file_preserves_existing_values(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("USERNAME=alice\nPASSWORD=secret\n", encoding="utf-8")

    added = sync_env_file(env_path)

    values = parse_env_values(env_path.read_text(encoding="utf-8"))
    assert values["USERNAME"] == "alice"
    assert values["PASSWORD"] == "secret"
    assert "VPS_URL" in values
    assert values["VPS_URL"] == ""
    assert "VPS_URL" in added


def test_setup_writer_writes_every_template_key(tmp_path):
    env_path = write_env_file(
        tmp_path,
        username="admin",
        password="password",
        vps_url="https://relay.example.test",
        agent_label="test-agent",
        server_port=8765,
        assistant_pin="",
    )

    values = parse_env_values(env_path.read_text(encoding="utf-8"))
    assert set(values) == {key for key, _ in ENV_TEMPLATE}
    assert values["VPS_URL"] == "https://relay.example.test"
    assert values["AGENT_NAME"] == "test-agent"
