import { test } from 'node:test';
import assert from 'node:assert/strict';
import { TokenBucket } from '../lib/tokenbucket.js';

test('a new bucket starts full', () => {
  const bucket = new TokenBucket({ capacity: 3, refillPerSecond: 1 });
  assert.equal(bucket.capacity, 3);
  assert.equal(bucket.available(0), 3);
});

test('tryTake consumes tokens and refuses when short', () => {
  const bucket = new TokenBucket({ capacity: 2, refillPerSecond: 1 });
  assert.equal(bucket.tryTake(1, 0), true);
  assert.equal(bucket.tryTake(1, 0), true);
  assert.equal(bucket.tryTake(1, 0), false);
  assert.equal(bucket.available(0), 0);
});

test('tokens refill over time and are capped at capacity', () => {
  const bucket = new TokenBucket({ capacity: 4, refillPerSecond: 2 });
  assert.equal(bucket.tryTake(4, 0), true);
  assert.equal(bucket.available(500), 1);   // 0.5 s * 2/s = 1 token
  assert.equal(bucket.available(1000), 2);
  assert.equal(bucket.available(60_000), 4); // never above capacity
});

test('a clock that does not advance (or goes backwards) never refills', () => {
  const bucket = new TokenBucket({ capacity: 1, refillPerSecond: 10, now: 1000 });
  assert.equal(bucket.tryTake(1, 1000), true);
  assert.equal(bucket.available(1000), 0);
  assert.equal(bucket.available(500), 0);
});

test('rejects invalid configuration', () => {
  assert.throws(() => new TokenBucket({ capacity: 0, refillPerSecond: 1 }), RangeError);
  assert.throws(() => new TokenBucket({ capacity: 1.5, refillPerSecond: 1 }), RangeError);
  assert.throws(() => new TokenBucket({ capacity: 1, refillPerSecond: 0 }), RangeError);
  assert.throws(() => new TokenBucket({ capacity: 1, refillPerSecond: 1 }).tryTake(0, 0), RangeError);
});
