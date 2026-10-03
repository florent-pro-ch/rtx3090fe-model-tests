/**
 * SVG to PNG with resvg, given the self-hosted fonts only (no system font, so
 * the same SVG gives the same pixels on any machine), and SVG to SVG with the
 * text turned into outlines (for figures shown on GitHub, which renders an SVG
 * as an image without our fonts).
 *
 * A PNG over its byte budget is re-encoded as an indexed PNG (at most 256
 * colours, median cut) with node:zlib: no extra dependency. The images are
 * flat token colours plus anti-aliasing, so 256 colours lose nothing visible.
 * No text chunk is ever written (G7 media gate).
 */
import zlib from 'node:zlib';
import { Resvg, type ResvgRenderOptions } from '@resvg/resvg-js';
import { SANS, fontFiles } from './fonts';

export function resvgOptions(): ResvgRenderOptions {
  return {
    font: { loadSystemFonts: false, fontFiles: fontFiles(), defaultFontFamily: SANS },
    fitTo: { mode: 'original' },
    shapeRendering: 2,
    textRendering: 1,
  };
}

/**
 * The SVG with every text turned into paths (usvg), coordinates rounded to
 * 0.01 px (a hundredth of a pixel changes nothing visible and halves the file).
 */
export function outlineText(svg: string): string {
  return new Resvg(svg, resvgOptions())
    .toString()
    .replace(/-?\d+\.\d+/g, (n) => String(Math.round(parseFloat(n) * 100) / 100))
    .replace(/\n\s*/g, '\n');
}

export const OG_BUDGET = 150 * 1024;

export function renderPng(svg: string, budget = OG_BUDGET): Buffer {
  const img = new Resvg(svg, resvgOptions()).render();
  const png = Buffer.from(img.asPng());
  if (png.length <= budget) return stripAncillary(png);
  const indexed = encodeIndexed(Buffer.from(img.pixels), img.width, img.height);
  return indexed.length < png.length ? indexed : stripAncillary(png);
}

// ---------------------------------------------------------------------------
// PNG chunks

const SIG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

let crcTable: Uint32Array | null = null;
function crc32(buf: Buffer): number {
  if (!crcTable) {
    crcTable = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      crcTable[n] = c >>> 0;
    }
  }
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = crcTable[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type: string, data: Buffer): Buffer {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type, 'latin1'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}

/** Keep only the critical chunks (IHDR, PLTE, IDAT, IEND) and tRNS. */
function stripAncillary(png: Buffer): Buffer {
  const out: Buffer[] = [SIG];
  let off = 8;
  while (off < png.length) {
    const len = png.readUInt32BE(off);
    const type = png.toString('latin1', off + 4, off + 8);
    const end = off + 12 + len;
    if (['IHDR', 'PLTE', 'IDAT', 'IEND', 'tRNS'].includes(type)) out.push(png.subarray(off, end));
    off = end;
  }
  return Buffer.concat(out);
}

// ---------------------------------------------------------------------------
// Median-cut quantisation to an indexed PNG

interface Box {
  colours: number[]; // packed 0xRRGGBB
  weight: number;
}

function encodeIndexed(rgba: Buffer, w: number, h: number): Buffer {
  const counts = new Map<number, number>();
  for (let i = 0; i < rgba.length; i += 4) {
    // Composite on black is never needed: every figure paints an opaque background.
    const key = (rgba[i] << 16) | (rgba[i + 1] << 8) | rgba[i + 2];
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  let palette: number[];
  if (counts.size <= 256) {
    palette = [...counts.keys()].sort((a, b) => a - b);
  } else {
    const boxes: Box[] = [{ colours: [...counts.keys()], weight: rgba.length / 4 }];
    while (boxes.length < 256) {
      // split the heaviest box that has more than one colour, along its widest channel
      boxes.sort((a, b) => b.weight - a.weight);
      const i = boxes.findIndex((b) => b.colours.length > 1);
      if (i < 0) break;
      const box = boxes.splice(i, 1)[0];
      const ch = widestChannel(box.colours);
      const shift = 16 - 8 * ch;
      box.colours.sort((a, b) => ((a >> shift) & 255) - ((b >> shift) & 255) || a - b);
      let acc = 0;
      let cut = 1;
      for (let k = 0; k < box.colours.length - 1; k++) {
        acc += counts.get(box.colours[k])!;
        if (acc >= box.weight / 2) {
          cut = k + 1;
          break;
        }
        cut = k + 1;
      }
      const a = box.colours.slice(0, cut);
      const b = box.colours.slice(cut);
      boxes.push({ colours: a, weight: a.reduce((s, x) => s + counts.get(x)!, 0) });
      boxes.push({ colours: b, weight: b.reduce((s, x) => s + counts.get(x)!, 0) });
    }
    // Each box's colour: its most frequent member (keeps the exact token colours).
    palette = boxes.map((b) => b.colours.reduce((best, x) => (counts.get(x)! > counts.get(best)! ? x : best), b.colours[0]));
  }
  const index = new Map<number, number>();
  palette.forEach((p, i) => index.set(p, i));
  const nearest = (key: number): number => {
    const hit = index.get(key);
    if (hit !== undefined) return hit;
    const r = key >> 16, g = (key >> 8) & 255, b = key & 255;
    let best = 0, bestD = Infinity;
    for (let i = 0; i < palette.length; i++) {
      const p = palette[i];
      const dr = r - (p >> 16), dg = g - ((p >> 8) & 255), db = b - (p & 255);
      const d = 2 * dr * dr + 4 * dg * dg + 3 * db * db;
      if (d < bestD) { bestD = d; best = i; }
    }
    index.set(key, best);
    return best;
  };
  const raw = Buffer.alloc((w + 1) * h);
  for (let y = 0; y < h; y++) {
    raw[y * (w + 1)] = 0; // filter: none
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      raw[y * (w + 1) + 1 + x] = nearest((rgba[i] << 16) | (rgba[i + 1] << 8) | rgba[i + 2]);
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0);
  ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 3; // colour type: indexed
  ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
  const plte = Buffer.alloc(palette.length * 3);
  palette.forEach((p, i) => { plte[i * 3] = p >> 16; plte[i * 3 + 1] = (p >> 8) & 255; plte[i * 3 + 2] = p & 255; });
  const idat = zlib.deflateSync(raw, { level: 9, memLevel: 9 });
  return Buffer.concat([SIG, chunk('IHDR', ihdr), chunk('PLTE', plte), chunk('IDAT', idat), chunk('IEND', Buffer.alloc(0))]);
}

function widestChannel(colours: number[]): number {
  let best = 0, bestR = -1;
  for (let ch = 0; ch < 3; ch++) {
    const shift = 16 - 8 * ch;
    let lo = 255, hi = 0;
    for (const x of colours) { const v = (x >> shift) & 255; if (v < lo) lo = v; if (v > hi) hi = v; }
    if (hi - lo > bestR) { bestR = hi - lo; best = ch; }
  }
  return best;
}
