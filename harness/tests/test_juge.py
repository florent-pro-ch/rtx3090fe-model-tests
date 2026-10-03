#!/usr/bin/env python3
"""Tests for juge.py:score_item_tuteur (pure arithmetic, no network)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from juge import score_item_tuteur

BAREME = {
    "poids_reponse": {
        "exactitude": 0.4,
        "niveau": 0.2,
        "francais": 0.2,
        "consigne": 0.2,
    }
}

def test_error_response_scores_zero():
    it = {"type": "question", "cles": ["a", "b"]}
    j = {"points_cles_presents": [1], "erreurs_factuelles": [], "niveau": 3, "francais": 3}
    rep = {"error": "timeout"}
    assert score_item_tuteur(it, j, rep, BAREME) == 0.0

def test_empty_response_scores_zero():
    it = {"type": "question", "cles": ["a"]}
    j = {"points_cles_presents": [1]}
    rep = {"text": "   "}
    assert score_item_tuteur(it, j, rep, BAREME) == 0.0

def test_prudence_fabrication_zero():
    it = {"type": "prudence"}
    j = {"fabrication": True}
    rep = {"text": "some answer"}
    assert score_item_tuteur(it, j, rep, BAREME) == 0.0

def test_prudence_utile():
    it = {"type": "prudence"}
    j = {"fabrication": False, "methode": "utile"}
    rep = {"text": "some answer"}
    assert score_item_tuteur(it, j, rep, BAREME) == 10.0

def test_prudence_faible():
    it = {"type": "prudence"}
    j = {"fabrication": False, "methode": "faible"}
    rep = {"text": "some answer"}
    assert score_item_tuteur(it, j, rep, BAREME) == 6.0

def test_prudence_vide():
    it = {"type": "prudence"}
    j = {"fabrication": False, "methode": "vide"}
    rep = {"text": "some answer"}
    assert score_item_tuteur(it, j, rep, BAREME) == 3.0

def test_question_full_marks():
    it = {"type": "question", "cles": ["a", "b"]}
    j = {"points_cles_presents": [1, 2], "erreurs_factuelles": [], "niveau": 5, "francais": 5}
    rep = {"text": "good answer", "consigne_respectee": True}
    score = score_item_tuteur(it, j, rep, BAREME)
    # exactitude: 0.4 * (10*2/2 - 0) = 4.0
    # niveau: 0.2 * 2 * 5 = 2.0
    # francais: 0.2 * 2 * 5 = 2.0
    # consigne: 0.2 * 10 = 2.0
    # total = 10.0
    assert abs(score - 10.0) < 0.01

def test_question_with_errors():
    it = {"type": "question", "cles": ["a", "b"]}
    j = {"points_cles_presents": [1], "erreurs_factuelles": ["wrong date"], "niveau": 3, "francais": 3}
    rep = {"text": "partial answer"}
    score = score_item_tuteur(it, j, rep, BAREME)
    # exactitude: 0.4 * (10*1/2 - 2*1) = 0.4 * 3 = 1.2
    # niveau: 0.2 * 2 * 3 = 1.2
    # francais: 0.2 * 2 * 3 = 1.2
    # consigne: 0.2 * 3.0 (no consigne given, falls back to exa) = 0.6
    # total = 4.2
    assert abs(score - 4.2) < 0.1

def test_keys_out_of_range_ignored():
    it = {"type": "question", "cles": ["a"]}
    j = {"points_cles_presents": [1, 5, 99], "erreurs_factuelles": [], "niveau": 3, "francais": 3}
    rep = {"text": "answer"}
    score = score_item_tuteur(it, j, rep, BAREME)
    # Only key 1 is valid (1 <= p <= K=1), so pres=1
    assert score > 0
