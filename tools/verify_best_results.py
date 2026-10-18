#!/usr/bin/env python3
"""Check the best-results page against data/, with an implementation of its rules of its own.

The page (site/src/pages/best-results.astro, rules in site/src/lib/best.ts) picks, for one card and one NVLink
pair, the largest models, the fastest headline runs, the agent loops and the top score per bench, then reads the
two-pairs records and four results of the night of 17 to 18 October. This script recomputes every figure the page
should show from data/runs, data/models, data/rankings, data/benches, data/hardware and data/comparisons alone,
reads the built page (site/dist/best-results/index.html), and checks that:

  1. expected  every figure it computes is on the page, with that value and that link (run, model, ranking,
               bench, configuration or comparison page), as many times as computed;
  2. nothing   every data-num element of the page is one of them, except inside the judge banner (a shared
     else     component, checked by G5) and the top-score tables, checked by rule 3;
  3. top       each top-score row shows the highest score of its ranking among rows whose run was on that
     scores   configuration, and links that row's run;
  4. format    the visible text of every figure is fmtNum of its value (site/src/lib/site.ts);
  5. prose     every number written outside a figure is a date, an id, a name or a label of the data, or one
               of the reviewed PROSE tokens below, each found in the record it is quoted from.

It prints the four results of the night with the field each figure is read from. The choice of the latest ranking
per bench is the site's own (latestRankingPerBench); this script checks the row chosen within it.

usage: tools/verify_best_results.py [--root DIR] [--dist DIR] [--quiet]
exit status: 0 every check passes, 1 a check failed, 2 the page or data/ is missing.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal
from html.parser import HTMLParser
from pathlib import Path

PAGE = 'best-results/index.html'
BASE = '/rtx3090fe-model-tests/'
GITHUB_BLOB = 'https://github.com/florent-pro-ch/rtx3090fe-model-tests/blob/main/'
HW = ['1x3090fe', '2x3090fe-nvlink']
GPUS = {'1x3090fe': 1, '2x3090fe-nvlink': 2}
HARDWARE_IDS = ['1x3090fe', '2x3090fe-nvlink', '2x2x3090fe-nvlink']
CLASSES = [('small', 0, 10), ('mid', 10, 40), ('large', 40, float('inf'))]
REFUSAL_CAMPAIGN = '2026-09-05-labo-non-censures'
REFUSAL_COPY_CAMPAIGNS = ('2026-09-11-tests-veille', '2026-09-12-tests-veille')
LOOP_RANKING = 'code-loop-v1--rank'
N3 = '2026-10-18-night-3/'
NIGHT = dict(
    oneCard=N3 + 'gpt-oss-120b-one-card', oneCardLoop=N3 + 'gpt-oss-120b-one-card-loop', pair=N3 + 'gpt-oss-120b-pair',
    np4=N3 + 'gpt-oss-120b-np4', loopLow=N3 + 'gpt-oss-120b-loop-effort-low', nextOne=N3 + 'qwen3-coder-next-pair', nextFour=N3 + 'qwen3-coder-next-np4',
    nextEight=N3 + 'qwen3-coder-next-np8', on1024=N3 + 'gpt-oss-120b-reasoning-on1024-t0',
    on2048=N3 + 'gpt-oss-120b-reasoning-on2048', onNoBudget=N3 + 'gpt-oss-120b-reasoning-on',
    v1=N3 + 'qwen3-coder-adapter-v1-loop',
    v2=[N3 + 'qwen3-coder-adapter-v2-loop', N3 + 'qwen3-coder-adapter-v2-loop-r2', N3 + 'qwen3-coder-adapter-v2-loop-r3'],
)
# Numbers written in the page's prose, outside a figure, that are not a date, an id or a name of the data:
# each with the record it is quoted from and the text that must be in it.
PROSE = {
    '0': ('data/runs/2026-10-18-night-3/gpt-oss-120b-reasoning-on1024-t0.json', 'temperature 0'),
    '1.0': ('data/runs/2026-10-18-night-3/gpt-oss-120b-reasoning-on2048.json', 'temperature 1.0'),
    '17': ('data/campaigns/2026-10-18-night-3.json', '17 to 18 October'),
    '18': ('data/campaigns/2026-10-18-night-3.json', '17 to 18 October'),
    '3': ('data/campaigns/2026-10-18-night-3.json', 'Night 3'),
    '48': ('data/hardware/2x2x3090fe-nvlink.json', '48 GB'),
}


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def fmt_num(v: float, digits: int | None = None) -> str:
    """fmtNum of site/src/lib/site.ts: en-US grouping, 0 to 4 fraction digits (or exactly `digits`), half away from zero."""
    d = Decimal(repr(float(v))) if isinstance(v, float) else Decimal(v)
    q = Decimal(1).scaleb(-(4 if digits is None else digits))
    d = d.quantize(q, rounding=ROUND_HALF_UP)
    s = f'{d:,f}'
    if digits is None and '.' in s:
        s = s.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def one_decimal(v) -> int | None:
    return 1 if is_num(v) and abs(round(v * 10) - v * 10) > 1e-9 else None


class Data:
    def __init__(self, root: Path):
        d = root / 'data'
        if not d.is_dir():
            raise FileNotFoundError(d)
        load = lambda p: json.loads(p.read_text(encoding='utf-8'))
        self.models = {m['model_id']: m for m in (load(p) for p in sorted((d / 'models').glob('*.json')) if p.name != '_index.json')}
        self.runs = {r['run_id']: r for r in (load(p) for p in sorted((d / 'runs').glob('*/*.json')))}
        self.rankings = {k['ranking_id']: k for k in (load(p) for p in sorted((d / 'rankings').glob('*.json')))}
        self.benches = {b['bench_id']: b for b in (load(p) for p in sorted((d / 'benches').glob('*.json')))}
        self.hardware = {h['hardware_id']: h for h in (load(p) for p in sorted((d / 'hardware').glob('*.json')))}
        self.comparisons = {c['comparison_id']: c for c in (load(p) for p in sorted((d / 'comparisons').glob('*.json')))}
        self.root = root

    # --- the run filters of site/src/lib/data.ts, written again
    def refusal_only(self, r) -> bool:
        rid = r['run_id']
        camp = rid.split('/')[0]
        if rid.startswith(REFUSAL_CAMPAIGN + '/') or r.get('campaign') == REFUSAL_CAMPAIGN:
            return True
        if camp in REFUSAL_COPY_CAMPAIGNS and rid[len(camp) + 1:].startswith('labo-'):
            return True
        if isinstance(r.get('duplicate_of'), str) and r['duplicate_of'].startswith(REFUSAL_CAMPAIGN + '/'):
            return True
        return any(isinstance(r.get(k), str) and re.search('refusal', r[k], re.I) for k in ('sensitive', 'publish_scope', 'scope'))

    @staticmethod
    def topology_known(r) -> bool:
        t = r['topology']
        return r['hardware'] in HARDWARE_IDS and is_num(t.get('gpus')) and bool(t.get('split')) and t['split'] != 'unknown'

    @staticmethod
    def solo(r):
        v = r['metrics'].get('solo_tok_s')
        return v if is_num(v) else None

    @staticmethod
    def proto(r) -> str:
        return (r.get('protocol') or '').strip().lower()

    def speculative(self, r) -> bool:
        s = (r.get('engine_args') or {}).get('speculative')
        return s is not None and s is not False

    def ab_treatment(self, r) -> bool:
        arm = (r.get('engine_args') or {}).get('ab_arm')
        return (isinstance(arm, str) and arm.lower() == 'treatment') or r['topology'].get('p2p') == 'off-software'

    @staticmethod
    def reps(r) -> int:
        for k in ('repetitions', 'passes', 'n_passes'):
            v = r['metrics'].get(k)
            if is_num(v):
                return v
            if isinstance(v, list) and v:
                return len(v)
        return 1

    @staticmethod
    def stamp(r) -> str:
        for v in (r.get('started_at'), r.get('ended_at')):
            if isinstance(v, str) and v:
                return v
        m = re.match(r'^(\d{4}-\d{2}-\d{2})', r.get('campaign', ''))
        return m.group(1) if m else ''

    def headline_key(self, r):
        # pinned first, house protocol first, most repetitions, most recent, run id
        return (0 if r['engine'].get('pre_pin') is False else 1, 0 if self.proto(r) == 'speed-house/v1' else 1, -self.reps(r),
                _desc(self.stamp(r)), r['run_id'])

    def headline_eligible(self, r) -> bool:
        a = r.get('engine_args') or {}
        if r.get('protocol') == 'speed-house/v1-fixedlen' or (a.get('parallel_slots') == 1 and r['metrics'].get('agg_concurrency') == 8):
            return False
        return (r['status'] == 'ok' and not r.get('duplicate_of') and self.topology_known(r) and self.solo(r) is not None
                and not self.speculative(r) and not self.ab_treatment(r) and self.proto(r) != 'speed-house/v1-en' and not self.refusal_only(r))

    def scope(self, hw):
        return [r for r in self.runs.values() if r['hardware'] == hw and r['status'] == 'ok' and not r.get('duplicate_of')
                and self.topology_known(r) and not self.refusal_only(r)]

    def headlines(self, hw):
        ids = sorted({r['model_id'] for r in self.runs.values() if r['hardware'] == hw and self.topology_known(r)})
        out = []
        for mid in ids:
            c = sorted((r for r in self.runs.values() if r['model_id'] == mid and r['hardware'] == hw and self.headline_eligible(r)), key=self.headline_key)
            if c:
                out.append(c[0])
        return out

    def params(self, mid):
        v = self.models.get(mid, {}).get('params_b_total')
        return v if is_num(v) else None

    def active(self, mid):
        v = self.models.get(mid, {}).get('params_b_active')
        return v if is_num(v) else None

    def cls(self, mid):
        p = self.params(mid)
        return None if p is None else next(c for c, lo, hi in CLASSES if lo <= p < hi)

    @staticmethod
    def in_ram(r):
        t = r['topology']
        if t.get('ram_spill') is True or (is_num(t.get('cpu_offload_gb')) and t['cpu_offload_gb'] > 0):
            return True
        return False if t.get('ram_spill') is False else None

    @staticmethod
    def slots(r):
        a = r.get('engine_args') or {}
        for k in ('parallel_slots', 'max_num_seqs'):
            if is_num(a.get(k)):
                return a[k]
        return None

    def mslug(self, mid):
        return self.models[mid]['slug']


def _desc(s: str):
    """Sort key for 'most recent first' on ISO strings."""
    return tuple(-ord(c) for c in s) + (0,)


def L(kind: str, ident: str = '') -> str:
    """Normalised link target, as norm_href() reads it from the page."""
    return {'run': f'runs/{ident}/', 'model': f'models/{ident}/', 'ranking': f'rankings/{ident}/', 'bench': f'benches/{ident}/',
            'compare': f'compare/{ident}/', 'config': f'configs/{ident}', 'blob': f'blob:{ident}'}[kind]


def expected(D: Data, notes: list[str]) -> Counter:
    """Every figure the page should show, as (value, link) pairs, in the page's own order of rules."""
    E: Counter = Counter()
    add = lambda v, link, why: (E.update([(float(v), link)]), notes.append(f'{why}: {fmt_num(v)} -> {link}')) if is_num(v) else notes.append(f'{why}: no value')
    for hw in HW:
        scope = D.scope(hw)
        # rule 2: largest models
        for ram in (False, True):
            lst = [r for r in scope if D.in_ram(r) is ram and D.params(r['model_id']) is not None]
            if not lst:
                continue
            top = max(D.params(r['model_id']) for r in lst)
            mid = min(r['model_id'] for r in lst if D.params(r['model_id']) == top)
            mine = [r for r in lst if r['model_id'] == mid]
            sp = sorted((r for r in mine if D.solo(r) is not None and r.get('protocol') != 'speed-house/v1-fixedlen' and not D.speculative(r)
                         and not D.ab_treatment(r) and D.proto(r) != 'speed-house/v1-en'), key=D.headline_key)
            sp = sp[0] if sp else None
            tag = f'{hw} largest ({"part in RAM" if ram else "all on the cards"}) {mid}'
            if sp and is_num(sp['topology'].get('cpu_offload_gb')) and sp['topology']['cpu_offload_gb'] > 0:
                add(sp['topology']['cpu_offload_gb'], L('run', sp['run_id']), tag + ' GB in RAM')
            add(D.params(mid), L('model', D.mslug(mid)), tag + ' params total')
            if D.active(mid) is not None:
                add(D.active(mid), L('model', D.mslug(mid)), tag + ' params active')
            if sp:
                add(D.solo(sp), L('run', sp['run_id']), tag + ' single stream')
                add(D.reps(sp), L('run', sp['run_id']), tag + ' passes')
        # rule 3: per size class
        heads = [r for r in D.headlines(hw) if r in scope]
        no_class = len([r for r in D.headlines(hw) if D.cls(r['model_id']) is None])
        for c, _, _ in CLASSES:
            s = sorted((r for r in heads if D.cls(r['model_id']) == c and D.solo(r) is not None), key=lambda r: (-D.solo(r), r['model_id']))
            if s:
                add(D.solo(s[0]), L('run', s[0]['run_id']), f'{hw} fastest single stream, {c}: {s[0]["model_id"]}')
                add(D.reps(s[0]), L('run', s[0]['run_id']), f'{hw} fastest single stream, {c}: passes')
            a = sorted((r for r in heads if D.cls(r['model_id']) == c and is_num(r['metrics'].get('agg_tok_s')) and r['metrics'].get('agg_concurrency') == 8
                        and (D.slots(r) is None or D.slots(r) > 1)), key=lambda r: (-r['metrics']['agg_tok_s'], r['model_id']))
            if a:
                add(a[0]['metrics']['agg_tok_s'], L('run', a[0]['run_id']), f'{hw} highest aggregate, {c}: {a[0]["model_id"]}')
                if D.slots(a[0]) is not None:
                    add(D.slots(a[0]), L('run', a[0]['run_id']), f'{hw} highest aggregate, {c}: slots')
                add(D.reps(a[0]), L('run', a[0]['run_id']), f'{hw} highest aggregate, {c}: passes')
        if no_class:
            add(no_class, L('config', f'{hw}/#headline'), f'{hw} headline models without a parameter count')
        # rule 4: agent loop, ranking then later run records
        k = D.rankings.get(LOOP_RANKING)
        tasks = D.benches.get('code-loop/v1', {}).get('n_items')
        since = None
        if k:
            since = (k.get('generated_at') or '')[:10] or None
            rows = [row for row in k['rows'] if (row.get('extra') or {}).get('gpus') == GPUS[hw] and is_num(row.get('score'))]
            if rows:
                best = max(row['score'] for row in rows)
                for row in (row for row in rows if row['score'] == best):
                    ex = row.get('extra') or {}
                    ppr = [p for p in ex.get('passes_per_run') or [] if is_num(p)]
                    tag = f'{hw} loop ranking {row["model_id"]}'
                    add(row['score'], L('ranking', LOOP_RANKING), tag + ' fewest passes')
                    add(tasks, L('bench', 'code-loop/v1'), tag + ' tasks')
                    add(len(ppr), L('ranking', LOOP_RANKING), tag + ' loops')
                    for p in ppr:
                        add(p, L('ranking', LOOP_RANKING), tag + ' passes of one loop')
                    if is_num(ex.get('context_k_tokens')):
                        add(ex['context_k_tokens'], L('ranking', LOOP_RANKING), tag + ' context (K)')
        def run_date(r):
            for v in (r.get('started_at'), r.get('ended_at')):
                if isinstance(v, str) and re.match(r'^\d{4}-\d{2}-\d{2}', v):
                    return v[:10]
            m_ = re.match(r'^(\d{4}-\d{2}-\d{2})', r.get('campaign', ''))
            return m_.group(1) if m_ else ''

        def loops_of(r):
            m_ = r['metrics']
            if is_num(m_.get('fresh_passes')) and is_num(m_.get('tasks_per_pass')):
                return [(r, m_[f'fresh_pass{i}_tasks_passed'], m_['tasks_per_pass'], i) for i in range(1, int(m_['fresh_passes']) + 1)
                        if is_num(m_.get(f'fresh_pass{i}_tasks_passed'))]
            total = next((m_[k] for k in ('agent_tasks_total', 'agent_task_cases', 'tasks_per_pass') if is_num(m_.get(k))), None)
            return [(r, m_['agent_tasks_passed'], total, 0)] if is_num(m_.get('agent_tasks_passed')) and total is not None else []

        loops = [l for r in scope if not since or run_date(r) > since for l in loops_of(r)]
        if loops:
            best = max(l[1] for l in loops)
            keys = sorted({f'{l[0]["model_id"]}|{l[0].get("build_id") or ""}' for l in loops if l[1] == best})
            groups = []
            for key in keys:
                mid, build = key.split('|')
                groups.append(sorted((l for l in loops if l[0]['model_id'] == mid and (l[0].get('build_id') or '') == build),
                                     key=lambda l: (l[0].get('started_at') or '', l[0]['run_id'], l[3])))
            first_best = next(l for l in groups[0] if l[1] == best)
            add(best, L('run', first_best[0]['run_id']), f'{hw} loop records: most passed')
            add(groups[0][0][2], L('run', groups[0][0][0]['run_id']), f'{hw} loop records: tasks')
            for g in groups:
                for r, passed, total, i in g:
                    a = r.get('engine_args') or {}
                    ctx = a['client_context_window'] if is_num(a.get('client_context_window')) else (
                        next((a[k] for k in ('ctx_per_slot', 'ctx_size', 'max_model_len') if is_num(a.get(k))), None) if r.get('kind') == 'quality' else None)
                    add(passed, L('run', r['run_id']), f'{hw} loop {r["run_id"]} #{i} passed')
                    add(total, L('run', r['run_id']), f'{hw} loop {r["run_id"]} #{i} tasks')
                    if ctx is not None:
                        add(ctx, L('run', r['run_id']), f'{hw} loop {r["run_id"]} #{i} context')
    # two pairs
    rows = D.comparisons.get('two-pairs-parallel', {}).get('rows', [])
    pick = lambda prefix, metric: next((r for r in rows if r.get('label', '').startswith(prefix) and r.get('metric') == metric and is_num(r.get('value'))), None)
    single = pick('Runs of one model across all four cards', 'single_model_runs')
    maxg = pick('Every recorded launch line', 'max_gpus_per_server')
    busy = pick('3D generation bench: cards generating', 'max_cards_busy')
    if single:
        add(single['value'], L('compare', 'two-pairs-parallel'), 'two pairs: runs of one model on four cards')
    if maxg:
        add(maxg['value'], L('compare', 'two-pairs-parallel'), 'two pairs: most GPUs per server')
    if busy:
        bid = next((x for x in busy.get('run_ids', []) if x in D.runs), None)
        add(busy['value'], L('run', bid) if bid else L('compare', 'two-pairs-parallel'), 'two pairs: most cards busy at once')
    return E


def night(D: Data, E: Counter, notes: list[str]) -> list[tuple[str, str, str, object]]:
    """The four results of the night: (result, figure, field, value), added to the expected figures."""
    out = []

    def f(result, label, rid, where, key, kind='run'):
        r = D.runs.get(rid)
        v = None
        if r is not None:
            v = r['metrics'].get(key) if where == 'metrics' else (r.get('engine_args') or {}).get(key) if where == 'engine_args' else r['topology'].get(key)
        out.append((result, label, f'{rid} · {where}.{key}', v))
        if is_num(v):
            E.update([(float(v), L('run', rid))])
            notes.append(f'night {result}, {label}: {fmt_num(v)} -> {L("run", rid)}')
        return v

    def mp(result, label, mid, key):
        v = D.models.get(mid, {}).get(key)
        out.append((result, label, f'data/models/{D.mslug(mid)}.json · {key}', v))
        if is_num(v):
            E.update([(float(v), L('model', D.mslug(mid)))])
        return v

    a = '1 gpt-oss-120b on one card'
    mp(a, 'parameters, total (B)', 'openai/gpt-oss-120b', 'params_b_total')
    mp(a, 'parameters, active (B)', 'openai/gpt-oss-120b', 'params_b_active')
    f(a, 'server reasoning budget', NIGHT['oneCard'], 'engine_args', 'reasoning_budget')
    f(a, 'layers whose experts are in RAM', NIGHT['oneCard'], 'engine_args', 'n_cpu_moe')
    f(a, 'GB in system RAM', NIGHT['oneCard'], 'topology', 'cpu_offload_gb')
    f(a, 'single stream (tok/s)', NIGHT['oneCard'], 'metrics', 'solo_tok_s')
    f(a, 'passes', NIGHT['oneCard'], 'metrics', 'repetitions')
    f(a, 'context (tokens)', NIGHT['oneCard'], 'engine_args', 'ctx_size')
    f(a, 'pair: layers whose experts are in RAM', NIGHT['pair'], 'engine_args', 'n_cpu_moe')
    f(a, 'pair, one slot: single stream (tok/s)', NIGHT['pair'], 'metrics', 'solo_tok_s')
    f(a, 'pair, one slot: context per slot', NIGHT['pair'], 'engine_args', 'ctx_per_slot')
    f(a, 'pair, four slots: context per slot', NIGHT['np4'], 'engine_args', 'ctx_per_slot')
    f(a, 'pair, four slots: single stream (tok/s)', NIGHT['np4'], 'metrics', 'solo_tok_s')
    f(a, 'pair, four slots: aggregate (tok/s)', NIGHT['np4'], 'metrics', 'agg_tok_s')
    f(a, 'pair: slots', NIGHT['np4'], 'engine_args', 'parallel_slots')
    f(a, 'pair, four slots: passes', NIGHT['np4'], 'metrics', 'repetitions')
    f(a, 'agent loop on one card: Cline window', NIGHT['oneCardLoop'], 'engine_args', 'client_context_window')
    f(a, 'agent loop on one card: passed', NIGHT['oneCardLoop'], 'metrics', 'agent_tasks_passed')
    f(a, 'agent loop on one card: tasks', NIGHT['oneCardLoop'], 'metrics', 'agent_tasks_total')
    f(a, 'agent loop on one card: stopped at the cap', NIGHT['oneCardLoop'], 'metrics', 'agent_killed_or_timed_out')
    f(a, 'pair: server reasoning budget', NIGHT['pair'], 'engine_args', 'reasoning_budget')
    f(a, 'pair loop, budget 0: passed', NIGHT['pair'], 'metrics', 'agent_tasks_passed')
    f(a, 'pair loop, budget 0: tasks', NIGHT['pair'], 'metrics', 'agent_tasks_total')
    f(a, 'pair loop, effort low: passed', NIGHT['loopLow'], 'metrics', 'agent_tasks_passed')
    f(a, 'pair loop, effort low: tasks', NIGHT['loopLow'], 'metrics', 'agent_tasks_total')
    b = '2 Qwen3-Coder-Next, 1/4/8 slots'
    mp(b, 'parameters, total (B)', 'qwen/qwen3-coder-next', 'params_b_total')
    mp(b, 'parameters, active (B)', 'qwen/qwen3-coder-next', 'params_b_active')
    f(b, 'layers whose experts are in RAM', NIGHT['nextEight'], 'engine_args', 'n_cpu_moe')
    f(b, 'GB in system RAM', NIGHT['nextEight'], 'topology', 'cpu_offload_gb')
    for rid in (NIGHT['nextOne'], NIGHT['nextFour'], NIGHT['nextEight']):
        f(b, 'slots', rid, 'engine_args', 'parallel_slots')
        f(b, 'server context', rid, 'engine_args', 'ctx_size')
        f(b, 'context per slot', rid, 'engine_args', 'ctx_per_slot')
        f(b, 'single stream (tok/s)', rid, 'metrics', 'solo_tok_s')
        f(b, 'aggregate at eight requests (tok/s)', rid, 'metrics', 'agg_tok_s')
        f(b, 'passes', rid, 'metrics', 'repetitions')
    c = '3 gpt-oss-120b thinking on/off'
    f(c, 'off: server reasoning budget', NIGHT['pair'], 'engine_args', 'reasoning_budget')
    f(c, 'off: exact', NIGHT['pair'], 'metrics', 'reason_OFF_exact')
    f(c, 'off: items', NIGHT['pair'], 'metrics', 'reason_OFF_cases')
    f(c, 'on: output cap (tokens)', NIGHT['on1024'], 'metrics', 'reason_max_tokens')
    f(c, 'on: server reasoning budget', NIGHT['on1024'], 'engine_args', 'reasoning_budget')
    f(c, 'on: budget re-opened', NIGHT['on1024'], 'metrics', 'reason_budget_reopened')
    f(c, 'on: exact', NIGHT['on1024'], 'metrics', 'reason_exact')
    f(c, 'on: items', NIGHT['on1024'], 'metrics', 'reason_cases')
    f(c, 'on: stopped at the cap', NIGHT['on1024'], 'metrics', 'reason_truncated')
    f(c, 'on: empty', NIGHT['on1024'], 'metrics', 'reason_empty')
    f(c, 'other run (budget 2048): exact', NIGHT['on2048'], 'metrics', 'reason_exact')
    f(c, 'other run (budget 2048): items', NIGHT['on2048'], 'metrics', 'reason_cases')
    f(c, 'other run (budget 2048): output cap', NIGHT['on2048'], 'metrics', 'reason_max_tokens')
    f(c, 'other run (budget 2048): server budget', NIGHT['on2048'], 'engine_args', 'reasoning_budget')
    f(c, 'other run (no budget): exact', NIGHT['onNoBudget'], 'metrics', 'reason_ON_exact')
    f(c, 'other run (no budget): items', NIGHT['onNoBudget'], 'metrics', 'reason_ON_cases')
    d = '4 Qwen3-Coder adapter'
    s = D.models.get('qwen/qwen3-coder-30b-a3b', {}).get('verdict', {}).get('summary', '')
    m = re.search(r'agent loop completed (\d+)/(\d+)[^.]*?stock \S+ parser at a ([\d,]+)-token context', s)
    slug = D.mslug('qwen/qwen3-coder-30b-a3b')
    for label, v in zip(('stock parser: passed', 'stock parser: tasks', 'stock parser: context'), (m.groups() if m else (None,) * 3)):
        v = int(v.replace(',', '')) if v else None
        out.append((d, label, f'data/models/{slug}.json · verdict.summary', v))
        if v is not None:
            E.update([(float(v), L('model', slug))])
    f(d, 'adapter: context (tokens)', NIGHT['v2'][0], 'engine_args', 'max_model_len')
    f(d, 'adapter: Cline window', NIGHT['v2'][0], 'engine_args', 'client_context_window')
    f(d, 'v1: passed', NIGHT['v1'], 'metrics', 'agent_tasks_passed')
    f(d, 'v1: tasks', NIGHT['v1'], 'metrics', 'agent_tasks_total')
    for rid in NIGHT['v2']:
        f(d, 'v2: passed', rid, 'metrics', 'agent_tasks_passed')
        f(d, 'v2: tasks', rid, 'metrics', 'agent_tasks_total')
    return out


class Page(HTMLParser):
    """Collects the page's data-num elements (value, link, visible text, context) and its prose outside them."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.nums: list[dict] = []
        self.prose: list[str] = []
        self.stack: list[str] = []
        self.ctx = ''        # id of the last h2/h3
        self.in_main = False
        self.banner = 0      # depth inside <aside class="banner">
        self.num = None      # the data-num element being read
        self.row_links: list[str] = []
        self.row_nums: list[dict] = []
        self.skip = 0        # <script>/<style>

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'main':
            self.in_main = True
        if tag in ('script', 'style'):
            self.skip += 1
        if tag in ('h2', 'h3') and a.get('id'):
            self.ctx = a['id']
        if tag == 'aside' and 'banner' in (a.get('class') or '').split():
            self.banner += 1
        elif tag == 'aside' and self.banner:
            self.banner += 1
        if tag == 'tr':
            self.row_links, self.row_nums = [], []
        if tag == 'a' and a.get('href'):
            self.row_links.append(a['href'])
        if 'data-num' in a and self.in_main:
            self.num = dict(value=a['data-num'], href=a.get('href'), text='', ctx=self.ctx, banner=self.banner > 0, row_links=self.row_links)
            self.stack.append(tag)
            return
        if self.num is not None:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag == 'main':
            self.in_main = False
        if tag in ('script', 'style'):
            self.skip -= 1
        if tag == 'aside' and self.banner:
            self.banner -= 1
        if self.num is not None and self.stack:
            self.stack.pop()
            if not self.stack:
                self.nums.append(self.num)
                self.num = None

    def handle_data(self, data):
        if self.skip or not self.in_main:
            return
        if self.num is not None:
            if len(self.stack) == 1:  # the number itself, not its unit span
                self.num['text'] += data
            return
        if not self.banner:
            self.prose.append(data)


def norm_href(h: str | None) -> str | None:
    if not h:
        return None
    h = html.unescape(h)
    if h.startswith(GITHUB_BLOB):
        return 'blob:' + h[len(GITHUB_BLOB):]
    if h.startswith(BASE):
        return h[len(BASE):]
    return h


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--root', default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument('--dist', default=None)
    ap.add_argument('--quiet', action='store_true')
    o = ap.parse_args(argv)
    root = Path(o.root)
    page = Path(o.dist or root / 'site' / 'dist') / PAGE
    try:
        D = Data(root)
        text = page.read_text(encoding='utf-8')
    except FileNotFoundError as e:
        print(f'verify_best_results: missing {e}', file=sys.stderr)
        return 2
    notes: list[str] = []
    E = expected(D, notes)
    facts = night(D, E, notes)
    P = Page()
    P.feed(text)
    fails: list[str] = []

    # 4. format, and the multiset of shown figures
    shown: Counter = Counter()
    top_rows = []
    skipped_banner = 0
    for n in P.nums:
        v = float(n['value'])
        digits = one_decimal(v)
        vis = n['text'].strip().lstrip('~')
        if vis not in (fmt_num(v), fmt_num(v, digits) if digits else fmt_num(v)):
            fails.append(f'format: {n["value"]} shown as {vis!r} ({n["ctx"]})')
        if n['banner']:
            skipped_banner += 1
            continue
        if n['ctx'].startswith('top-'):
            link = norm_href(n['href']) or ''
            if link.startswith('benches/'):  # the Items column: the bench's frozen set
                b = D.benches.get(link[len('benches/'):-1], {})
                if not is_num(b.get('n_items')) or float(b['n_items']) != v:
                    fails.append(f'top-score items {n["value"]} are not n_items of {link}')
                continue
            top_rows.append(n)
            continue
        shown.update([(v, norm_href(n['href']))])
    # 1 and 2
    for key, cnt in (E - shown).items():
        fails.append(f'expected, not on the page: {fmt_num(key[0])} -> {key[1]} (x{cnt})')
    for key, cnt in (shown - E).items():
        fails.append(f'on the page, not expected: {fmt_num(key[0])} -> {key[1]} (x{cnt})')
    # 3. top scores
    for n in top_rows:
        hw = n['ctx'][len('top-'):]
        rk = next((norm_href(h)[len('rankings/'):-1] for h in n['row_links'] if (norm_href(h) or '').startswith('rankings/')), None)
        run = norm_href(n['href'])[len('runs/'):-1] if (norm_href(n['href']) or '').startswith('runs/') else None
        k = D.rankings.get(rk)
        if not k or not run:
            fails.append(f'top score {n["value"]} ({hw}): ranking or run link missing')
            continue
        rows = [row for row in k['rows'] if is_num(row.get('score')) and row.get('run_id') in D.runs and D.runs[row['run_id']]['hardware'] == hw
                and not ((row.get('extra') or {}).get('not_rated') or ((row.get('extra') or {}).get('mechanics') or {}).get('not_rated'))]
        best = max((row['score'] for row in rows), default=None)
        if k['bench_id'] == 'code-loop/v1':
            fails.append(f'top score: code-loop/v1 should be left to the agent-loop section ({hw})')
        if best is None or float(n['value']) != float(best) or not any(row['run_id'] == run and row['score'] == best for row in rows):
            fails.append(f'top score {n["value"]} ({hw}, {rk}) is not the highest row on this configuration ({best})')
        notes.append(f'{hw} top score {k["bench_id"]}: {n["value"]} -> runs/{run}/ (highest of {rk} on {hw}: {best})')

    # 5. prose numbers
    prose = re.sub(r'\s+', ' ', ' '.join(P.prose))
    known = set()
    for m_ in D.models.values():
        known.add(m_['name'])
    for r in D.runs.values():
        known.update([r['run_id'], r['campaign'], r.get('build_id') or '', r['engine'].get('version') or ''])
        t = r['topology']  # topoLabel(): "2 GPUs · TP2"
        if is_num(t.get('gpus')):
            known.add(f"{t['gpus']} GPU{'' if t['gpus'] == 1 else 's'}")
        if is_num(t.get('tp')):
            known.add(f"TP{t['tp']}")
    for b in (root / 'data' / 'builds').glob('*.json'):
        q = json.loads(b.read_text(encoding='utf-8')).get('quant', {})
        known.add(q.get('label') or '')
    for k in D.rankings.values():
        known.update([k.get('title') or '', k['bench_id'], k['ranking_id']])
        if k.get('mode') is not None:
            known.add(f'(mode {k["mode"]})')  # rankingTitle(): "<bench name> (mode N)"
        judge = (k.get('grader') or {}).get('judge')
        if isinstance(judge, str):
            known.update([judge, judge.split(' (')[0]])
    for h in D.hardware.values():
        known.update([h.get('label') or ''] + list(h.get('never_measured') or []))
    for c in D.comparisons.values():
        known.add(c.get('title') or '')
    known.update(['code-loop/v1', 'raison/v1', 'speed-house/v1', 'tuteur/v1', 'vision/v1', 'document/v1', 'code/v1', 'volume/v1', 'RTX 3090', '3090'])
    rest = prose
    for s in sorted((x for x in known if x and re.search(r'\d', x)), key=len, reverse=True):
        rest = rest.replace(s, ' ')
    rest = re.sub(r'\b\d{4}-\d{2}-\d{2}\b', ' ', rest)            # dates
    rest = re.sub(r'\bv[12]\b', ' ', rest)                         # adapter versions v1, v2 (methodology/ADAPTERS.md)
    rest = re.sub(r'\bpair [AB]\b', ' ', rest)
    tokens = re.findall(r'(?<![\w.])\d[\d,.]*(?![\w])', rest)
    for t in sorted(set(tokens)):
        t = t.rstrip('.,')
        src = PROSE.get(t)
        if not src:
            fails.append(f'prose number {t!r} is not a figure, a name of the data or a reviewed token')
            continue
        body = (root / src[0]).read_text(encoding='utf-8') if (root / src[0]).exists() else ''
        if src[1] not in body:
            fails.append(f'prose number {t!r}: {src[1]!r} not found in {src[0]}')
        else:
            notes.append(f'prose {t!r}: {src[1]!r} in {src[0]}')

    if not o.quiet:
        print('The night of 17 to 18 October, as the page reads it:')
        for res, label, field, v in facts:
            print(f'  [{res}] {label}: {fmt_num(v) if is_num(v) else "MISSING"}  ({field})')
        print(f'{sum(E.values())} expected figures, {len(P.nums)} data-num elements on the page '
              f'({skipped_banner} in the judge banner, {len(top_rows)} top scores checked by rule 3).')
    for f_ in fails:
        print('FAIL', f_)
    if any(v is None for _, _, _, v in facts):
        print('FAIL a figure of the night is missing from the data')
        return 1
    if fails:
        print(f'verify_best_results: {len(fails)} failure(s)')
        return 1
    print('verify_best_results: every figure of the page traced to data/ by its rule')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
