/**
 * SVG primitives and the motifs of DESIGN.md (brand mark, console bar, badge,
 * GPU chip, NVLink bridge, the 1× / 2× / 2×2 schematics, the dot grid), drawn
 * in the dark palette at the geometry of the design file's components (page
 * Components: GPU chip, NVLink bridge, console bar, schematics 1× / 2× / 2×2,
 * badge set).
 *
 * Every colour is a token name; every string is checked against the glyphs of
 * the self-hosted fonts, so a character the fonts cannot draw fails the build
 * instead of rendering as a blank box.
 */
import { dark, type TokenName } from './tokens';
import { FACES, type FaceKey, baseline, missingGlyphs, textWidth } from './fonts';

export const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
/** A coordinate, rounded to 0.01 px so the output is stable. */
export const f = (v: number) => String(Math.round(v * 100) / 100);
export const c = (t: TokenName) => dark()[t];

export interface TextStyle {
  face: FaceKey;
  size: number;
  fill: TokenName;
  anchor?: 'start' | 'middle' | 'end';
  /** letter spacing in px */
  ls?: number;
  opacity?: number;
}

function checkGlyphs(s: string, face: FaceKey) {
  const miss = missingGlyphs(s, face);
  if (miss.length) throw new Error(`og/draw: ${FACES[face].file} cannot draw ${miss.map((ch) => JSON.stringify(ch)).join(', ')} in ${JSON.stringify(s)}`);
}

function fontAttrs(face: FaceKey, size: number): string {
  const fc = FACES[face];
  return `font-family="${fc.family}" font-weight="${fc.weight}" font-size="${f(size)}"`;
}

/** One line of text at a baseline. */
export function text(x: number, y: number, s: string, st: TextStyle): string {
  checkGlyphs(s, st.face);
  const anchor = st.anchor && st.anchor !== 'start' ? ` text-anchor="${st.anchor}"` : '';
  const ls = st.ls ? ` letter-spacing="${f(st.ls)}"` : '';
  const op = st.opacity !== undefined && st.opacity < 1 ? ` fill-opacity="${st.opacity}"` : '';
  return `<text x="${f(x)}" y="${f(y)}" ${fontAttrs(st.face, st.size)} fill="${c(st.fill)}"${op}${anchor}${ls}>${esc(s)}</text>`;
}

/** One line of text whose Figma text box starts at `top` with the given line height. */
export function textTop(x: number, top: number, lineHeight: number, s: string, st: TextStyle): string {
  return text(x, baseline(top, st.size, lineHeight, st.face), s, st);
}

export interface Span {
  s: string;
  face: FaceKey;
  size: number;
  fill: TokenName;
  /** gap before this span, in px */
  dx?: number;
}

/** Several runs of text on one baseline (a number, its unit, a label), flowing left to right. */
export function spans(x: number, y: number, list: Span[]): string {
  const parts = list.map((sp) => {
    checkGlyphs(sp.s, sp.face);
    const dx = sp.dx ? ` dx="${f(sp.dx)}"` : '';
    return `<tspan${dx} ${fontAttrs(sp.face, sp.size)} fill="${c(sp.fill)}">${esc(sp.s)}</tspan>`;
  });
  return `<text x="${f(x)}" y="${f(y)}" xml:space="preserve">${parts.join('')}</text>`;
}

export function spansWidth(list: Span[]): number {
  return list.reduce((w, sp) => w + (sp.dx ?? 0) + textWidth(sp.s, sp.face, sp.size), 0);
}

export interface RectStyle {
  fill?: TokenName | 'none';
  stroke?: TokenName;
  sw?: number;
  rx?: number;
  dash?: string;
  opacity?: number;
}

export function rect(x: number, y: number, w: number, h: number, st: RectStyle = {}): string {
  const fill = st.fill && st.fill !== 'none' ? c(st.fill) : 'none';
  const stroke = st.stroke ? ` stroke="${c(st.stroke)}" stroke-width="${f(st.sw ?? 1)}"` : '';
  const rx = st.rx ? ` rx="${f(st.rx)}"` : '';
  const dash = st.dash ? ` stroke-dasharray="${st.dash}"` : '';
  const op = st.opacity !== undefined && st.opacity < 1 ? ` opacity="${st.opacity}"` : '';
  return `<rect x="${f(x)}" y="${f(y)}" width="${f(w)}" height="${f(h)}"${rx} fill="${fill}"${stroke}${dash}${op}/>`;
}

/** A rectangle whose stroke sits inside the box (as Figma's inside strokes do). */
export function boxInside(x: number, y: number, w: number, h: number, st: RectStyle = {}): string {
  const sw = st.stroke ? st.sw ?? 1 : 0;
  return rect(x + sw / 2, y + sw / 2, w - sw, h - sw, { ...st, rx: st.rx !== undefined ? Math.max(0, st.rx - sw / 2) : undefined });
}

export function line(x1: number, y1: number, x2: number, y2: number, stroke: TokenName, sw = 1): string {
  return `<line x1="${f(x1)}" y1="${f(y1)}" x2="${f(x2)}" y2="${f(y2)}" fill="none" stroke="${c(stroke)}" stroke-width="${f(sw)}"/>`;
}

export function circle(cx: number, cy: number, r: number, st: { fill?: TokenName; stroke?: TokenName; sw?: number }): string {
  const fill = st.fill ? c(st.fill) : 'none';
  const stroke = st.stroke ? ` stroke="${c(st.stroke)}" stroke-width="${f(st.sw ?? 1)}"` : '';
  return `<circle cx="${f(cx)}" cy="${f(cy)}" r="${f(r)}" fill="${fill}"${stroke}/>`;
}

export const group = (body: string, x = 0, y = 0, scale = 1) =>
  `<g transform="translate(${f(x)} ${f(y)})${scale !== 1 ? ` scale(${scale})` : ''}">${body}</g>`;

// ---------------------------------------------------------------------------
// Motifs

/** Dot-grid texture (--grid), hero surfaces only: a 2 px dot every 24 px. */
export function dotGrid(w: number, h: number, id = 'dots'): string {
  return (
    `<defs><pattern id="${id}" width="24" height="24" patternUnits="userSpaceOnUse">` +
    `<rect width="2" height="2" fill="${c('grid')}"/></pattern></defs>` +
    `<rect width="${f(w)}" height="${f(h)}" fill="url(#${id})"/>`
  );
}

/** The site mark (30 × 20 at scale 1): a slot with two fans, green and blue. */
export function brandMark(x: number, y: number, scale = 1): string {
  const body =
    `<rect x="1" y="1" width="28" height="18" rx="3" fill="none" stroke="${c('text')}" stroke-width="1.6" stroke-opacity="0.75"/>` +
    `<circle cx="10" cy="10" r="5" fill="none" stroke="${c('green')}" stroke-width="1.6"/>` +
    `<circle cx="21" cy="10" r="5" fill="none" stroke="${c('blue')}" stroke-width="1.6"/>`;
  return group(body, x, y, scale);
}

export const BRAND_TEXT = 'RTX 3090 FE MODEL TESTS';
/** Mark + site name, as in the site header (Figma "Brand" 5:10). Returns its width. */
export function brand(x: number, top: number): { svg: string; w: number } {
  const st: TextStyle = { face: 'sans800', size: 15, fill: 'text', ls: 0.3 };
  const tx = x + 40;
  const svg = brandMark(x, top) + text(tx, baseline(top + 1, 15, 1.2, 'sans800'), BRAND_TEXT, st);
  return { svg, w: 40 + textWidth(BRAND_TEXT, 'sans800', 15, 0.3) };
}

/**
 * Title bar of the console frame (Figma 5:109): three dots, a mono title, a
 * right-aligned date chip, a separator under it. 38 px tall at scale 1.
 */
export function consoleBar(x: number, y: number, w: number, title: string, chip: string | null): string {
  const cy = y + 19;
  let s = '';
  for (let i = 0; i < 3; i++) s += circle(x + 12 + 5.5 + i * 17, cy, 5.5, { fill: 'panel2' });
  const cap: TextStyle = { face: 'mono400', size: 12, fill: 'muted' };
  const by = baseline(cy - 8.4, 12, 1.4, 'mono400');
  s += text(x + 12 + 3 * 11 + 3 * 6, by, title, cap);
  if (chip) {
    const cw = textWidth(chip, 'mono400', 12) + 18 + 2;
    const cx = x + w - 12 - cw;
    s += rect(cx + 0.5, cy - 9.4 + 0.5, cw - 1, 18.8 - 1, { fill: 'panel', stroke: 'border', rx: 9 });
    s += text(cx + 10, by, chip, cap);
  }
  s += line(x, y + 38 - 0.5, x + w, y + 38 - 0.5, 'border');
  return s;
}

export type Tone = 'green' | 'amber' | 'red' | 'blue' | 'muted';

/** A pill badge (Figma 5:84): 1 px border in the tone, the word always present, an optional status dot. */
export function badge(x: number, top: number, label: string, tone: Tone, opts: { dot?: boolean; mono?: boolean } = {}): { svg: string; w: number } {
  const face: FaceKey = opts.mono ? 'mono400' : 'sans400';
  const tw = textWidth(label, face, 12);
  const dotW = opts.dot ? 6 + 5 : 0;
  const w = 8 + dotW + tw + 8 + 2;
  const h = 22;
  let s = boxInside(x, top, w, h, { stroke: tone, rx: 11 });
  if (opts.dot) s += circle(x + 9 + 3, top + h / 2, 3, { fill: tone });
  s += text(x + 9 + dotW, baseline(top + 3, 12, 1.3, face), label, { face, size: 12, fill: tone });
  return { svg: s, w };
}

/** A row of badges with a 6 px gap. */
export function badgeRow(x: number, top: number, list: { label: string; tone: Tone; dot?: boolean; mono?: boolean }[], gap = 6): { svg: string; w: number } {
  let cx = x;
  let svg = '';
  for (const b of list) {
    const r = badge(cx, top, b.label, b.tone, { dot: b.dot, mono: b.mono });
    svg += r.svg;
    cx += r.w + gap;
  }
  return { svg, w: Math.max(0, cx - x - gap) };
}

/** One RTX 3090 Founders Edition (Figma 5:97), 176 × 44 at scale 1: a slot, a fan circle, the label 3090. */
export function gpuChip(x: number, y: number): string {
  const body =
    rect(0.25, 0.25, 175.5, 43.5, { fill: 'panel2', stroke: 'border', sw: 0.5, rx: 6 }) +
    `<path d="M5 0 V44 H3 A3 3 0 0 1 0 41 V3 A3 3 0 0 1 3 0 Z" fill="${c('muted')}"/>` +
    circle(35, 22, 14.25, { stroke: 'muted', sw: 1.5 }) +
    circle(35, 22, 4, { fill: 'muted' }) +
    textTop(60, 14, 1.4, '3090', { face: 'mono400', size: 12, fill: 'text' });
  return group(body, x, y);
}

/**
 * The NVLink bridge (Figma 5:107): a short --blue bar joining two GPU chips,
 * 12 × 84 at scale 1. `software-off`: the bridge in place with peer-to-peer
 * closed in software (the A/B proxy), drawn dashed. No state shows a removed bridge.
 */
export function bridge(x: number, y: number, state: 'on' | 'software-off' = 'on'): string {
  return state === 'on'
    ? rect(x, y, 12, 84, { fill: 'blue', rx: 6 })
    : rect(x + 0.75, y + 0.75, 10.5, 82.5, { fill: 'none', stroke: 'blue', sw: 1.5, rx: 5.25, dash: '4 3' });
}

/** Schematic 1× (Figma 8:7): one card, 240 × 120 at scale 1. */
export function schematic1(): { svg: string; w: number; h: number } {
  return { svg: gpuChip(32, 38), w: 240, h: 120 };
}

/** Schematic 2× (Figma 8:15): one NVLink pair, two cards joined by a 4-slot bridge, 240 × 150 at scale 1. */
export function schematic2(state: 'on' | 'software-off' = 'on'): { svg: string; w: number; h: number } {
  const lab: TextStyle = { face: 'mono400', size: 12, fill: 'blue' };
  const svg =
    gpuChip(20, 14) +
    gpuChip(20, 78) +
    bridge(170, 22, state) +
    textTop(188, 48, 1.4, 'NVLink', lab) +
    textTop(188, 64, 1.4, '4-slot', lab);
  return { svg, w: 240, h: 150 };
}

/**
 * Schematic 2×2, small-scale variant of Figma 8:33 (geometry shared with the site's
 * Schematic2x2Compact.astro; the detailed 620-unit drawing lives on the configuration pages):
 * two dashed pair boxes with a wide gap and "no link" in it, each pair two plain
 * cards (no per-card text) and its bridge, pair labels at 11 units and an optional
 * caption at 12 units, so the "two machines" words stay readable where the full
 * 620-unit drawing would shrink to unreadable text. Drawn at scale 1 or larger.
 */
export const COMPACT22 = {
  w: 204,
  box: 74,
  gap: 56,
  boxH: 60,
  label: 11,
  captionSize: 12,
  captionBase: 79,
  hCaption: 84,
  caption: '2 independent machines',
} as const;

/** Schematic 2×2, small-scale variant (see COMPACT22). */
export function schematic22Compact(withCaption = true): { svg: string; w: number; h: number } {
  const G = COMPACT22;
  const card = (y: number) =>
    rect(8.5, y + 0.5, 43, 12, { fill: 'panel2', stroke: 'border', rx: 2.5 }) +
    `<path d="M10.5 ${f(y)} H11 V${f(y + 13)} H10.5 A2.5 2.5 0 0 1 8 ${f(y + 10.5)} V${f(y + 2.5)} A2.5 2.5 0 0 1 10.5 ${f(y)} Z" fill="${c('muted')}"/>` +
    circle(20, y + 6.5, 4, { stroke: 'muted', sw: 1.2 }) +
    circle(20, y + 6.5, 1.2, { fill: 'muted' });
  const pair = (x: number, name: string) =>
    group(
      rect(0.5, 0.5, G.box - 1, G.boxH - 1, { fill: 'none', stroke: 'muted', rx: 8, dash: '4 3' }) +
        text(8, 15, name, { face: 'mono400', size: G.label, fill: 'text' }) +
        card(22) +
        card(40) +
        rect(56, 24, 5, 27, { fill: 'blue', rx: 2.5 }),
      x,
      0,
    );
  let svg = pair(0, 'pair A') + pair(G.box + G.gap, 'pair B');
  svg += text(G.box + G.gap / 2, 34, 'no link', { face: 'mono400', size: G.label, fill: 'muted', anchor: 'middle' });
  if (withCaption) svg += text(G.w / 2, G.captionBase, G.caption, { face: 'mono400', size: G.captionSize, fill: 'muted', anchor: 'middle' });
  return { svg, w: G.w, h: withCaption ? G.hCaption : G.boxH };
}

/** A configuration chip ("1×", "2×", "2×2"): Inter 17 semibold in --blue inside a 1 px --border box. */
export function configChip(x: number, top: number, label: string, padX = 6): { svg: string; w: number; h: number } {
  const w = textWidth(label, 'sans600', 17) + 2 * padX + 2;
  const h = 24;
  const svg = boxInside(x, top, w, h, { stroke: 'border', rx: 6 }) + textTop(x + padX + 1, top + 1, 1.3, label, { face: 'sans600', size: 17, fill: 'blue' });
  return { svg, w, h };
}
