from app.services.maintenance import _parse_services_json, _parse_services_table


def test_parse_services_json_maps_unit_to_name():
    raw = """
    [
      {"unit":"nginx.service","load":"loaded","active":"active","sub":"running","description":"nginx"},
      {"unit":"api-monitor.service","load":"loaded","active":"activating","sub":"auto-restart","description":"API Monitoring Script"}
    ]
    """
    services = _parse_services_json(raw)
    assert services[0].name == "nginx.service"
    assert services[0].sub == "running"
    assert services[1].name == "api-monitor.service"
    assert services[1].active == "activating"
    assert services[1].sub == "auto-restart"
    assert services[1].description == "API Monitoring Script"


def test_parse_services_table_strips_leading_spaces_and_glyphs():
    stdout = """
  accounts-daemon.service                               loaded    active     running      Accounts Service
● api-monitor.service                                   loaded    activating auto-restart API Monitoring Script
  alsa-restore.service                                  loaded    active     exited       Save/Restore Sound Card State
● auditd.service                                        not-found inactive   dead         auditd.service
"""
    services = {s.name: s for s in _parse_services_table(stdout)}
    assert services["accounts-daemon.service"].load == "loaded"
    assert services["accounts-daemon.service"].active == "active"
    assert services["accounts-daemon.service"].sub == "running"
    assert services["accounts-daemon.service"].description == "Accounts Service"

    assert services["api-monitor.service"].load == "loaded"
    assert services["api-monitor.service"].active == "activating"
    assert services["api-monitor.service"].sub == "auto-restart"
    assert services["api-monitor.service"].description == "API Monitoring Script"

    assert services["alsa-restore.service"].sub == "exited"
    assert services["alsa-restore.service"].description == "Save/Restore Sound Card State"

    assert services["auditd.service"].load == "not-found"
    assert services["auditd.service"].name != "●"
