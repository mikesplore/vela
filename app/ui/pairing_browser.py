import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.ui.pairing_page import render_pairing_page


def start_pairing_browser_ui(state: dict):
    class PairingHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in {"/", "/index.html"}:
                page = render_pairing_page(state)
                body = page.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if self.path in {"/status", "/state"}:
                payload = json.dumps(state).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            self.send_response(404)
            self.end_headers()

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), PairingHandler)
    host, port = server.server_address
    url = f"http://{host}:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def update_status(new_status: str) -> None:
        import time

        state["status"] = new_status
        state["updated_at_epoch"] = int(time.time())

    def stop() -> None:
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass

    webbrowser.open(url)
    return url, update_status, stop

