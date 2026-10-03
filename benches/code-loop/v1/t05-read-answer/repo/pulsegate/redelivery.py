"""Retry policy for failed upstream deliveries.

A delivery that fails is not dropped. The worker asks RetryPolicy whether
another attempt is allowed and how long to wait before it. Attempt numbers are
1-based and count the first try, so the budget is a total, not "extra tries".
"""
from __future__ import annotations

from dataclasses import dataclass

# Total delivery attempts per event, first try included.
MAX_ATTEMPTS = 5
BASE_DELAY_SECONDS = 0.5
MAX_DELAY_SECONDS = 30.0


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = MAX_ATTEMPTS
    base_delay: float = BASE_DELAY_SECONDS
    max_delay: float = MAX_DELAY_SECONDS

    def allows(self, attempt: int) -> bool:
        """True when attempt number ``attempt`` (1-based) may run."""
        return 1 <= attempt <= self.max_attempts

    def delay_before(self, attempt: int) -> float:
        """Seconds to wait before ``attempt`` (nothing before the first one)."""
        if attempt <= 1:
            return 0.0
        return min(self.base_delay * 2 ** (attempt - 2), self.max_delay)

    def schedule(self) -> list:
        """Every delay this policy will ever apply, in order. Handy for logs."""
        return [self.delay_before(n) for n in range(1, self.max_attempts + 1)]

    def describe(self) -> str:
        return f"{self.max_attempts} attempts, delays {self.schedule()}"
