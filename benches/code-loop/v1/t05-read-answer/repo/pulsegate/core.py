"""Event intake shared by every entry point.

Whatever the transport, an event reaches the queue through one function, so
payloads are validated and ids are minted in a single place and the queue
never sees two shapes of record.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_FIELDS = ("topic", "body")
MAX_TOPIC_LENGTH = 64


class RejectedEvent(ValueError):
    """Raised when an inbound payload cannot become a queue record."""


@dataclass
class Relay:
    """The outbound queue. Records live in memory and are mirrored to disk."""

    queue_dir: Path | None = None
    records: list = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.queue_dir is not None and self.queue_dir.is_dir():
            for path in sorted(self.queue_dir.glob("evt-*.json")):
                self.records.append(json.loads(path.read_text(encoding="utf-8")))

    def push(self, record: dict) -> str:
        digest = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
        event_id = f"evt-{len(self.records) + 1:06d}-{digest[:8]}"
        record = {"id": event_id, **record}
        self.records.append(record)
        if self.queue_dir is not None:
            self.queue_dir.mkdir(parents=True, exist_ok=True)
            (self.queue_dir / f"{event_id}.json").write_text(json.dumps(record), encoding="utf-8")
        return event_id

    def pending(self) -> list:
        return list(self.records)

    def discard(self, event_id: str) -> None:
        self.records = [r for r in self.records if r["id"] != event_id]
        if self.queue_dir is not None:
            path = self.queue_dir / f"{event_id}.json"
            if path.exists():
                path.unlink()


def normalize(payload) -> dict:
    """Validate a raw payload and return a clean record (without id/source)."""
    if not isinstance(payload, dict):
        raise RejectedEvent("payload must be a JSON object")
    missing = [key for key in REQUIRED_FIELDS if key not in payload]
    if missing:
        raise RejectedEvent(f"missing field(s): {', '.join(missing)}")
    topic = str(payload["topic"]).strip().lower()
    if not topic or len(topic) > MAX_TOPIC_LENGTH:
        raise RejectedEvent(f"topic must be 1..{MAX_TOPIC_LENGTH} characters")
    return {"topic": topic, "body": payload["body"], "headers": dict(payload.get("headers") or {})}


def accept_event(relay: Relay, payload, *, source: str) -> str:
    """Validate one inbound payload and hand it to the relay; returns its id."""
    record = normalize(payload)
    record["source"] = source
    return relay.push(record)


def accept_batch(relay: Relay, payloads: list, *, source: str) -> list:
    """Replay helper: accept many payloads in order, stopping at the first bad one."""
    return [accept_event(relay, payload, source=source) for payload in payloads]
