#!/usr/bin/env python3
"""Fill the generated blocks of the prose from data/ and from two source texts.

    python3 tools/build_readme.py           rewrite the blocks in place
    python3 tools/build_readme.py --check   exit 1 if a block is stale
    python3 tools/build_readme.py --print   print the blocks, write nothing

Blocks (each between <!-- gen:NAME --> and <!-- /gen:NAME -->):

  counts         README.md. Counts of models, private fine-tune checkpoints,
                 builds, runs per hardware configuration, benches, campaigns
                 and the watchlist (open-weight models spotted for the rig;
                 cloud or API-only models and tools counted apart), and the
                 "data as of" date, computed from data/ only, so the README
                 never carries a hand-typed count. A run is a distinct run
                 record: a record whose duplicate_of is set is an identical
                 copy of an earlier run and is counted apart, as "+N copies",
                 never as a run.
  headline-rule  README.md and methodology/METHODOLOGY.md. The text of
                 methodology/headline-rule.md (its title line removed), so
                 the rule is written once and shown the same everywhere.
  judge-banner   methodology/JUDGE.md. The text of
                 methodology/judge-banner.md (its title line removed), quoted:
                 the banner of Claude Fable 5.1's tables.
  judge-banner-local
                 methodology/JUDGE.md. The text of
                 methodology/judge-banner-local.md, quoted: the banner of the
                 local judge's tables (the refusal probe and the forge).

A record is recognised by its id field (model_id, build_id, run_id, bench_id,
campaign_id), each id is counted once, and files are read in sorted order:
the same inputs always give the same blocks. Private fine-tune checkpoints are
taken from the aggregate data/forge/summary.json when it exists (its
`checkpoints` count), else from model records whose category is private-forge.
Standard library only.

Exit codes: 0 up to date (or rewritten), 1 stale or markers missing,
2 unreadable data or source text.
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADLINE_RULE = Path("methodology/headline-rule.md")
JUDGE_BANNER = Path("methodology/judge-banner.md")
JUDGE_BANNER_LOCAL = Path("methodology/judge-banner-local.md")

# Keys whose values are dates of measurement, freezing, verdict or correction.
DATE_KEYS = frozenset({
    "as_of", "date", "ended_at", "first_tested", "frozen_at",
    "generated_at", "last_tested", "started_at",
})
DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:$|[T ])")

HARDWARE_ROWS = (
    ("1x3090fe", "on one card"),
    ("2x3090fe-nvlink", "on one NVLink pair"),
    ("2x2x3090fe-nvlink", "on both pairs as one configuration"),
    ("unknown", "topology unknown"),
)


class DataError(Exception):
    pass


def begin(name: str) -> str:
    return f"<!-- gen:{name} -->"


def end(name: str) -> str:
    return f"<!-- /gen:{name} -->"


def load_records(data_dir: Path):
    """Yield (relative path, parsed JSON) for every .json file, sorted."""
    if not data_dir.is_dir():
        return
    for path in sorted(data_dir.rglob("*.json")):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise DataError(f"{path}: {exc}") from exc
        yield path, obj


def iter_dates(obj):
    """Every valid ISO date found under a date key, at any depth."""
    if isinstance(obj, dict):
        for key in sorted(obj):
            value = obj[key]
            if key in DATE_KEYS and isinstance(value, str):
                m = DATE_RE.match(value.strip())
                if m:
                    try:
                        yield dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    except ValueError:
                        pass
            else:
                yield from iter_dates(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from iter_dates(value)


# watchlist routes (data/watchlist.json, entries[].route) and their labels, singular and plural
WATCH_ROUTES = {"local-weights": ("open-weight model", "open-weight models"),
                "cloud-api": ("cloud or API-only model", "cloud or API-only models"),
                "tool": ("tool that is not a model", "tools that are not models")}


def is_forge(model: dict) -> bool:
    lineage = model.get("lineage") if isinstance(model.get("lineage"), dict) else {}
    return model.get("category") == "private-forge" or lineage.get("kind") == "private-forge"


def compute(data_dir: Path) -> dict:
    models, forge, builds, benches, campaigns = set(), set(), set(), set(), set()
    runs: dict[str, tuple[str, bool]] = {}
    forge_summary = None
    watchlist = None
    latest = None
    known_hw = {h for h, _ in HARDWARE_ROWS}
    for path, obj in load_records(data_dir):
        for day in iter_dates(obj):
            if latest is None or day > latest:
                latest = day
        if not isinstance(obj, dict):
            continue
        rel = path.relative_to(data_dir).as_posix()
        if rel == "forge/summary.json" and isinstance(obj.get("checkpoints"), int):
            forge_summary = obj["checkpoints"]
            continue
        if rel == "watchlist.json" and isinstance(obj.get("entries"), list):
            entries = [e for e in obj["entries"] if isinstance(e, dict)]
            watchlist = {"total": len(obj["entries"]),
                         "routes": {r: sum(1 for e in entries if e.get("route") == r) for r in WATCH_ROUTES},
                         "later": {r: sum(1 for e in entries if e.get("route") == r
                                          and e.get("measured_later") is True) for r in WATCH_ROUTES}}
            continue
        if isinstance(obj.get("model_id"), str) and "slug" in obj and "builds" in obj:
            (forge if is_forge(obj) else models).add(obj["model_id"])
        elif isinstance(obj.get("build_id"), str) and "quant" in obj:
            builds.add(obj["build_id"])
        elif isinstance(obj.get("run_id"), str) and "hardware" in obj:
            hw = obj.get("hardware")
            copy = isinstance(obj.get("duplicate_of"), str) and bool(obj["duplicate_of"])
            runs[obj["run_id"]] = (hw if hw in known_hw else "unknown", copy)
        elif isinstance(obj.get("bench_id"), str) and "manifest" in obj:
            benches.add(obj["bench_id"])
        elif isinstance(obj.get("campaign_id"), str) and "status" in obj:
            campaigns.add(obj["campaign_id"])
    per_hw = {h: 0 for h, _ in HARDWARE_ROWS}
    copies_hw = {h: 0 for h, _ in HARDWARE_ROWS}
    for hw, copy in runs.values():
        (copies_hw if copy else per_hw)[hw] += 1
    return {
        "models": len(models), "builds": len(builds), "watchlist": watchlist,
        "forge": forge_summary if forge_summary is not None else len(forge),
        "runs": sum(per_hw.values()), "copies": sum(copies_hw.values()),
        "per_hw": per_hw, "copies_hw": copies_hw, "benches": len(benches),
        "campaigns": len(campaigns), "latest": latest.isoformat() if latest else None,
    }


def with_copies(n: int, copies: int, bold: bool = False) -> str:
    text = f"**{n}**" if bold else str(n)
    if copies:
        text += f" (+{copies} {'copy' if copies == 1 else 'copies'})"
    return text


def render_counts(c: dict) -> str:
    rows = [
        ("Models (upstream, public)", f"**{c['models']}**"),
        ("Private fine-tune checkpoints, counted apart", str(c["forge"])),
        ("Builds (quantisations, GGUFs, adapters)", str(c["builds"])),
        ("Runs (distinct run records)", with_copies(c["runs"], c["copies"], bold=True)),
    ]
    rows += [(f"&nbsp;&nbsp;· {label} (`{hw}`)" if hw != "unknown" else f"&nbsp;&nbsp;· {label}",
              with_copies(c["per_hw"][hw], c["copies_hw"][hw])) for hw, label in HARDWARE_ROWS]
    rows += [("Frozen benches", str(c["benches"])), ("Campaigns", str(c["campaigns"]))]
    if c["watchlist"] is not None:
        w = c["watchlist"]
        # The watchlist's count is the open-weight models spotted for the rig; cloud or API-only models and
        # tools sit in the same file but are counted apart, never added to it.
        def later(r: str) -> str:
            return f" ({w['later'][r]} measured later)" if w["later"][r] else ""
        rows.append(("Watchlist entries: open-weight models or builds spotted for the rig, not run here when listed",
                     f"{w['routes']['local-weights']}{later('local-weights')}"))
        rows += [(f"&nbsp;&nbsp;· listed apart, not counted above: {WATCH_ROUTES[r][1]}", f"{n}{later(r)}")
                 for r, n in w["routes"].items() if r != "local-weights" and n]
        unrouted = w["total"] - sum(w["routes"].values())
        if unrouted:
            rows.append(("&nbsp;&nbsp;· listed apart, not counted above: entries without a known route", str(unrouted)))
    lines = [
        begin("counts"),
        "<!-- Generated by tools/build_readme.py from data/. Do not edit by hand. -->",
        "",
        "| What | Count |",
        "|---|---:|",
    ]
    lines += [f"| {label} | {value} |" for label, value in rows]
    lines += [
        "",
        "A **run** is one distinct run record in [data/runs/](data/runs/). A **copy** is",
        "an identical copy of an earlier run's record and evidence, carried into a later",
        "campaign; its `duplicate_of` names the original. Copies are shown apart, as",
        "\"+N copies\", and never counted as runs.",
        "",
    ]
    if c["latest"]:
        lines.append(f"Data as of **{c['latest']}**, the latest date found in [data/](data/).")
    else:
        lines.append("Data as of: no dated record in [data/](data/) yet.")
    lines.append(end("counts"))
    return "\n".join(lines)


def source_text(root: Path, rel: Path) -> str:
    """The body of a source text: its first '# ' title line removed, outer blank lines trimmed."""
    path = root / rel
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise DataError(f"{path}: {exc}") from exc
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        raise DataError(f"{path}: empty")
    return "\n".join(lines)


def render_text(name: str, body: str, src: Path, quote: bool = False) -> str:
    if quote:
        body = "\n".join(f"> {line}" if line.strip() else ">" for line in body.splitlines())
    return "\n".join([
        begin(name),
        f"<!-- Copied by tools/build_readme.py from {src.as_posix()}. Edit that file, not this block. -->",
        "",
        body,
        "",
        end(name),
    ])


def splice(text: str, name: str, block: str) -> str:
    start = text.find(begin(name))
    stop = text.find(end(name))
    if start < 0 or stop < 0 or stop < start:
        raise ValueError(f"markers {begin(name)} ... {end(name)} not found in order")
    return text[:start] + block + text[stop + len(end(name)):]


def plan(root: Path, data_dir: Path, readme: Path) -> dict[Path, list[tuple[str, str]]]:
    """Every target file with the (block name, block text) pairs it must carry."""
    counts = render_counts(compute(data_dir))
    rule = render_text("headline-rule", source_text(root, HEADLINE_RULE), HEADLINE_RULE)
    banner = render_text("judge-banner", source_text(root, JUDGE_BANNER), JUDGE_BANNER, quote=True)
    banner_local = render_text("judge-banner-local", source_text(root, JUDGE_BANNER_LOCAL), JUDGE_BANNER_LOCAL, quote=True)
    return {
        readme: [("counts", counts), ("headline-rule", rule)],
        root / "methodology" / "METHODOLOGY.md": [("headline-rule", rule)],
        root / "methodology" / "JUDGE.md": [("judge-banner", banner), ("judge-banner-local", banner_local)],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="exit 1 if a generated block is stale")
    mode.add_argument("--print", action="store_true", help="print the blocks and write nothing")
    ap.add_argument("--readme", type=Path, default=ROOT / "README.md")
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    a = ap.parse_args(argv)

    try:
        targets = plan(ROOT, a.data, a.readme)
    except DataError as exc:
        print(f"build_readme: unreadable input: {exc}", file=sys.stderr)
        return 2
    if a.print:
        seen = set()
        for blocks in targets.values():
            for name, block in blocks:
                if name not in seen:
                    seen.add(name)
                    print(block)
        return 0
    status = 0
    for path, blocks in targets.items():
        label = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
        try:
            current = path.read_text(encoding="utf-8")
            updated = current
            for name, block in blocks:
                updated = splice(updated, name, block)
        except (OSError, ValueError) as exc:
            print(f"build_readme: {label}: {exc}", file=sys.stderr)
            status = 1
            continue
        names = ", ".join(n for n, _ in blocks)
        if a.check:
            if updated == current:
                print(f"build_readme: {label}: up to date ({names})")
            else:
                sys.stdout.writelines(difflib.unified_diff(
                    current.splitlines(keepends=True), updated.splitlines(keepends=True),
                    f"{label} (on disk)", f"{label} (generated)"))
                print(f"build_readme: {label}: stale; run python3 tools/build_readme.py", file=sys.stderr)
                status = 1
        elif updated != current:
            path.write_text(updated, encoding="utf-8", newline="\n")
            print(f"build_readme: {label}: rewritten ({names})")
        else:
            print(f"build_readme: {label}: already up to date ({names})")
    return status


if __name__ == "__main__":
    sys.exit(main())
