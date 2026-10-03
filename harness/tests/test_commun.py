#!/usr/bin/env python3
"""Tests for commun.py pure functions (no network, no GPU)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from commun import compter_phrases, consigne_respectee, fuite_reflexion

def test_compter_phrases_simple():
    assert compter_phrases("Une phrase.") == 1
    assert compter_phrases("Deux phrases. Et une autre.") == 2
    assert compter_phrases("") == 0
    assert compter_phrases(None) == 0

def test_compter_phrases_special_punctuation():
    assert compter_phrases("Question? Réponse! Oui…") == 3

def test_fuite_reflexion_think_tag():
    assert fuite_reflexion("Let me think...\n</think>\nThe answer.") is True
    assert fuite_reflexion("The answer is 42.") is False

def test_fuite_reflexion_leak_patterns():
    assert fuite_reflexion("ok, let me think about this") is True
    assert fuite_reflexion("Okay, let me consider") is True
    assert fuite_reflexion("The user is asking about") is True
    assert fuite_reflexion("The capital of France is Paris.") is False

def test_consigne_respectee_max_phrases():
    assert consigne_respectee({"max_phrases": 3}, "Une. Deux.") is True
    assert consigne_respectee({"max_phrases": 1}, "Une. Deux.") is False

def test_consigne_respectee_max_mots():
    assert consigne_respectee({"max_mots": 10}, "Trois mots ici.") is True
    assert consigne_respectee({"max_mots": 2}, "Trois mots ici.") is False

def test_consigne_respectee_format_liste():
    assert consigne_respectee({"format": "liste"}, "- item 1\n- item 2") is True
    assert consigne_respectee({"format": "liste"}, "Just a paragraph.") is False

def test_consigne_respectee_none():
    assert consigne_respectee(None, "text") is None
    assert consigne_respectee({}, "text") is None
