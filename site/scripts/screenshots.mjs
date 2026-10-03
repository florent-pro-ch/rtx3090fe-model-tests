// Screenshots of the built site in light and dark, desktop (1280x900) and
// phone (390x844), through headless Chrome driven over the DevTools protocol
// (a plain --window-size cannot go below Chrome's minimum window width, so a
// phone viewport is emulated with Emulation.setDeviceMetricsOverride).
//
// Serve dist/ under the base path first, e.g.:
//   mkdir -p /tmp/serve && cp -R dist /tmp/serve/rtx3090fe-model-tests
//   (cd /tmp/serve && python3 -m http.server 8765 --bind 127.0.0.1)
// Usage: node scripts/screenshots.mjs [out_dir] [origin] [--full] [--only=name,name]
//   --full captures the whole page height instead of the first screen.
//   --only keeps the listed page names (e.g. --only=home,nav-open).
// The phone nav is shot open through ?menu=open (the layout's menu script
// reads it), phone size only.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const args = process.argv.slice(2).filter((a) => !a.startsWith('--'));
const FULL = process.argv.includes('--full');
const ONLY = (process.argv.find((a) => a.startsWith('--only=')) ?? '').slice(7).split(',').filter(Boolean);
const OUT = path.resolve(args[0] ?? 'screenshots');
const ORIGIN = args[1] ?? 'http://127.0.0.1:8765';
const BASE = `${ORIGIN}/rtx3090fe-model-tests`;
const CHROME = process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 9333 + Math.floor(Math.random() * 500);

const PAGES = [
  ['home', '/'],
  ['config-1x', '/configs/1x3090fe/'],
  ['config-2x-nvlink', '/configs/2x3090fe-nvlink/'],
  ['config-2x2', '/configs/2x2x3090fe-nvlink/'],
  ['model-gemma-4-26b', '/models/google__gemma-4-26b-a4b-it/'],
  ['ranking-code-v1', '/rankings/code-v1--2026-10-01-tests-veille/'],
  ['compare-nvlink-dense', '/compare/nvlink-ab-dense/'],
  ['compare-spec-decoding', '/compare/spec-decoding-3090/'],
  ['model-qwen38-27b', '/models/qwen__qwen3.8-27b/'],
  ['pitfalls', '/pitfalls/'],
  ['rig', '/rig/'],
  ['forge', '/forge/'],
  // Phone only: the collapsed nav opened (Figma 9:182).
  ['nav-open', '/models/?menu=open', 'phone'],
];
const SIZES = [
  ['desktop', 1280, 900, false],
  ['phone', 390, 844, true],
];

fs.mkdirSync(OUT, { recursive: true });
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'shots-'));
const chrome = spawn(CHROME, ['--headless=new', '--disable-gpu', '--hide-scrollbars', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, 'about:blank'], { stdio: 'ignore' });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function wsUrl() {
  for (let i = 0; i < 60; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find((t) => t.type === 'page');
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(250);
  }
  throw new Error('Chrome did not start');
}

const ws = new WebSocket(await wsUrl());
await new Promise((r) => ws.addEventListener('open', r, { once: true }));
let id = 0;
const pending = new Map();
const waiters = [];
ws.addEventListener('message', (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) {
    pending.get(msg.id)(msg);
    pending.delete(msg.id);
  } else if (msg.method) for (const w of waiters.splice(0)) w(msg);
});
const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const i = ++id;
    pending.set(i, (m) => (m.error ? reject(new Error(`${method}: ${m.error.message}`)) : resolve(m.result)));
    ws.send(JSON.stringify({ id: i, method, params }));
  });
async function waitLoad() {
  const t0 = Date.now();
  while (Date.now() - t0 < 15000) {
    const r = await send('Runtime.evaluate', { expression: 'document.readyState', returnByValue: true });
    if (r.result.value === 'complete') return;
    await sleep(100);
  }
}

await send('Page.enable');
const written = [];
for (const [name, p, only] of PAGES) {
  if (ONLY.length && !ONLY.includes(name)) continue;
  for (const theme of ['light', 'dark']) {
    for (const [sname, w, h, mobile] of SIZES) {
      if (only && only !== sname) continue;
      await send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile });
      await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: theme }] });
      await send('Page.navigate', { url: `${BASE}${p}${p.includes('?') ? '&' : '?'}theme=${theme}` });
      await sleep(150);
      await waitLoad();
      await sleep(250);
      // Self-hosted fonts: shoot once they are in, not the fallback.
      await send('Runtime.evaluate', { expression: 'document.fonts.ready.then(() => true)', awaitPromise: true, returnByValue: true });
      let clip;
      if (FULL) {
        const r = await send('Runtime.evaluate', { expression: 'document.documentElement.scrollHeight', returnByValue: true });
        clip = { x: 0, y: 0, width: w, height: Math.min(r.result.value, 12000), scale: 1 };
      }
      const shot = await send('Page.captureScreenshot', { format: 'png', ...(clip ? { clip, captureBeyondViewport: true } : {}) });
      const file = path.join(OUT, `${name}-${theme}-${sname}.png`);
      fs.writeFileSync(file, Buffer.from(shot.data, 'base64'));
      written.push(path.basename(file));
    }
  }
}
ws.close();
chrome.kill();
await new Promise((r) => (chrome.exitCode !== null ? r() : chrome.once('exit', r)));
try {
  fs.rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
} catch {}
console.log(`${written.length} screenshots in ${OUT}`);
for (const f of written) console.log('  ' + f);
