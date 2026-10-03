/**
 * What the home console and the configuration tiles say about each of the
 * three configurations: distinct-run counts (copies apart), models, headline
 * figures, and the figures of the two-pairs comparison. Read from data/ only;
 * a figure whose record is missing comes back null and is not shown.
 */
import {
  comparisonRow,
  hardware,
  hardwareById,
  headlineRun,
  headlinesOnConfig,
  isNum,
  modelById,
  modelName,
  runById,
  runCount,
  runsOnConfig,
} from './data';
import type { ComparisonRow, Hardware, Run } from './data';

export const CONFIG_SHORT: Record<string, { tag: string; sub: string }> = {
  '1x3090fe': { tag: '1×', sub: 'one card' },
  '2x3090fe-nvlink': { tag: '2×', sub: 'one NVLink pair' },
  '2x2x3090fe-nvlink': { tag: '2×2', sub: 'two pairs, side by side' },
};

/** "one card · 24 GB", from the hardware record (the two-pairs line names no pool: there is none of 96 GB). */
export function configSub(h: Hardware): string {
  const s = CONFIG_SHORT[h.hardware_id]?.sub ?? h.hardware_id;
  return h.hardware_id !== '2x2x3090fe-nvlink' && isNum(h.vram_gb_total) ? `${s} · ${h.vram_gb_total} GB` : s;
}

/** Link a comparison figure to its first published run, else its evidence. */
export const rowSrc = (r: ComparisonRow) => ({ run: r.run_ids.find((id) => runById().has(id)) ?? null, evidence: r.evidence[0] ?? null });
/** A figure with no evidence of its own links to the comparison record that holds it. */
export const rowSrcIn = (r: ComparisonRow, compId: string) =>
  r.evidence.length === 0 ? { run: null, evidence: `data/comparisons/${compId}.json` } : rowSrc(r);

export const twoPairs = () => ({
  busy: comparisonRow('two-pairs-parallel', '3D generation bench: cards generating', 'max_cards_busy'),
  maxGpus: comparisonRow('two-pairs-parallel', 'Every recorded launch line', 'max_gpus_per_server'),
  single: comparisonRow('two-pairs-parallel', 'Runs of one model across all four cards', 'single_model_runs'),
});

export interface ConfigSummary {
  h: Hardware;
  runs: number;
  copies: number;
  models: number;
  headlines: number;
  /** Two pairs only: runs of one model across the four cards (from the comparison, else the hardware record). */
  singleModelRuns: number | null;
  singleModelRow: ComparisonRow | null;
}

export function configSummaries(): ConfigSummary[] {
  const pairs = twoPairs();
  return hardware().map((h) => {
    const list = runsOnConfig(h.hardware_id);
    const rc = runCount(list);
    return {
      h,
      runs: rc.distinct,
      copies: rc.copies,
      models: new Set(list.map((r) => r.model_id)).size,
      headlines: headlinesOnConfig(h.hardware_id).length,
      singleModelRuns: h.hardware_id === '2x2x3090fe-nvlink' ? (pairs.single?.value ?? (isNum(h.single_model_runs) ? h.single_model_runs : null)) : null,
      singleModelRow: h.hardware_id === '2x2x3090fe-nvlink' ? pairs.single : null,
    };
  });
}

/**
 * Two pairs: runs of one model across all four cards (the two-pairs comparison,
 * else the hardware record), and the row it comes from. When it is 0, a model's
 * two-pairs cell says so ("Two pairs: never one model on four cards") instead of
 * a generic "not measured".
 */
export function fourCardRuns(): { value: number | null; row: ComparisonRow | null } {
  const row = twoPairs().single;
  const h = hardwareById('2x2x3090fe-nvlink');
  return { value: row?.value ?? (h && isNum(h.single_model_runs) ? h.single_model_runs : null), row };
}
export const NEVER_FOUR = 'Two pairs: never one model on four cards.';

/** The one-card finding: the headline run of Gemma 4 26B-A4B on one card (what fits, how fast, what it reserved). */
export const ONE_CARD_MODEL = 'google/gemma-4-26b-a4b-it';
export function oneCardHeadline(): { run: Run; name: string; vram: number | null; vramKind: string | null } | null {
  if (!hardwareById('1x3090fe')) return null;
  const run = headlineRun(ONE_CARD_MODEL, '1x3090fe');
  if (!run) return null;
  const v = run.vram?.mib_per_gpu;
  return {
    run,
    name: modelById().get(ONE_CARD_MODEL)?.name ?? modelName(ONE_CARD_MODEL),
    vram: Array.isArray(v) && v.length === 1 && isNum(v[0]) ? v[0] : null,
    vramKind: typeof run.vram?.kind === 'string' ? run.vram.kind : null,
  };
}
