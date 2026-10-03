#!/usr/bin/env python3
"""G5 number gate: every number the built site shows through <Num> comes from data/.

<Num> (site/src/components/Num.astro) renders a number as an element carrying
`data-num` (the raw value, String(value)) and, when it has a source, an `href`
to the run page, the evidence file on GitHub, or a fallback page. The markup
names no JSON path, so the gate checks the strictest thing it allows, for every
data-num element of site/dist/**/*.html:

  1. rounding  the visible text (unit span and a leading "~" aside) is exactly
               fmtNum(data-num) of site/src/lib/site.ts: en-US grouping,
               half-expand rounding of the shortest decimal (as V8 does), with
               either the default 0 to 4 fraction digits or a fixed `digits`.
  2. source    data-num equals, exactly as a float, a number of the JSON the
               element links to:
                 runs/<id>/        data/runs/<id>.json and every data/ object
                                   naming that run id (ranking rows, item
                                   scores, comparisons, campaigns...)
                 rankings/<id>/    data/rankings/<id>.json (+ objects naming it)
                 models/<slug>/    data/models/<slug>.json, its builds, and the
                                   objects naming the model id
                 benches/ campaigns/ compare/ configs/ rig/ forge/
                                   the matching data/ record(s); a section
                                   index (e.g. models/) is the whole directory
                 github blob|tree  that repository file (JSON numbers, or a
                                   number token of a text file) or directory
                 #anchor           the record(s) of the page itself
               A count is accepted when it is the length of an array of that
               source, the number of records of a linked section directory, or,
               for a page about an id, the number of files or run records
               naming that id, or of distinct models or builds of those runs,
               or the number of rows of the linked file naming the page's id.
               An element without a link must hold a number of its page's
               record(s), or failing that one found anywhere under data/
               (counted apart as "unlinked, found elsewhere").
               An integer the page computes from a filtered list and links to
               an anchor or a section index ("3 runs used a floating tag") has
               no stored value: it must not exceed the source's largest record
               count, and is reported as a warning.
               Chart scale ticks (inside an aria-hidden element) are not data:
               only their rounding is checked.

Numbers written in prose (text outside data-num elements) on the model, config
and compare pages are reported as warnings with counts: they bypass the check
(single digits and the card's name "3090" are counted apart).

The README's generated block is checked with tools/build_readme.py --check.

Exceptions, in tools/exceptions.json, reviewed one by one: {"tool":
"verify_numbers", "file": "<page glob under site/dist>", "rule": "rounding" |
"source", "value": "<data-num, optional>", "reason": "..."}.

usage:
  tools/verify_numbers.py [--dist DIR] [--max-print N] [--verbose] [--no-readme]
Exit status: 0 every number traced, 1 a number failed or the README block is
stale, 2 site/dist missing.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import math
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gatelib import REPO, load_exceptions  # noqa: E402

BASE = "/rtx3090fe-model-tests/"
GITHUB_RE = re.compile(r"^https://github\.com/[^/]+/[^/]+/(?:blob|tree)/[^/]+/(.+)$")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "source", "track", "wbr"}
SKIP_TEXT = {"script", "style", "code", "pre", "svg", "title", "template"}
PROSE_PAGES = ("models/", "configs/", "compare/")
# a number in prose: digits with optional grouping and decimals, not inside a word,
# an id, a date, a version or a path
PROSE_NUM = re.compile(r"(?<![\w.\-/@:#])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w\-/@:]|\.\d)")
SECTION_DIRS = {"models": "data/models", "campaigns": "data/campaigns", "benches": "data/benches",
                "rankings": "data/rankings", "compare": "data/comparisons", "configs": "data/hardware",
                "runs": "data/runs"}


# ------------------------------------------------------------------ fmtNum
def _group(int_part: str) -> str:
    out = []
    while len(int_part) > 3:
        out.insert(0, int_part[-3:])
        int_part = int_part[:-3]
    out.insert(0, int_part)
    return ",".join(out)


def fmt_num(v: float, min_frac: int, max_frac: int) -> str:
    """Intl.NumberFormat('en-US', {minimumFractionDigits, maximumFractionDigits}).format(v)."""
    # V8 rounds the shortest decimal that round-trips (String(v)), half away from zero:
    # 1.005 -> "1.01"; a negative value that rounds to zero keeps its sign: "-0"
    q = Decimal(repr(float(v))).quantize(Decimal(1).scaleb(-max_frac), rounding=ROUND_HALF_UP)
    int_part, _, frac = f"{abs(q):f}".partition(".")
    frac = frac.rstrip("0")
    frac += "0" * max(0, min_frac - len(frac))
    text = _group(int_part) + (f".{frac}" if frac else "")
    return ("-" + text) if math.copysign(1.0, v) < 0 else text


def rounding_ok(v: float, shown: str) -> bool:
    shown = shown.replace("−", "-")
    if fmt_num(v, 0, 4) == shown:      # default digits
        return True
    d = len(shown.partition(".")[2])  # an explicit `digits`
    return fmt_num(v, d, d) == shown


# ------------------------------------------------------------------ data index
def walk(obj, values: set, counts: set):
    """Every number of a JSON value into values; the length of every array into counts."""
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        values.add(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            walk(v, values, counts)
    elif isinstance(obj, list):
        counts.add(float(len(obj)))
        for v in obj:
            walk(v, values, counts)


def strings_of(obj, out: set) -> set:
    if isinstance(obj, str):
        if len(obj) < 200:
            out.add(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            strings_of(v, out)
    elif isinstance(obj, list):
        for v in obj:
            strings_of(v, out)
    return out


@dataclass
class Source:
    label: str
    values: set = field(default_factory=set)
    counts: set = field(default_factory=set)
    rels: set = field(default_factory=set)   # data files it was read from

    def add(self, other: "Source") -> "Source":
        self.values |= other.values
        self.counts |= other.counts
        self.rels |= other.rels
        return self

    def has(self, v: float) -> str | None:
        if v in self.values:
            return "value"
        if v in self.counts:
            return "count"
        return None


class DataIndex:
    def __init__(self, root: Path):
        self.root = root
        self.files: dict[str, object] = {}
        for f in sorted((root / "data").rglob("*.json")):
            try:
                self.files[f.relative_to(root).as_posix()] = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
        self._src: dict[str, Source] = {}
        self.everything = Source("data/")
        for p in self.files:
            self.everything.add(self.file(p))
        # every string id held by an object (as a value, or in a list value) -> the
        # numbers of that object: what a page about that id may show
        self.ctx: dict[str, Source] = defaultdict(lambda: Source("objects naming it"))
        for o in self.files.values():
            self._walk_ctx(o)
        # record counts per id: files naming it, run records naming it, and the distinct
        # models and builds of those runs ("25 runs", "35 models" on a page about the id)
        naming: dict[str, set] = defaultdict(set)
        for p, o in self.files.items():
            for sv in strings_of(o, set()):
                naming[sv].add(p)
        for ident, ps in naming.items():
            runs = [self.files[p] for p in ps if p.startswith("data/runs/") and isinstance(self.files[p], dict)]
            cnt = {len(ps), len(runs), len({r.get("model_id") for r in runs}),
                   len({r.get("build_id") for r in runs})}
            self.ctx[ident].counts |= {float(x) for x in cnt}

    def file(self, rel: str) -> Source:
        if rel not in self._src:
            s = Source(rel, rels={rel})
            if rel in self.files:
                walk(self.files[rel], s.values, s.counts)
            self._src[rel] = s
        return self._src[rel]

    def _walk_ctx(self, o):
        if isinstance(o, dict):
            ids = set()
            for v in o.values():
                if isinstance(v, str) and len(v) < 200:
                    ids.add(v)
                elif isinstance(v, list):
                    ids.update(x for x in v if isinstance(x, str) and len(x) < 200)
            if ids:
                s = Source("")
                walk(o, s.values, s.counts)
                if s.values or s.counts:
                    for i in ids:
                        self.ctx[i].add(s)
            for v in o.values():
                self._walk_ctx(v)
        elif isinstance(o, list):
            for v in o:
                self._walk_ctx(v)

    def rows_naming(self, rels, ident: str) -> int | None:
        """Array elements (objects) of the given files that name ident: "10 arms of this
        model" on a model page linking to a ranking that has 10 rows of it."""
        if len(rels) != 1:
            return None
        n = 0
        stack = [self.files.get(next(iter(rels)))]
        while stack:
            o = stack.pop()
            if isinstance(o, list):
                for x in o:
                    if isinstance(x, dict) and ident in x.values():
                        n += 1
                    stack.append(x)
            elif isinstance(o, dict):
                stack.extend(v for v in o.values() if isinstance(v, (dict, list)))
        return n

    def subject_ids(self, page: str) -> set:
        """The ids a page is about: its model (and builds), run, campaign, bench..."""
        parts = [p for p in page.split("/") if p and p != "index.html"]
        if len(parts) < 2:
            return set()
        sec, rest = parts[0], parts[1:]
        if sec == "models":
            m = self.files.get(f"data/models/{rest[0]}.json")
            return {m["model_id"]} if isinstance(m, dict) and m.get("model_id") else set()
        if sec == "runs":
            return {"/".join(rest)}
        if sec == "benches":
            return {"/".join(rest[:2])}
        return {rest[0]}

    def directory(self, rel_dir: str) -> Source:
        rel_dir = rel_dir.rstrip("/")
        s = Source(rel_dir + "/")
        n = 0
        for p in self.files:
            if p.startswith(rel_dir + "/"):
                s.add(self.file(p))
                n += 1
        s.counts.add(float(n))
        return s

    def totals(self) -> set:
        """Record counts of every record directory (a section index may show any of them)."""
        out = set()
        for d in ("models", "builds", "runs", "benches", "campaigns", "rankings", "comparisons",
                  "hardware", "item-scores"):
            out.add(float(sum(1 for p in self.files if p.startswith(f"data/{d}/") and
                              not p.rsplit("/", 1)[-1].startswith("_"))))
        return out

    def about(self, ident: str | None) -> Source:
        return self.ctx[ident] if ident and ident in self.ctx else Source("")


def page_source(idx: DataIndex, page: str) -> Source:
    """What a site page (path under the base, no leading slash) shows: its record(s)."""
    parts = [p for p in page.split("/") if p and p != "index.html"]
    if not parts:
        return Source("home page (no record)")
    sec, rest = parts[0], parts[1:]
    if not rest and sec in SECTION_DIRS:
        s = idx.directory(SECTION_DIRS[sec])
        s.label = f"{SECTION_DIRS[sec]}/ (section index)"
        s.counts |= idx.totals()
        if sec == "runs":
            s.add(idx.file("data/indexes/runs.json"))
        return s
    if sec == "runs":
        rid = "/".join(rest)
        return Source(f"run {rid}").add(idx.file(f"data/runs/{rid}.json")).add(idx.about(rid))
    if sec == "rankings":
        return Source(f"ranking {rest[0]}").add(idx.file(f"data/rankings/{rest[0]}.json")).add(idx.about(rest[0]))
    if sec == "models":
        slug = rest[0]
        s = Source(f"model {slug}").add(idx.file(f"data/models/{slug}.json"))
        for p in idx.files:
            if p.startswith(f"data/builds/{slug}@"):
                s.add(idx.file(p))
                s.add(idx.about(idx.files[p].get("build_id") if isinstance(idx.files[p], dict) else None))
        m = idx.files.get(f"data/models/{slug}.json")
        return s.add(idx.about(m.get("model_id") if isinstance(m, dict) else None))
    if sec == "benches":
        bid = "/".join(rest[:2])
        return Source(f"bench {bid}").add(idx.file(f"data/benches/{'__'.join(rest[:2])}.json")).add(idx.about(bid))
    if sec == "campaigns":
        return Source(f"campaign {rest[0]}").add(idx.file(f"data/campaigns/{rest[0]}.json")).add(idx.about(rest[0]))
    if sec == "compare":
        return Source(f"comparison {rest[0]}").add(idx.file(f"data/comparisons/{rest[0]}.json")).add(idx.about(rest[0]))
    if sec == "configs":
        return Source(f"hardware {rest[0]}").add(idx.file(f"data/hardware/{rest[0]}.json")).add(idx.about(rest[0]))
    return Source(f"{sec}/ (no record)")


def section_source(idx: DataIndex, sec: str) -> Source | None:
    if sec == "rig":
        return idx.directory("data/hardware")
    if sec == "forge":
        return idx.directory("data/forge")
    return None


def link_source(idx: DataIndex, href: str, page: str) -> Source | None:
    """The data an href points to; None for a link outside the site and the repository."""
    if href.startswith("#"):
        return page_source(idx, page)
    m = GITHUB_RE.match(href)
    if m:
        rel = unquote(m.group(1)).split("#")[0].rstrip("/")
        p = idx.root / rel
        if rel in idx.files:
            return idx.file(rel)
        if p.is_dir():
            s = idx.directory(rel)
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix != ".json":
                    s.values |= text_numbers(f)
            return s
        if p.is_file():
            return Source(rel, text_numbers(p))
        return Source(f"{rel} (missing from the repository)")
    u = urlsplit(href)
    if u.scheme or u.netloc:
        return None
    path = unquote(u.path)
    if not path.startswith(BASE):
        return None
    sub = path[len(BASE):]
    sec = sub.split("/")[0]
    return section_source(idx, sec) or page_source(idx, sub)


_TEXT_NUM = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def text_numbers(p: Path) -> set:
    try:
        return {float(x) for x in _TEXT_NUM.findall(p.read_text(encoding="utf-8"))}
    except (OSError, UnicodeDecodeError):
        return set()


# ------------------------------------------------------------------ HTML scan
class Scan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool]] = []   # (tag, aria-hidden here or above)
        self.cur = None
        self.cur_depth = 0
        self.unit_depth = None
        self.skip_depth = None
        self.nums: list[dict] = []
        self.prose: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        a = dict(attrs)
        hidden = (self.stack[-1][1] if self.stack else False) or a.get("aria-hidden") == "true"
        self.stack.append((tag, hidden))
        d = len(self.stack)
        if self.skip_depth is None and tag in SKIP_TEXT:
            self.skip_depth = d
        if self.cur is None and "data-num" in a:
            self.cur = {"num": a["data-num"], "href": a.get("href"), "text": "", "axis": hidden,
                        "n": len(self.nums) + 1}
            self.cur_depth = d
        elif self.cur is not None and "num-unit" in (a.get("class") or "").split():
            self.unit_depth = d

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not any(t == tag for t, _ in self.stack):
            return  # stray end tag
        while self.stack:
            d = len(self.stack)
            t, _ = self.stack.pop()
            if self.unit_depth == d:
                self.unit_depth = None
            if self.skip_depth == d:
                self.skip_depth = None
            if self.cur is not None and self.cur_depth == d:
                self.nums.append(self.cur)
                self.cur = None
            if t == tag:
                break

    def handle_data(self, data):
        if self.cur is not None:
            if self.unit_depth is None:
                self.cur["text"] += data
        elif self.skip_depth is None:
            self.prose.append(data)


# ------------------------------------------------------------------ main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("--dist", default=str(REPO / "site" / "dist"), help="built site (default site/dist)")
    ap.add_argument("--max-print", type=int, default=40, help="failures printed per rule (default 40)")
    ap.add_argument("--verbose", action="store_true", help="also list the prose numbers of each page")
    ap.add_argument("--no-readme", action="store_true", help="skip tools/build_readme.py --check")
    args = ap.parse_args(argv)
    dist = Path(args.dist).resolve()
    if not dist.is_dir() or not any(dist.rglob("*.html")):
        print(f"verify_numbers: no built site under {dist} — build it first (cd site && npm run build)")
        return 2

    exceptions, exc_errors = load_exceptions("verify_numbers")
    used_exc = Counter()

    def excused(page: str, rule: str, num: str) -> bool:
        for i, x in enumerate(exceptions):
            if (fnmatch.fnmatch(page, x["file"]) and x["rule"] in ("*", rule)
                    and str(x.get("value", num)) == num):
                used_exc[i] += 1
                return True
        return False

    idx = DataIndex(REPO)
    fails: dict[str, list] = defaultdict(list)
    c = Counter()
    prose = Counter()
    derived_list: list[str] = []
    prose_small = 0
    pages = sorted(dist.rglob("*.html"))
    for f in pages:
        page = f.relative_to(dist).as_posix()
        page_dir = page[: -len("index.html")] if page.endswith("index.html") else page
        sc = Scan()
        sc.feed(f.read_text(encoding="utf-8"))
        sc.close()
        own = None
        for n in sc.nums:
            c["numbers"] += 1
            where = f"{page} #{n['n']}"
            try:
                v = float(n["num"])
            except ValueError:
                fails["rounding"].append(f"{where}: data-num {n['num']!r} is not a number")
                continue
            shown = n["text"].strip().removeprefix("~")
            if not rounding_ok(v, shown) and not excused(page, "rounding", n["num"]):
                fails["rounding"].append(f"{where}: shows {shown!r} for data-num {n['num']} "
                                         f"(fmtNum: {fmt_num(v, 0, 4)!r})")
            if n["axis"]:
                c["axis"] += 1
                continue
            href = n["href"]
            src = link_source(idx, href, page_dir) if href else None
            if href and src is None:
                c["external"] += 1
                src = idx.everything
            elif href:
                c["linked"] += 1
            else:
                c["unlinked"] += 1
                if own is None:
                    own = page_source(idx, page_dir)
                src = own
                if not src.has(v):
                    src = idx.everything
                    c["unlinked_elsewhere"] += 1
            kind = src.has(v)
            # a count the page computes (a filtered list: "3 runs used a floating tag") and
            # links to an anchor or a section index: no stored value to trace it to, so it
            # is only bounded by the records of the source, and reported
            derived = (not kind and href and ("#" in href or src.label.endswith("(section index)"))
                       and v.is_integer() and 0 <= v <= max(src.counts | {0.0}))
            if not kind and href and v.is_integer():
                if any(idx.rows_naming(src.rels, i) == v for i in idx.subject_ids(page_dir)):
                    kind = "count"
            if kind:
                c[f"match_{kind}"] += 1
            elif derived:
                c["derived"] += 1
                derived_list.append(f"{where}: {n['num']} (href {href})")
            elif excused(page, "source", n["num"]):
                c["excepted"] += 1
            else:
                fails["source"].append(f"{where}: {n['num']} not in {src.label}"
                                       + (f" (href {href})" if href else " (no link)"))
        if page_dir.startswith(PROSE_PAGES):
            found = [x for x in PROSE_NUM.findall(" ".join(" ".join(sc.prose).split()))
                     if x != "3090"]  # the card's name, not a measurement
            small = sum(1 for x in found if len(x) == 1)
            prose_small += small
            found = [x for x in found if len(x) > 1]
            if found:
                prose[page_dir] = len(found)
                if args.verbose:
                    print(f"prose {page_dir}: {', '.join(found[:40])}{' …' if len(found) > 40 else ''}")

    fails["exceptions"].extend(f"tools/exceptions.json: {e}" for e in exc_errors)
    for i, x in enumerate(exceptions):
        if x.get("tool") == "verify_numbers" and not used_exc[i]:
            fails["exceptions"].append(f"tools/exceptions.json: unused verify_numbers exception {x}")
    for rule in ("rounding", "source", "exceptions"):
        for line in fails[rule][: args.max_print]:
            print(f"FAIL {rule}: {line}")
        if len(fails[rule]) > args.max_print:
            print(f"FAIL {rule}: ... {len(fails[rule]) - args.max_print} more (--max-print)")

    if derived_list:
        print(f"warning: {len(derived_list)} count(s) computed by the page (filtered lists linked to an "
              f"anchor or a section index) are only bounded by their source's record counts")
        if args.verbose:
            for line in derived_list:
                print(f"  derived {line}")
    if prose:
        by_sec = Counter()
        for p, k in prose.items():
            by_sec[p.split("/")[0]] += k
        print(f"warning: {sum(prose.values())} number(s) in prose, outside <Num>, on {len(prose)} "
              f"model/config/compare page(s) ({', '.join(f'{s}/ {k}' for s, k in sorted(by_sec.items()))}); "
              f"most: {', '.join(f'{p} {k}' for p, k in prose.most_common(4))}; plus {prose_small} single "
              f"digit(s) and every \"3090\" left out. --verbose lists them")

    readme_rc = 0
    if not args.no_readme:
        r = subprocess.run([sys.executable, str(REPO / "tools" / "build_readme.py"), "--check"],
                           capture_output=True, text=True)
        readme_rc = r.returncode
        out = (r.stdout + r.stderr).strip().splitlines()
        print(("FAIL readme: README.md generated block is stale: " + (out[0] if out else ""))
              if readme_rc else "readme: generated block up to date")

    n_fail = sum(len(v) for v in fails.values())
    print(f"verify_numbers: {c['numbers']} numbers on {len(pages)} pages — {c['linked']} linked, "
          f"{c['unlinked']} unlinked ({c['unlinked_elsewhere']} found only elsewhere in data/), "
          f"{c['external']} external, {c['axis']} chart ticks; matched {c['match_value']} as values and "
          f"{c['match_count']} as array/record counts, {c['derived']} bounded page counts; {len(fails['rounding'])} rounding and "
          f"{len(fails['source'])} source failure(s), {c['excepted']} excepted")
    return 1 if (n_fail or readme_rc) else 0


if __name__ == "__main__":
    sys.exit(main())
