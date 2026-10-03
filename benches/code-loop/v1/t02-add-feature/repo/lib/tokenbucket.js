// lib/tokenbucket.js — token-bucket rate limiter.
//
// The bucket never reads the clock itself: every call takes an explicit `now`
// (milliseconds). That keeps it deterministic and trivial to test.

export class TokenBucket {
  #capacity;
  #refillPerSecond;
  #tokens;
  #updatedAt;

  constructor({ capacity, refillPerSecond, now = 0 } = {}) {
    if (!Number.isInteger(capacity) || capacity < 1) {
      throw new RangeError(`capacity must be a positive integer, got ${capacity}`);
    }
    if (typeof refillPerSecond !== 'number' || !(refillPerSecond > 0)) {
      throw new RangeError(`refillPerSecond must be a positive number, got ${refillPerSecond}`);
    }
    this.#capacity = capacity;
    this.#refillPerSecond = refillPerSecond;
    this.#tokens = capacity;
    this.#updatedAt = now;
  }

  get capacity() {
    return this.#capacity;
  }

  /** Whole tokens available at time `now` (ms). */
  available(now) {
    this.#refill(now);
    return Math.floor(this.#tokens);
  }

  /** Try to take `count` tokens at time `now` (ms). Returns true on success. */
  tryTake(count, now) {
    if (!Number.isInteger(count) || count < 1) {
      throw new RangeError(`count must be a positive integer, got ${count}`);
    }
    this.#refill(now);
    if (this.#tokens < count) return false;
    this.#tokens -= count;
    return true;
  }

  #refill(now) {
    if (typeof now !== 'number' || Number.isNaN(now)) {
      throw new TypeError('now must be a number of milliseconds');
    }
    if (now <= this.#updatedAt) return; // clock did not advance (or went backwards)
    const elapsedSeconds = (now - this.#updatedAt) / 1000;
    this.#tokens = Math.min(this.#capacity, this.#tokens + elapsedSeconds * this.#refillPerSecond);
    this.#updatedAt = now;
  }
}
