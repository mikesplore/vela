from app.services import network
from app.utils.config import get_config


def test_geolocate_ip_uses_ipinfo_when_ip_api_is_unavailable(monkeypatch):
    network._geo_cache.clear()
    monkeypatch.setattr(network, "_lookup_ip_api", lambda ip: None)
    monkeypatch.setattr(get_config(), "ipinfo_token", "test-token")

    seen: dict[str, str] = {}

    def fake_ipinfo(ip: str, token: str):
        seen["ip"] = ip
        seen["token"] = token
        return {
            "status": "success",
            "query": ip,
            "country": "United States",
            "region": None,
            "city": None,
            "zip": None,
            "timezone": None,
            "isp": "Google LLC",
            "org": "google.com",
            "lat": None,
            "lon": None,
            "message": "Location resolved by IPinfo Lite; city and coordinates are unavailable on this plan.",
        }

    monkeypatch.setattr(network, "_lookup_ipinfo_lite", fake_ipinfo)

    result = network.geolocate_ip("8.8.8.8")

    assert seen == {"ip": "8.8.8.8", "token": "test-token"}
    assert result is not None
    assert result["country"] == "United States"
    assert result["city"] is None
    assert result["lat"] is None


def test_geolocate_ip_prefers_richer_ip_api_result(monkeypatch):
    network._geo_cache.clear()
    monkeypatch.setattr(get_config(), "ipinfo_token", "test-token")
    monkeypatch.setattr(
        network,
        "_lookup_ip_api",
        lambda ip: {
            "status": "success",
            "query": ip,
            "country": "France",
            "region": "Île-de-France",
            "city": "Paris",
            "zip": "75000",
            "timezone": "Europe/Paris",
            "isp": "Example ISP",
            "org": "Example Org",
            "lat": 48.8566,
            "lon": 2.3522,
            "message": None,
        },
    )
    monkeypatch.setattr(
        network,
        "_lookup_ipinfo_lite",
        lambda *_: (_ for _ in ()).throw(AssertionError("IPinfo should not be used")),
    )

    result = network.geolocate_ip("203.0.113.1")

    assert result is not None
    assert result["city"] == "Paris"
    assert result["lat"] == 48.8566
