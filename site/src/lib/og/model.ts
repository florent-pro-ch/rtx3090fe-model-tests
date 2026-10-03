/**
 * The Open Graph card of a model page, 1200 × 630, dark theme, after the
 * Figma template "OG · model page" (node 14:1762): a console frame with the
 * model's name, id, parameters and badges, one cell per hardware
 * configuration with its headline numbers, the verdict, and a footer with the
 * data date.
 *
 * Nothing is recomputed here: the cells follow FitBox (src/components/
 * FitBox.astro) through the same functions of src/lib/data.ts — the headline
 * run is headlineRun() (the headline-run rule), numbers are formatted by
 * fmtNum() as <Num> does, and runs of the uncensored lab never give a number
 * (headlineRun() excludes them; the card asserts it again).
 */
import type { Model, Run } from '../data';
import {
  HARDWARE_IDS, VERSION_LABEL, aggSlots, assertSiteRules, dataAsOf, distinctRuns, headlineRun, isForge,
  isHouseProtocol, isNum, isRefusalOnly, runDate, runsOnConfig, soloTokS, splitGroup, vramKind, vramKindLabel, vramPerGpu,
} from '../data';
import { STATUS_LABEL, STATUS_TONE, engineLabel, fmtNum } from '../site';
import { fourCardRuns } from '../configs';
import { baseline, textWidth, wrap, type FaceKey } from './fonts';
import {
  badgeRow, boxInside, brand, consoleBar, rect, spans, spansWidth, text, textTop, type Span, type Tone,
} from './draw';

export const OG_W = 1200;
export const OG_H = 630;
export const REPO_NAME = 'rtx3090fe-model-tests';

/** Short headings of the three configurations (the site's FitBox uses the hardware labels). */
export const CONFIG_HEADING: Record<string, string> = {
  '1x3090fe': 'One card',
  '2x3090fe-nvlink': 'NVLink pair',
  '2x2x3090fe-nvlink': 'Two pairs',
};

type CellKind = 'measured' | 'spill' | 'ran' | 'tried' | 'none';
interface Cell {
  hw: string;
  kind: CellKind;
  head: Run | null;
  okCount: number;
  statuses: string[];
}

function cellsOf(m: Model): Cell[] {
  return HARDWARE_IDS.map((hw) => {
    const head = headlineRun(m.model_id, hw);
    if (head && isRefusalOnly(head)) throw new Error(`og: ${head.run_id} is a refusal-only run and cannot give a number`);
    const others = distinctRuns(runsOnConfig(hw).filter((r) => r.model_id === m.model_id));
    const ok = others.filter((r) => r.status === 'ok');
    const kind: CellKind = head
      ? splitGroup(head) === 'cpu-offload' ? 'spill' : 'measured'
      : ok.length ? 'ran' : others.length ? 'tried' : 'none';
    return { hw, kind, head, okCount: ok.length, statuses: [...new Set(others.map((r) => r.status))].sort() };
  });
}

interface NumRow {
  value: string;
  unit: string;
  label: string;
  /** the raw values, for the alt text */
  raw: number[];
}

function numRows(r: Run): NumRow[] {
  const rows: NumRow[] = [];
  const solo = soloTokS(r);
  if (solo !== null) rows.push({ value: fmtNum(solo), unit: 'tok/s', label: 'single stream', raw: [solo] });
  const agg = r.metrics.agg_tok_s;
  if (isNum(agg)) {
    const c = r.metrics.agg_concurrency;
    const s = aggSlots(r);
    const label = (isNum(c) ? `at ${fmtNum(c)} requests` : 'aggregate') + (s.serialised && s.engine === 'llamacpp' ? ', 1 slot (serialised)' : '');
    rows.push({ value: fmtNum(agg), unit: 'tok/s', label, raw: [agg] });
  }
  const vr = vramPerGpu(r);
  if (vr.length) rows.push({ value: vr.map((v) => fmtNum(v)).join(' + '), unit: 'MiB', label: vramKindLabel(vramKind(r)).short, raw: vr });
  return rows;
}

const caption = (r: Run) => `${r.protocol ?? 'no protocol'} · ${engineLabel(r.engine, { prePin: true })} · ${runDate(r) ?? 'undated'}`;

function headBadges(c: Cell): { label: string; tone: Tone; dot?: boolean }[] {
  const out: { label: string; tone: Tone; dot?: boolean }[] = [];
  if (c.head && !isHouseProtocol(c.head.protocol)) out.push({ label: 'other protocol', tone: 'amber' });
  if (c.head && c.head.engine.pre_pin === true) out.push({ label: 'pre-pin', tone: 'amber' });
  return out;
}

function statusBadge(c: Cell): { label: string; tone: Tone; dot?: boolean }[] {
  if (c.kind === 'measured') return [{ label: 'fits · measured', tone: 'green', dot: true }];
  if (c.kind === 'spill') return [{ label: 'runs, with part of the model in system RAM', tone: 'amber', dot: true }];
  if (c.kind === 'ran') return [{ label: 'fits · ran', tone: 'green', dot: true }];
  if (c.kind === 'tried') return c.statuses.map((s) => ({ label: STATUS_LABEL[s] ?? s, tone: (STATUS_TONE[s] ?? 'muted') as Tone, dot: true }));
  return [];
}

const PAD_X = 16;
const PAD_Y = 14;
const GAP = 8;
const H_HEAD = 17 * 1.3;
const H_BADGE = 22;
const H_CAP = 12 * 1.4;

function numSpans(row: NumRow, numSize: number): Span[] {
  return [
    { s: row.value, face: 'mono400', size: numSize, fill: 'text' },
    { s: row.unit, face: 'mono400', size: 12, fill: 'muted', dx: 6 },
    { s: row.label, face: 'sans400', size: 14, fill: 'muted', dx: 6 },
  ];
}

const NOTE_SIZE = 14;
const NOTE_LH = 1.45;
function noteText(c: Cell): string {
  if (c.kind === 'ran') return `No headline single-stream figure here; ${c.okCount} run${c.okCount === 1 ? '' : 's'} ended ok.`;
  if (c.kind === 'tried') return 'Tried on this configuration, never ended ok.';
  // The heading already says "Two pairs": with it, the cell reads "Two pairs: never one model on four cards".
  if (c.hw === '2x2x3090fe-nvlink' && fourCardRuns().value === 0) return 'Never one model on four cards; each pair is its own machine.';
  return 'Not measured on this configuration.';
}

/** Natural width of a cell's content (without padding). */
function contentWidth(c: Cell, numSize: number): number {
  const head = textWidth(CONFIG_HEADING[c.hw], 'sans600', 17) + headBadges(c).reduce((w, b) => w + 8 + textWidth(b.label, 'sans400', 12) + 18, 0);
  const badges = statusBadge(c).reduce((w, b) => w + 6 + textWidth(b.label, 'sans400', 12) + 18 + (b.dot ? 11 : 0), -6);
  if (c.head) {
    const rows = numRows(c.head).map((r) => spansWidth(numSpans(r, numSize)));
    return Math.max(head, badges, ...rows, textWidth(caption(c.head), 'mono400', 12));
  }
  return Math.max(head, badges);
}

function cellHeight(c: Cell, w: number): number {
  let h = PAD_Y + H_HEAD;
  if (statusBadge(c).length) h += GAP + H_BADGE;
  if (c.head) {
    h += numRows(c.head).length * (GAP + 26 * 1.2) + GAP + H_CAP;
  } else if (c.kind === 'none') {
    h += GAP + wrap(noteText(c), 'sans400', 16, w - 2 * PAD_X - 2).length * 16 * 1.55;
  } else {
    h += GAP + wrap(noteText(c), 'sans400', NOTE_SIZE, w - 2 * PAD_X - 2).length * NOTE_SIZE * NOTE_LH;
  }
  return h + PAD_Y;
}

function drawCell(c: Cell, x: number, top: number, w: number, h: number, numSize: number): string {
  const stroke: Tone | 'border' =
    c.kind === 'measured' || c.kind === 'ran' ? 'green' : c.kind === 'spill' ? 'amber' : c.kind === 'tried' ? (statusBadge(c)[0]?.tone ?? 'muted') : 'border';
  let s = c.kind === 'none'
    ? boxInside(x, top, w, h, { stroke: 'border', rx: 10, dash: '5 4' })
    : boxInside(x, top, w, h, { fill: 'panel', stroke: stroke === 'border' ? 'border' : stroke, rx: 10 });
  const x0 = x + 1 + PAD_X;
  let y = top + PAD_Y;
  const heading = CONFIG_HEADING[c.hw];
  s += textTop(x0, y, 1.3, heading, { face: 'sans600', size: 17, fill: 'text' });
  const hb = headBadges(c);
  if (hb.length) s += badgeRow(x0 + textWidth(heading, 'sans600', 17) + 8, y + (H_HEAD - H_BADGE) / 2, hb).svg;
  y += H_HEAD;
  const sb = statusBadge(c);
  if (sb.length) {
    y += GAP;
    s += badgeRow(x0, y, sb).svg;
    y += H_BADGE;
  }
  if (c.head) {
    for (const row of numRows(c.head)) {
      y += GAP;
      s += spans(x0, baseline(y, numSize, 1.2, 'mono400') + (26 - numSize) / 2, numSpans(row, numSize));
      y += 26 * 1.2;
    }
    y += GAP;
    s += textTop(x0, y, 1.4, caption(c.head), { face: 'mono400', size: 12, fill: 'muted' });
  } else {
    y += GAP;
    const size = c.kind === 'none' ? 16 : NOTE_SIZE;
    const lh = c.kind === 'none' ? 1.55 : NOTE_LH;
    for (const ln of wrap(noteText(c), 'sans400', size, w - 2 * PAD_X - 2)) {
      s += textTop(x0, y, lh, ln, { face: 'sans400', size, fill: 'muted' });
      y += size * lh;
    }
  }
  return s;
}

// ---------------------------------------------------------------------------
// Verdict paragraph: Inter, with numbers, dates and ids set in mono (DESIGN.md: mono for numbers)

const NUMERIC_WORD = /^[([]?(?:[~+\-−]?\d[\d.,:/×x%\-–]*|\d{4}-\d{2}-\d{2})[)\].,;:]?[)\].,;:]?$/;

interface Word { s: string; face: FaceKey; size: number }
type Lines = Word[][] & { truncated?: boolean };
function words(textIn: string, size: number): Word[] {
  return textIn.split(/\s+/).filter(Boolean).map((s) => (NUMERIC_WORD.test(s) ? { s, face: 'mono400', size: size - 1 } : { s, face: 'sans400', size }));
}
const wordW = (w: Word) => textWidth(w.s, w.face, w.size);
const space = (size: number) => textWidth(' ', 'sans400', size);

function wrapWords(ws: Word[], maxW: number, size: number): Lines {
  const lines: Lines = [];
  let cur: Word[] = [];
  let curW = 0;
  for (const w of ws) {
    const add = (cur.length ? space(size) : 0) + wordW(w);
    if (cur.length && curW + add > maxW) {
      lines.push(cur);
      cur = [w];
      curW = wordW(w);
    } else {
      cur.push(w);
      curW += add;
    }
  }
  if (cur.length) lines.push(cur);
  return lines;
}

/** The verdict, cut at a sentence end (else a word) with an ellipsis to fit `maxLines`, then its date. */
function fitVerdict(summary: string, asOf: string | null, maxW: number, maxLines: number, size: number): Lines {
  const tail = asOf ? ` (as of ${asOf})` : '';
  const tryText = (t: string) => wrapWords(words(t + tail, size), maxW, size);
  let lines = tryText(summary);
  if (lines.length <= maxLines) return lines;
  const cut = (t: string) => {
    const l = tryText(t);
    l.truncated = true;
    return l;
  };
  // A sentence ends at . ! or ? followed by a space and a capital (so 3.5-bit or vLLM 0.29 never split one).
  const sentences = summary.split(/(?<=[.!?])\s+(?=[A-Z])/);
  for (let n = sentences.length - 1; n >= 1; n--) {
    lines = cut(`${sentences.slice(0, n).join(' ').trim()} …`);
    if (lines.length <= maxLines) return lines;
  }
  const ws = summary.split(/\s+/);
  for (let n = ws.length - 1; n >= 1; n--) {
    lines = cut(`${ws.slice(0, n).join(' ')} …`);
    if (lines.length <= maxLines) return lines;
  }
  const l: Lines = tryText('').slice(0, maxLines);
  l.truncated = true;
  return l;
}

function drawWords(x: number, top: number, line: Word[], size: number): string {
  const list: Span[] = line.map((w, i) => ({ s: w.s, face: w.face, size: w.size, fill: 'text', dx: i ? space(size) : 0 }));
  return spans(x, baseline(top, size, 1.55, 'sans400'), list);
}

// ---------------------------------------------------------------------------

/** The badges of the model header, as on the model page. */
function modelBadges(m: Model): { label: string; tone: Tone; dot?: boolean }[] {
  const st = m.verdict.status || 'unknown';
  const out: { label: string; tone: Tone; dot?: boolean }[] = [
    { label: STATUS_LABEL[st] ?? st, tone: (STATUS_TONE[st] ?? 'muted') as Tone, dot: true },
    { label: m.licence?.name || 'unknown licence', tone: 'muted' },
    ...(m.licence?.flags ?? []).map((fl) => ({ label: fl, tone: 'amber' as Tone })),
  ];
  if (m.access && m.access !== 'unknown') out.push({ label: m.access, tone: m.access === 'gated' ? 'amber' : 'green' });
  if (m.category) out.push({ label: m.category, tone: 'muted' });
  if (m.arch && m.arch !== 'unknown') out.push({ label: m.arch, tone: 'muted' });
  if (isForge(m)) out.push({ label: 'private fine-tune', tone: 'amber' });
  return out;
}

function paramsText(m: Model): string | null {
  const parts: string[] = [];
  if (isNum(m.params_b_total)) parts.push(`${fmtNum(m.params_b_total)} B total`);
  if (isNum(m.params_b_active)) parts.push(`${fmtNum(m.params_b_active)} B active`);
  return parts.length ? parts.join(' · ') : null;
}

export function footerText(): string {
  return `${REPO_NAME} · data as of ${dataAsOf() ?? 'undated'} · ${VERSION_LABEL}`;
}

export function modelOgSvg(m: Model): string {
  assertSiteRules();
  const W = OG_W, H = OG_H;
  const bodyX = 58, bodyW = 1084;
  let s = rect(0, 0, W, H, { fill: 'bg' });
  s += boxInside(28, 28, 1144, 574, { fill: 'bg', stroke: 'border', sw: 2, rx: 16 });
  s += consoleBar(30, 30, 1140, '3090fe · model', m.last_tested ? `last tested ${m.last_tested}` : null);

  // name, shrunk to fit one line
  let y = 30 + 38 + 22;
  let ts = 46;
  while (ts > 28 && textWidth(m.name, 'sans800', ts, -0.015 * ts) > bodyW) ts -= 1;
  s += textTop(bodyX, y, 1.1, m.name, { face: 'sans800', size: ts, fill: 'text', ls: -0.015 * ts });
  y += ts * 1.1 + 12;

  // id row
  const params = paramsText(m);
  s += textTop(bodyX, y, 1.45, m.model_id, { face: 'mono400', size: 16, fill: 'muted' });
  if (params) s += textTop(bodyX + textWidth(m.model_id, 'mono400', 16) + 14, y, 1.45, params, { face: 'mono400', size: 16, fill: 'muted' });
  y += 16 * 1.45 + 12;

  // badges
  s += badgeRow(bodyX, y, modelBadges(m)).svg;
  y += 22 + 12;

  // configuration cells
  const cells = cellsOf(m);
  const gap = 14;
  const avail = bodyW - gap * (cells.length - 1);
  let numSize = 26;
  let widths: number[] = [];
  for (; numSize >= 20; numSize -= 2) {
    const natural = cells.map((c) => (c.kind === 'none' ? 0 : Math.max(c.kind === 'measured' || c.kind === 'spill' ? 300 : 260, contentWidth(c, numSize) + 2 * PAD_X + 2)));
    const flex = cells.filter((c) => c.kind === 'none').length;
    const fixed = natural.reduce((a, b) => a + b, 0);
    if (fixed + flex * 200 <= avail || numSize === 20) {
      const rest = avail - fixed;
      widths = flex
        ? natural.map((w, i) => (cells[i].kind === 'none' ? rest / flex : w))
        : natural.map((w) => w + rest / cells.length);
      break;
    }
  }
  const heights = cells.map((c, i) => cellHeight(c, widths[i]));
  const filled = cells.map((c, i) => (c.kind === 'none' ? 0 : heights[i]));
  const rowH = Math.max(...filled, 0);
  let cx = bodyX;
  cells.forEach((c, i) => {
    const h = c.kind === 'none' ? heights[i] : rowH;
    s += drawCell(c, cx, y, widths[i], h, numSize);
    cx += widths[i] + gap;
  });
  y += Math.max(rowH, ...heights) + 12;

  // footer (fixed at the bottom of the console body)
  const footTop = 561;
  const b = brand(bodyX, footTop);
  s += b.svg;
  s += text(bodyX + b.w + 12, baseline(footTop + 1.5, 12, 1.4, 'mono400'), footerText(), { face: 'mono400', size: 12, fill: 'muted' });

  // verdict box, between the cells and the footer: 16 px if it fits whole, else 15 px, cut at a sentence
  const summary = (m.verdict.summary ?? '').trim();
  const room = footTop - 12 - y - 20;
  if (summary && room >= 15 * 1.55) {
    let lines: Word[][] = [];
    let size = 16;
    for (const sz of [16, 15]) {
      size = sz;
      const maxLines = Math.min(4, Math.floor(room / (sz * 1.55)));
      lines = fitVerdict(summary, m.verdict.as_of ?? null, bodyW - 2 * PAD_X - 2, maxLines, sz);
      if (!lines.truncated) break;
    }
    const lineH = size * 1.55;
    const bh = lines.length * lineH + 20;
    s += boxInside(bodyX, y, bodyW, bh, { fill: 'panel', stroke: 'border', rx: 8 });
    lines.forEach((ln, i) => (s += drawWords(bodyX + 1 + PAD_X, y + 10 + i * lineH, ln, size)));
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${s}</svg>`;
}

/** Alt text of the card: every value drawn, with its date (DESIGN.md: alt text tells the whole figure). */
export function modelOgAlt(m: Model): string {
  const parts = cellsOf(m).map((c) => {
    const name = CONFIG_HEADING[c.hw].toLowerCase();
    if (c.head) {
      const rows = numRows(c.head).map((r) => `${r.value} ${r.unit} ${r.label}`).join(', ');
      return `${name}: ${c.kind === 'spill' ? 'runs with part of the model in system RAM' : 'fits'}, ${rows} (${caption(c.head)})`;
    }
    if (c.kind === 'ran') return `${name}: ran, no headline figure`;
    if (c.kind === 'tried') return `${name}: tried, never ended ok`;
    return `${name}: ${noteText(c).replace(/\.$/, '').replace(/^N/, 'n')}`;
  });
  return `${m.name} (${m.model_id}) on RTX 3090 Founders Edition cards. ${parts.join('; ')}. Data as of ${dataAsOf() ?? 'undated'}, ${VERSION_LABEL}.`;
}

