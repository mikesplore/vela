from types import SimpleNamespace

import pytest

from app.agent import pairing


def test_fetch_pairing_status_reports_retry_after(monkeypatch):
    monkeypatch.setenv("VPS_URL", "https://relay.example")
    monkeypatch.setattr(pairing, "get_config", lambda: SimpleNamespace(local_service_timeout=10))
    monkeypatch.setattr(
        pairing.requests,
        "get",
        lambda *args, **kwargs: SimpleNamespace(status_code=429, headers={"Retry-After": "7"}, text="slow_down"),
    )

    with pytest.raises(pairing.PairingRateLimitedError) as caught:
        pairing._fetch_pairing_status("agt_test")

    assert caught.value.retry_after == 7


def test_wait_for_pairing_retries_rate_limited_status_poll(monkeypatch):
    monkeypatch.setenv("PAIRING_STATUS_TIMEOUT", "10")
    status_results = iter(
        [
            pairing.PairingRateLimitedError(2),
            ("PAIRED", "activation-token"),
        ]
    )

    def fetch_status(_agent_id):
        result = next(status_results)
        if isinstance(result, Exception):
            raise result
        return result

    sleeps = []
    monkeypatch.setattr(pairing, "_fetch_pairing_status", fetch_status)
    monkeypatch.setattr(pairing.time, "sleep", sleeps.append)

    assert pairing._wait_for_pairing("agt_test") == "activation-token"
    assert sleeps == [2]
