"""Browser setup wizard server (orchestration only — HTML lives in app.ui)."""

from __future__ import annotations

import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from app.ui.setup_wizard_page import render_setup_wizard_page


def browser_onboarding_enabled() -> bool:
    raw = os.getenv("VELA_BROWSER_ONBOARDING", "true").strip().lower()
    return raw not in {"0", "false", "no"}


def browser_is_available() -> bool:
    try:
        webbrowser.get()
        return True
    except webbrowser.Error:
        return False


def start_setup_wizard(defaults: dict[str, str]):
    state_lock = threading.Lock()
    state = {
        "phase": "collect",
        "message": "Fill the form to start setup.",
        "pairing": None,
        "pairing_status": None,
        "dependency": None,
        "dependency_decision_required": False,
        "done": False,
        "error": None,
    }
    submitted: dict[str, str] = {}
    submitted_event = threading.Event()
    dependency_decision: dict[str, str | None] = {"value": None}
    dependency_event = threading.Event()
    page = render_setup_wizard_page(defaults)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/wizard-state":
                with state_lock:
                    payload = json.dumps(state).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            if self.path not in {"/", "/index.html"}:
                self.send_response(404)
                self.end_headers()
                return
            body = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path not in {"/submit", "/dependency-decision"}:
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            data = parse_qs(raw, keep_blank_values=True)
            if self.path == "/dependency-decision":
                decision = (data.get("decision") or [""])[0].strip().lower()
                if decision not in {"install", "skip"}:
                    self.send_response(400)
                    self.end_headers()
                    return
                with state_lock:
                    if not state["dependency_decision_required"]:
                        self.send_response(409)
                        self.end_headers()
                        return
                    dependency_decision["value"] = decision
                    state["dependency_decision_required"] = False
                    state["message"] = (
                        "Installing selected packages. Your terminal may ask for your system password."
                        if decision == "install"
                        else "Skipping optional package installation."
                    )
                dependency_event.set()
                body = b'{"ok":true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            for key in (
                "username",
                "password",
                "vps_url",
                "agent_label",
                "host",
                "port",
                "allowed_dirs_csv",
                "assistant_pin",
                "fireworks_api_key",
                "ipinfo_token",
                "resend_api_key",
                "resend_from_email",
                "recipient_email",
                "spotify_client_id",
                "spotify_client_secret",
            ):
                submitted[key] = (data.get(key) or [""])[0].strip()
            with state_lock:
                state["phase"] = "configuring"
                state["message"] = "Setup submitted. Continuing..."
            submitted_event.set()
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://{host}:{port}"
    print(f"Opening browser onboarding: {url}")
    webbrowser.open(url)
    return {
        "url": url,
        "wait_for_submit": lambda timeout: submitted_event.wait(timeout=timeout),
        "get_submitted": lambda: dict(submitted),
        "wait_for_dependency_decision": lambda missing, pkg_manager, packages, timeout: _wait_for_dependency_decision(
            state_lock,
            state,
            dependency_decision,
            dependency_event,
            missing,
            pkg_manager,
            packages,
            timeout,
        ),
        "set_phase": lambda phase, message: _set_phase(state_lock, state, phase, message),
        "set_pairing_session": lambda payload: _set_pairing_session(state_lock, state, payload),
        "set_pairing_status": lambda status: _set_pairing_status(state_lock, state, status),
        "set_done": lambda message: _set_done(state_lock, state, message),
        "set_error": lambda message: _set_error(state_lock, state, message),
        "close": lambda: _close(server),
    }


def _wait_for_dependency_decision(
    lock: threading.Lock,
    state: dict,
    decision: dict[str, str | None],
    event: threading.Event,
    missing: list[dict],
    pkg_manager: str,
    packages: list[str],
    timeout: int,
) -> str:
    with lock:
        state["phase"] = "dependencies"
        state["message"] = "Review missing optional system tools."
        state["dependency"] = {
            "missing": missing,
            "package_manager": pkg_manager,
            "packages": packages,
        }
        state["dependency_decision_required"] = True
    if not event.wait(timeout=max(1, timeout)):
        with lock:
            state["dependency_decision_required"] = False
            state["message"] = "Package installation was skipped because no selection was received."
        return "skip"
    return decision["value"] or "skip"


def _set_phase(lock: threading.Lock, state: dict, phase: str, message: str) -> None:
    with lock:
        state["phase"] = phase
        state["message"] = message


def _set_pairing_session(lock: threading.Lock, state: dict, payload: dict) -> None:
    with lock:
        state["phase"] = "pairing"
        state["message"] = "Waiting for mobile app pairing..."
        state["pairing"] = payload
        state["pairing_status"] = payload.get("status", "AWAITING_PAIR")


def _set_pairing_status(lock: threading.Lock, state: dict, status: str) -> None:
    with lock:
        state["pairing_status"] = status
        if status == "PAIRED":
            state["message"] = "Paired. Activating..."
        elif status == "ACTIVE":
            state["message"] = "Pairing complete."


def _set_done(lock: threading.Lock, state: dict, message: str) -> None:
    with lock:
        state["phase"] = "done"
        state["message"] = message
        state["done"] = True


def _set_error(lock: threading.Lock, state: dict, message: str) -> None:
    with lock:
        state["phase"] = "error"
        state["message"] = "Setup failed."
        state["error"] = message


def _close(server: ThreadingHTTPServer) -> None:
    try:
        server.shutdown()
        server.server_close()
    except Exception:
        pass
