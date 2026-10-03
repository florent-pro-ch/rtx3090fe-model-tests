/**
 * The two self-hosted typefaces of DESIGN.md (Inter for text, JetBrains Mono
 * for every number), as the Latin-subset TTF files in site/fonts-og/, and a
 * small reader of their advance widths so the generators can lay text out
 * (wrap a paragraph, put a unit after a number) without a browser.
 *
 * Widths come from the fonts' hmtx table, without kerning: a measured string
 * is never narrower than the rendered one, so a layout built on it does not
 * overflow. The renderer (resvg) is given exactly these files and no system
 * font (loadSystemFonts: false), so every image renders the same everywhere.
 */
import fs from 'node:fs';
import path from 'node:path';
import { ROOT } from '../data';

export const FONT_DIR = path.join(ROOT, 'site', 'fonts-og');

export const SANS = 'Inter';
export const MONO = 'JetBrains Mono';

/**
 * A face: family and weight as written in the SVG, and its file. The Latin
 * subsets of Inter carry no typographic family name (name ID 16), so each
 * static weight is its own family for the renderer ("Inter SemiBold").
 */
export const FACES = {
  sans400: { family: SANS, weight: 400, file: 'Inter-Regular-latin.ttf' },
  sans600: { family: `${SANS} SemiBold`, weight: 600, file: 'Inter-SemiBold-latin.ttf' },
  sans800: { family: `${SANS} ExtraBold`, weight: 800, file: 'Inter-ExtraBold-latin.ttf' },
  mono400: { family: MONO, weight: 400, file: 'JetBrainsMono-Regular-latin.ttf' },
  mono700: { family: MONO, weight: 700, file: 'JetBrainsMono-Bold-latin.ttf' },
} as const;
export type FaceKey = keyof typeof FACES;

export function fontFiles(): string[] {
  return Object.values(FACES).map((f) => path.join(FONT_DIR, f.file));
}

interface Metrics {
  upm: number;
  ascender: number;
  descender: number;
  advances: number[];
  cmap: Map<number, number>;
}

function readMetrics(file: string): Metrics {
  const buf = fs.readFileSync(file);
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  const numTables = dv.getUint16(4);
  const tables = new Map<string, number>();
  for (let i = 0; i < numTables; i++) {
    const rec = 12 + i * 16;
    const tag = String.fromCharCode(buf[rec], buf[rec + 1], buf[rec + 2], buf[rec + 3]);
    tables.set(tag, dv.getUint32(rec + 8));
  }
  const need = (t: string) => {
    const off = tables.get(t);
    if (off === undefined) throw new Error(`og/fonts: ${path.basename(file)} has no ${t} table`);
    return off;
  };
  const head = need('head');
  const hhea = need('hhea');
  const hmtx = need('hmtx');
  const maxp = need('maxp');
  const cmapOff = need('cmap');
  const upm = dv.getUint16(head + 18);
  const ascender = dv.getInt16(hhea + 4);
  const descender = dv.getInt16(hhea + 6);
  const nHMetrics = dv.getUint16(hhea + 34);
  const nGlyphs = dv.getUint16(maxp + 4);
  const advances: number[] = [];
  for (let g = 0; g < nGlyphs; g++) {
    advances.push(dv.getUint16(hmtx + 4 * Math.min(g, nHMetrics - 1)));
  }
  // cmap: prefer a full-repertoire subtable (3,10 format 12), else the BMP one (3,1 format 4).
  const cmap = new Map<number, number>();
  const nSub = dv.getUint16(cmapOff + 2);
  const subs: { pid: number; eid: number; off: number }[] = [];
  for (let i = 0; i < nSub; i++) {
    const r = cmapOff + 4 + i * 8;
    subs.push({ pid: dv.getUint16(r), eid: dv.getUint16(r + 2), off: cmapOff + dv.getUint32(r + 4) });
  }
  const pick = subs.find((s) => dv.getUint16(s.off) === 12) ?? subs.find((s) => dv.getUint16(s.off) === 4);
  if (!pick) throw new Error(`og/fonts: ${path.basename(file)} has no usable cmap`);
  const fmt = dv.getUint16(pick.off);
  if (fmt === 12) {
    const nGroups = dv.getUint32(pick.off + 12);
    for (let i = 0; i < nGroups; i++) {
      const g = pick.off + 16 + i * 12;
      const start = dv.getUint32(g);
      const end = dv.getUint32(g + 4);
      const gid = dv.getUint32(g + 8);
      for (let c = start; c <= end; c++) cmap.set(c, gid + (c - start));
    }
  } else {
    const segX2 = dv.getUint16(pick.off + 6);
    const ends = pick.off + 14;
    const starts = ends + segX2 + 2;
    const deltas = starts + segX2;
    const ranges = deltas + segX2;
    for (let s = 0; s < segX2 / 2; s++) {
      const end = dv.getUint16(ends + 2 * s);
      const start = dv.getUint16(starts + 2 * s);
      const delta = dv.getInt16(deltas + 2 * s);
      const ro = dv.getUint16(ranges + 2 * s);
      for (let c = start; c <= end && c !== 0xffff; c++) {
        let gid: number;
        if (ro === 0) gid = (c + delta) & 0xffff;
        else {
          const at = ranges + 2 * s + ro + 2 * (c - start);
          gid = dv.getUint16(at);
          if (gid !== 0) gid = (gid + delta) & 0xffff;
        }
        if (gid) cmap.set(c, gid);
      }
    }
  }
  return { upm, ascender, descender, advances, cmap };
}

const cache = new Map<FaceKey, Metrics>();
function metrics(face: FaceKey): Metrics {
  let m = cache.get(face);
  if (!m) {
    m = readMetrics(path.join(FONT_DIR, FACES[face].file));
    cache.set(face, m);
  }
  return m;
}

/** Characters a face cannot draw (the renderer would substitute nothing: no system fonts). */
export function missingGlyphs(text: string, face: FaceKey): string[] {
  const m = metrics(face);
  return [...new Set([...text].filter((ch) => !/\s/.test(ch) && !m.cmap.has(ch.codePointAt(0)!)))];
}

/** Advance width of a string in px, without kerning; letterSpacing in px is added after every character. */
export function textWidth(text: string, face: FaceKey, size: number, letterSpacing = 0): number {
  const m = metrics(face);
  let units = 0;
  let n = 0;
  for (const ch of text) {
    const gid = m.cmap.get(ch.codePointAt(0)!) ?? 0;
    units += m.advances[gid] ?? 0;
    n++;
  }
  return (units * size) / m.upm + letterSpacing * n;
}

/**
 * The baseline of a line of text whose box starts at `top` and is
 * `size * lineHeight` tall, the glyphs centred in the box as in Figma.
 */
export function baseline(top: number, size: number, lineHeight: number, face: FaceKey): number {
  const m = metrics(face);
  const asc = (m.ascender / m.upm) * size;
  const desc = (-m.descender / m.upm) * size;
  return top + (size * lineHeight - (asc + desc)) / 2 + asc;
}

/** The face's natural line height as a multiple of the size (Figma's "auto": ascender + descender). */
export function autoLineHeight(face: FaceKey): number {
  const m = metrics(face);
  return (m.ascender - m.descender) / m.upm;
}

/** Greedy word wrap to `maxWidth`; a single word wider than the line keeps its own line. */
export function wrap(text: string, face: FaceKey, size: number, maxWidth: number): string[] {
  const words = text.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let cur = '';
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w;
    if (cur && textWidth(next, face, size) > maxWidth) {
      lines.push(cur);
      cur = w;
    } else cur = next;
  }
  if (cur) lines.push(cur);
  return lines;
}
