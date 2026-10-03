"""HTTP intake: ``POST /events`` with a JSON body, ``GET /health``."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import __version__
from .core import Relay, RejectedEvent, accept_event
from .settings import Settings

MAX_BODY_BYTES = 64 * 1024


class IntakeHandler(BaseHTTPRequestHandler):
    server_version = f"pulsegate/{__version__}"

    def do_GET(self) -> None:
        if self.path != "/health":
            return self._reply(404, {"error": "not found"})
        self._reply(200, {"status": "ok", "version": __version__})

    def do_POST(self) -> None:
        if self.path != "/events":
            return self._reply(404, {"error": "not found"})
        try:
            payload = self._read_json()
            event_id = accept_event(self.server.relay, payload, source="http")
        except RejectedEvent as exc:
            return self._reply(400, {"error": str(exc)})
        except ValueError as exc:
            return self._reply(400, {"error": f"bad json: {exc}"})
        self._reply(202, {"id": event_id})

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            raise RejectedEvent("body too large")
        return json.loads(self.rfile.read(length) or b"null")

    def _reply(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args) -> None:  # keep the fake quiet
        pass


class IntakeServer(HTTPServer):
    def __init__(self, settings: Settings, relay: Relay) -> None:
        super().__init__((settings.host, settings.port), IntakeHandler)
        self.relay = relay


def serve(settings: Settings, relay: Relay | None = None) -> None:
    server = IntakeServer(settings, relay or Relay(settings.queue_dir))
    print(f"pulsegate listening on {settings.host}:{settings.port}")
    server.serve_forever()
