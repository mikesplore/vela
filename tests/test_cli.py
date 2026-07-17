import sys
from types import SimpleNamespace

from app import cli


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
