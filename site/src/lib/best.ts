/**
 * The best-results page: for one card and for one NVLink pair, the highest
 * values measured under the stated rules below, each read from one run record
 * (never averaged or merged), or from the agent-loop ranking where the lab
 * kept no run record; for the two pairs, what their hardware record and the
 * two-pairs comparison hold. The rules are coded here, and the page shows their
 * text (BEST_RULES). A value whose record is missing comes back null and is
 * not shown.
 */
import {
  benchById,
  compareHeadline,
  headlinesOnConfig,
  isABTreatment,
  isEnglishTwin,
  isNum,
  isRefusalOnly,
  modelById,
  rankings,
  runById,
  runDate,
  runs,
  soloTokS,
  topologyKnown,
  usesSpeculation,
} from './data';
import type { Model, Ranking, RankingRow, Run } from './data';
import { topoLabel } from './site';

export const BEST_HW = ['1x3090fe', '2x3090fe-nvlink'] as const;
/** GPU count of each configuration, as the agent-loop ranking records it (extra.gpus). */
export const HW_GPUS: Record<string, number> = { '1x3090fe': 1, '2x3090fe-nvlink': 2 };

/** Size classes by total parameters (the model record's params_b_total), lower bound included. */
export const SIZE_CLASSES = [
  { id: 'small', label: 'under 10B parameters', min: 0, max: 10 },
  { id: 'mid', label: '10B to under 40B', min: 10, max: 40 },
  { id: 'large', label: '40B and more', min: 40, max: Infinity },
] as const;
export type SizeClass = (typeof SIZE_CLASSES)[number];

/** The rules, word for word as the page shows them. */
export const BEST_RULES = [
  'Only run records with status ok, not copies of earlier runs, with a topology known from their launch record, on that configuration; never an average.',
  'Largest model: the most total parameters among those runs, separately for runs whose record says every weight was on the cards and runs with part of the model in system RAM; a run whose record does not say is left out. Its speed is that of its own speed run chosen by the headline-run order (pinned engine, house protocol, most repetitions, most recent), with any number of server slots; English twins, speculative-decoding and A/B treatment arms are left out.',
  'Single stream and aggregate: the headline run of each model (the headline-run rule of the configuration pages, which leaves out runs that served the house protocol\'s eight requests one after another), the highest value in each size class. The aggregate is read only where eight requests were served at once by more than one slot.',
  'Agent loop: the ranking of code-loop/v1 (six frozen tasks, score = the fewest passes over a row\'s runs) for rows on that number of cards, then the most tasks passed in one loop among run records dated after its last re-ordering (a record may hold several loops), with every such loop of that model and build on that configuration.',
  'Top score per bench: the highest row of the latest ranking of each bench whose run was on that configuration, as on the configuration pages. Scores of different benches are not comparable.',
] as const;

export function paramsOf(modelId: string): number | null {
  const v = modelById().get(modelId)?.params_b_total;
  return isNum(v) ? v : null;
}
export function activeOf(modelId: string): number | null {
  const v = modelById().get(modelId)?.params_b_active;
  return isNum(v) ? v : null;
}
export function sizeClassOf(modelId: string): SizeClass | null {
  const p = paramsOf(modelId);
  if (p === null) return null;
  return SIZE_CLASSES.find((c) => p >= c.min && p < c.max) ?? null;
}

/** Part of the model was held in system RAM (an offload size, or the spill flag): true; every weight on the cards: false; not recorded: null. */
export function inSystemRam(r: Run): boolean | null {
  if (r.topology.ram_spill === true || (isNum(r.topology.cpu_offload_gb) && r.topology.cpu_offload_gb > 0)) return true;
  return r.topology.ram_spill === false ? false : null;
}

/** The topology label of the site, with expert parallelism when the record says so. */
export function topoText(r: Run): string {
  return `${topoLabel(r.topology)}${r.topology.expert_parallel === true ? ' · expert parallel' : ''}`;
}

/** What a run's notes say about its place in its campaign: added after the predeclared list, or run in the day window. */
export function addedTag(r: Run): string | null {
  const n = (r.parse_notes ?? []).join(' ');
  if (/day window/i.test(n)) return 'day window';
  if (/not in the night's predeclared list/i.test(n)) return 'added after the predeclared list';
  return null;
}

/** Rule 1: the run records this page reads on a configuration. */
export function bestScope(hw: string): Run[] {
  return runs().filter((r) => r.hardware === hw && r.status === 'ok' && !r.duplicate_of && topologyKnown(r) && !isRefusalOnly(r));
}

/** A run whose single-stream figure may stand for its model's speed here (any slot count). */
function speedEligible(r: Run): boolean {
  return soloTokS(r) !== null && r.protocol !== 'speed-house/v1-fixedlen' && !usesSpeculation(r) && !isABTreatment(r) && !isEnglishTwin(r);
}

export function slotsOf(r: Run): number | null {
  const a = r.engine_args ?? {};
  for (const k of ['parallel_slots', 'max_num_seqs']) if (isNum(a[k])) return a[k] as number;
  return null;
}

export interface Largest {
  model: Model | undefined;
  model_id: string;
  params: number;
  runs: Run[];
  speed: Run | null;
}

/** Rule 2: the largest model, all weights on the cards (ram false) or part in system RAM (ram true). */
export function largestModel(hw: string, ram: boolean): Largest | null {
  const list = bestScope(hw).filter((r) => inSystemRam(r) === ram && paramsOf(r.model_id) !== null);
  if (!list.length) return null;
  const best = list.reduce((a, b) => (paramsOf(b.model_id)! > paramsOf(a.model_id)! || (paramsOf(b.model_id)! === paramsOf(a.model_id)! && b.model_id < a.model_id) ? b : a));
  const mine = list.filter((r) => r.model_id === best.model_id);
  const speed = mine.filter(speedEligible).sort(compareHeadline)[0] ?? null;
  return { model: modelById().get(best.model_id), model_id: best.model_id, params: paramsOf(best.model_id)!, runs: mine, speed };
}

export interface ClassBest { cls: SizeClass; model_id: string; run: Run; value: number }

/** Rule 3: per size class, the headline run with the highest single-stream speed. */
export function fastestSolo(hw: string): ClassBest[] {
  const heads = headlinesOnConfig(hw).filter(({ run }) => bestScope(hw).includes(run) && soloTokS(run) !== null);
  return SIZE_CLASSES.flatMap((cls) => {
    const top = heads
      .filter(({ model_id }) => sizeClassOf(model_id)?.id === cls.id)
      .sort((a, b) => soloTokS(b.run)! - soloTokS(a.run)! || a.model_id.localeCompare(b.model_id))[0];
    return top ? [{ cls, model_id: top.model_id, run: top.run, value: soloTokS(top.run)! }] : [];
  });
}

/** Rule 3: per size class, the headline run with the highest aggregate at eight concurrent requests, served by more than one slot. */
export function highestAggregate(hw: string): ClassBest[] {
  const heads = headlinesOnConfig(hw).filter(({ run }) =>
    bestScope(hw).includes(run) && isNum(run.metrics.agg_tok_s) && run.metrics.agg_concurrency === 8 && (slotsOf(run) === null || slotsOf(run)! > 1));
  return SIZE_CLASSES.flatMap((cls) => {
    const top = heads
      .filter(({ model_id }) => sizeClassOf(model_id)?.id === cls.id)
      .sort((a, b) => (b.run.metrics.agg_tok_s as number) - (a.run.metrics.agg_tok_s as number) || a.model_id.localeCompare(b.model_id))[0];
    return top ? [{ cls, model_id: top.model_id, run: top.run, value: top.run.metrics.agg_tok_s as number }] : [];
  });
}

/** Models with a headline run on the configuration but no parameter count: left out of the size classes, and counted. */
export function unclassified(hw: string): number {
  return headlinesOnConfig(hw).filter(({ model_id }) => sizeClassOf(model_id) === null).length;
}

export const LOOP_RANKING_ID = 'code-loop-v1--rank';
export const loopRanking = (): Ranking | undefined => rankings().find((k) => k.ranking_id === LOOP_RANKING_ID);

/** Rule 4, first part: the top rows of the agent-loop ranking on that number of cards (every row tied at the top score). */
export function loopRankingTop(hw: string): { ranking: Ranking; rows: RankingRow[] } | null {
  const k = loopRanking();
  if (!k) return null;
  const mine = k.rows.filter((row) => row.extra?.gpus === HW_GPUS[hw] && isNum(row.score));
  if (!mine.length) return null;
  const top = Math.max(...mine.map((row) => row.score as number));
  return { ranking: k, rows: mine.filter((row) => row.score === top) };
}

/** The date the agent-loop ranking was generated (its last re-ordering). */
export const loopRankingDate = (): string | null => {
  const g = loopRanking()?.generated_at;
  return typeof g === 'string' ? g.slice(0, 10) : null;
};

/** One agent loop held by a run record: its run, its pass count, its task count, and its index among the run's loops. */
export interface Loop { run: Run; passed: number; total: number; pass: number | null }

/**
 * The agent loops of a run record, whatever its metric scheme: fresh_pass<N>_tasks_passed out of tasks_per_pass
 * (several loops in one record, 16 October), else agent_tasks_passed out of agent_tasks_total or agent_task_cases.
 */
export function loopsOf(r: Run): Loop[] {
  const m = r.metrics;
  if (isNum(m.fresh_passes) && isNum(m.tasks_per_pass)) {
    const out: Loop[] = [];
    for (let i = 1; i <= (m.fresh_passes as number); i++) {
      const v = m[`fresh_pass${i}_tasks_passed`];
      if (isNum(v)) out.push({ run: r, passed: v, total: m.tasks_per_pass as number, pass: i });
    }
    return out;
  }
  const total = [m.agent_tasks_total, m.agent_task_cases, m.tasks_per_pass].find(isNum);
  return isNum(m.agent_tasks_passed) && isNum(total) ? [{ run: r, passed: m.agent_tasks_passed as number, total: total as number, pass: null }] : [];
}

export interface LoopBest { passed: number; total: number; groups: { model_id: string; build_id: string | null; loops: Loop[] }[] }

/** Rule 4, second part: loops of run records dated after the ranking's date, the most tasks passed in one loop. */
export function loopRecordsBest(hw: string): LoopBest | null {
  const since = loopRankingDate();
  const loops = bestScope(hw).filter((r) => !since || (runDate(r) ?? '') > since).flatMap(loopsOf);
  if (!loops.length) return null;
  const passed = Math.max(...loops.map((l) => l.passed));
  const top = loops.filter((l) => l.passed === passed);
  const keys = [...new Set(top.map((l) => `${l.run.model_id}|${l.run.build_id ?? ''}`))].sort();
  const groups = keys.map((key) => {
    const [model_id, build] = key.split('|');
    const all = loops
      .filter((l) => l.run.model_id === model_id && (l.run.build_id ?? '') === build)
      .sort((a, b) => (a.run.started_at ?? '').localeCompare(b.run.started_at ?? '') || a.run.run_id.localeCompare(b.run.run_id) || (a.pass ?? 0) - (b.pass ?? 0));
    return { model_id, build_id: build || null, loops: all };
  });
  return { passed, total: top[0].total, groups };
}

/**
 * The night of 17 to 18 October: four results the page reads together, each
 * from the run records named here (the selection is the page's; every figure
 * comes from those records).
 */
export const NIGHT = {
  oneCard: '2026-10-18-night-3/gpt-oss-120b-one-card',
  oneCardLoop: '2026-10-18-night-3/gpt-oss-120b-one-card-loop',
  pairOneSlot: '2026-10-18-night-3/gpt-oss-120b-pair',
  pairFourSlots: '2026-10-18-night-3/gpt-oss-120b-np4',
  pairLoopLow: '2026-10-18-night-3/gpt-oss-120b-loop-effort-low',
  nextOne: '2026-10-18-night-3/qwen3-coder-next-pair',
  nextFour: '2026-10-18-night-3/qwen3-coder-next-np4',
  nextEight: '2026-10-18-night-3/qwen3-coder-next-np8',
  thinkOff: '2026-10-18-night-3/gpt-oss-120b-pair',
  thinkOn1024: '2026-10-18-night-3/gpt-oss-120b-reasoning-on1024-t0',
  thinkOn2048: '2026-10-18-night-3/gpt-oss-120b-reasoning-on2048',
  thinkOnNoBudget: '2026-10-18-night-3/gpt-oss-120b-reasoning-on',
  adapterV1: '2026-10-18-night-3/qwen3-coder-adapter-v1-loop',
  adapterV2: ['2026-10-18-night-3/qwen3-coder-adapter-v2-loop', '2026-10-18-night-3/qwen3-coder-adapter-v2-loop-r2', '2026-10-18-night-3/qwen3-coder-adapter-v2-loop-r3'],
  /** the stock-parser loop has no run record of its own: its count is in the adapters note and the model's verdict */
  adapterModel: 'qwen/qwen3-coder-30b-a3b',
  adaptersDoc: 'methodology/ADAPTERS.md',
} as const;

export const nightRun = (id: string): Run | null => runById().get(id) ?? null;
export function metric(id: string, key: string): number | null {
  const v = runById().get(id)?.metrics[key];
  return isNum(v) ? v : null;
}
export function arg(id: string, key: string): number | null {
  const v = runById().get(id)?.engine_args?.[key];
  return isNum(v) ? v : null;
}

/**
 * The stock-parser loop, which has no run record: its count and server context, read from the model's verdict
 * ("... agent loop completed 1/6 ... stock qwen3_coder parser at a 16,384-token context"), or null.
 */
export function stockLoop(): { passed: number; total: number; context: number } | null {
  const s = modelById().get(NIGHT.adapterModel)?.verdict.summary ?? '';
  const m = /agent loop completed (\d+)\/(\d+)[^.]*?stock \S+ parser at a ([\d,]+)-token context/.exec(s);
  return m ? { passed: Number(m[1]), total: Number(m[2]), context: Number(m[3].replace(/,/g, '')) } : null;
}

/** The number of tasks of the agent-loop bench (its record's n_items). */
export const loopTasks = (): number | null => {
  const v = benchById().get('code-loop/v1')?.n_items;
  return isNum(v) ? v : null;
};

/**
 * The context an agent loop ran at, in tokens: the client's window; else, in a record of one launch (kind quality),
 * the server's per-slot or total context. A speed-and-quality record's server context is its speed launch's, not
 * necessarily its loop's (the server may have been relaunched for the loop): null, and its notes say.
 */
export function loopContext(r: Run): { value: number; kind: 'Cline window' | 'server' } | null {
  const a = r.engine_args ?? {};
  if (isNum(a.client_context_window)) return { value: a.client_context_window as number, kind: 'Cline window' };
  if (r.kind !== 'quality') return null;
  for (const k of ['ctx_per_slot', 'ctx_size', 'max_model_len']) if (isNum(a[k])) return { value: a[k] as number, kind: 'server' };
  return null;
}

/** The model also has an ok run record on one card (said beside a pair's largest model). */
export function alsoOnOneCard(modelId: string): Run | null {
  return bestScope('1x3090fe').find((r) => r.model_id === modelId) ?? null;
}

/** Fixed one-decimal display for a value with more than one decimal (84.5333 → 84.5); other values as stored. */
export function oneDecimal(v: unknown): number | undefined {
  return isNum(v) && Math.abs(Math.round(v * 10) - v * 10) > 1e-9 ? 1 : undefined;
}
