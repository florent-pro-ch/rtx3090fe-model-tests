// Glyph coverage of the self-hosted font subsets: every character of the
// built site's text (the text nodes of every dist/ page, inline SVG labels
// included) and of the figure specs (figures/specs/*.json, the README banner
// and social preview words) must be in the cmap of every subset that can draw
// it: the three WOFF2 files of public/fonts/ (the pages) and the five TTFs of
// fonts-og/ (the Open Graph cards and figures, whose text comes from the same
// data as the pages). A missing character would fall back to a system font in
// the middle of Inter or JetBrains Mono text. Emoji are excluded: they fall
// back to the system's emoji font by design.
// The OG and figure generators also check every string they draw against the
// exact face (site/src/lib/og/draw.ts); this check covers the pages and the
// subsets as a whole.
// Usage: node scripts/check-glyphs.mjs [dist]   (exit 1 when a character is missing)
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import { fileURLToPath } from 'node:url';

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DIST = path.resolve(process.argv[2] ?? path.join(SITE, 'dist'));
const SPECS = path.join(SITE, '..', 'figures', 'specs');

// --- font cmaps (sfnt, and WOFF2 through its brotli stream; cmap is never transformed)
const WOFF2_TAGS = ['cmap', 'head', 'hhea', 'hmtx', 'maxp', 'name', 'OS/2', 'post', 'cvt ', 'fpgm', 'glyf', 'loca', 'prep', 'CFF ', 'VORG', 'EBDT', 'EBLC', 'gasp', 'hdmx', 'kern', 'LTSH', 'PCLT', 'VDMX', 'vhea', 'vmtx', 'BASE', 'GDEF', 'GPOS', 'GSUB', 'EBSC', 'JSTF', 'MATH', 'CBDT', 'CBLC', 'COLR', 'CPAL', 'SVG ', 'sbix', 'acnt', 'avar', 'bdat', 'bloc', 'bsln', 'cvar', 'fdsc', 'feat', 'fmtx', 'fvar', 'gvar', 'hsty', 'just', 'lcar', 'mort', 'morx', 'opbd', 'prop', 'trak', 'Zapf', 'Silf', 'Glat', 'Gloc', 'Feat', 'Sill'];

function cmapTableOf(buf) {
  const sig = buf.toString('latin1', 0, 4);
  if (sig === 'wOF2') {
    const numTables = buf.readUInt16BE(12);
    const compLen = buf.readUInt32BE(20);
    let p = 48;
    const base128 = () => {
      let v = 0;
      for (let i = 0; i < 5; i++) {
        const b = buf[p++];
        v = v * 128 + (b & 0x7f);
        if (!(b & 0x80)) return v;
      }
      throw new Error('bad UIntBase128');
    };
    const dir = [];
    for (let i = 0; i < numTables; i++) {
      const flags = buf[p++];
      let tag = WOFF2_TAGS[flags & 0x3f];
      if ((flags & 0x3f) === 63) { tag = buf.toString('latin1', p, p + 4); p += 4; }
      const version = flags >> 6;
      const orig = base128();
      const transformed = tag === 'glyf' || tag === 'loca' ? version !== 3 : version !== 0;
      dir.push({ tag, len: transformed ? base128() : orig });
    }
    const data = zlib.brotliDecompressSync(buf.subarray(p, p + compLen));
    let off = 0;
    for (const t of dir) {
      if (t.tag === 'cmap') return data.subarray(off, off + t.len);
      off += t.len;
    }
    throw new Error('no cmap table');
  }
  const n = buf.readUInt16BE(4);
  for (let i = 0; i < n; i++) {
    const rec = 12 + i * 16;
    if (buf.toString('latin1', rec, rec + 4) === 'cmap') {
      const o = buf.readUInt32BE(rec + 8);
      return buf.subarray(o, o + buf.readUInt32BE(rec + 12));
    }
  }
  throw new Error('no cmap table');
}

function codepoints(file) {
  const t = cmapTableOf(fs.readFileSync(file));
  const out = new Set();
  const n = t.readUInt16BE(2);
  for (let i = 0; i < n; i++) {
    const pid = t.readUInt16BE(4 + i * 8);
    const eid = t.readUInt16BE(6 + i * 8);
    const o = t.readUInt32BE(8 + i * 8);
    if (pid !== 3 && pid !== 0) continue;
    const fmt = t.readUInt16BE(o);
    if (fmt === 4) {
      const segX2 = t.readUInt16BE(o + 6);
      const ends = o + 14, starts = ends + segX2 + 2, deltas = starts + segX2, ros = deltas + segX2;
      for (let s = 0; s < segX2 / 2; s++) {
        const end = t.readUInt16BE(ends + 2 * s), start = t.readUInt16BE(starts + 2 * s);
        const delta = t.readInt16BE(deltas + 2 * s), ro = t.readUInt16BE(ros + 2 * s);
        for (let cp = start; cp <= end && cp !== 0xffff; cp++) {
          const g = ro === 0 ? (cp + delta) & 0xffff : (() => {
            const gi = t.readUInt16BE(ros + 2 * s + ro + 2 * (cp - start));
            return gi === 0 ? 0 : (gi + delta) & 0xffff;
          })();
          if (g) out.add(cp);
        }
      }
    } else if (fmt === 12) {
      const groups = t.readUInt32BE(o + 12);
      for (let gI = 0; gI < groups; gI++) {
        const r = o + 16 + gI * 12;
        const a = t.readUInt32BE(r), b = t.readUInt32BE(r + 4), g0 = t.readUInt32BE(r + 8);
        for (let cp = a; cp <= b; cp++) if (g0 + (cp - a)) out.add(cp);
      }
    }
    void eid;
  }
  return out;
}

const fonts = [
  ...['Inter-Variable-latin.woff2', 'JetBrainsMono-Regular-latin.woff2', 'JetBrainsMono-Bold-latin.woff2'].map((f) => path.join(SITE, 'public', 'fonts', f)),
  ...fs.readdirSync(path.join(SITE, 'fonts-og')).filter((f) => f.endsWith('.ttf')).sort().map((f) => path.join(SITE, 'fonts-og', f)),
].map((file) => ({ name: path.relative(SITE, file), cps: codepoints(file) }));

// --- the text to cover
const ENT = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' };
const decode = (s) => s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e) => {
  if (e[0] === '#') return String.fromCodePoint(e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10));
  return ENT[e.toLowerCase()] ?? m;
});
const used = new Map(); // codepoint -> first place seen
const add = (s, where) => {
  for (const ch of s) {
    const cp = ch.codePointAt(0);
    if (!used.has(cp)) used.set(cp, where);
  }
};

let pages = 0;
const walk = (d) => {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const f = path.join(d, e.name);
    if (e.isDirectory()) walk(f);
    else if (e.name.endsWith('.html')) {
      pages++;
      const html = fs.readFileSync(f, 'utf8')
        .replace(/<script\b[\s\S]*?<\/script>/gi, ' ')
        .replace(/<style\b[\s\S]*?<\/style>/gi, ' ')
        .replace(/<!--[\s\S]*?-->/g, ' ');
      add(decode(html.replace(/<[^>]*>/g, ' ')), path.relative(DIST, f));
    }
  }
};
if (!fs.existsSync(path.join(DIST, 'index.html'))) {
  console.error(`check-glyphs: ${DIST} has no index.html; build the site first`);
  process.exit(2);
}
walk(DIST);
const strings = (v) => (typeof v === 'string' ? [v] : Array.isArray(v) ? v.flatMap(strings) : v && typeof v === 'object' ? Object.values(v).flatMap(strings) : []);
let specs = 0;
if (fs.existsSync(SPECS)) {
  for (const f of fs.readdirSync(SPECS).filter((x) => x.endsWith('.json'))) {
    specs++;
    add(strings(JSON.parse(fs.readFileSync(path.join(SPECS, f), 'utf8'))).join(' '), `figures/specs/${f}`);
  }
}

// Emoji (and their joiners and selectors) fall back to the emoji font by design;
// line breaks and tabs are not drawn.
const EXEMPT = /[\p{Extended_Pictographic}\p{Regional_Indicator}\u{1F3FB}-\u{1F3FF}︎️‍⃣\n\r\t]/u;
const problems = [];
for (const [cp, where] of [...used].sort((a, b) => a[0] - b[0])) {
  const ch = String.fromCodePoint(cp);
  if (EXEMPT.test(ch)) continue;
  const missing = fonts.filter((fo) => !fo.cps.has(cp)).map((fo) => fo.name);
  if (missing.length) problems.push(`U+${cp.toString(16).toUpperCase().padStart(4, '0')} ${JSON.stringify(ch)} (first seen in ${where}) is missing from ${missing.join(', ')}`);
}
for (const p of problems) console.log(`MISSING ${p}`);
console.log(`check-glyphs: ${used.size} distinct characters in ${pages} pages and ${specs} figure specs against ${fonts.length} font subsets, ${problems.length} missing`);
process.exit(problems.length ? 1 : 0);
