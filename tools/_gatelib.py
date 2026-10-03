"""Shared helpers of the public quality gates (stdlib only).

The gates in tools/ hold generic patterns only: nothing in this directory may name
a private host, address, person or path. Private literals are checked before export,
outside this repository.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ALWAYS_SKIP = {".git", "node_modules"}
TEXT_EXT = {
    ".md", ".mdx", ".txt", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".csv", ".tsv",
    ".py", ".sh", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".astro", ".html", ".htm", ".css",
    ".svg", ".xml", ".ini", ".cfg", ".conf", ".lock", ".map", ".webmanifest", ".rss",
    ".ipynb", ".sql", ".tex", ".gitignore", ".gitattributes",
}
_PRINTABLE = re.compile(rb"[\x20-\x7e]{6,}")


def iter_files(root: Path, skip_dirs=ALWAYS_SKIP, skip_rel=()):
    """Every file under root, sorted, skipping directory names in skip_dirs and the
    root-relative directory prefixes in skip_rel (e.g. 'site/dist')."""
    root = Path(root)
    skip_rel = tuple(s.rstrip("/") + "/" for s in skip_rel)
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir + "/"
        dirnames[:] = sorted(d for d in dirnames
                             if d not in skip_dirs and not (rel_dir + d + "/").startswith(skip_rel))
        for name in sorted(filenames):
            yield Path(dirpath) / name


def repo_files(root: Path, extra_dirs=("site/dist",)):
    """What would be committed: tracked plus untracked-but-not-ignored files when root is
    a git work tree (so ignored caches such as site/.astro are left out), plus the files
    of extra_dirs (the built site is ignored by git but deployed). Without git: a walk."""
    root = Path(root)
    files = None
    if (root / ".git").exists():
        try:
            out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others",
                                  "--exclude-standard"], capture_output=True, check=True).stdout
            files = {root / p.decode("utf-8", "surrogateescape") for p in out.split(b"\0") if p}
        except (OSError, subprocess.CalledProcessError):
            files = None
    if files is None:  # not a git work tree: walk, leaving out generated caches
        return list(iter_files(root, skip_dirs=ALWAYS_SKIP | {".astro", "__pycache__"}))
    for d in extra_dirs:
        if (root / d).is_dir():
            files.update(iter_files(root / d))
    return sorted(f for f in files if f.is_file() and "node_modules" not in f.relative_to(root).parts)


def rel(path: Path, root: Path = REPO) -> str:
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def is_text(path: Path, head: bytes) -> bool:
    if b"\x00" in head:
        return False
    if path.suffix.lower() in TEXT_EXT:
        return True
    try:
        head.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def lines_of(path: Path):
    """(line_number | None, text). Text files line by line; binary files as their
    printable ASCII runs (EXIF/XMP/PDF metadata), without line numbers."""
    data = path.read_bytes()
    if is_text(path, data[:8192]):
        for n, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
            yield n, line
        return
    for m in _PRINTABLE.finditer(data):
        yield None, m.group(0).decode("ascii")


def mask(s: str) -> str:
    """Never echo a finding in full: CI logs of a public repo are public too."""
    s = s.strip()
    if len(s) <= 4:
        return "*" * len(s)
    return f"{s[:2]}…{s[-1]} ({len(s)} chars)"


def load_exceptions(tool: str, path: Path | None = None) -> tuple[list[dict], list[str]]:
    """tools/exceptions.json: {"exceptions": [{"tool", "file" (glob), "rule", "reason"}]}.
    Every exception needs a reason; a reviewed exception is the only way past a gate."""
    path = path or (REPO / "tools" / "exceptions.json")
    if not path.exists():
        return [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [], [f"{rel(path)}: invalid JSON ({exc})"]
    out, errors = [], []
    for i, x in enumerate(data.get("exceptions", [])):
        if x.get("tool") not in (tool, "*"):
            continue
        if not x.get("file") or not x.get("rule") or not str(x.get("reason", "")).strip():
            errors.append(f"exception #{i}: needs file, rule and a reason")
            continue
        out.append(x)
    return out, errors


def excepted(exceptions: list[dict], file: str, rule: str) -> bool:
    return any(fnmatch.fnmatch(file, x["file"]) and x["rule"] in ("*", rule) for x in exceptions)
