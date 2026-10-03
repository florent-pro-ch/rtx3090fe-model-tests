#!/usr/bin/env python3
"""G3 — size and media gate.

  * every file is at most 5 MiB (built site included);
    (files are what git would commit — ignored caches are left out — plus site/dist)
  * the repository, without node_modules, dist and .git, stays under 50 MiB;
  * no audio, array, log or model-weight file anywhere (.flac .wav .mp3 .ogg .m4a
    .npy .npz .log .safetensors .gguf .pt .pth .ckpt .onnx).

usage:
  tools/check_size.py [--max-file-mib 5] [--max-total-mib 50] [ROOT]
Exit status: 0 ok, 1 violation.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gatelib import REPO, excepted, load_exceptions, repo_files  # noqa: E402

FORBIDDEN_EXT = {".flac", ".wav", ".mp3", ".ogg", ".m4a", ".npy", ".npz", ".log",
                 ".safetensors", ".gguf", ".pt", ".pth", ".ckpt", ".onnx"}
NOT_COUNTED = {"node_modules", "dist", ".git", ".astro"}
MIB = 1024 * 1024


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 epilog="Exit status: 0 ok, 1 violation.")
    ap.add_argument("root", nargs="?", default=str(REPO), help="tree to check (default: the repo)")
    ap.add_argument("--max-file-mib", type=float, default=5.0, help="per-file limit in MiB (default 5)")
    ap.add_argument("--max-total-mib", type=float, default=50.0,
                    help="limit for the whole tree without node_modules, dist and .git, in MiB (default 50)")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"check_size: no such directory: {root}", file=sys.stderr)
        return 1
    exceptions, exc_errors = load_exceptions("check_size")
    problems = list(exc_errors)
    total = nfiles = 0
    sizes = []
    for f in repo_files(root):
        r = f.relative_to(root).as_posix()
        size = f.stat().st_size
        nfiles += 1
        parts = set(Path(r).parts[:-1])
        if not parts & NOT_COUNTED:
            total += size
        sizes.append((size, r))
        if size > args.max_file_mib * MIB and not excepted(exceptions, r, "file-size"):
            problems.append(f"TOO BIG   {r}  {size / MIB:.2f} MiB > {args.max_file_mib:g} MiB")
        if f.suffix.lower() in FORBIDDEN_EXT and not excepted(exceptions, r, "forbidden-ext"):
            problems.append(f"FORBIDDEN {r}  ({f.suffix.lower()} files never go in this repo)")
    if total >= args.max_total_mib * MIB:
        problems.append(f"REPO TOO BIG  {total / MIB:.2f} MiB >= {args.max_total_mib:g} MiB "
                        f"(without node_modules, dist, .git)")
    for p in problems:
        print(p)
    largest = ", ".join(f"{rel_} {s / MIB:.2f} MiB" for s, rel_ in sorted(sizes, reverse=True)[:3])
    print(f"check_size: {nfiles} files, {total / MIB:.2f} MiB counted; largest: {largest or '-'}; "
          f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
