#!/usr/bin/env python3
"""G8 — no French in English prose.

The repo is English; only measurement material stays French (bench items, prompts
sent to models), and it is tagged. This heuristic flags a sentence when it holds at
least three distinct French function words (le, les, des, est, avec, dans, pour...)
and they make up at least a tenth of its words. Accents alone are not enough, and
neither are proper names (« Banque de France ») or one borrowed phrase (« déjà vu »).

Checked:
  * every *.md / *.mdx outside benches/, .git, node_modules and dist/ — code blocks,
    inline code, HTML comments, link targets and « guillemet » quotes are ignored, as
    are regions tagged French: <!-- lang: fr --> ... <!-- /lang -->, an element with
    lang="fr", or a whole file whose front matter says lang: fr;
  * the string fields of data/models, data/campaigns, data/watchlist(.json),
    data/hardware and data/errata.json — an object carrying "lang": "fr" (or
    "language": "fr") is skipped with everything under it, and so is any key ending
    in _fr.

usage:
  tools/check_language.py [--min-markers 3] [PATH ...]
Exit status: 0 ok, 1 French found.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gatelib import REPO, excepted, iter_files, load_exceptions  # noqa: E402

# French function words that are not (common) English words. Deliberately left out:
# a, on, son, plus, pour, par, car, ce, sa, ma, au, y, nos, mon, ton — English too.
FR = set("""
le la les un une des du de et ou où est sont dans avec sans sur que qui dont ne pas
cette ces cet leur leurs nous vous ils elles elle être été était avoir mais donc chaque
selon entre chez aussi très déjà encore toujours jamais aucun aucune seul seule même
tous toutes lorsque quand puis comme ainsi alors après avant depuis pendant contre aux
à il lui sous vers cela ceci ça peu bien fait faire peut doit sera ont avait notre
votre vos tes ses
""".split())
WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿŒœ]+")
SENT_SPLIT = re.compile(r"(?<=[.!?;:])\s+|\s*\|\s*|\n")
DATA_DIRS = ("data/models", "data/campaigns", "data/watchlist", "data/watchlist.json",
             "data/hardware", "data/errata.json")
SKIP_KEYS_RX = re.compile(r"(?:_fr|_id|_ids|url|urls|path|paths|sha256|slug|aliases|id)$")


def french_score(sentence: str) -> tuple[int, int, list[str]]:
    words = [w.lower() for w in WORD.findall(sentence.replace("’", "'"))]
    markers = sorted({w for w in words if w in FR})
    return len(markers), len(words), markers


def is_french(sentence: str, min_markers: int) -> tuple[bool, list[str]]:
    n, total, markers = french_score(sentence)
    return (n >= min_markers and total and n / total >= 0.10), markers


# ------------------------------------------------------------------ markdown
CODE = re.compile(r"^(```|~~~)[^\n]*\n.*?^\1[^\n]*$|`[^`\n]*`", re.S | re.M)
LANG_REGION = re.compile(r"<!--\s*lang\s*:\s*fr\s*-->.*?<!--\s*/lang\s*-->", re.S | re.I)
LANG_ELEMENT = re.compile(r"<(\w+)\b[^>]*\blang\s*=\s*[\"']fr[^\"']*[\"'][^>]*>.*?</\1>", re.S | re.I)
GUILLEMETS = re.compile(r"«[^»]*»", re.S)
COMMENT = re.compile(r"<!--.*?-->", re.S)
LINK_TARGET = re.compile(r"\]\([^)]*\)")
TAG = re.compile(r"<[^>]+>")
URL = re.compile(r"https?://\S+")
FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def blank(m: re.Match) -> str:
    return re.sub(r"[^\n]", " ", m.group(0))


def check_markdown(f: Path, root: Path, min_markers: int, exceptions):
    r = f.relative_to(root).as_posix()
    text = f.read_text(encoding="utf-8", errors="replace")
    fm = FRONT.match(text)
    if fm and re.search(r"^lang\s*:\s*[\"']?fr", fm.group(1), re.M):
        return [], True
    for rx in (CODE, LANG_REGION, LANG_ELEMENT, GUILLEMETS, COMMENT, LINK_TARGET, URL, TAG):
        text = rx.sub(blank, text)
    out = []
    pos = 0
    for line_no, line in enumerate(text.split("\n"), 1):
        for sent in SENT_SPLIT.split(line):
            hit, markers = is_french(sent, min_markers)
            if hit and not excepted(exceptions, r, "french"):
                out.append(f"FRENCH   {r}:{line_no}  markers={markers[:6]}  « {sent.strip()[:90]} »")
        pos += len(line) + 1
    return out, False


# ------------------------------------------------------------------ json
def walk(obj, path="$"):
    """Yield (json_path, string) for English-bearing strings, skipping French-tagged parts."""
    if isinstance(obj, dict):
        lang = str(obj.get("lang", obj.get("language", ""))).lower()
        if lang.startswith("fr"):
            return
        for k, v in obj.items():
            if SKIP_KEYS_RX.search(k):
                continue
            yield from walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")
    elif isinstance(obj, str) and " " in obj.strip():
        yield path, obj


def check_json(f: Path, root: Path, min_markers: int, exceptions):
    r = f.relative_to(root).as_posix()
    try:
        obj = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"UNREADABLE {r}: {exc}"], False
    raw = f.read_text(encoding="utf-8")
    out = []
    for jp, s in walk(obj):
        for sent in SENT_SPLIT.split(s):
            hit, markers = is_french(sent, min_markers)
            if hit and not excepted(exceptions, r, "french"):
                line = "-"
                for ascii_only in (False, True):
                    needle = json.dumps(s, ensure_ascii=ascii_only)[1:40]
                    if needle in raw:
                        line = raw[: raw.find(needle)].count("\n") + 1
                        break
                out.append(f"FRENCH   {r}:{line} {jp}  markers={markers[:6]}  « {sent.strip()[:90]} »")
                break
    return out, False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 epilog="Exit status: 0 ok, 1 French found.")
    ap.add_argument("paths", nargs="*", help="files to check (default: the repo's prose and English data fields)")
    ap.add_argument("--root", default=str(REPO), help="repo root (default: this repo)")
    ap.add_argument("--min-markers", type=int, default=3, help="distinct French function words per sentence (default 3)")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    exceptions, problems = load_exceptions("check_language")

    md, js = [], []
    if args.paths:
        for p in args.paths:
            f = Path(p).resolve()
            (js if f.suffix == ".json" else md).append(f)
    else:
        for f in iter_files(root, skip_dirs={".git", "node_modules", "dist", ".astro"}):
            r = f.relative_to(root).as_posix()
            if r.startswith("benches/"):
                continue
            if f.suffix.lower() in (".md", ".mdx"):
                md.append(f)
            elif f.suffix == ".json" and any(r == d or r.startswith(d + "/") for d in DATA_DIRS):
                if not f.name.startswith("_"):
                    js.append(f)
    skipped_fr = 0
    for f in md:
        out, skipped = check_markdown(f, root, args.min_markers, exceptions)
        skipped_fr += skipped
        problems.extend(out)
    for f in js:
        out, _ = check_json(f, root, args.min_markers, exceptions)
        problems.extend(out)
    for p in problems:
        print(p)
    print(f"check_language: {len(md)} Markdown files ({skipped_fr} tagged French), {len(js)} JSON files — "
          f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
