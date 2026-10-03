#!/usr/bin/env python3
"""Version-label gate: every copy of the release label in the prose equals VERSION_LABEL.

The release label (for example "v0 (2026-10-02)") has one source, VERSION_LABEL in
site/src/lib/data.ts: the site footer, /data, all.json and the Open Graph cards read it
there. The prose carries hand-written copies of it (README, CHANGELOG, GLOSSARY,
ATTRIBUTION, DESIGN, the methodology notes, the generated bench cards). This gate finds
every label-shaped string, "v<N> (" ... "<YYYY-MM-DD>)", in the repository's text files
and fails on any that differs from VERSION_LABEL.

Scanned: every *.md file outside node_modules, site/dist and the frozen bench files (a
bench card, benches/**/CARD.md, is generated and scanned), and site/src/**.
CHANGELOG.md: only its first release heading is the current label (older entries keep
their own labels).

usage: tools/check_version.py [--quiet]
Exit status: 0 every copy matches, 1 a copy differs or VERSION_LABEL is missing.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gatelib import REPO  # noqa: E402

SOURCE = REPO / "site" / "src" / "lib" / "data.ts"
SOURCE_RE = re.compile(r"""export const VERSION_LABEL = '([^']+)';""")
LABEL_RE = re.compile(r"\bv\d+ \((?:[^()\n]*?, )?\d{4}-\d{2}-\d{2}\)")
SKIP_DIRS = {".git", "node_modules", "dist"}


def scanned(root: Path):
    for p in sorted(root.rglob("*")):
        if not p.is_file() or SKIP_DIRS & set(p.relative_to(root).parts):
            continue
        r = p.relative_to(root).as_posix()
        if r.startswith("site/src/"):
            yield p, r
        elif p.suffix == ".md" and (not r.startswith("benches/") or p.name == "CARD.md"):
            yield p, r


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--quiet", action="store_true", help="print failures and the summary only")
    a = ap.parse_args(argv)
    m = SOURCE_RE.search(SOURCE.read_text(encoding="utf-8")) if SOURCE.is_file() else None
    if not m:
        print(f"check_version: VERSION_LABEL not found in {SOURCE.relative_to(REPO)}")
        return 1
    label = m.group(1)
    bad, n, files = [], 0, 0
    for p, r in scanned(REPO):
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        hits = list(LABEL_RE.finditer(text))
        if r == "CHANGELOG.md":
            hits = hits[:1]
        if hits:
            files += 1
        for h in hits:
            n += 1
            if h.group(0) != label:
                line = text.count("\n", 0, h.start()) + 1
                bad.append(f"{r}:{line}: {h.group(0)!r} is not VERSION_LABEL {label!r}")
    for b in bad:
        print(f"FAIL {b}")
    print(f"check_version: {n} label(s) in {files} file(s) against {label!r} — {len(bad)} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
