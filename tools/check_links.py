#!/usr/bin/env python3
"""G6 — link gate for the Markdown of the repo.

  * every relative link and image in *.md / *.mdx resolves, inside the repository,
    to a file that would be committed (tracked, or untracked but not ignored by
    git) or to a directory holding at least one such file: a link to an ignored
    file or to an empty folder breaks once the repository is cloned;
  * a #fragment pointing at a Markdown file resolves to one of its headings
    (GitHub slugs) or to an explicit <a id|name> anchor.

Outside a git work tree the gate falls back to the file system. Skipped: .git,
node_modules, ignored files, and frozen bench files listed as published in a
benches/**/MANIFEST.json (they are byte-identical copies and are checked by
tools/verify_benches.py). Links that start with "/" inside site/ are site routes,
not files, and are not checked here.

usage:
  tools/check_links.py [FILE.md ...]
Exit status: 0 ok, 1 broken link.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gatelib import REPO, excepted, iter_files, load_exceptions, repo_files  # noqa: E402

SKIP_SCHEMES = ("http://", "https://", "mailto:", "tel:", "data:", "ftp://", "javascript:")

CODE = re.compile(r"^(```|~~~)[^\n]*\n.*?^\1[^\n]*$|`[^`\n]*`", re.S | re.M)
COMMENT = re.compile(r"<!--.*?-->", re.S)
INLINE = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*<?([^)>\s]+)>?(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
REFDEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s+.*)?$", re.M)
HTML = re.compile(r"\b(?:href|src)\s*=\s*[\"']([^\"']+)[\"']", re.I)
ANCHOR_TAG = re.compile(r"<a\s+[^>]*(?:id|name)\s*=\s*[\"']([^\"']+)[\"']", re.I)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.M)


def gh_slug(text: str) -> str:
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)      # links -> their text
    text = re.sub(r"<[^>]+>", "", text)                          # inline html
    text = text.replace("`", "").strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)                         # GitHub keeps letters, digits, _ - and spaces
    return text.replace(" ", "-")


_anchor_cache: dict[Path, set[str]] = {}


def anchors_of(path: Path) -> set[str]:
    if path not in _anchor_cache:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        clean = CODE.sub("", text)
        seen: Counter = Counter()
        out = set()
        for m in HEADING.finditer(clean):
            s = gh_slug(m.group(2))
            out.add(s if not seen[s] else f"{s}-{seen[s]}")
            seen[s] += 1
        out.update(ANCHOR_TAG.findall(text))
        _anchor_cache[path] = out
    return _anchor_cache[path]


def frozen_bench_files(root: Path) -> set[str]:
    """Byte-identical bench files: listed as published (or frozen) in a bench MANIFEST."""
    out = set()
    for man in sorted((root / "benches").rglob("MANIFEST.json")) if (root / "benches").is_dir() else []:
        try:
            d = json.loads(man.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        names = []
        if isinstance(d.get("published"), list):
            names += [x for x in d["published"] if isinstance(x, str)]
        for key in ("fichiers", "files"):
            if isinstance(d.get(key), dict):
                names += list(d[key])
        fs = d.get("frozen_set")
        if isinstance(fs, dict) and isinstance(fs.get("files"), dict):
            names += list(fs["files"])
        unhashed = set(d.get("unhashed") or [])
        for n in names:
            if n not in unhashed:
                out.add((man.parent / n).relative_to(root).as_posix())
    return out


class Shipped:
    """The files a clone of the repository would hold, and the folders holding them."""

    def __init__(self, root: Path):
        self.files: set[Path] | None = None
        self.dirs: set[Path] = set()
        if (root / ".git").exists():
            self.files = {f.resolve() for f in repo_files(root, extra_dirs=())}
            for f in self.files:
                for parent in f.parents:
                    if parent in self.dirs:
                        break
                    self.dirs.add(parent)

    def has(self, full: Path) -> bool:
        if self.files is None:  # not a git work tree
            return full.exists()
        return full in self.files or full in self.dirs


def check_file(f: Path, root: Path, exceptions: list[dict], shipped: Shipped):
    r = f.relative_to(root).as_posix()
    text = f.read_text(encoding="utf-8", errors="replace")
    clean = COMMENT.sub(lambda m: " " * len(m.group(0)), CODE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text))
    targets = []
    for rx in (INLINE, REFDEF, HTML):
        for m in rx.finditer(clean):
            targets.append((m.start(1), m.group(1)))
    problems, checked = [], 0
    in_site = r.startswith("site/")
    for pos, target in sorted(targets):
        line = 1 + text.count("\n", 0, pos)
        checked += 1
        if target.startswith(SKIP_SCHEMES) or target.startswith("{") or "<" in target:
            continue
        path_part, _, frag = target.partition("#")
        path_part = urllib.parse.unquote(path_part.split("?", 1)[0])
        if not path_part:
            if frag and frag not in anchors_of(f) and not excepted(exceptions, r, "anchor"):
                problems.append(f"ANCHOR   {r}:{line}  -> #{frag} (no such heading here)")
            continue
        if path_part.startswith("/"):
            if in_site:
                continue  # a site route
            full = (root / path_part.lstrip("/")).resolve()
        else:
            full = (f.parent / path_part).resolve()
        try:
            full.relative_to(root)
        except ValueError:
            problems.append(f"OUTSIDE  {r}:{line}  -> {target} (leaves the repository)")
            continue
        if not full.exists():
            if not excepted(exceptions, r, "broken"):
                problems.append(f"BROKEN   {r}:{line}  -> {target}")
            continue
        if not shipped.has(full):
            if not excepted(exceptions, r, "unshipped"):
                kind = "an empty folder" if full.is_dir() else "a file git ignores"
                problems.append(f"UNSHIPPED {r}:{line}  -> {target} ({kind}: absent from a clone)")
            continue
        if frag and full.is_file() and full.suffix.lower() in (".md", ".mdx") \
                and frag not in anchors_of(full) and not excepted(exceptions, r, "anchor"):
            problems.append(f"ANCHOR   {r}:{line}  -> {target} (#{frag} not a heading of {full.name})")
    return checked, problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 epilog="Exit status: 0 ok, 1 broken link.")
    ap.add_argument("files", nargs="*", help="Markdown files to check (default: every *.md / *.mdx of the repo)")
    ap.add_argument("--root", default=str(REPO), help="repo root (default: this repo)")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    exceptions, problems = load_exceptions("check_links")
    frozen = frozen_bench_files(root)
    shipped = Shipped(root)
    if args.files:
        files = [Path(x).resolve() for x in args.files]
    else:
        files = [f for f in iter_files(root, skip_dirs={".git", "node_modules", "dist", ".astro"})
                 if f.suffix.lower() in (".md", ".mdx")]
    nfiles = nlinks = nfrozen = 0
    for f in files:
        r = f.relative_to(root).as_posix()
        if r in frozen:
            nfrozen += 1
            continue
        nfiles += 1
        checked, probs = check_file(f, root, exceptions, shipped)
        nlinks += checked
        problems.extend(probs)
    for p in problems:
        print(p)
    print(f"check_links: {nlinks} links in {nfiles} files ({nfrozen} frozen bench files skipped) — "
          f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
