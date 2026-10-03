# SPEC — `lib/lru.js`, an LRU cache

Add a new module `lib/lru.js` exporting a class `LRUCache` as a **named export**.
Follow the conventions of `lib/tokenbucket.js`: ESM, private fields, `RangeError`
on invalid configuration, no dependencies.

## Construction

    new LRUCache(capacity, { onEvict } = {})

- `capacity` must be a positive integer (`>= 1`). Anything else — `0`, a negative
  number, a non-integer, `NaN`, a string, `null`, `undefined` — throws `RangeError`.
- `onEvict` is optional. When given, it is a function that is called **synchronously**
  as `onEvict(key, value)` — exactly two positional arguments, the evicted key then the
  evicted value — every time an entry is evicted because the cache is full. It is
  **not** called by `delete()`, and **not** called when an existing key is overwritten.
- `cache.capacity` is a read-only getter returning the configured capacity.

## Recency model

Every stored entry has a recency position. The **least recently used** (LRU) entry is
the one that has gone the longest without being set or read. These operations mark a
key as **most recently used** (MRU):

- `set(key, value)` — whether the key is new or already present.
- `get(key)` — when the key is present. A cache hit MUST refresh recency.

These operations do **not** change recency: `has(key)`, `delete(key)`, `size`,
`keys()`, and a `get(key)` of a missing key.

## Members

| Member            | Behaviour                                                                 |
|-------------------|---------------------------------------------------------------------------|
| `get(key)`        | Returns the stored value, or `undefined` when absent. A hit marks the key MRU. |
| `set(key, value)` | Stores the value and marks the key MRU. If the key is **new** and the cache is already at capacity, the LRU entry is evicted first (calling `onEvict`). Overwriting an existing key never evicts. Returns `this` so calls can be chained. |
| `has(key)`        | `true` if the key is present, else `false`. Does not touch recency.       |
| `delete(key)`     | Removes the key. Returns `true` if it was present, else `false`. Never calls `onEvict`. |
| `size`            | Getter: number of entries currently stored.                               |
| `keys()`          | Returns a **new array** of the keys ordered from LRU (first) to MRU (last). |

Keys follow `Map` semantics (SameValueZero): `1` and `'1'` are distinct keys, objects
are compared by identity. Storing `undefined` as a value is allowed, but `get` cannot
distinguish it from a miss — use `has` for that.

## Tests

`test/lru.test.js` already contains two starting cases. Extend it so the spec above
is covered (recency after `get`, overwrite, capacity 1, `delete`, `onEvict`, errors).
