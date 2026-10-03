'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');

function run(...args) {
  const r = spawnSync(process.execPath, ['bin/tool.js', ...args], { cwd: ROOT, encoding: 'utf8' });
  return { code: r.status, stdout: r.stdout, stderr: r.stderr };
}

test('default invocation on sample.txt', () => {
  const r = run('sample.txt');
  assert.equal(r.code, 0, `expected exit code 0, got ${r.code}; stderr: ${r.stderr}`);
  const expected = { lines: 5, words: 51, top: [['is', 15], ['rust', 5], ['go', 4]] };
  assert.equal(r.stdout, JSON.stringify(expected) + '\n');
});
