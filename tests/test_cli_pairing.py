import sys


def test_pair_command_uses_interactive_inputs(monkeypatch, capsys):
    from app import cli

    answers = iter(["https://relay.example", "12345678", "123456", "Desk agent"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    monkeypatch.setattr("getpass.getpass", lambda _prompt="": next(answers))
    submitted = {}

    def fake_complete(vps_url, pairing_code, pairing_pin, agent_label):
        submitted.update({
            "vps_url": vps_url,
            "pairing_code": pairing_code,
            "pairing_pin": pairing_pin,
            "agent_label": agent_label,
        })
        return {"agent_id": "agt_test"}

    monkeypatch.setattr("app.agent.pairing.complete_pairing", fake_complete)
    monkeypatch.setattr(sys, "argv", ["vela", "pair"])

    cli.main()

    assert submitted == {
        "vps_url": "https://relay.example",
        "pairing_code": "12345678",
        "pairing_pin": "123456",
        "agent_label": "Desk agent",
    }
    assert "Pairing submitted for agent agt_test." in capsys.readouterr().out
