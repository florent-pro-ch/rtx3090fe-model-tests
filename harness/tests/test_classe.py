#!/usr/bin/env python3
"""Tests for classe.py: judge selection by id, duels keyed by judge, RANKING merge (no network, no GPU).
The campaign is synthetic, built in tmp_path: 2 candidates, a 3-item tutoring bench frozen with a MANIFEST written
exactly as commun.charger_banc verifies it, two judges' absolute files for the same candidate, two judges' duel files
against the same anchor. `campagne_partielle` adds the shapes where a missing judge must not yield a partial Q: a tutoring
candidate with an error item judged only by the other judge, and a code bench with one item to judge next to mechanical ones."""
import json, os, subprocess, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from commun import sha256_fichier
import classe
from classe import bootstrap_ic, spearman, classer, charger_candidat, fusionner_ranking

CLASSE = os.path.join(os.path.dirname(os.path.abspath(classe.__file__)), "classe.py")
ITEMS = [{"id": f"it-{k}", "matiere": m, "type": "reponse", "q": f"Question {k} ?", "cles": ["a", "b"]} for k, m in ((1, "biologie"), (2, "histoire"), (3, "géographie"))]
BAREME = {"version": "v1", "mode": "tuteur", "poids_reponse": {"exactitude": 0.5, "niveau": 0.2, "francais": 0.15, "consigne": 0.15},
          "egalite": {"delta_Q_max": 3.0, "duel_ecart_min": 10.0, "depart_vitesse": ["ttft_ms", "tok_s_solo"]},
          "bootstrap": {"n": 1000, "graine": 20260905}, "duel_items": 3, "duel_graine": 20260905, "ancre": "cand-b"}

def ecrire(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        if isinstance(obj, str): f.write(obj)
        else: json.dump(obj, f, ensure_ascii=False, indent=1)

def absolu(cid, juge, scores):
    return {"meta": {"mode": "tuteur", "passage": "absolu", "candidat": cid, "juge": juge, "juge_famille": "X", "sha_items": "x"},
            "items": {it["id"]: {"score_10": s} for it, s in zip(ITEMS, scores)}}

def duel(cid, ancre, juge, verdicts):
    return {"meta": {"mode": "tuteur", "passage": "duel", "candidat": cid, "ancre": ancre, "juge": juge, "juge_famille": "X"},
            "items": {it["id"]: {"verdict": v} for it, v in zip(ITEMS, verdicts)}}

def campagne(tmp_path):
    """Builds the synthetic campaign; returns (campaign dir, benches dir, registry path)."""
    # classe.py loads the tutoring and code benches unconditionally (vision only when frozen): the code one is
    # frozen empty of results, so Mode 2 reports no candidate and the tests read Mode 1.
    for mode in ("tuteur", "code"):
        banc = tmp_path / "bancs" / mode / "v1"
        ecrire(str(banc / "items.json"), ITEMS); ecrire(str(banc / "bareme.json"), dict(BAREME, mode=mode)); ecrire(str(banc / "prompt-juge.md"), "Tu es un correcteur.\n")
        fichiers = {n: sha256_fichier(str(banc / n)) for n in ("items.json", "bareme.json", "prompt-juge.md")}
        ecrire(str(banc / "MANIFEST.json"), {"banc": f"{mode}/v1", "version": "v1", "gele_le": "2026-09-25T00:00:00Z", "auteur": "test", "relecteur": "test", "note": "", "comptes": {"n_items": 3}, "fichiers": fichiers})
    camp = tmp_path / "campagne"
    for cid, ttft in (("cand-a", 100), ("cand-b", 200)):
        d = camp / "resultats" / cid
        ecrire(str(d / "reponses-tuteur.json"), {"candidat": cid, "mode": "tuteur", "reponses": [{"id": it["id"], "text": f"Réponse de {cid} à {it['id']}.", "completion_tokens": 50 + k} for k, it in enumerate(ITEMS)]})
        ecrire(str(d / "mecanique-tuteur.json"), {"vide": 0, "tronque": 0, "fuite_reflexion": 0, "erreur": 0, "n": 3, "taux_erreur": 0.0, "non_cote": False})
        ecrire(str(d / "vitesse.json"), {"candidat": cid, "solo": {"ttft_ms": ttft, "tok_s": 50.0}, "agrege": {"conc": 8, "agg_tok_s": 300.0}})
    j = camp / "jugements" / "tuteur"
    ecrire(str(j / "cand-a.absolu.juge-flash-next.json"), absolu("cand-a", "juge-flash-next", [8, 6, 7]))   # Q 70.0
    ecrire(str(j / "cand-a.absolu.juge-gemma4.json"), absolu("cand-a", "juge-gemma4", [2, 2, 2]))           # Q 20.0, sorts last
    ecrire(str(j / "cand-b.absolu.juge-flash-next.json"), absolu("cand-b", "juge-flash-next", [5, 5, 5]))   # Q 50.0
    ecrire(str(j / "cand-a.vs-cand-b.juge-flash-next.json"), duel("cand-a", "cand-b", "juge-flash-next", ["candidat", "candidat", "égalité"]))
    ecrire(str(j / "cand-a.vs-cand-b.juge-gemma4.json"), duel("cand-a", "cand-b", "juge-gemma4", ["ancre", "ancre", "incohérent"]))
    reg = tmp_path / "candidats.json"
    ecrire(str(reg), {"candidats": [{"id": "cand-a", "nom": "Cand A"}, {"id": "cand-b", "nom": "Cand B"}]})
    return str(camp), str(tmp_path / "bancs"), str(reg)

def lancer(camp, bancs, reg, out, *extra):
    p = subprocess.run([sys.executable, CLASSE, "--campagne", camp, "--bancs", bancs, "--candidats", reg, "--out", out, *extra], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p, json.load(open(os.path.join(camp, "classement.json")))

def rang(res, cid, mode="tuteur"): return next(r for r in res["modes"][mode]["rangs"] if r["id"] == cid)

def campagne_partielle(tmp_path):
    """The shared campaign plus the not-judged shapes: cand-c (tutoring, it-2 in error, judged by juge-gemma4 only) and a
    populated code bench (cand-a: it-1 to judge + two mechanical items, judged by juge-gemma4 only; cand-b: mechanical only)."""
    camp, bancs, reg = campagne(tmp_path)
    d = os.path.join(camp, "resultats", "cand-c")
    ecrire(os.path.join(d, "reponses-tuteur.json"), {"candidat": "cand-c", "mode": "tuteur", "reponses": [{"id": "it-1", "text": "Réponse.", "completion_tokens": 40}, {"id": "it-2", "error": "HTTP 500", "text": ""}, {"id": "it-3", "text": "Réponse.", "completion_tokens": 40}]})
    ecrire(os.path.join(d, "mecanique-tuteur.json"), {"vide": 0, "tronque": 0, "fuite_reflexion": 0, "erreur": 1, "n": 3, "taux_erreur": 0.33, "non_cote": False})
    ecrire(os.path.join(d, "vitesse.json"), {"candidat": "cand-c", "solo": {"ttft_ms": 150, "tok_s": 50.0}, "agrege": {"conc": 8, "agg_tok_s": 300.0}})
    jc = dict(absolu("cand-c", "juge-gemma4", [6, 0, 6])); del jc["items"]["it-2"]      # the judge never sees the item in error
    ecrire(os.path.join(camp, "jugements", "tuteur", "cand-c.absolu.juge-gemma4.json"), jc)
    for cid, items in (("cand-a", [{"id": "it-1", "content": "revue", "a_juger": True, "score_10": None, "completion_tokens": 30}, {"id": "it-2", "score_10": 8}, {"id": "it-3", "score_10": 10}]),
                       ("cand-b", [{"id": "it-1", "score_10": 10}, {"id": "it-2", "score_10": 8}, {"id": "it-3", "score_10": 6}])):
        ecrire(os.path.join(camp, "resultats", cid, "reponses-code.json"), {"candidat": cid, "mode": "code", "items": items})
        ecrire(os.path.join(camp, "resultats", cid, "mecanique-code.json"), {"vide": 0, "tronque": 0, "fuite_reflexion": 0, "erreur": 0, "n": 3, "taux_erreur": 0.0, "non_cote": False})
    ecrire(os.path.join(camp, "jugements", "code", "cand-a.absolu.juge-gemma4.json"), {"meta": {"mode": "code", "passage": "absolu", "candidat": "cand-a", "juge": "juge-gemma4", "juge_famille": "X", "sha_items": "x"}, "items": {"it-1": {"score_10": 4}}})
    ecrire(reg, {"candidats": [{"id": "cand-a", "nom": "Cand A"}, {"id": "cand-b", "nom": "Cand B"}, {"id": "cand-c", "nom": "Cand C"}]})
    return camp, bancs, reg

def section(md, titre, suivant): return md[md.index(titre):md.index(suivant)]

# --- judge selection ---------------------------------------------------------------------------

def test_default_judge_scores_are_used_not_the_alphabetically_last(tmp_path):
    camp, bancs, reg = campagne(tmp_path)
    p, res = lancer(camp, bancs, reg, str(tmp_path / "out.md"))
    a = rang(res, "cand-a")
    assert a["Q"] == 70.0 and a["juge"] == "juge-flash-next" and a["juge_id"] == "juge-flash-next"
    assert sorted(a["juges_absolu_disponibles"]) == ["juge-flash-next", "juge-gemma4"]
    assert res["juge_id"] == "juge-flash-next" and res["modes"]["tuteur"]["juge_id"] == "juge-flash-next"
    assert "judge id: juge-flash-next" in open(tmp_path / "out.md", encoding="utf-8").read()
    assert "warning" not in p.stderr

def test_other_judges_duel_does_not_overwrite_the_selected_one(tmp_path):
    camp, bancs, reg = campagne(tmp_path)
    _, res = lancer(camp, bancs, reg, str(tmp_path / "out.md"))
    a = rang(res, "cand-a")
    assert a["duels"]["cand-b"]["victoires"] == 2 and a["duels"]["cand-b"]["egalites"] == 1 and a["duels"]["cand-b"]["juge"] == "juge-flash-next"
    assert a["duels_autres_juges"]["cand-b"]["juge-gemma4"]["defaites"] == 2 and a["duels_autres_juges"]["cand-b"]["juge-gemma4"]["incoherents"] == 1
    assert "| 2/0/1, 0 incoh. |" in open(tmp_path / "out.md", encoding="utf-8").read()

def test_missing_judge_with_other_judges_present_is_not_judged_and_warns(tmp_path):
    camp, bancs, reg = campagne(tmp_path)
    p, res = lancer(camp, bancs, reg, str(tmp_path / "out.md"), "--juge-id", "juge-cloud-x")
    a = rang(res, "cand-a")
    assert a["Q"] is None and a["non_cote"] and a["juge"] is None and a["duels"] == {}
    assert set(a["duels_autres_juges"]["cand-b"]) == {"juge-flash-next", "juge-gemma4"}
    assert "no judgement by juge-cloud-x" in p.stderr and "juge-flash-next" in p.stderr and "juge-gemma4" in p.stderr
    assert "not yet judged" in open(tmp_path / "out.md", encoding="utf-8").read()

def test_any_reproduces_the_legacy_pick_with_a_warning(tmp_path):
    camp, bancs, reg = campagne(tmp_path)
    p, res = lancer(camp, bancs, reg, str(tmp_path / "out.md"), "--juge-id", "any")
    a = rang(res, "cand-a")
    assert a["Q"] == 20.0 and a["juge"] == "juge-gemma4"                       # alphabetically last absolute file
    assert a["duels"]["cand-b"]["juge"] == "juge-gemma4" and a["duels"]["cand-b"]["defaites"] == 2   # last duel file wins
    assert a["duels_autres_juges"] == {}
    assert "--juge-id any" in p.stderr and "cand-a.absolu.juge-gemma4.json" in p.stderr
    md = open(tmp_path / "out.md", encoding="utf-8").read()
    assert "judge id: any (legacy pick; files used: juge-flash-next, juge-gemma4)" in md

def test_charger_candidat_direct_call_default_and_any(tmp_path):
    camp, bancs, reg = campagne(tmp_path)
    banc = {"items": ITEMS, "bareme": BAREME}
    assert charger_candidat(camp, "cand-a", "tuteur", banc)["Q"] == 70.0
    assert charger_candidat(camp, "cand-a", "tuteur", banc, "any")["Q"] == 20.0
    assert charger_candidat(camp, "cand-a", "tuteur", banc, "juge-cloud-x")["Q"] is None
    assert charger_candidat(camp, "cand-z", "tuteur", banc) is None

def test_missing_judge_never_yields_a_partial_q_from_error_items(tmp_path):
    camp, bancs, reg = campagne_partielle(tmp_path)
    p, res = lancer(camp, bancs, reg, str(tmp_path / "out.md"))
    c = rang(res, "cand-c")
    assert c["Q"] is None and c["non_cote"] and c["n_scores"] == 0 and c["ic95"] == [None, None] and c["juge"] is None
    assert "tuteur/cand-c: no judgement by juge-flash-next" in p.stderr
    md = open(tmp_path / "out.md", encoding="utf-8").read()
    assert "| — | Cand C | not yet judged |" in section(md, "## Mode 1", "## Mode 2")
    assert "| 1 | Cand A | **70.0** |" in md                     # the fully judged rows are unaffected
    _, res = lancer(camp, bancs, reg, str(tmp_path / "out.md"), "--juge-id", "any")
    c = rang(res, "cand-c")
    assert c["Q"] == 40.0 and c["n_scores"] == 3 and c["juge"] == "juge-gemma4"   # legacy pick: 6, 0 (error), 6

def test_code_mode_candidate_with_items_to_judge_is_not_ranked_without_its_judge(tmp_path):
    camp, bancs, reg = campagne_partielle(tmp_path)
    p, res = lancer(camp, bancs, reg, str(tmp_path / "out.md"))
    a, b = rang(res, "cand-a", "code"), rang(res, "cand-b", "code")
    assert a["Q"] is None and a["non_cote"] and a["n_scores"] == 0 and a["juge"] is None
    assert b["Q"] == 80.0 and b["n_scores"] == 3 and not b["non_cote"]      # mechanical only: no judge needed, no file, ranked
    assert "code/cand-a: no judgement by juge-flash-next" in p.stderr and "cand-b" not in p.stderr
    m2 = section(open(tmp_path / "out.md", encoding="utf-8").read(), "## Mode 2", "## Mode 3")
    assert "| — | Cand A | not yet judged |" in m2 and "| 1 | Cand B | **80.0** |" in m2
    _, res = lancer(camp, bancs, reg, str(tmp_path / "out.md"), "--juge-id", "juge-gemma4")
    a = rang(res, "cand-a", "code")
    assert a["Q"] == 73.3 and a["n_scores"] == 3 and a["juge"] == "juge-gemma4"   # 4 (judged), 8, 10
    banc = {"items": ITEMS, "bareme": dict(BAREME, mode="code")}
    assert charger_candidat(camp, "cand-a", "code", banc, "juge-cloud-x")["Q"] is None
    assert charger_candidat(camp, "cand-b", "code", banc, "juge-cloud-x")["Q"] == 80.0

# --- RANKING merge -----------------------------------------------------------------------------

ANCIEN = """# RANKING — quality first, by mode

> ⚠️ **Hand-written banner, line 1.**
> Banner line 2 with a [link](MODEL-TABLE.md).

*Generated on 2026-09-05T13:42:07Z by `harness/classe.py` — OLD generated line.*

## Mode 1 — Tutor / FR school

| old | table |

## Mode 3 — Forge: base models

_old forge_

## Mode 8 — Cline agent loop (opened 2026-09-16)

| Rank | Model |
|---|---|
| 1 | hand-kept row |

*Re-ordered on 2026-09-23.*
"""

def test_ranking_merge_preserves_banner_and_mode_8(tmp_path):
    camp, bancs, reg = campagne(tmp_path)
    out = tmp_path / "out" / "RANKING.md"; ecrire(str(out), ANCIEN)
    lancer(camp, bancs, reg, str(out))
    md = open(out, encoding="utf-8").read()
    assert md.startswith("# RANKING — quality first, by mode\n\n> ⚠️ **Hand-written banner, line 1.**\n> Banner line 2 with a [link](MODEL-TABLE.md).\n\n*Generated on ")
    assert "OLD generated line" not in md and "| old | table |" not in md and "_old forge_" not in md
    assert md.count("## Mode 8") == 1
    queue = md[md.index("## Mode 8"):]
    assert queue == ANCIEN[ANCIEN.index("## Mode 8"):]
    assert "\n\n## Mode 8" in md                      # one blank line before the preserved tail
    assert "| 1 | Cand A | **70.0** |" in md and "Judge id: `juge-flash-next`" in md

def test_ranking_no_preserve_overwrites_everything(tmp_path):
    camp, bancs, reg = campagne(tmp_path)
    out = tmp_path / "out" / "RANKING.md"; ecrire(str(out), ANCIEN)
    lancer(camp, bancs, reg, str(out), "--no-preserve")
    md = open(out, encoding="utf-8").read()
    assert "Hand-written banner" not in md and "## Mode 8" not in md and "hand-kept row" not in md
    assert md.startswith("# RANKING — quality first, by mode\n\n*Generated on ")

def test_ranking_merge_is_idempotent_and_tolerates_a_file_without_hand_kept_parts(tmp_path):
    camp, bancs, reg = campagne(tmp_path)
    out = tmp_path / "out" / "RANKING.md"; ecrire(str(out), ANCIEN)
    lancer(camp, bancs, reg, str(out)); une = open(out, encoding="utf-8").read()
    lancer(camp, bancs, reg, str(out)); deux = open(out, encoding="utf-8").read()
    assert une.split("*Generated on")[0] == deux.split("*Generated on")[0] and une[une.index("## Mode 1"):] == deux[deux.index("## Mode 1"):]
    nouveau = "# RANKING\n\n*Generated on NEW*\n\n## Mode 1\n\nx\n"
    assert fusionner_ranking("# RANKING\n\n*Generated on OLD*\n\n## Mode 1\n\ny\n", nouveau) == nouveau
    assert fusionner_ranking("just prose, no markers\n", nouveau) == nouveau

# --- arithmetic, kept as it was -----------------------------------------------------------------

def test_bootstrap_ic():
    assert bootstrap_ic([]) == (None, None)
    assert bootstrap_ic([7.0, 7.0, 7.0]) == (70.0, 70.0)
    lo, hi = bootstrap_ic([2.0, 4.0, 6.0, 8.0, 10.0]); assert 20.0 <= lo < 60.0 < hi <= 100.0
    assert bootstrap_ic([1.0, 5.0, 9.0, 3.0]) == bootstrap_ic([1.0, 5.0, 9.0, 3.0])   # seeded, reproducible

def test_spearman():
    assert spearman([1, 2, 3], [1, 2, 3]) is None
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == -1.0

def ligne(cid, q, ic, duels=None, ttft=100):
    return {"id": cid, "Q": q, "ic95": ic, "non_cote": False, "duels": duels or {}, "vitesse": {"solo": {"ttft_ms": ttft, "tok_s": 50.0}, "agrege": {"agg_tok_s": 300.0}}, "mecanique": {}, "sous_scores": {}}

def test_classer_orders_by_q_then_breaks_ties_by_duel_or_speed():
    rows = [ligne("lent", 80.0, (70.0, 90.0), ttft=300), ligne("rapide", 81.0, (71.0, 91.0), ttft=50), ligne("loin", 50.0, (40.0, 60.0)), {"id": "nc", "Q": None, "ic95": (None, None), "non_cote": True, "duels": {}, "mecanique": {}, "sous_scores": {}}]
    o = classer(rows, "tuteur", BAREME, "cand-b")
    assert [r["id"] for r in o] == ["rapide", "lent", "loin", "nc"] and o[0]["departage"] == "vitesse"
    d = lambda v, l: {"cand-b": {"victoires": v, "defaites": l, "egalites": 0, "incoherents": 0, "n": v + l, "juge": "j"}}
    rows = [ligne("gagne", 80.0, (70.0, 90.0), d(9, 1), ttft=300), ligne("perd", 81.0, (71.0, 91.0), d(1, 9), ttft=50)]
    o = classer(rows, "tuteur", BAREME, "cand-b")
    assert [r["id"] for r in o] == ["gagne", "perd"] and o[0]["departage"] == "duel" and o[0]["taux_victoires_ancre"] == 90.0
