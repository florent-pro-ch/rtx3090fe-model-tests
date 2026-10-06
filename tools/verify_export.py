#!/usr/bin/env python3
"""Verify the full-export / G1 receipt and bind it to the final public source tree.

The receipt is an attestation from the private exporter, not a digital signature.
Its digest detects missing checks and later edits, including site/workflow edits.
The trusted exporter and protected publication workflow establish who checked it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RECEIPT = "export-receipt.json"
SKIP_COMPONENTS = {".git", "node_modules", "__pycache__"}
SKIP_PREFIXES = ("site/dist/", "site/.astro/")


def source_manifest(root: Path) -> list[list[str]]:
    """Tracked and non-ignored untracked source files, sorted by POSIX path.

    Build output and dependency/cache paths are not publication inputs. Included
    symlinks are rejected: the receipt must describe the bytes GitHub will ship.
    """
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        check=True, capture_output=True,
    ).stdout
    names = sorted({p.decode("utf-8") for p in out.split(b"\0") if p})
    manifest = []
    for name in names:
        rel = Path(name)
        if name == RECEIPT or SKIP_COMPONENTS.intersection(rel.parts) or name.startswith(SKIP_PREFIXES):
            continue
        file = root / rel
        if file.is_symlink():
            raise ValueError(f"included source symlink: {name}")
        if not file.is_file():
            raise ValueError(f"listed source file is missing or not a regular file: {name}")
        manifest.append([name, hashlib.sha256(file.read_bytes()).hexdigest()])
    return manifest


def source_digest(root: Path) -> tuple[str, int]:
    manifest = source_manifest(root)
    encoded = json.dumps(manifest, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), len(manifest)


def verify(root: Path) -> list[str]:
    problems = []
    receipt_file = root / RECEIPT
    if receipt_file.is_symlink():
        return ["export receipt must be a regular file, not a symlink"]
    try:
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["export receipt missing or invalid; run a complete export and G1 on the final tree"]
    if not isinstance(receipt, dict):
        return ["export receipt must be an object"]
    if type(receipt.get("version")) is not int or receipt["version"] != 1:
        problems.append("unsupported export receipt version")
    if receipt.get("full_export") is not True:
        problems.append("receipt does not attest a successful complete export")
    if not re.fullmatch(r"[0-9a-f]{40}", str(receipt.get("source_commit", ""))):
        problems.append("receipt requires an exact source commit SHA")
    g1 = receipt.get("g1")
    if not isinstance(g1, dict) or g1.get("passed") is not True:
        problems.append("receipt does not attest a passing G1")
    else:
        if type(g1.get("block_hits")) is not int or g1["block_hits"] != 0:
            problems.append("G1 must have zero blocking findings")
        for key in ("review_hits", "files_scanned"):
            if type(g1.get(key)) is not int or g1[key] < (1 if key == "files_scanned" else 0):
                problems.append(f"invalid G1 {key} count")
    tree = receipt.get("source_tree")
    if not isinstance(tree, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(tree.get("sha256", ""))):
        problems.append("receipt requires a SHA-256 source-tree digest")
    else:
        try:
            digest, count = source_digest(root)
        except (OSError, ValueError, subprocess.CalledProcessError):
            problems.append("cannot enumerate the public Git source tree, or a listed source is missing or a symlink")
        else:
            if tree["sha256"] != digest:
                problems.append("source tree changed after G1; recheck the final tree with the private exporter")
            if type(tree.get("files")) is not int or tree["files"] != count:
                problems.append("source-tree file count does not match the receipt")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO)
    args = parser.parse_args()
    problems = verify(args.root.resolve())
    for problem in problems:
        print(f"verify_export: {problem}", file=sys.stderr)
    if problems:
        return 1
    print("verify_export: complete export, G1 and public source digest agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
