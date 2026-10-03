"""Delivery loop: takes queued records and pushes them to the upstream URL.

A failed push is not fatal. The worker asks the retry policy whether another
attempt is allowed and how long to wait before it; only when the policy has no
attempts left is the record reported as failed (it stays in the queue).
"""
from __future__ import annotations

import time
from typing import Callable

from .core import Relay
from .redelivery import RetryPolicy
from .settings import Settings
from .transport import DeliveryError, post_json


def deliver(
    settings: Settings,
    record: dict,
    policy: RetryPolicy,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Deliver one record; returns the number of the attempt that succeeded."""
    attempt = 1
    while True:
        try:
            post_json(settings.upstream_url, record, settings.upstream_timeout)
            return attempt
        except DeliveryError as exc:
            attempt += 1
            if not policy.allows(attempt):
                raise DeliveryError(
                    f"gave up on {record['id']} after {attempt - 1} attempts"
                ) from exc
            sleep(policy.delay_before(attempt))


def drain(settings: Settings, relay: Relay, policy: RetryPolicy | None = None) -> tuple:
    """Deliver everything currently queued. Returns ``(delivered, failed)``."""
    policy = policy or RetryPolicy()
    delivered = failed = 0
    for record in relay.pending():
        try:
            deliver(settings, record, policy)
        except DeliveryError as exc:
            print(f"worker: {exc}")
            failed += 1
            continue
        relay.discard(record["id"])
        delivered += 1
    return delivered, failed
