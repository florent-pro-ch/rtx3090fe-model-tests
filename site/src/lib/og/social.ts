/**
 * The repository-level figures, drawn from a spec in figures/specs/ and the
 * data it names:
 *   - the README banner, 1280 × 320 (Figma 14:1516 dark, 14:1623 light):
 *     repository name, the lead, the counts and the data date, and the console
 *     with the 1× / 2× / 2×2 schematics and the distinct runs on each;
 *   - the social preview, 1280 × 640 (Figma 20:14, "Social preview v2 · A"):
 *     the title, the lead, the site's counters of models, runs and benches,
 *     the data date and the version label, and the pair of RTX 3090 Founders
 *     Edition cards joined by NVLink (fe-card.ts), captioned from the pair's
 *     hardware record; the site's og/default.png is the same composition at
 *     1200 × 630.
 * Every number comes from src/lib/data.ts; the dark SVG is the source, the
 * light one is derived by the DESIGN.md token swap (tokens.ts).
 */
import fs from 'node:fs';
import path from 'node:path';
import {
  HARDWARE_IDS, ROOT, VERSION_LABEL, counts, dataAsOf, distinctRuns, hardwareById, runs,
} from '../data';
import { fmtNum } from '../site';
import { autoLineHeight, baseline, textWidth, wrap } from './fonts';
import {
  boxInside, brandMark, configChip, consoleBar, dotGrid, group, rect, schematic1, schematic2, schematic22Compact, spans, spansWidth, textTop, type Span,
} from './draw';
import { fePair } from './fe-card';

interface ConfigSpec { hardware: string; chip: string; schematic: '1x' | '2x' | '2x2'; count_suffix?: string }
interface BannerSpec { size: [number, number]; title: string; lead: string; console_title: string; configs: ConfigSpec[] }
interface SocialSpec { size: [number, number]; title_lines: string[]; lead: string; features: [string, string][]; pair_hardware: string; bridge_label: string; caption: string; footer: string }

export const SPEC_DIR = path.join(ROOT, 'figures', 'specs');
function spec<T>(name: string): T {
  return JSON.parse(fs.readFileSync(path.join(SPEC_DIR, `${name}.json`), 'utf8')) as T;
}

/**
 * The schematic of a configuration for these small-scale figures. The 2×2 is
 * always the small-scale variant (pair labels, "no link" and the caption
 * "2 independent machines" stay readable): the full 620-unit drawing, scaled
 * down to fit, would read as four cards in one box.
 */
function schematic(kind: ConfigSpec['schematic']) {
  if (kind === '1x') return schematic1();
  if (kind === '2x') return schematic2();
  return schematic22Compact(true);
}

/** Distinct runs (no byte copies) recorded on a hardware configuration — the README's per-configuration counts. */
export function runsOn(hw: string): number {
  if (!(HARDWARE_IDS as readonly string[]).includes(hw)) throw new Error(`figures: unknown configuration ${hw}`);
  return distinctRuns(runs().filter((r) => r.hardware === hw)).length;
}

/** "v0 (2026-10-02)" -> "v0 · 2026-10-02" for the console date chip. */
export function versionChip(): string {
  const m = /^(v\d+)\b.*?(\d{4}-\d{2}-\d{2})/.exec(VERSION_LABEL);
  return m ? `${m[1]} · ${m[2]}` : VERSION_LABEL;
}

function countsLine(): string {
  const k = counts();
  return `${k.models} models · ${k.runs} runs${k.run_copies ? ` (+${k.run_copies} copies)` : ''} · ${k.benches} benches · data as of ${dataAsOf() ?? 'undated'}`;
}

const svgDoc = (w: number, h: number, body: string) =>
  `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">${body}</svg>`;

// ---------------------------------------------------------------------------
// README banner

export function bannerSvg(): { svg: string; alt: string } {
  const sp = spec<BannerSpec>('banner');
  const [W, H] = sp.size;
  let s = rect(0, 0, W, H, { fill: 'bg' }) + dotGrid(W, H, 'banner-dots');

  // text block, centred vertically
  const textX = 48;
  const textW = 540;
  const lead = wrap(sp.lead, 'sans400', 19, textW);
  const blockH = 36 + 12 + lead.length * 19 * 1.5 + 12 + 12 * 1.4;
  let y = (H - blockH) / 2;
  s += brandMark(textX, y + 2, 1.6);
  s += textTop(textX + 62, y, 1.2, sp.title, { face: 'mono400', size: 30, fill: 'text' });
  y += 36 + 12;
  for (const ln of lead) {
    s += textTop(textX, y, 1.5, ln, { face: 'sans400', size: 19, fill: 'text' });
    y += 19 * 1.5;
  }
  y += 12;
  const countText = countsLine();
  s += textTop(textX, y, 1.4, countText, { face: 'mono400', size: 12, fill: 'muted' });

  // console with the three schematics
  const cw = 600, ch = 215;
  const cx = textX + textW + 36;
  const cy = (H - ch) / 2;
  s += boxInside(cx, cy, cw, ch, { fill: 'bg', stroke: 'border', sw: 2, rx: 16 });
  s += consoleBar(cx + 2, cy + 2, cw - 4, sp.console_title, versionChip());
  // The 2×2 at 1.4: its pair labels and "no link" at 15.4 px and its caption at
  // 16.8 px in the 1280-wide file, about 10 and 11 px where GitHub shows the
  // banner some 830 px wide.
  const scale = { '1x': 0.5, '2x': 0.5, '2x2': 1.4 } as const;
  const bottom = cy + ch - 14;
  let ix = cx + 2 + 16;
  const altCfg: string[] = [];
  for (const c of sp.configs) {
    const sc = schematic(c.schematic);
    const k = scale[c.schematic];
    const n = runsOn(c.hardware);
    const label = `${fmtNum(n)} ${c.count_suffix ?? (n === 1 ? 'run' : 'runs')}`;
    const chip = configChip(0, 0, c.chip);
    const rowW = chip.w + 6 + textWidth(label, 'mono400', 12);
    const sw = sc.w * k, sh = sc.h * k;
    const itemW = Math.max(sw, rowW);
    s += group(sc.svg, ix + (itemW - sw) / 2, bottom - 24 - 6 - sh, k);
    const rx = ix + (itemW - rowW) / 2;
    s += configChip(rx, bottom - 24, c.chip).svg;
    s += textTop(rx + chip.w + 6, bottom - 24 + 3.6, 1.4, label, { face: 'mono400', size: 12, fill: 'muted' });
    altCfg.push(`${c.chip}, ${hardwareById(c.hardware)?.label ?? c.hardware}: ${label}`);
    ix += itemW + 18;
  }
  const svg = svgDoc(W, H, s);
  const alt =
    `${sp.title}: ${sp.lead.replace(/ — /g, ', ').replace(/,\s*,/g, ',')} ` +
    `${countText.replace(/ · /g, ', ')}. ` +
    `Schematics of the three configurations with the distinct runs on each: ${altCfg.join('; ')}. ${VERSION_LABEL}.`;
  return { svg, alt };
}

// ---------------------------------------------------------------------------
// Social preview (and the site's default OG card)

/**
 * The social preview, after the Figma frame "Social preview v2 · A · the card"
 * (20:14, 1280 × 640): the title on two lines, the lead, three features of
 * the spec and the site's address on the left; on the right the pair of RTX
 * 3090 Founders Edition cards (fe-card.ts, DESIGN.md Motifs) with "NVLink"
 * beside the bridge and a caption whose numbers come from the pair's hardware
 * record. Static by design (2026-10-05): no count, date or version label, since
 * the image is uploaded by hand in the repository settings and would go stale.
 */
const FEATURE_RIGHT = 572; // the features end before the pair, drawn from x = 596

function pairCaption(sp: SocialSpec): string {
  const hw = hardwareById(sp.pair_hardware);
  if (!hw || hw.placeholder) throw new Error(`figures: hardware ${sp.pair_hardware} not found in data/hardware/`);
  if (hw.nvlink !== true) throw new Error(`figures: ${sp.pair_hardware} is not an NVLink pair; the illustration draws a bridge`);
  if (hw.gpus !== 2) throw new Error(`figures: ${sp.pair_hardware} has ${hw.gpus} GPUs; the illustration draws two cards`);
  if (typeof hw.vram_gb_total !== 'number') throw new Error(`figures: ${sp.pair_hardware} has no vram_gb_total`);
  return sp.caption.replace(/\{gpus\}/g, fmtNum(hw.gpus)).replace(/\{vram_per_gpu\}/g, fmtNum(hw.vram_gb_total / hw.gpus));
}

/** The 1280 × 640 composition, without its background (so it can be scaled into the 1200 × 630 card). */
function socialBody(sp: SocialSpec): { body: string; alt: string } {
  let s = '';
  // title: Inter ExtraBold 88, line height 1.02, tracking -2.5 %
  sp.title_lines.forEach((ln, i) => {
    s += textTop(64, 84 + i * 88 * 1.02, 1.02, ln, { face: 'sans800', size: 88, fill: 'text', ls: -0.025 * 88 });
  });
  // lead: Inter 24 --muted, 1.4, in a 500-wide box
  const lead = wrap(sp.lead, 'sans400', 24, 500);
  lead.forEach((ln, i) => {
    s += textTop(66, 296 + i * 24 * 1.4, 1.4, ln, { face: 'sans400', size: 24, fill: 'muted' });
  });
  // the three features, where the counters were: JetBrains Mono Bold over an Inter 22 --muted word, 44 apart,
  // the size the largest (at most 52) that ends them before the pair
  const gap = 44;
  const widthAt = (size: number) => sp.features.reduce((w, [head, word]) =>
    w + Math.max(textWidth(head, 'mono700', size), spansWidth([{ s: word, face: 'sans400', size: 22, fill: 'muted' }])), 0) + gap * (sp.features.length - 1);
  let fsz = 52;
  while (fsz > 28 && 64 + widthAt(fsz) > FEATURE_RIGHT) fsz -= 2;
  let x = 64;
  for (const [head, word] of sp.features) {
    s += textTop(x, 420, 1.1, head, { face: 'mono700', size: fsz, fill: 'text' });
    const w: Span[] = [{ s: word, face: 'sans400', size: 22, fill: 'muted' }];
    s += spans(x, baseline(420 + fsz * 1.1 + 2, 22, autoLineHeight('sans400'), 'sans400'), w);
    x += Math.max(textWidth(head, 'mono700', fsz), spansWidth(w)) + gap;
  }
  // footer: the site's address (never a date or a version: the image is uploaded by hand)
  s += textTop(64, 574, autoLineHeight('mono400'), sp.footer, { face: 'mono400', size: 17, fill: 'muted' });
  // the pair, the bridge's word and the caption
  const pair = fePair(sp.bridge_label);
  s += group(pair.svg, 596, 128);
  const caption = pairCaption(sp);
  s += textTop(910, 540, autoLineHeight('mono400'), caption, { face: 'mono400', size: 16, fill: 'muted', anchor: 'middle' });
  const alt =
    `${sp.title_lines.join(' ')}: ${sp.lead} ` +
    `${sp.features.map(([head, word]) => `${head} ${word}`).join(', ')}. ` +
    `Drawing: two RTX 3090 Founders Edition cards joined by the ${sp.bridge_label} bridge, captioned ${caption.replace(/ · /g, ', ')}. ` +
    `${sp.footer}.`;
  return { body: s, alt };
}

export function socialSvg(): { svg: string; alt: string } {
  const sp = spec<SocialSpec>('social-preview');
  const [W, H] = sp.size;
  const { body, alt } = socialBody(sp);
  return { svg: svgDoc(W, H, rect(0, 0, W, H, { fill: 'bg' }) + dotGrid(W, H, 'social-dots') + body), alt };
}

/** The site's default OG card: the social-preview composition fitted to 1200 × 630. */
export function defaultOgSvg(): { svg: string; alt: string } {
  const sp = spec<SocialSpec>('social-preview');
  const [SW, SH] = sp.size;
  const W = 1200, H = 630;
  const k = W / SW;
  const { body, alt } = socialBody(sp);
  const svg = svgDoc(W, H, rect(0, 0, W, H, { fill: 'bg' }) + dotGrid(W, H, 'og-dots') + group(body, 0, (H - SH * k) / 2, k));
  return { svg, alt };
}

