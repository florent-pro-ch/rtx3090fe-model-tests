/**
 * URL and formatting helpers shared by every page and component.
 * All internal links go through href() so that the base path
 * (/rtx3090fe-model-tests) and the trailing slash are always right.
 */
import { githubUrl, isNum, modelSlug, readRepoText, repoPathExists, runById } from './data';

const BASE = (import.meta.env.BASE_URL || '/').replace(/\/+$/, '');

function encodePath(p: string): string {
  return p
    .split('/')
    .map((s) => encodeURIComponent(s).replace(/%40/g, '@').replace(/%2B/gi, '+'))
    .join('/');
}

/** Internal link: base + path, with a trailing slash unless the path names a file. */
export function href(p = '/'): string {
  const clean = p.replace(/^\/+/, '');
  if (!clean) return `${BASE}/`;
  const [pathPart, hash = ''] = clean.split('#');
  const isFile = /\.(json|xml|txt|svg|png|md|html|css|js|csv)$/i.test(pathPart);
  const withSlash = isFile || pathPart.endsWith('/') ? pathPart : `${pathPart}/`;
  return `${BASE}/${encodePath(withSlash)}${hash ? `#${hash}` : ''}`;
}

export const runHref = (runId: string) => href(`runs/${runId}/`);
export const modelHref = (slugOrId: string) => href(`models/${slugOrId.includes('/') ? modelSlug(slugOrId) : slugOrId}/`);
export const benchHref = (benchId: string) => href(`benches/${benchId}/`);
export const rankingHref = (id: string) => href(`rankings/${id}/`);
export const compareHref = (id: string) => href(`compare/${id}/`);
export const campaignHref = (id: string) => href(`campaigns/${id}/`);
export const configHref = (hw: string) => href(`configs/${hw}/`);
export const evidenceHref = (repoPath: string) => githubUrl(repoPath);

/**
 * Where an `evidence` string points: a URL, a run of this site, or a file of
 * the repository on GitHub, or the rig page for "rig description". Any other
 * plain description has no link and is shown as text.
 */
export function evidenceLink(e: string): string | null {
  const s = e.trim();
  // Facts about the rig itself are documented on the rig page.
  if (/^rig description$/i.test(s) || /^data\/(hardware\/)?rig\.json$/i.test(s)) return href('rig/#host');
  if (/^https?:\/\//i.test(s)) return s;
  if (runById().has(s)) return runHref(s);
  if (repoPathExists(s)) return githubUrl(s);
  if (/^(evidence|data|benches|methodology|figures|schema|harness|tools)\//.test(s)) return githubUrl(s);
  return null;
}

/** Unit of a metric from its key suffix (the data puts the unit in the key). */
export function unitForKey(key: string): string {
  // Statistic suffixes do not change the unit: solo_tok_s_max, solo_ttft_ms_median...
  const k = key.toLowerCase().replace(/_(mean|median|min|max|p50|p90|p95|p99|avg|std)$/, '');
  const table: [RegExp, string][] = [
    // energy of a speed pass (nvml-energy/v1): solo_tok_per_j, agg_energy_j, en_solo_energy_j...
    [/_tok_per_j$/, 'tok/J'],
    [/_energy_j$/, 'J'],
    [/_tok_s$/, 'tok/s'],
    [/_tok_per_s$/, 'tok/s'],
    [/_it_s$/, 'it/s'],
    [/_ms$/, 'ms'],
    [/_mib$/, 'MiB'],
    [/_gib$/, 'GiB'],
    [/_gb$/, 'GB'],
    [/_mb$/, 'MB'],
    [/_w$/, 'W'],
    [/_pct$/, '%'],
    [/_percent$/, '%'],
    [/_s$/, 's'],
    [/_seconds$/, 's'],
    [/_tokens$/, 'tokens'],
    [/^params_b_/, 'B'],
    [/_b$/, 'B'],
  ];
  for (const [re, u] of table) if (re.test(k)) return u;
  return '';
}

/** Number formatting: en-US grouping, never rounding below 4 decimals (no invented precision either way). */
export function fmtNum(v: number, digits?: number): string {
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: digits ?? 4,
    minimumFractionDigits: digits ?? 0,
  }).format(v);
}

const KEY_LABEL: Record<string, string> = {
  vram_kind: 'VRAM reading',
  model_id: 'Model',
  run_id: 'Run',
  run_ids: 'Runs',
  build_id: 'Build',
  parallel_slots: 'Slots',
  concurrency: 'Requests at once',
  n_passes: 'Passes',
  tie_break: 'Tie broken by',
  duel_vs_anchor: 'Duel against the anchor',
  same_lineage: "Same lineage as the table's judge",
  harness_rated: 'Rated by the harness',
  not_rated_reason: 'Why not rated',
  items_not_graded: 'Items not graded',
  items_not_graded_reason: 'Why not graded',
  not_graded: 'Not graded',
  n_not_graded: 'Not graded',
  rank_interval: "Rank range across the two judges (this table's numbering)",
  second_judge: "The other judge's order",
  rank_counted_on: 'Second rank counted on',
  table_judge_rank_on_same_rows: "Rank among the same rows under this table's judge",
  rated_in_campaign: 'Rated in campaign',
  lora_r: 'LoRA rank',
  lora_alpha: 'LoRA alpha',
  max_seq_len: 'Maximum sequence length',
  lr: 'Learning rate',
};

export function humanKey(key: string): string {
  if (KEY_LABEL[key]) return KEY_LABEL[key];
  return key
    .replace(/_(tok_s|ms|mib|gib|gb|mb|w|pct|s|it_s)(?=(_(mean|median|min|max))?$)/i, '')
    .replace(/_/g, ' ')
    .replace(/^./, (c) => c.toUpperCase());
}

export const HW_SHORT: Record<string, string> = {
  '1x3090fe': '1× 3090 FE',
  '2x3090fe-nvlink': '2× 3090 FE NVLink',
  '2x2x3090fe-nvlink': '2 × (2× 3090 FE NVLink)',
  'cpu-only': 'CPU only (no card)',
  unknown: 'unknown',
};

export function hwShort(id: string): string {
  return HW_SHORT[id] ?? id;
}

/** Display names of the engines (the data uses lower-case ids). */
const ENGINE_NAME: Record<string, string> = {
  vllm: 'vLLM',
  llamacpp: 'llama.cpp',
  'llama.cpp': 'llama.cpp',
  'llama-cpp': 'llama.cpp',
  comfyui: 'ComfyUI',
  transformers: 'Transformers',
};

/**
 * The one engine label of the site: display name and version ("vLLM 0.29.0",
 * "llama.cpp b10830"); "version not recorded" when the run names no version.
 * With `prePin`, a run on an engine older than the pins says so in the label
 * itself ("vLLM 0.26.0 pre-pin"), for places that show no pre-pin badge.
 */
export function engineLabel(e: { name: string; version?: string | null; pre_pin?: boolean | null }, opts: { prePin?: boolean } = {}): string {
  const name = ENGINE_NAME[e.name.toLowerCase()] ?? e.name;
  const known = name !== 'other' && name !== 'unknown';
  const base = e.version ? `${name} ${e.version}` : known && e.pre_pin === true ? `${name} (version not recorded)` : name;
  return opts.prePin && e.pre_pin === true ? `${base} pre-pin` : base;
}

/** True when this build shows the local-preview banner (PREVIEW_LOCAL=1 at build time). */
export const PREVIEW_LOCAL = process.env.PREVIEW_LOCAL === '1';

/** Labels of the comparison metric keys (the data puts the unit and the leg in the key). */
const METRIC_BASE: Record<string, string> = {
  solo_tok_s: 'single stream',
  agg_tok_s: 'aggregate',
  tok_s: 'decode speed',
  ttft_ms: 'time to first token',
  ttft_ms_cold: 'time to first token, cold',
  ready_s: 'ready time',
  p50_latency_s: 'median latency',
  kv_pool_tokens: 'KV-cache pool',
  kv_cache_gib_per_gpu: 'KV cache per GPU',
  weights_gib_per_gpu: 'weights per GPU',
  vram_mib_gpu0: 'VRAM, GPU 0',
  vram_mib_gpu1: 'VRAM, GPU 1',
  vram_mib_sum: 'VRAM, both GPUs',
  vram_mib_gpu0_at_ready: 'VRAM at ready, GPU 0',
  vram_mib_gpu1_at_ready: 'VRAM at ready, GPU 1',
  vram_mib_sum_at_ready: 'VRAM at ready, both GPUs',
  gpu_memory_utilization: 'GPU memory share given to vLLM',
  nccl_channels: 'NCCL channels',
  agg_over_solo: 'aggregate ÷ single stream',
  n_runs: 'runs',
  n_runs_one_slot: 'runs started with one slot',
  acceptance_length: 'acceptance length',
  arms_failed_to_start: 'arms that failed to start',
  arms_kept: 'arms kept',
  arms_rated: 'arms rated',
  arms_passing_solo_leg: 'arms passing the single-stream leg',
  arms_passing_c8_leg: 'arms passing the 8-request leg',
  arms_passing_both_speed_legs: 'arms passing both speed legs',
  arms_passing_both_speed_legs_and_identity: 'arms passing both speed legs and the identity check',
  max_cards_busy: 'cards busy at once (maximum)',
  multi_card_jobs: 'jobs on more than one card',
  jobs: 'jobs',
  engines: 'engines side by side',
  overlap_min: 'overlap',
  gap_min: 'gap',
  judge_min: 'judging time',
  overlaps: 'overlapping windows',
  max_gpus_per_server: 'GPUs per model server (maximum)',
  single_model_runs: 'runs of one model on four cards',
};
const LANG: Record<string, string> = { fr: 'French prompts', en: 'English prompts', all_prompts: 'all prompts' };

/** Human label of a comparison metric key ("delta_agg_tok_s_c8_fr_pct" -> "Change in aggregate, 8 requests, French prompts"). */
export function metricLabel(key: string): string {
  const cap = (x: string) => x.replace(/^./, (c) => c.toUpperCase());
  if (METRIC_BASE[key]) return cap(METRIC_BASE[key]);
  const m = /^(delta_|ratio_)?(.+?)(?:_c(\d+))?(?:_(fr|en|all_prompts))?(?:_(min|max))?(?:_pct)?$/.exec(key);
  if (m && METRIC_BASE[m[2]]) {
    const parts = [METRIC_BASE[m[2]]];
    if (m[3]) parts.push(`${m[3]} requests`);
    if (m[4]) parts.push(LANG[m[4]]);
    let s = parts.join(', ');
    if (m[5]) s += ` (${m[5] === 'min' ? 'lowest' : 'highest'})`;
    if (m[1] === 'delta_') s = `change in ${s}`;
    if (m[1] === 'ratio_') s = `ratio of ${s}`;
    return cap(s);
  }
  return humanKey(key);
}

export function topoLabel(t: { gpus: number | null; tp?: number | null; pp?: number | null; split: string; cpu_offload_gb?: number | null; ram_spill?: boolean | null }): string {
  const parts: string[] = [];
  if (isNum(t.gpus)) parts.push(`${t.gpus} GPU${t.gpus === 1 ? '' : 's'}`);
  if (t.split === 'tensor') parts.push(`TP${isNum(t.tp) ? t.tp : '?'}`);
  else if (t.split === 'layer') parts.push('layer split');
  else if (t.split === 'row') parts.push('row split');
  if (isNum(t.pp) && t.pp > 1) parts.push(`PP${t.pp}`);
  if (isNum(t.cpu_offload_gb) && t.cpu_offload_gb > 0) parts.push('CPU offload');
  else if (t.ram_spill === true) parts.push('+ system RAM');
  return parts.join(' · ') || t.split;
}

/** Truncate a long description for <meta name="description">. */
export function metaDescription(s: string, max = 158): string {
  const t = s.replace(/\s+/g, ' ').trim();
  return t.length <= max ? t : `${t.slice(0, max - 1).replace(/\s+\S*$/, '')}…`;
}

export const STATUS_LABEL: Record<string, string> = {
  'serves-lane': 'served on demand for a role',
  kept: 'kept',
  parked: 'parked',
  reservations: 'with reservations',
  'rated-no-role': 'rated, no role',
  rejected: 'rejected',
  'not-rated': 'not rated',
};

export const STATUS_TONE: Record<string, 'green' | 'amber' | 'muted' | 'red'> = {
  'serves-lane': 'green',
  kept: 'green',
  ok: 'green',
  closed: 'green',
  reviewed: 'green',
  parked: 'amber',
  reservations: 'amber',
  partial: 'amber',
  interrupted: 'amber',
  'to-review': 'amber',
  'review-requested': 'amber',
  exploratory: 'amber',
  'rated-no-role': 'muted',
  'not-rated': 'muted',
  unknown: 'muted',
  'not-run': 'muted',
  rejected: 'red',
  failed: 'red',
  'failed-start': 'red',
};

/** Heading id of a markdown heading, as lib/markdown.ts writes it. */
function mdHeadingId(text: string): string {
  return (
    text
      .replace(/[*_`]/g, '')
      .toLowerCase()
      .replace(/&[a-z]+;/g, '')
      .replace(/[^\p{L}\p{N}\s-]/gu, '')
      .trim()
      .replace(/\s+/g, '-') || 'section'
  );
}

let glossaryLines: string[] | null = null;
/**
 * Link to the glossary section that defines a term (the heading above the
 * first line naming it as `term` or **term**); the glossary page when absent.
 */
export function glossaryHref(term: string): string {
  if (glossaryLines === null) glossaryLines = (readRepoText('GLOSSARY.md') ?? '').split('\n');
  const needles = [`\`${term}\``, `**${term}**`];
  let heading: string | null = null;
  for (const line of glossaryLines) {
    const h = line.match(/^#{2,6}\s+(.+)$/);
    if (h) heading = h[1];
    else if (heading && needles.some((n) => line.includes(n))) return href(`glossary/#${mdHeadingId(heading)}`);
  }
  return href('glossary/');
}
