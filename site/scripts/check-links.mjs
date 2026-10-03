// Checks every internal link of the built site (dist/): the target page or
// file exists, and a #fragment names an id on that page. External links
// (https://...) are listed by host, not fetched. Exit code 1 on a dangling link.
// Usage: node scripts/check-links.mjs [dist]
import fs from 'node:fs';
import path from 'node:path';

const DIST = path.resolve(process.argv[2] ?? 'dist');
const BASE = '/rtx3090fe-model-tests';

const pages = [];
const walk = (d) => {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const f = path.join(d, e.name);
    if (e.isDirectory()) walk(f);
    else if (e.name.endsWith('.html')) pages.push(f);
  }
};
walk(DIST);

const idCache = new Map();
function idsOf(file) {
  if (!idCache.has(file)) {
    const html = fs.readFileSync(file, 'utf8');
    idCache.set(file, new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1])));
  }
  return idCache.get(file);
}

function resolveTarget(urlPath) {
  // urlPath: path below dist, decoded, without query
  const p = path.join(DIST, urlPath);
  if (fs.existsSync(p) && fs.statSync(p).isFile()) return p;
  const idx = path.join(p, 'index.html');
  if (fs.existsSync(idx)) return idx;
  return null;
}

const bad = [];
const REPO = path.resolve(DIST, '..', '..');
const repoBad = new Set();
let repoChecked = 0;
const external = new Map();
let checked = 0;
for (const page of pages) {
  const html = fs.readFileSync(page, 'utf8');
  const pageUrlDir = '/' + path.relative(DIST, path.dirname(page)).split(path.sep).join('/');
  for (const m of html.matchAll(/\s(?:href|src)="([^"]*)"/g)) {
    const raw = m[1].replace(/&amp;/g, '&');
    if (!raw || raw.startsWith('mailto:') || raw.startsWith('data:')) continue;
    if (/^https?:\/\//.test(raw)) {
      const host = new URL(raw).host;
      const gh = raw.match(/^https:\/\/github\.com\/florent-pro-ch\/rtx3090fe-model-tests\/(?:blob|tree)\/main\/([^#?]*)/);
      if (gh) {
        repoChecked++;
        const rel = decodeURIComponent(gh[1]);
        if (!fs.existsSync(path.join(REPO, rel))) repoBad.add(rel);
      }
      external.set(host, (external.get(host) ?? 0) + 1);
      continue;
    }
    checked++;
    const [pathPart, frag] = raw.split('#');
    let target;
    if (pathPart === '') target = page;
    else {
      let abs;
      if (pathPart.startsWith('/')) {
        if (!pathPart.startsWith(BASE + '/') && pathPart !== BASE) {
          bad.push(`${path.relative(DIST, page)}: ${raw} (outside the base path)`);
          continue;
        }
        abs = pathPart.slice(BASE.length) || '/';
      } else abs = path.posix.join(pageUrlDir, pathPart);
      abs = decodeURIComponent(abs.split('?')[0]);
      target = resolveTarget(abs);
      if (!target) {
        bad.push(`${path.relative(DIST, page)}: ${raw}`);
        continue;
      }
    }
    if (frag && target.endsWith('.html') && !idsOf(target).has(decodeURIComponent(frag))) {
      bad.push(`${path.relative(DIST, page)}: ${raw} (no id "${frag}")`);
    }
  }
}
console.log(`${pages.length} pages, ${checked} internal links checked, ${bad.length} dangling`);
console.log('external hosts:', [...external.entries()].sort().map(([h, n]) => `${h} (${n})`).join(', ') || 'none');
console.log(`${repoChecked} links into the repository on GitHub, ${repoBad.size} distinct paths missing from the local tree`);
for (const b of [...repoBad].sort().slice(0, 40)) console.log('  missing in repo: ' + b);
for (const b of bad.slice(0, 60)) console.log('  ' + b);
if (bad.length > 60) console.log(`  ... and ${bad.length - 60} more`);
process.exit(bad.length || repoBad.size ? 1 : 0);
