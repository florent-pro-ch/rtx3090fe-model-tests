"""HTTP transport to the upstream ingest endpoint (stdlib only)."""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

# Socket-level reconnect budget while opening the TCP connection. It is spent
# inside one delivery attempt and says nothing about how many times an event
# is delivered overall.
CONNECT_RETRIES = 3
CONNECT_BACKOFF_SECONDS = 0.2


class DeliveryError(Exception):
    """The upstream did not accept the record (network error or non-2xx)."""


def post_json(url: str, payload: dict, timeout: float) -> int:
    """POST ``payload`` as JSON; returns the HTTP status on success."""
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "pulsegate"},
        method="POST",
    )
    last_error: Exception | None = None
    for _ in range(CONNECT_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            # The connection worked; the upstream simply said no.
            raise DeliveryError(f"upstream answered {exc.code}") from exc
        except (urllib.error.URLError, socket.timeout, OSError) as exc:
            last_error = exc
    raise DeliveryError(f"could not connect after {CONNECT_RETRIES} tries: {last_error}")
