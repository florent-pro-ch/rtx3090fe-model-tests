#!/usr/bin/env python3
"""Tests for classe_oracles.py on a synthetic oracle-scored campaign in tmp_path (no network, no GPU)."""
import json, os, subprocess, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from commun import sha256_fichier
from classe_oracles import score_item, sous_scores, ligne_candidat, parametres_bootstrap

USINE = os.path.join(os.path.dirname(__file__), "..")
ITEMS = [
    {"id": "bq-dos-01", "matiere": "histoire", "tier": "8k", "q": "Q1"},
    {"id": "bq-dos-02", "matiere": "histoire", "tier": "32k", "q": "Q2"},
    {"id": "bq-dos-03", "matiere": "chimie", "tier": "8k", "q": "Q3"},
    {"id": "bq-dos-04", "matiere": "chimie", "tier": "32k", "q": "Q4"},
]


def _json(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, indent=1)


def _scores(camp, cid, par_id, mec=None, vit=None, sha=None):
    d = os.path.join(camp, "resultats", cid)
    sc = {"candidat": cid, "banc": "dossier", "items": par_id}
    if sha: sc["sha_items"] = sha
    _json(os.path.join(d, "scores-dossier.json"), sc)
    if mec is not None: _json(os.path.join(d, "mecanique-dossier.json"), mec)
    if vit is not None: _json(os.path.join(d, "vitesse.json"), vit)


def construit(tmp_path, egalite=True):
    """A frozen synthetic bench dossier/v1 (MANIFEST included), a registry and a campaign with six candidates."""
    bancs = tmp_path / "bancs"; bd = bancs / "dossier" / "v1"; bd.mkdir(parents=True)
    _json(str(bd / "items.json"), ITEMS)
    bareme = {"version": "v1", "mode": "dossier", "bootstrap": 1000}
    if egalite: bareme["egalite"] = {"delta_Q_max": 3.0, "duel_ecart_min": 10.0}
    _json(str(bd / "bareme.json"), bareme)
    _json(str(bd / "MANIFEST.json"), {"fichiers": {n: sha256_fichier(str(bd / n)) for n in ("items.json", "bareme.json")}})
    sha = sha256_fichier(str(bd / "items.json"))
    reg = tmp_path / "candidats.json"
    _json(str(reg), {"candidats": [{"id": c, "nom": f"Model {c}"} for c in ("a-rapide", "b-lent", "c-moyen", "d-erreurs", "e-absent", "f-autre-banc", "g-partiel")]})
    camp = tmp_path / "campagne"; camp.mkdir()
    dix = {it["id"]: {"score_10": 10.0, "completion_tokens": 100 + i} for i, it in enumerate(ITEMS)}
    # a and b tie at Q 100; a is faster on aggregate throughput (the tie-break for a non-tutoring mode)
    _scores(str(camp), "a-rapide", dix, mec={"vide": 0, "erreur": 0}, vit={"solo": {"tok_s": 50, "ttft_ms": 100}, "agrege": {"agg_tok_s": 200, "conc": 8}}, sha=sha)
    _scores(str(camp), "b-lent", dix, mec={"vide": 0, "erreur": 0}, vit={"solo": {"tok_s": 50, "ttft_ms": 100}, "agrege": {"agg_tok_s": 100, "conc": 8}}, sha=sha)
    # c: one item in error (null score + error → 0.0): 8, 6, 0, 4 → Q 45
    _scores(str(camp), "c-moyen", {"bq-dos-01": {"score_10": 8}, "bq-dos-02": {"score_10": 6}, "bq-dos-03": {"score_10": None, "error": "timeout"}, "bq-dos-04": {"score_10": 4}})
    # d: mechanically not rated
    _scores(str(camp), "d-erreurs", dix, mec={"non_cote": True, "taux_erreur": 0.5, "erreur": 2})
    # e: registered, no result folder at all
    # f: scored against another items.json → refused
    _scores(str(camp), "f-autre-banc", dix, sha="0" * 64)
    # g: only two items scored → skipped items, n 2/4
    _scores(str(camp), "g-partiel", {"bq-dos-01": {"score_10": 10}, "bq-dos-03": {"score_10": 5}})
    return bancs, reg, camp


def lance(tmp_path, bancs, reg, camp):
    out = tmp_path / "sortie" / "classement-dossier.md"
    r = subprocess.run([sys.executable, os.path.join(USINE, "classe_oracles.py"), "--banc", "dossier", "--campagne", str(camp),
                        "--bancs", str(bancs), "--candidats", str(reg), "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return out, r


def test_score_item():
    assert score_item({"score_10": 7.5}) == 7.5
    assert score_item({"score_10": None, "error": "timeout"}) == 0.0
    assert score_item({"score_10": None}) is None
    assert score_item({}) is None


def test_spearman_needs_a_length_on_every_scored_item():
    banc = {"items": ITEMS}
    complet = {it["id"]: {"score_10": 2.0 * i, "completion_tokens": 100 + i} for i, it in enumerate(ITEMS)}
    assert ligne_candidat("x", banc, "dossier", {"items": complet}, {}, {})["spearman_longueur"] == 1.0
    un_manque = dict(complet); un_manque["bq-dos-03"] = {"score_10": 4.0}   # no count: alert off, no zero mixed in
    assert ligne_candidat("x", banc, "dossier", {"items": un_manque}, {}, {})["spearman_longueur"] is None
    repli = dict(complet); repli["bq-dos-03"] = {"score_10": 4.0, "longueur": 102}   # the character fallback counts
    assert ligne_candidat("x", banc, "dossier", {"items": repli}, {}, {})["spearman_longueur"] == 1.0


def test_parametres_bootstrap():
    assert parametres_bootstrap({"bootstrap": {"n": 200, "graine": 7}}) == (200, 7)
    assert parametres_bootstrap({"bootstrap": {"n": 500}}) == (500, 20260905)
    assert parametres_bootstrap({"bootstrap": 1000}) == (1000, 20260905)
    assert parametres_bootstrap({}) == (1000, 20260905)


def test_sous_scores_per_field():
    banc = {"items": ITEMS}
    par_id = {"bq-dos-01": {"score_10": 10}, "bq-dos-02": {"score_10": 5}, "bq-dos-03": {"score_10": 0}, "bq-dos-04": {"score_10": None}}
    ss = sous_scores(banc, par_id)
    assert ss == {"matiere": {"histoire": 75.0, "chimie": 0.0}, "tier": {"8k": 50.0, "32k": 50.0}}
    assert sous_scores({"items": [{"id": "x", "q": "?"}]}, {"x": {"score_10": 3}}) == {}


def test_ranking_end_to_end(tmp_path):
    bancs, reg, camp = construit(tmp_path)
    out, r = lance(tmp_path, bancs, reg, camp)
    md = out.read_text(encoding="utf-8"); js = json.load(open(str(out)[:-3] + ".json", encoding="utf-8"))
    assert js["juge"] is None and js["banc"] == "dossier"
    rangs = {x["id"]: x for x in js["rangs"]}
    assert "e-absent" not in rangs and "f-autre-banc" not in rangs
    assert "refused: f-autre-banc" in r.stderr
    assert "g-partiel: 2 of 4 items scored" in r.stderr
    # same tie rule as classe.py: a and b tie at 100 and speed decides
    ordre = [x["id"] for x in js["rangs"]]
    assert ordre[:4] == ["a-rapide", "b-lent", "g-partiel", "c-moyen"]  # g: 75 on its two scored items
    assert rangs["a-rapide"]["departage"] == "vitesse" and rangs["a-rapide"]["groupe_egalite"] == ["a-rapide", "b-lent"]
    assert rangs["a-rapide"]["Q"] == 100.0 and rangs["a-rapide"]["ic95"] == [100.0, 100.0]
    assert rangs["c-moyen"]["Q"] == 45.0 and rangs["c-moyen"]["n_scores"] == 4
    assert rangs["c-moyen"]["sous_scores"] == {"matiere": {"histoire": 70.0, "chimie": 20.0}, "tier": {"8k": 40.0, "32k": 50.0}}
    assert rangs["g-partiel"]["n_scores"] == 2 and rangs["g-partiel"]["Q"] == 75.0
    assert rangs["d-erreurs"]["non_cote"] is True and "departage" not in rangs["d-erreurs"]
    # the Markdown carries the rows, the not-rated motive, and no judge
    assert "| 1 (vitesse) | Model a-rapide | **100.0** | 100.0–100.0 | 4/4 |" in md
    assert "| 2 (vitesse) | Model b-lent |" in md
    assert "| 3 | Model g-partiel | **75.0** |" in md and "| 2/4 |" in md
    assert "| 4 | Model c-moyen | **45.0** |" in md and "matiere: histoire 70.0, chimie 20.0; tier: 8k 40.0, 32k 50.0" in md
    assert "Model d-erreurs | not rated (50% of items in error)" in md
    assert "oracle-scored, no judge" in md and "juge" not in md.lower().replace("no judge", "")


def test_header_states_the_bootstrap_actually_used(tmp_path):
    bancs, reg, camp = construit(tmp_path)
    out, r = lance(tmp_path, bancs, reg, camp)
    assert "1000 resamples, seed 20260905" in out.read_text(encoding="utf-8")
    # the frozen benches write {"n", "graine"}: the bareme is rewritten and the MANIFEST refreshed
    bd = bancs / "dossier" / "v1"; bareme = json.load(open(bd / "bareme.json", encoding="utf-8"))
    bareme["bootstrap"] = {"n": 200, "graine": 7}; _json(str(bd / "bareme.json"), bareme)
    _json(str(bd / "MANIFEST.json"), {"fichiers": {n: sha256_fichier(str(bd / n)) for n in ("items.json", "bareme.json")}})
    out, r = lance(tmp_path, bancs, reg, camp)
    assert "200 resamples, seed 7" in out.read_text(encoding="utf-8")


def test_bareme_without_egalite_uses_default(tmp_path):
    bancs, reg, camp = construit(tmp_path, egalite=False)
    out, r = lance(tmp_path, bancs, reg, camp)
    assert "no 'egalite' block" in r.stderr
    js = json.load(open(str(out)[:-3] + ".json", encoding="utf-8"))
    assert [x["id"] for x in js["rangs"]][:2] == ["a-rapide", "b-lent"]


def test_modified_bench_refused(tmp_path):
    bancs, reg, camp = construit(tmp_path)
    p = bancs / "dossier" / "v1" / "items.json"
    p.write_text(p.read_text(encoding="utf-8").replace("Q1", "Q1 modifiée"), encoding="utf-8")
    out = tmp_path / "x.md"
    r = subprocess.run([sys.executable, os.path.join(USINE, "classe_oracles.py"), "--banc", "dossier", "--campagne", str(camp),
                        "--bancs", str(bancs), "--candidats", str(reg), "--out", str(out)], capture_output=True, text=True)
    assert r.returncode != 0 and "MANIFEST" in (r.stderr + r.stdout) and not out.exists()
