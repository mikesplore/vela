import sys
from pathlib import Path
from types import SimpleNamespace

from app import cli
from app.utils import env_paths


def test_dashboard_opens_local_operations_url(monkeypatch, capsys):
    from app.utils import config as config_module

    opened: list[str] = []
    monkeypatch.setattr(sys, "argv", ["vela", "--dashboard"])
    monkeypatch.setattr(
        config_module,
        "get_config",
        lambda: SimpleNamespace(host="0.0.0.0", port=8765),
    )
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url) or True)

    cli.main()

    assert opened == ["http://127.0.0.1:8765/admin/dashboard"]
    assert "Opened Operations dashboard" in capsys.readouterr().out


def test_env_opens_active_dotenv(monkeypatch, capsys, tmp_path):
    systemd_dir = tmp_path / "systemd"
    systemd_dir.mkdir()
    env_file = tmp_path / "runtime" / ".env"
    env_file.parent.mkdir()
    env_file.write_text("USERNAME=admin\n", encoding="utf-8")

    (systemd_dir / "vela-agent.service").write_text(
        f"[Service]\nEnvironmentFile={env_file}\n",
        encoding="utf-8",
    )
    opened: list[str] = []
    monkeypatch.setattr(sys, "argv", ["vela", "--env"])
    monkeypatch.setattr(env_paths, "SYSTEMD_USER_DIR", systemd_dir)
    monkeypatch.setattr(env_paths, "open_dotenv_in_editor", lambda path=None: env_file)

    cli.main()

    out = capsys.readouterr().out
    assert str(env_file) in out
    assert "vela --restart" in out


def test_resolve_active_dotenv_from_agent_unit(monkeypatch, tmp_path):
    systemd_dir = tmp_path / "systemd"
    systemd_dir.mkdir()
    env_file = tmp_path / "data" / ".env"
    (systemd_dir / "vela-agent.service").write_text(
        f"[Service]\nEnvironmentFile={env_file}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(env_paths, "SYSTEMD_USER_DIR", systemd_dir)

    assert env_paths.resolve_active_dotenv_path() == env_file.resolve()


def test_resolve_active_dotenv_falls_back_to_working_directory(monkeypatch, tmp_path):
    systemd_dir = tmp_path / "systemd"
    systemd_dir.mkdir()
    work_dir = tmp_path / "vela-home"
    work_dir.mkdir()
    (systemd_dir / "vela.service").write_text(
        f"[Service]\nWorkingDirectory={work_dir}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(env_paths, "SYSTEMD_USER_DIR", systemd_dir)

    assert env_paths.resolve_active_dotenv_path() == (work_dir / ".env").resolve()
