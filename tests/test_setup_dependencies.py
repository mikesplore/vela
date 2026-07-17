import threading
import time

from app.setup import deps, wizard


def test_dependency_install_plan_deduplicates_suggested_packages(monkeypatch):
    missing = [
        {"feature": "Audio", "packages": {"apt": ["alsa-utils", "shared"]}},
        {"feature": "Media", "packages": {"apt": ["playerctl", "shared"]}},
    ]
    monkeypatch.setattr(deps, "check_missing_dependencies", lambda: missing)
    monkeypatch.setattr(deps, "detect_pkg_manager", lambda: "apt")

    result_missing, manager, packages = deps.dependency_install_plan()

    assert result_missing == missing
    assert manager == "apt"
    assert packages == ["alsa-utils", "playerctl", "shared"]


def test_browser_dependency_choice_unblocks_setup():
    lock = threading.Lock()
    state = {}
    decision = {"value": None}
    event = threading.Event()

    def choose_skip():
        while "dependency_decision_required" not in state:
            time.sleep(0.001)
        with lock:
            decision["value"] = "skip"
            state["dependency_decision_required"] = False
        event.set()

    threading.Thread(target=choose_skip, daemon=True).start()

    selected = wizard._wait_for_dependency_decision(
        lock,
        state,
        decision,
        event,
        [{"feature": "Media", "missing_commands": ["playerctl"]}],
        "apt",
        ["playerctl"],
        timeout=1,
    )

    assert selected == "skip"
    assert state["phase"] == "dependencies"
    assert state["dependency_decision_required"] is False
