"""Publication must fail on absent G1, partial export, or a changed final tree."""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("verify_export", Path(__file__).parents[1] / "verify_export.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


@pytest.fixture
def exported(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("node_modules/\nsite/dist/\n")
    (tmp_path / "record.json").write_text('{"measured": true}\n')
    write_receipt(tmp_path)
    return tmp_path


def write_receipt(root, **changes):
    digest, count = gate.source_digest(root)
    receipt = {"version": 1, "full_export": True, "source_commit": "a" * 40,
               "g1": {"passed": True, "block_hits": 0, "review_hits": 0, "files_scanned": count},
               "source_tree": {"sha256": digest, "files": count}}
    receipt.update(changes)
    (root / gate.RECEIPT).write_text(json.dumps(receipt))


def test_valid_export_and_ignored_build_output(exported):
    build = exported / "site" / "dist"
    build.mkdir(parents=True)
    (build / "index.html").write_text("rebuilt by CI")
    assert gate.verify(exported) == []


@pytest.mark.parametrize("change", [
    {"full_export": False}, {"g1": {"passed": False}},
    {"g1": {"passed": True, "block_hits": 1, "review_hits": 0, "files_scanned": 2}},
    {"source_commit": "main"}, {"source_tree": {"sha256": "0" * 64, "files": 2}},
])
def test_unchecked_or_incomplete_export_fails(exported, change):
    write_receipt(exported, **change)
    assert gate.verify(exported)


def test_missing_receipt_fails(exported):
    (exported / gate.RECEIPT).unlink()
    assert gate.verify(exported)


@pytest.mark.parametrize("name", ["record.json", ".github/workflows/pages.yml", "site/src/pages/index.astro"])
def test_any_final_source_edit_requires_g1_refresh(exported, name):
    file = exported / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("changed after G1")
    assert gate.verify(exported)
    write_receipt(exported)
    assert gate.verify(exported) == []


def test_included_symlink_fails(exported):
    (exported / "linked.json").symlink_to("record.json")
    assert gate.verify(exported)


def test_tracked_ignored_source_is_sealed(exported):
    (exported / ".gitignore").write_text("ignored.dat\n")
    (exported / "ignored.dat").write_text("tracked despite ignore rule")
    subprocess.run(["git", "-C", str(exported), "add", "-f", "ignored.dat"], check=True)
    write_receipt(exported)
    assert gate.verify(exported) == []
    (exported / "ignored.dat").write_text("changed after G1")
    assert gate.verify(exported)


def test_missing_tracked_source_fails_even_manifest_refresh(exported):
    subprocess.run(["git", "-C", str(exported), "add", "record.json"], check=True)
    write_receipt(exported)
    (exported / "record.json").unlink()
    assert gate.verify(exported)
    with pytest.raises(ValueError):
        gate.source_digest(exported)
