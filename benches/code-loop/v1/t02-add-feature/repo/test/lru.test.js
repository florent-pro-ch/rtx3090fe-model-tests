import { test } from 'node:test';
import assert from 'node:assert/strict';
import { LRUCache } from '../lib/lru.js';

test('set/get/has/size on a small cache', () => {
  const cache = new LRUCache(3);
  cache.set('a', 1).set('b', 2);
  assert.equal(cache.get('a'), 1);
  assert.equal(cache.get('b'), 2);
  assert.equal(cache.get('zzz'), undefined);
  assert.equal(cache.has('a'), true);
  assert.equal(cache.has('zzz'), false);
  assert.equal(cache.size, 2);
});

test('evicts the least recently used entry when full', () => {
  const cache = new LRUCache(2);
  cache.set('a', 1);
  cache.set('b', 2);
  cache.set('c', 3); // 'a' is the oldest entry, it goes
  assert.equal(cache.has('a'), false);
  assert.equal(cache.has('b'), true);
  assert.equal(cache.has('c'), true);
  assert.equal(cache.size, 2);
});
