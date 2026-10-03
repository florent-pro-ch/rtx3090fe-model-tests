// WCAG 2.x contrast of every text/background token pair the site uses, in
// both themes, read from src/styles/global.css. Exit code 1 if a pair is
// below AA for normal text (4.5:1).
// Usage: node scripts/contrast.mjs
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const css = fs.readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'src/styles/global.css'), 'utf8');

function tokens(block) {
  const out = {};
  for (const m of block.matchAll(/--([a-z0-9]+):\s*(#[0-9a-f]{6})/gi)) out[m[1]] = m[2].toLowerCase();
  return out;
}
const dark = tokens(css.match(/:root\s*\{([^}]*)\}/)[1]);
const light = tokens(css.match(/:root\[data-theme='light'\]\s*\{([^}]*)\}/)[1]);
const lightMedia = tokens(css.match(/:root:not\(\[data-theme='dark'\]\)\s*\{([^}]*)\}/)[1]);
for (const k of Object.keys(light)) if (light[k] !== lightMedia[k]) throw new Error(`light tokens differ between the media query and [data-theme=light]: --${k}`);

function lum(hex) {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
function ratio(a, b) {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

// Text colours used on each background (see global.css): body and tiles
// (bg, panel), table header/hover rows, banners, frame chips (panel), code and
// the current nav item (panel2). Every tone may appear on every surface.
const FG = ['text', 'muted', 'blue', 'green', 'amber', 'red'];
const BG = ['bg', 'panel', 'panel2'];
let fail = 0;
for (const [name, t] of [['dark', dark], ['light', light]]) {
  console.log(`${name} theme`);
  for (const fg of FG) {
    const cells = BG.map((bg) => {
      const r = ratio(t[fg], t[bg]);
      if (r < 4.5) fail++;
      return `${bg} ${r.toFixed(2)}${r < 4.5 ? ' FAIL' : ''}`;
    });
    console.log(`  ${fg.padEnd(6)} ${t[fg]}  on  ${cells.join('   ')}`);
  }
}
console.log(fail ? `${fail} pair(s) below 4.5:1` : 'every pair reaches AA (4.5:1)');
process.exit(fail ? 1 : 0);
