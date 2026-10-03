# tinylib

A dependency-free ESM utility library for Node 24. No build step, no install.

- `lib/tokenbucket.js` — token-bucket rate limiter. Deterministic: callers pass the clock.
- `lib/lru.js` — LRU cache. Specified in `SPEC.md`, not implemented yet.

Run the whole test suite from the repository root with:

    node --test
