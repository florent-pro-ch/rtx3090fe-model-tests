#!/usr/bin/env python3
"""Schema gate: every data/**/*.json parses, and every record validates against
schema/<type>.schema.json, the type being chosen by path:

  data/models/*.json              -> model     (files starting with _ are indexes, skipped)
  data/builds/*.json              -> build
  data/runs/**/*.json             -> run
  data/benches/*.json             -> bench
  data/hardware/*.json            -> hardware
  data/campaigns/*.json           -> campaign
  data/rankings/*.json            -> ranking
  data/comparisons/*.json         -> comparison
  data/item-scores/**/*.json      -> item-scores
  data/forge/summary.json         -> forge-summary
  data/forge/checkpoints/*.json   -> forge-checkpoint
  data/indexes/runs.json          -> runs-index
  data/rig.json                   -> rig
  data/watchlist.json             -> watchlist
  data/errata.json                -> errata
  data/judge-audit.json           -> judge-audit

A data/**/*.json that matches none of these paths is "untyped": a warning, so an
error under --strict. A stray or misplaced record therefore fails the gate instead
of passing unchecked.

Uses jsonschema (Draft 2020-12) when it is importable, otherwise a built-in validator
for the keywords the schemas use (type, required, properties, items, enum, pattern,
const, minimum/maximum, exclusiveMinimum/exclusiveMaximum, minLength, minItems,
additionalProperties, anyOf/oneOf/allOf, if/then/else, local $ref to #/$defs). Any other
keyword is ignored by the built-in validator, so a schema that adds one must extend it.

One judge per table (errors, also without --strict): every row of a judged ranking is graded by its
grader.judge, its item files carry the same judge and reproduce its Q and n_scored, a second judge is never
the table's own (in a two-full-orders table a row's second_judge holds judge and rank only, and no row is
flagged as graded by another judge), and a row without a score (or rated on part of its judged items) says why.

Judged numbers in prose (errors): a score-like number in a model or campaign summary's sentence about tutoring,
code, vision, a judge or a score must be a score or sub-score of the current judged tables for that model, that
campaign or a model the summary names.

Integrity checks (warnings): duplicate ids, file names that do not match their id,
and references between records (run -> model/build, build -> model, model ->
builds, ranking -> bench/runs, item scores -> run/bench/model/build and their
path, judge audit -> benches/campaigns, comparison -> runs and evidence paths,
runs index <-> run records, watchlist -> models and its count, forge summary <->
checkpoint records).

--strict is what tools/check_all.sh runs: every warning is an error, so it passes
with 0 warnings only.

usage:
  tools/validate.py [--strict] [--quiet] [--builtin] [ROOT]
Exit status: 0 valid, 1 invalid.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gatelib import REPO  # noqa: E402

try:  # optional: CI installs it, the fallback keeps the gate stdlib-only
    import jsonschema  # type: ignore
except ImportError:  # pragma: no cover
    jsonschema = None

DIR_TYPES = {"models": "model", "builds": "build", "runs": "run", "benches": "bench",
             "hardware": "hardware", "campaigns": "campaign", "rankings": "ranking",
             "comparisons": "comparison"}
FILE_TYPES = {("data", "errata.json"): "errata",
              ("data", "judge-audit.json"): "judge-audit",
              ("data", "rig.json"): "rig",
              ("data", "watchlist.json"): "watchlist",
              ("data", "forge", "summary.json"): "forge-summary",
              ("data", "indexes", "runs.json"): "runs-index"}
ID_KEY = {"model": "model_id", "build": "build_id", "run": "run_id", "bench": "bench_id",
          "hardware": "hardware_id", "campaign": "campaign_id", "ranking": "ranking_id",
          "comparison": "comparison_id", "forge-checkpoint": "checkpoint_id"}
# fields of a runs-index entry and where they live in the run record
INDEX_FIELDS = {"model_id": ("model_id",), "build_id": ("build_id",), "hardware": ("hardware",),
                "status": ("status",), "kind": ("kind",), "protocol": ("protocol",),
                "engine": ("engine", "name"), "engine_version": ("engine", "version"),
                "pre_pin": ("engine", "pre_pin"), "started_at": ("started_at",),
                "solo_tok_s": ("metrics", "solo_tok_s"), "agg_tok_s": ("metrics", "agg_tok_s"),
                "agg_concurrency": ("metrics", "agg_concurrency"), "split": ("topology", "split"),
                "gpus": ("topology", "gpus"), "duplicate_of": ("duplicate_of",)}


# ------------------------------------------------------------------ minimal validator
_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def _resolve(ref: str, root: dict) -> dict:
    if not ref.startswith("#/"):
        raise ValueError(f"only local $ref is supported, got {ref!r}")
    node = root
    for part in ref[2:].split("/"):
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node


def mini_validate(inst, schema: dict, path: str = "$", root: dict | None = None):
    """Yield (json_path, message) for the subset of JSON Schema the repo uses."""
    if not isinstance(schema, dict):
        return
    root = schema if root is None else root
    if "$ref" in schema:
        yield from mini_validate(inst, _resolve(schema["$ref"], root), path, root)
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if not any(_TYPES.get(x, lambda v: True)(inst) for x in types):
            yield path, f"expected type {types}, got {type(inst).__name__}"
            return
    if "enum" in schema and inst not in schema["enum"]:
        yield path, f"{inst!r} not in enum {schema['enum']}"
    if "const" in schema and inst != schema["const"]:
        yield path, f"{inst!r} != const {schema['const']!r}"
    if isinstance(inst, str):
        if "pattern" in schema and not re.search(schema["pattern"], inst):
            yield path, f"{inst!r} does not match {schema['pattern']}"
        if "minLength" in schema and len(inst) < schema["minLength"]:
            yield path, f"string shorter than minLength {schema['minLength']}"
    if _TYPES["number"](inst):
        if "minimum" in schema and inst < schema["minimum"]:
            yield path, f"{inst} < minimum {schema['minimum']}"
        if "maximum" in schema and inst > schema["maximum"]:
            yield path, f"{inst} > maximum {schema['maximum']}"
        if "exclusiveMinimum" in schema and inst <= schema["exclusiveMinimum"]:
            yield path, f"{inst} <= exclusiveMinimum {schema['exclusiveMinimum']}"
        if "exclusiveMaximum" in schema and inst >= schema["exclusiveMaximum"]:
            yield path, f"{inst} >= exclusiveMaximum {schema['exclusiveMaximum']}"
    if isinstance(inst, dict):
        for k in schema.get("required", []):
            if k not in inst:
                yield path, f"missing required key {k!r}"
        props = schema.get("properties", {})
        for k, v in inst.items():
            if k in props:
                yield from mini_validate(v, props[k], f"{path}.{k}", root)
            elif schema.get("additionalProperties") is False:
                yield path, f"unexpected key {k!r}"
            elif isinstance(schema.get("additionalProperties"), dict):
                yield from mini_validate(v, schema["additionalProperties"], f"{path}.{k}", root)
    if isinstance(inst, list):
        if "minItems" in schema and len(inst) < schema["minItems"]:
            yield path, f"array shorter than minItems {schema['minItems']}"
        if isinstance(schema.get("items"), dict):
            for i, v in enumerate(inst):
                yield from mini_validate(v, schema["items"], f"{path}[{i}]", root)
    for sub in schema.get("allOf", []):
        yield from mini_validate(inst, sub, path, root)
    if isinstance(schema.get("if"), dict):
        branch = "then" if not list(mini_validate(inst, schema["if"], path, root)) else "else"
        if isinstance(schema.get(branch), dict):
            yield from mini_validate(inst, schema[branch], path, root)
    for kw in ("anyOf", "oneOf"):
        if kw in schema:
            ok = sum(1 for sub in schema[kw] if not list(mini_validate(inst, sub, path, root)))
            if (kw == "anyOf" and ok == 0) or (kw == "oneOf" and ok != 1):
                yield path, f"does not satisfy {kw}"


def make_validator(schema: dict, builtin: bool = False):
    if jsonschema is not None and not builtin:
        cls = jsonschema.validators.validator_for(schema)
        cls.check_schema(schema)
        v = cls(schema)
        return lambda inst: [("$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in e.absolute_path),
                              e.message if len(e.message) <= 240 else e.message[:200] + " … " + e.message[-36:])
                             for e in sorted(v.iter_errors(inst), key=lambda e: list(map(str, e.path)))]
    return lambda inst: list(mini_validate(inst, schema))


# ------------------------------------------------------------------ helpers
def slugify(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9._-]+", "-", t).strip("-.")
    return re.sub(r"-{2,}", "-", t) or "x"


def model_slug(model_id: str) -> str:
    vendor, _, name = model_id.partition("/")
    if not name:
        vendor, name = "local", vendor
    return f"{slugify(vendor)}__{slugify(name)}"


def type_of(rel: Path):
    """The record type of a data/ file, from its path; None when the path is untyped."""
    parts = rel.parts
    if parts in FILE_TYPES:
        return FILE_TYPES[parts]
    if len(parts) == 4 and parts[1:3] == ("forge", "checkpoints"):
        return "forge-checkpoint"
    if len(parts) >= 3 and parts[1] == "item-scores":
        return "item-scores"
    if len(parts) >= 3 and parts[1] in DIR_TYPES:
        if parts[1] != "runs" and len(parts) != 3:
            return None
        return DIR_TYPES[parts[1]]
    return None


def dig(obj, path):
    for k in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
    return obj


# A score-like number in prose: one decimal, 0 to 100, not part of a version, a name or a quantity with a unit.
SUMMARY_NUM = re.compile(r"(?<![\w.\-/])(\d{1,3}\.\d)(?!\d|\.\d|-|\s*(?:bits?\b|bpw\b|GB\b|GiB\b|MB\b|B\b|%|x\b|×|"
                         r"tok|t/s|s\b|ms\b|k\b|K\b|W\b|°|points? of|times\b)|\s+\d+(?:\.\d+)?[BM]\b)")
SUMMARY_SUB = re.compile(r"\b(?:biology|history|geography|tools?|review|editing|instruction|sub-scores?)\b", re.I)
SUMMARY_JUDGED = re.compile(r"\b(?:tutor\w*|code|coding|vision|judged?|scor\w*|Q)\b", re.I)
SUMMARY_NOT_SCORE = re.compile(r"(?:Fable|vLLM|Ling|Llama|Python|version|v|engine|CUDA|Ubuntu)\s*$")


def summary_numbers(objs: dict) -> list[str]:
    """The judged-bench numbers of hand-written prose (model verdict summaries, campaign summaries) must be the current
    tables' numbers: in a sentence about tutoring, code, vision, a judge or a score, every score-like number (one decimal,
    0 to 100) must be the score or a sub-score of a row of a judged ranking (tutoring, code, vision) of that model, or of
    that campaign, or of a model the text names. A local-judge figure left in prose after the tables changed judge fails."""
    judged = [o for _, o in objs["ranking"] if (o.get("grader") or {}).get("judge")
              and o.get("bench_id") in ("tuteur/v1", "code/v1", "vision/v1")]
    by_model, by_campaign = defaultdict(set), defaultdict(set)  # (value, is a sub-score)
    for o in judged:
        for row in o.get("rows") or []:
            if not isinstance(row, dict) or not isinstance(row.get("score"), (int, float)):
                continue
            vals = {(round(float(row["score"]), 1), False)} | {
                (round(float(v), 1), True) for v in (row.get("sub_scores") or {}).values() if isinstance(v, (int, float))}
            by_model[row.get("model_id")] |= vals
            by_campaign[o.get("campaign")] |= vals
    names = {}
    for _, m in objs["model"]:
        n = m.get("name") or ""
        for k in {n, re.sub(r"\s+IT$", "", n), n.split(" (")[0]}:
            if len(k) >= 6:
                names[k] = m.get("model_id")

    def named(text):
        return {mid for k, mid in names.items() if k in text}
    errs = []

    def check(where, text, allowed):
        for sent in re.split(r"(?<=[.;])\s+", text or ""):
            if not SUMMARY_JUDGED.search(sent):
                continue
            ok = set(allowed)
            for mid in named(sent) | named(text or ""):
                ok |= by_model.get(mid, set())
            subs = bool(SUMMARY_SUB.search(sent))  # a sub-score may be cited only where the sentence names one
            ok = {v for v, sub in ok if subs or not sub}
            for mm in SUMMARY_NUM.finditer(sent):
                if SUMMARY_NOT_SCORE.search(sent[:mm.start()]):
                    continue
                if round(float(mm.group(1)), 1) not in ok:
                    errs.append(f"SUMMARY {where}: {mm.group(1)} in a sentence about a judged bench is not a score of "
                                f"the current tables for what it names: {sent[:140]!r}")
    for rel, m in objs["model"]:
        check(rel, (m.get("verdict") or {}).get("summary"), by_model.get(m.get("model_id"), set()))
    for rel, c in objs["campaign"]:
        check(rel, c.get("summary"), by_campaign.get(c.get("campaign_id"), set()))
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 epilog="Exit status: 0 valid, 1 invalid.")
    ap.add_argument("root", nargs="?", default=str(REPO), help="repo root (default: this repo)")
    ap.add_argument("--strict", action="store_true", help="every warning is an error (what check_all.sh runs)")
    ap.add_argument("--builtin", action="store_true", help="use the built-in validator even when jsonschema is importable")
    ap.add_argument("--quiet", action="store_true", help="print only the summary and errors")
    ap.add_argument("--max-print", type=int, default=60, help="error lines printed per type (default 60)")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    data_dir, schema_dir = root / "data", root / "schema"
    errors, warnings = [], []
    if not data_dir.is_dir():
        print(f"validate: no data/ under {root}")
        return 1

    validators = {}
    for sf in sorted(schema_dir.glob("*.schema.json")):
        try:
            validators[sf.name.split(".")[0]] = make_validator(json.loads(sf.read_text(encoding="utf-8")),
                                                               builtin=args.builtin)
        except Exception as exc:  # broken schema = broken contract
            errors.append(f"SCHEMA  {sf.relative_to(root)}: {exc}")

    counts = Counter()
    per_type_err = Counter()
    records = defaultdict(dict)   # type -> id -> rel path
    objs = defaultdict(list)      # type -> [(rel, obj)]
    untyped = []                  # data/ files whose path matches no record type
    for f in sorted(data_dir.rglob("*.json")):
        rel = f.relative_to(root)
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"PARSE   {rel}: {exc}")
            counts["parse_errors"] += 1
            continue
        t = type_of(rel)
        if t is None:
            counts["untyped"] += 1
            untyped.append(rel)
            continue
        if f.name.startswith("_"):
            counts["skipped_index"] += 1
            continue
        if t not in validators:
            errors.append(f"NOSCHEMA {rel}: schema/{t}.schema.json missing")
            continue
        errs = validators[t](obj)
        counts[t] += 1
        if errs:
            counts[f"{t}_invalid"] += 1
            for p, msg in errs[:5]:
                per_type_err[t] += 1
                if per_type_err[t] <= args.max_print:
                    errors.append(f"INVALID {rel} {p}: {msg}")
                else:
                    errors.append(None)  # counted, not printed
            continue
        objs[t].append((rel, obj))
        if t in ID_KEY:
            rid = obj.get(ID_KEY[t])
            if rid in records[t]:
                errors.append(f"DUPID   {rel}: {ID_KEY[t]} {rid!r} also in {records[t][rid]}")
            else:
                records[t][rid] = rel.as_posix()

    # ------------------------------------------------------------ integrity
    def warn(msg):
        (errors if args.strict else warnings).append(msg)

    for rel, o in objs["model"]:
        if o.get("slug") and rel.stem != o["slug"]:
            warn(f"NAME    {rel}: file name != slug {o['slug']!r}")
        if o.get("model_id") and o.get("slug") and model_slug(o["model_id"]) != o["slug"]:
            warn(f"SLUG    {rel}: slug {o['slug']!r} != model_slug(model_id)")
        for b in o.get("builds") or []:
            if isinstance(b, str) and b not in records["build"]:
                warn(f"REF     {rel}: build {b!r} has no record")
    for rel, o in objs["build"]:
        bid, mid = o.get("build_id", ""), o.get("model_id", "")
        if "@" in bid and rel.stem != model_slug(mid) + "@" + bid.split("@", 1)[1]:
            warn(f"NAME    {rel}: file name != <model slug>@<quant slug> of {bid!r}")
        if mid and mid not in records["model"]:
            warn(f"REF     {rel}: model {mid!r} has no record")
    for rel, o in objs["run"]:
        expect = rel.relative_to(Path("data") / "runs").with_suffix("").as_posix()
        if o.get("run_id") and o["run_id"] != expect:
            warn(f"NAME    {rel}: run_id {o['run_id']!r} != path {expect!r}")
        if o.get("model_id") and o["model_id"] not in records["model"]:
            warn(f"REF     {rel}: model {o['model_id']!r} has no record")
        if o.get("build_id") and o["build_id"] not in records["build"]:
            warn(f"REF     {rel}: build {o['build_id']!r} has no record")
    for rel, o in objs["ranking"]:
        if o.get("bench_id") and records["bench"] and o["bench_id"] not in records["bench"]:
            warn(f"REF     {rel}: bench {o['bench_id']!r} has no record")
        for row in o.get("rows") or []:
            if isinstance(row, dict) and row.get("run_id") and row["run_id"] not in records["run"]:
                warn(f"REF     {rel}: row run {row['run_id']!r} has no record")

    seen_scores = {}
    for rel, o in objs["item-scores"]:
        rid, bid = o.get("run_id"), o.get("bench_id", "")
        bench_slug = bid.replace("/", "-")
        if rel.stem != bench_slug:
            warn(f"NAME    {rel}: file name != bench slug {bench_slug!r}")
        if rid is not None:
            expect = (Path("data") / "item-scores" / rid / f"{bench_slug}.json").as_posix()
            if rel.as_posix() != expect:
                warn(f"NAME    {rel}: path != {expect}")
            if rid not in records["run"]:
                warn(f"REF     {rel}: run {rid!r} has no record")
            if (rid, bid) in seen_scores:
                warn(f"DUPID   {rel}: run {rid!r} on {bid!r} also in {seen_scores[(rid, bid)]}")
            seen_scores[(rid, bid)] = rel.as_posix()
        if records["bench"] and bid not in records["bench"]:
            warn(f"REF     {rel}: bench {bid!r} has no record")
        if o.get("model_id") and o["model_id"] not in records["model"]:
            warn(f"REF     {rel}: model {o['model_id']!r} has no record")
        if o.get("build_id") and o["build_id"] not in records["build"]:
            warn(f"REF     {rel}: build {o['build_id']!r} has no record")
        ids = [it.get("item_id") for it in o.get("items") or [] if isinstance(it, dict)]
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            warn(f"DUPID   {rel}: item ids repeated: {', '.join(map(str, dup[:5]))}")
        for it in o.get("items") or []:
            if isinstance(it, dict) and isinstance(it.get("score"), (int, float)) and \
                    isinstance(it.get("max"), (int, float)) and it["score"] > it["max"]:
                warn(f"RANGE   {rel}: item {it.get('item_id')!r} score {it['score']} > max {it['max']}")
                break
        # an item or duel the judge did not grade has no score, no verdict and names no grader; a run no judge graded
        # (an item or duel waiting for the table's judge, or every judged item and duel not graded) names no judge
        items = [it for it in o.get("items") or [] if isinstance(it, dict)]
        duel_items = [y for dd in o.get("duels_vs_anchor") or [] if isinstance(dd, dict)
                      for y in dd.get("items") or [] if isinstance(y, dict)]
        for it in items:
            if it.get("not_graded") and (it.get("score") is not None or it.get("graded_by")):
                errors.append(f"ONEJUDGE {rel}: item {it.get('item_id')!r} is not_graded but carries "
                              f"{'a score' if it.get('score') is not None else 'graded_by ' + repr(it.get('graded_by'))}")
        for y in duel_items:
            if y.get("not_graded") and y.get("verdict") is not None:
                errors.append(f"ONEJUDGE {rel}: duel {y.get('item_id')!r} is not_graded but carries a verdict")
        waiting = any(x.get("not_graded") == "no-table-judge-verdict" for x in items + duel_items)
        judged = [it for it in items if it.get("graded_by", "llm-judge") == "llm-judge" or it.get("not_graded")]
        none_graded = bool(judged) and all(it.get("not_graded") for it in judged) and \
            all(y.get("not_graded") for y in duel_items)
        if (waiting or none_graded) and (o.get("grader") or {}).get("judge"):
            errors.append(f"ONEJUDGE {rel}: grader.judge {(o.get('grader') or {}).get('judge')!r} on a run no judge "
                          "graded (its judged items and duels are not graded)")
    # one judge per table (structural): every row of a judged ranking is graded by grader.judge (no row graded by another
    # judge, no second judge equal to the table's), the item files of its runs carry the same judge, and a row without a
    # score says why (not_rated_reason); a row rated on part of its judged items says why too, and its item file agrees.
    item_of = {(o.get("run_id"), o.get("bench_id")): o for _, o in objs["item-scores"] if o.get("run_id")}
    # the judged benches: a bench whose record's grader names a model judge; every ranking of one names its judge
    judged_bench = {b.get("bench_id"): (b.get("grader") or {}).get("judge") for _, b in objs["bench"]
                    if (b.get("grader") or {}).get("judge")}
    for rel, o in objs["ranking"]:
        g = o.get("grader") or {}
        judge = g.get("judge")
        if g.get("kind") in ("llm-judge", "mixed") and not judge:
            errors.append(f"ONEJUDGE {rel}: grader.kind {g.get('kind')!r} with no grader.judge (a judged table names "
                          "its judge)")
        if o.get("bench_id") in judged_bench and not (judge or g.get("judge_id")):
            errors.append(f"ONEJUDGE {rel}: a ranking of the judged bench {o.get('bench_id')!r} names no judge")
        if o.get("bench_id") in judged_bench and g.get("kind") not in ("llm-judge", "mixed"):
            errors.append(f"ONEJUDGE {rel}: a ranking of the judged bench {o.get('bench_id')!r} has grader.kind "
                          f"{g.get('kind')!r}, not llm-judge or mixed")
        # the rules below apply to every ranking whose grader names a model judge (judge or judge_id), whatever its kind
        if not (judge or g.get("judge_id")):
            continue
        judge = judge or g.get("judge_id")
        jr = o.get("judge_robustness") or {}
        if jr.get("second_judge") and jr["second_judge"] == judge:
            errors.append(f"ONEJUDGE {rel}: judge_robustness.second_judge is the table's own judge")
        # every table under Claude Fable 5.1 is compared with the local judge as two full orders (no substitution, no
        # missing method: a table that lost the field must not slip past the rules below)
        fable_table = g.get("judge_id") == "claude-fable-5-1" or "Claude Fable" in str(judge)
        if fable_table and jr.get("method") != "two-full-orders":
            errors.append(f"ONEJUDGE {rel}: a table graded by Claude Fable 5.1 must have judge_robustness.method "
                          f"two-full-orders, not {jr.get('method')!r}")
        two_orders = jr.get("method") == "two-full-orders"
        if two_orders:
            # the two orders on the rows both judges ranked: exactly rows_compared rows carry a second rank, each set of
            # ranks is 1..rows_compared without repeats, this table's ranks among them follow the ranks shown, and tau,
            # ranks_changed and top_of_table are what those two orders give
            common = [r for r in o.get("rows") or [] if isinstance(r, dict)
                      and isinstance((r.get("extra") or {}).get("second_judge"), dict)]
            n = jr.get("rows_compared")
            if not isinstance(n, int) or len(common) != n:
                errors.append(f"ONEJUDGE {rel}: {len(common)} row(s) carry extra.second_judge, judge_robustness."
                              f"rows_compared is {n!r}")
            for row in o.get("rows") or []:
                ex = (row.get("extra") or {}) if isinstance(row, dict) else {}
                if isinstance(row, dict) and ("rank_interval" in ex) != isinstance(ex.get("second_judge"), dict):
                    errors.append(f"ONEJUDGE {rel}: row {row.get('label') or row.get('model_id')!r}: rank_interval and "
                                  "extra.second_judge must come together (a row both judges ranked carries both)")
            here = [r["extra"]["second_judge"].get("table_judge_rank_on_same_rows") for r in common]
            other = [r["extra"]["second_judge"].get("rank") for r in common]
            want = list(range(1, len(common) + 1))
            ok_sets = all(isinstance(x, int) for x in here + other) and sorted(here) == want and sorted(other) == want
            if not ok_sets:
                errors.append(f"ONEJUDGE {rel}: the second ranks of the rows both judges ranked are not each 1.."
                              f"{len(common)} without repeats (table_judge_rank_on_same_rows {here}, rank {other})")
            else:
                shown = sorted(common, key=lambda r: (r.get("rank") if isinstance(r.get("rank"), int) else 10 ** 9))
                if [r["extra"]["second_judge"]["table_judge_rank_on_same_rows"] for r in shown] != want:
                    errors.append(f"ONEJUDGE {rel}: table_judge_rank_on_same_rows does not follow the ranks shown")
                a = [id(r) for r in sorted(common, key=lambda r: r["extra"]["second_judge"]["table_judge_rank_on_same_rows"])]
                b = [id(r) for r in sorted(common, key=lambda r: r["extra"]["second_judge"]["rank"])]

                def tau_a(xa, xb):
                    pos = {x: i for i, x in enumerate(xb)}
                    m = len(xa)
                    if m < 2:
                        return None
                    c = sum(1 if pos[xa[i]] < pos[xa[j]] else -1 for i in range(m) for j in range(i + 1, m))
                    return c / (m * (m - 1) / 2)
                t = tau_a(a, b)
                if t is not None and isinstance(jr.get("kendall_tau"), (int, float)) and abs(t - jr["kendall_tau"]) > 0.0006:
                    errors.append(f"ONEJUDGE {rel}: kendall_tau {jr['kendall_tau']} is not the two orders' {round(t, 3)}")
                ch = sum(1 for x, y in zip(a, b) if x != y)
                if jr.get("ranks_changed") is not None and jr.get("ranks_changed") != ch:
                    errors.append(f"ONEJUDGE {rel}: ranks_changed {jr.get('ranks_changed')} is not the two orders' {ch}")
                tops = jr.get("top_of_table") or {}
                for k in (5, 10):
                    key = f"top_{k}"
                    if len(a) > k and key not in tops:
                        errors.append(f"ONEJUDGE {rel}: {len(a)} rows both judges ranked but no top_of_table.{key}")
                    if key in tops:
                        tv = tops[key] or {}
                        ta = a[:k]
                        tb = [x for x in b if x in set(ta)]
                        tt = tau_a(ta, tb)
                        pc = sum(1 for x, y in zip(a[:k], b[:k]) if x != y)
                        if len(a) <= k or tv.get("rows") != k or tt is None or \
                                abs(tt - (tv.get("kendall_tau") if isinstance(tv.get("kendall_tau"), (int, float)) else 9)) > 0.0006 \
                                or tv.get("places_changed") != pc:
                            errors.append(f"ONEJUDGE {rel}: top_of_table.{key} {tv} is not what the two orders give "
                                          f"(rows {k}, tau {None if tt is None else round(tt, 3)}, places_changed {pc})")
        for row in o.get("rows") or []:
            if not isinstance(row, dict):
                continue
            ex = row.get("extra") or {}
            who = row.get("label") or row.get("model_id")
            # no judged ranking carries another judge's score or CI95 (no published table uses substitution any more)
            sj2 = ex.get("second_judge")
            if isinstance(sj2, dict) and set(sj2) & {"score", "ci95"}:
                errors.append(f"ONEJUDGE {rel}: row {who!r}: extra.second_judge carries "
                              f"{sorted(set(sj2) & {'score', 'ci95'})} (a table holds one judge's scores)")
            if two_orders:
                # a table compared with another judge's full order holds that judge's ranks only: no score, no CI95, no
                # flag of a row graded by another judge
                allowed = {"judge", "rank", "rank_counted_on", "table_judge_rank_on_same_rows"}
                if isinstance(sj2, dict) and set(sj2) - allowed:
                    errors.append(f"ONEJUDGE {rel}: row {who!r}: extra.second_judge carries "
                                  f"{sorted(set(sj2) - allowed)} (two-full-orders allows {sorted(allowed)} only)")
                # the rank interval is in the frame of the rank shown: the rank shown, moved by the row's shift between
                # the two judges on the rows both ranked
                iv = ex.get("rank_interval")
                if sj2 is not None or iv is not None:
                    d = row.get("rank")
                    k_o, k_t = (sj2 or {}).get("rank"), (sj2 or {}).get("table_judge_rank_on_same_rows")
                    if not (isinstance(d, int) and isinstance(k_o, int) and isinstance(k_t, int)
                            and (sj2 or {}).get("rank_counted_on") == "rows-both-judges-ranked"
                            and iv == [min(d, d + k_o - k_t), max(d, d + k_o - k_t)]):
                        errors.append(f"ONEJUDGE {rel}: row {who!r}: rank_interval {iv} is not the rank shown ({d}) "
                                      f"moved by the shift between the judges on the common rows ({k_t} -> {k_o})")
                for k in ("harness_rank", "graded_by", "comparable"):
                    if k in ex:
                        errors.append(f"ONEJUDGE {rel}: row {who!r}: extra.{k} in a two-full-orders table")
            for k in ("graded_by", "judge"):
                if ex.get(k) and ex[k] != judge:
                    errors.append(f"ONEJUDGE {rel}: row {who!r} graded by {ex[k]!r}, not by the table's judge")
            if ex.get("comparable") is False:
                errors.append(f"ONEJUDGE {rel}: row {who!r} is flagged not comparable (another judge's scale)")
            sj = ex.get("second_judge")
            if isinstance(sj, dict) and sj.get("judge") == judge:
                errors.append(f"ONEJUDGE {rel}: row {who!r} has the table's own judge as second judge")
            if g.get("judge_id") and row.get("score") is None and \
                    ex.get("not_rated_reason") not in ("harness", "no-table-judge-verdict"):
                errors.append(f"ONEJUDGE {rel}: row {who!r} has no score and no allowed not_rated_reason")
            if ex.get("items_not_graded") and ex.get("items_not_graded_reason") != "provider-safeguard":
                errors.append(f"ONEJUDGE {rel}: row {who!r} rated on part of its items without an allowed reason")
            it = item_of.get((row.get("run_id"), o.get("bench_id")))
            if it is None:
                continue
            judged_items = [x for x in it.get("items") or [] if isinstance(x, dict)
                            and x.get("graded_by", "llm-judge") == "llm-judge" and not x.get("not_graded")]
            if (it.get("grader") or {}).get("judge") is None and not judged_items and row.get("score") is None:
                pass  # no item of this run reached a judge: its item file names none
            elif (it.get("grader") or {}).get("judge") != judge:
                errors.append(f"ONEJUDGE {rel}: row {who!r}: its item file is graded by "
                              f"{(it.get('grader') or {}).get('judge')!r}, not by the table's judge")
            ng = [x for x in it.get("items") or [] if isinstance(x, dict) and x.get("not_graded")]
            if row.get("score") is not None and len(ng) != (ex.get("items_not_graded") or 0):
                errors.append(f"ONEJUDGE {rel}: row {who!r}: {len(ng)} item(s) not graded in its item file, "
                              f"{ex.get('items_not_graded') or 0} on the row")
            if row.get("score") is not None and any(x.get("not_graded") != "provider-safeguard" for x in ng):
                errors.append(f"ONEJUDGE {rel}: row {who!r}: a rated row's item file holds items its judge never graded")
            # the item file reproduces the row: its scored items are the row's n_scored and their mean is its Q
            sc = [x["score"] / x["max"] for x in it.get("items") or []
                  if isinstance(x, dict) and isinstance(x.get("score"), (int, float)) and x.get("max")]
            if g.get("judge_id") and isinstance(row.get("score"), (int, float)) and sc and \
                    (len(sc) != ex.get("n_scored", len(sc)) or abs(100 * sum(sc) / len(sc) - row["score"]) > 0.051):
                errors.append(f"ONEJUDGE {rel}: row {who!r}: its item file gives {round(100 * sum(sc) / len(sc), 1)} over "
                              f"{len(sc)} items, the row {row['score']} over {ex.get('n_scored')}")
    errors.extend(summary_numbers(objs))
    for rel, o in objs["judge-audit"]:
        lj = o.get("local_judge") or {}
        benches = [b.get("bench") for b in ((lj.get("same_lineage_share") or {}).get("by_bench") or {}).values()]
        campaigns = []
        for cc in o.get("cross_checks") or []:
            campaigns.append(cc.get("campaign"))
            benches += [d.get("bench") for d in (cc.get("delta_q_by_mode") or {}).values()]
            for rows in (cc.get("kendall_tau_by_mode") or {}).values():
                campaigns += [r.get("campaign") for r in rows]
        for b in sorted({b for b in benches if b}):
            if records["bench"] and b not in records["bench"]:
                warn(f"REF     {rel}: bench {b!r} has no record")
        for c in sorted({c for c in campaigns if c}):
            if records["campaign"] and c not in records["campaign"]:
                warn(f"REF     {rel}: campaign {c!r} has no record")

    for rel in untyped:
        warn(f"UNTYPED {rel}: no record type for this path (see validate.py --help); "
             "move it, or add a type and a schema")

    run_objs = {o.get("run_id"): o for _, o in objs["run"]}
    for rel, o in objs["comparison"]:
        if o.get("comparison_id") and rel.stem != o["comparison_id"]:
            warn(f"NAME    {rel}: file name != comparison_id {o['comparison_id']!r}")
        bad_runs, bad_paths = set(), set()
        for row in (o.get("rows") or []) + (o.get("summary_rows") or []):
            if isinstance(row, dict):
                bad_runs.update(r for r in row.get("run_ids") or [] if r not in records["run"])
                bad_paths.update(e for e in row.get("evidence") or []
                                 if isinstance(e, str) and not (root / e).exists())
        for rid in sorted(bad_runs, key=str):
            warn(f"REF     {rel}: a row names run {rid!r}, which has no record")
        for ev in sorted(bad_paths):
            warn(f"REF     {rel}: a row cites {ev!r}, which does not exist")
    for rel, o in objs["runs-index"]:
        entries = [e for e in o.get("runs") or [] if isinstance(e, dict)]
        if o.get("n") != len(entries):
            warn(f"COUNT   {rel}: n {o.get('n')!r} != {len(entries)} entries")
        ids = [e.get("run_id") for e in entries]
        for rid in sorted({i for i in ids if ids.count(i) > 1}):
            warn(f"DUPID   {rel}: run {rid!r} listed more than once")
        for rid in sorted(set(ids) - set(run_objs), key=str):
            warn(f"REF     {rel}: run {rid!r} has no record")
        for rid in sorted(set(run_objs) - set(ids), key=str):
            warn(f"REF     {rel}: run record {rid!r} is missing from the index")
        for e in entries:
            rec = run_objs.get(e.get("run_id"))
            if rec is None:
                continue
            for field, path in INDEX_FIELDS.items():
                if field in e and e[field] != dig(rec, path):
                    warn(f"STALE   {rel}: {e['run_id']}: {field} {e[field]!r} != run record {dig(rec, path)!r}")
            mib = (rec.get("vram") or {}).get("mib_per_gpu") or []
            if "vram_mib_per_gpu" in e and e["vram_mib_per_gpu"] != mib:
                warn(f"STALE   {rel}: {e['run_id']}: vram_mib_per_gpu != run record")
    for rel, o in objs["watchlist"]:
        entries = o.get("entries") or []
        if o.get("count") != len(entries):
            warn(f"COUNT   {rel}: count {o.get('count')!r} != {len(entries)} entries")
        for e in entries:
            if isinstance(e, dict) and e.get("model_id") and e["model_id"] not in records["model"]:
                warn(f"REF     {rel}: {e.get('name')!r} names model {e['model_id']!r}, which has no record")
        for key, n in sorted((o.get("counts") or {}).items()):
            real = sum(1 for e in entries if isinstance(e, dict) and
                       (e.get("measured_later") is True if key == "measured_later" else e.get("route") == key))
            if n != real:
                warn(f"COUNT   {rel}: counts.{key} {n!r} != {real} entries")
    ckpt_ids = set(records["forge-checkpoint"])
    for rel, o in objs["forge-checkpoint"]:
        if o.get("checkpoint_id") and rel.stem != o["checkpoint_id"]:
            warn(f"NAME    {rel}: file name != checkpoint_id {o['checkpoint_id']!r}")
    for rel, o in objs["forge-summary"]:
        listed = set(o.get("checkpoint_records") or [])
        if o.get("checkpoints") != len(ckpt_ids):
            warn(f"COUNT   {rel}: checkpoints {o.get('checkpoints')!r} != {len(ckpt_ids)} checkpoint records")
        for cid in sorted(listed - ckpt_ids):
            warn(f"REF     {rel}: checkpoint {cid!r} has no record")
        for cid in sorted(ckpt_ids - listed):
            warn(f"REF     {rel}: checkpoint record {cid!r} is not listed in checkpoint_records")

    shown = [e for e in errors if e]
    hidden = len(errors) - len(shown)
    for e in shown:
        print(e)
    if hidden:
        print(f"... {hidden} more invalid entries not printed (--max-print)")
    if not args.quiet:
        for w in warnings[:80]:
            print(f"warning: {w}")
        if len(warnings) > 80:
            print(f"warning: ... {len(warnings) - 80} more")
    engine = "jsonschema" if jsonschema and not args.builtin else "built-in validator"
    summary = {k: v for k, v in sorted(counts.items())}
    print(f"validate: {summary} — {len(errors)} error(s), {len(warnings)} warning(s) [{engine}]")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
