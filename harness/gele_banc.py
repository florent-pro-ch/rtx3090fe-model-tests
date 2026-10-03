#!/usr/bin/env python3
"""Freezes a bench of your own, or verifies a frozen one.

English summary.
  freeze: writes MANIFEST.json in the bench folder (SHA-256 of every file, item counts, date, author,
          reviewer) and appends a line to CHANGELOG.md. After that, every runner refuses the bench if
          a single byte changes: a changed bench is a new version folder, never an edit.
  verify: recomputes the hashes of a frozen bench. It reads both the layout written by `freeze`
          ("fichiers") and the published layout of this repository ("frozen_set", where answer keys
          are withheld and listed with their hash only, and files withheld for privacy are listed
          with a null hash). For a published bench it checks every published file and every derived
          view, reports the withheld files ("withheld, not hashed" for the privacy ones), and
          recomputes the frozen-set hash when every frozen file is on disk and the set hash is
          published (it is null for a set holding a file withheld for privacy).

Usage:
  gele_banc.py freeze DIR --auteur NAME [--relecteur NAME] [--note TEXT]
  gele_banc.py verify DIR [DIR ...]          (DIR may also be the benches folder itself)
  gele_banc.py DIR --auteur NAME ...         (older form, same as freeze)
Identifiers are French (banc = bench, auteur = author, relecteur = reviewer); see GLOSSARY.md.
"""
import argparse, glob, json, os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from commun import sha256_fichier, maintenant, BANCS_DEFAUT


def charge_items(dossier):
    """A set declares its items in items.json, or in briefs.json for the benches whose unit is a brief.
    Either file may be a bare list or an object wrapping the list under "items" / "briefs"."""
    for nom, cle in (("items.json", "items"), ("briefs.json", "briefs")):
        chemin = os.path.join(dossier, nom)
        if not os.path.exists(chemin): continue
        charge = json.load(open(chemin, encoding="utf-8"))
        if isinstance(charge, list): return nom, charge
        return nom, charge.get(cle) or charge.get("items") or []
    return None, []


def geler(d, auteur, relecteur="to review", note=""):
    fichiers = {}
    for p in sorted(glob.glob(os.path.join(d, "**", "*"), recursive=True)):
        if os.path.isfile(p) and os.path.basename(p) not in ("MANIFEST.json", "CHANGELOG.md"): fichiers[os.path.relpath(p, d)] = sha256_fichier(p)
    fichier_items, items = charge_items(d)
    items = [i for i in items if isinstance(i, dict)]
    comptes = {"n_items": len(items)}
    for k in ("matiere", "type", "support", "axe", "langue", "source"):
        c = Counter(i.get(k) for i in items if i.get(k))
        if c: comptes[k] = dict(c)
    man = {"banc": os.path.basename(os.path.dirname(os.path.abspath(d))), "version": os.path.basename(os.path.abspath(d)), "gele_le": maintenant(),
           "auteur": auteur, "relecteur": relecteur, "note": note, "comptes": comptes, "fichiers": fichiers}
    json.dump(man, open(os.path.join(d, "MANIFEST.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(d, "CHANGELOG.md"), "a", encoding="utf-8") as f:
        f.write(f"- {man['gele_le']} — {man['version']} frozen by {auteur} (reviewer: {relecteur}); {fichier_items} {fichiers.get(fichier_items or '', '')[:12]}; {note}\n")
    return {"banc": man["banc"], "items": comptes.get("n_items"), "sha_items": fichiers.get(fichier_items or "items.json", "")[:16], "fichiers": len(fichiers)}


def hash_ensemble(fichiers):
    """Frozen-set hash of the published layout: sha256 of '<sha256>  <path>\\n' lines sorted by path (sha256sum format)."""
    import hashlib
    texte = "".join(f"{sha}  {chemin}\n" for chemin, sha in sorted(fichiers.items()))
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def verifier(d):
    """Returns (problems, report) for one bench folder."""
    man = json.load(open(os.path.join(d, "MANIFEST.json"), encoding="utf-8"))
    problemes, rapport = [], {"banc": d, "ok": 0, "withheld": 0, "non_hashes": 0, "derived": 0}
    if man.get("withheld_entirely"):            # nothing published, not even hashes (see the bench's CARD.md)
        rapport["entirely_withheld"] = True
        return problemes, rapport
    if "frozen_set" in man:
        fs = man["frozen_set"]; withheld = man.get("withheld") or {}
        for nom, sha in fs["files"].items():
            p = os.path.join(d, nom)
            if sha is None:                      # withheld for privacy: no published hash
                if nom not in withheld: problemes.append(f"{nom}: no hash and not withheld")
                else: rapport["withheld"] += 1; rapport["non_hashes"] += 1
                continue
            if not os.path.exists(p):
                if nom in withheld: rapport["withheld"] += 1
                else: problemes.append(f"{nom}: missing (published)")
                continue
            if sha256_fichier(p) != sha: problemes.append(f"{nom}: checksum differs")
            else: rapport["ok"] += 1
        for nom, info in (man.get("derived") or {}).items():
            p = os.path.join(d, nom)
            if not os.path.exists(p): problemes.append(f"{nom}: derived view missing"); continue
            if sha256_fichier(p) != info["sha256"]: problemes.append(f"{nom}: derived view checksum differs")
            else: rapport["derived"] += 1
        if rapport["withheld"] == 0 and fs.get("set_hash"):
            rapport["set_hash_ok"] = hash_ensemble(fs["files"]) == fs["set_hash"]
            if not rapport["set_hash_ok"]: problemes.append("frozen-set hash differs")
    else:
        for nom, sha in man["fichiers"].items():
            p = os.path.join(d, nom)
            if not os.path.exists(p): problemes.append(f"{nom}: missing"); continue
            if sha256_fichier(p) != sha: problemes.append(f"{nom}: checksum differs")
            else: rapport["ok"] += 1
    return problemes, rapport


def dossiers_a_verifier(chemins):
    for c in chemins:
        if os.path.exists(os.path.join(c, "MANIFEST.json")): yield c; continue
        trouves = sorted(os.path.dirname(m) for m in glob.glob(os.path.join(c, "*", "*", "MANIFEST.json")))
        if not trouves: raise SystemExit(f"{c}: no MANIFEST.json here or two levels below")
        yield from trouves


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in ("freeze", "verify", "-h", "--help"): argv = ["freeze"] + argv
    ap = argparse.ArgumentParser(description="Freeze a bench of your own, or verify a frozen one (see the module docstring).")
    sp = ap.add_subparsers(dest="cmd", required=True)
    f = sp.add_parser("freeze"); f.add_argument("dossier"); f.add_argument("--auteur", required=True); f.add_argument("--relecteur", default="to review"); f.add_argument("--note", default="")
    v = sp.add_parser("verify"); v.add_argument("dossiers", nargs="*", default=[BANCS_DEFAUT])
    a = ap.parse_args(argv)
    if a.cmd == "freeze":
        print(json.dumps(geler(a.dossier, a.auteur, a.relecteur, a.note), ensure_ascii=False)); return 0
    total = 0
    for d in dossiers_a_verifier(a.dossiers):
        problemes, r = verifier(d); total += len(problemes)
        etat = "ok" if not problemes else "FAILED"
        if r.get("entirely_withheld"): print(f"skip   {d}: withheld entirely, nothing to verify"); continue
        print(f"{etat:6} {d}: {r['ok']} frozen file(s) match, {r['derived']} derived view(s) match, {r['withheld']} withheld"
              + (f" ({r['non_hashes']} withheld, not hashed)" if r.get("non_hashes") else "")
              + (f", frozen-set hash {'ok' if r.get('set_hash_ok') else 'differs'}" if "set_hash_ok" in r else ""))
        for p in problemes: print(f"       {p}")
    return 1 if total else 0


if __name__ == "__main__": sys.exit(main())
