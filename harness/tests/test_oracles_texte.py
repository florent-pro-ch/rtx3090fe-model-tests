#!/usr/bin/env python3
"""Tests for oracles_texte.py (pure functions, no network, no GPU)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from oracles_texte import (nombre, meme_nombre, date_iso, sans_accents, normalise_nom, jetons_nom, meme_nom,
                           jaccard_nom, levenshtein, cer, wer, normalise_texte, reponse_finale)

# ---------------------------------------------------------------- numbers

def test_nombre_french_and_swiss_group_separators():
    assert nombre("1 234,5") == (1234.5, None)
    assert nombre("1'234.50") == (1234.5, None)
    assert nombre("1’234.50") == (1234.5, None)          # typographic apostrophe
    assert nombre("1 234 567") == (1234567.0, None)  # narrow and plain no-break spaces
    assert nombre("12 500 CHF") == (12500.0, "CHF")

def test_nombre_units_and_percent():
    assert nombre("3,5 %") == (3.5, "%")
    assert nombre("3,5%") == (3.5, "%")
    assert nombre("3,5 pour cent") == (3.5, "%")
    assert nombre("12 500 francs") == (12500.0, "CHF")
    assert nombre("CHF 12'500") == (12500.0, "CHF")
    assert nombre("450 €") == (450.0, "EUR")
    assert nombre("5 km") == (5.0, "km")
    assert nombre("12 500.– CHF") == (12500.0, "CHF")   # the Swiss ".–" after a whole amount

def test_nombre_sentence_dot_is_not_part_of_the_unit():
    assert nombre("12 500 CHF.") == (12500.0, "CHF")
    assert nombre("5 km.") == (5.0, "km")
    assert nombre("450 euros.") == (450.0, "EUR")
    assert nombre("3,5 %.") == (3.5, "%")
    assert nombre("12 500 Fr.") == (12500.0, "CHF")
    assert meme_nombre("5 km", "5 km.") is True
    assert meme_nombre("12 500 CHF", reponse_finale("Calcul.\nRéponse finale : 12 500 CHF.")) is True

def test_nombre_only_known_units_and_long_forms():
    assert nombre("42 kilomètres") == (42.0, "km")
    assert nombre("42 années") == (42.0, "an")
    assert nombre("42 est la réponse") == (42.0, None)     # prose after the number is not a unit
    assert nombre("Il y a 3 enfants") == (3.0, None)
    assert nombre("42 et 17") == (42.0, None)
    assert nombre("Il y a 3 enfants", unites={"enfants": "enfant"}) == (3.0, "enfant")
    assert meme_nombre("42 km", "environ 42 kilomètres") is True
    assert meme_nombre("42 ans", "42 années") is True
    assert meme_nombre("42 km", "42 est la réponse") is True
    assert meme_nombre("42 km", "42 kg") is False

def test_nombre_decimal_marks():
    assert nombre("3.5") == (3.5, None)
    assert nombre("1.234,56") == (1234.56, None)
    assert nombre("1,234.56") == (1234.56, None)
    assert nombre("1.234") == (1.234, None)       # a lone dot is decimal, never a thousands mark
    assert nombre("1,234,567") is None            # several commas: refused, not guessed
    assert nombre("1.234.567") is None

def test_nombre_sign_and_edges():
    assert nombre("-12,5") == (-12.5, None)
    assert nombre("− 12,5 %") == (-12.5, "%")
    assert nombre("+7") == (7.0, None)
    assert nombre("La réponse est 42.") == (42.0, None)  # the sentence dot is not read
    assert nombre("") is None
    assert nombre(None) is None
    assert nombre("aucun chiffre") is None

def test_meme_nombre():
    assert meme_nombre("12 500 CHF", "12'500") is True          # a side without unit matches
    assert meme_nombre("12 500 CHF", "12 500 EUR") is False      # two units must agree
    assert meme_nombre("3,5 %", "3.5%") is True
    assert meme_nombre("3,5", "3,6", tolerance=0.05) is False
    assert meme_nombre("3,5", "3,54", tolerance=0.05) is True
    assert meme_nombre(None, "3") is False
    assert meme_nombre("3", "") is False

# ---------------------------------------------------------------- dates

def test_date_iso_french_letters():
    assert date_iso("12 mars 2026") == "2026-03-12"
    assert date_iso("1er janvier 2026") == "2026-01-01"
    assert date_iso("Le 3 FÉVRIER 2026, à midi") == "2026-02-03"
    assert date_iso("12 sept. 2026") == "2026-09-12"
    assert date_iso("15 aout 2025") == "2025-08-15"
    assert date_iso("25 décembre 2026") == "2026-12-25"

def test_date_iso_digits_and_iso():
    assert date_iso("12/03/2026") == "2026-03-12"
    assert date_iso("12.03.2026") == "2026-03-12"
    assert date_iso("12-03-2026") == "2026-03-12"
    assert date_iso("2026-03-12") == "2026-03-12"
    assert date_iso("Signé le 2026-03-12 à Lausanne") == "2026-03-12"

def test_date_iso_ambiguous_or_invalid_rejected():
    assert date_iso("12/03/26") is None       # two-digit year
    assert date_iso("mars 2026") is None      # no day
    assert date_iso("31/02/2026") is None     # calendar-invalid
    assert date_iso("03/13/2026") is None     # month 13: never swapped to rescue it
    assert date_iso("32 mars 2026") is None
    assert date_iso("12 brumaire 2026") is None
    assert date_iso("") is None
    assert date_iso(None) is None

# ---------------------------------------------------------------- names

def test_sans_accents():
    assert sans_accents("Élève à Genève") == "Eleve a Geneve"
    assert sans_accents("Œuvre à Nîmes, Øst") == "OEuvre a Nimes, Ost"   # letters NFKD leaves whole
    assert sans_accents(None) == ""

def test_normalise_nom_and_tokens():
    assert normalise_nom("Jean-Pierre DUBOIS") == "jean pierre dubois"
    assert normalise_nom("  Éliane  Müller ") == "eliane muller"
    assert jetons_nom("Dubois, Jean") == frozenset({"dubois", "jean"})
    assert normalise_nom("Łukasz Øst") == "lukasz ost"        # no letter dropped
    assert normalise_nom("Müller-Ærø") == "muller aero"
    assert meme_nom("Øst", "Ost") is True
    assert normalise_nom(None) == ""

def test_meme_nom():
    assert meme_nom("Jean Dubois", "DUBOIS Jean") is True
    assert meme_nom("Jean-Pierre Dubois", "Jean Pierre Dubois") is True
    assert meme_nom("Élise Favre", "Elise Favre") is True
    assert meme_nom("Jean Dubois", "Jean Dubois-Favre") is False
    assert meme_nom("", "") is False
    assert meme_nom(None, "Jean") is False

def test_jaccard_nom():
    assert jaccard_nom("Jean Pierre Dubois", "Jean Dubois") == 2 / 3
    assert jaccard_nom("Jean", "Marc") == 0.0
    assert jaccard_nom("", "") == 0.0
    assert jaccard_nom("Anne Roy", "roy ANNE") == 1.0

# ---------------------------------------------------------------- error rates

def test_levenshtein():
    assert levenshtein("", "") == 0
    assert levenshtein("abc", "") == 3
    assert levenshtein("kitten", "sitting") == 3
    assert levenshtein(None, "ab") == 2
    assert levenshtein(["le", "chat"], ["le", "chien"]) == 1

def test_cer():
    assert cer("bonjour", "bonjour") == 0.0
    assert cer("bonjour", "bonjuor") == 2 / 7
    assert cer("", "") == 0.0
    assert cer("", "x") == 1.0
    assert cer("ab", "abcdef") == 2.0     # can exceed 1.0
    assert cer(None, None) == 0.0

def test_normalise_texte_and_wer():
    assert normalise_texte("Bonjour, le Monde !") == "bonjour le monde"
    assert normalise_texte("Élève", accents=False) == "eleve"
    assert wer("le chat dort", "le chat dort") == 0.0
    assert wer("le chat dort", "le chien dort") == 1 / 3
    assert wer("Le chat dort.", "le chat dort") == 0.0   # punctuation and case do not count
    assert wer("l'élève", "l'eleve") > 0.0                # accents count by default
    assert wer("l'élève", "l'eleve", accents=False) == 0.0
    assert wer("", "") == 0.0
    assert wer("", "un mot") == 1.0

# ---------------------------------------------------------------- final answer

def test_reponse_finale_basic_and_last():
    assert reponse_finale("Calcul...\nRéponse finale : 42") == "42"
    assert reponse_finale("Réponse finale : 1\n... en fait non.\nRéponse finale : 2") == "2"

def test_reponse_finale_case_accent_markdown():
    assert reponse_finale("REPONSE FINALE: 12 500 CHF") == "12 500 CHF"
    assert reponse_finale("réponse finale : oui") == "oui"
    assert reponse_finale("**Réponse finale :** 3,5 %") == "3,5 %"
    assert reponse_finale("Réponse finale： Jean Dubois") == "Jean Dubois"
    assert reponse_finale("Réponse finale : *42*.") == "42"            # emphasis then a sentence dot
    assert reponse_finale("Réponse finale : 12 500 CHF.") == "12 500 CHF"
    assert reponse_finale("Réponse finale : Jean Dubois.") == "Jean Dubois"
    assert reponse_finale("Réponse finale : 3.5") == "3.5"             # a decimal dot stays
    assert reponse_finale("Réponse finale : -12,5.") == "-12,5"

def test_reponse_finale_next_line_and_none():
    assert reponse_finale("Réponse finale :\n\n**42**\nMerci.") == "42"
    assert reponse_finale("réponse  finale :\n- 42") == "42"             # list marker on the next line
    assert reponse_finale("Réponse finale :\n1. Jean Dubois") == "Jean Dubois"
    assert reponse_finale("Réponse finale :\n-12,5") == "-12,5"          # a sign is not a list marker
    assert reponse_finale("Réponse finale : - 12,5") == "- 12,5"        # same line: nothing stripped
    assert reponse_finale("Réponse finale :") is None
    assert reponse_finale("Pas de ligne finale ici.") is None
    assert reponse_finale("") is None
    assert reponse_finale(None) is None
