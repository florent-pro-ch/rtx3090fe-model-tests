#!/usr/bin/env python3
"""Text oracles shared by the exact-truth benches: pure functions, standard library only.

What lives here is the comparison floor a runner calls once it holds a model's answer and the
item's truth written in advance: numbers in French and Swiss notation,
dates in French forms, person names, character and word error rates, and the "Réponse finale :"
convention that lets a reasoning model be graded on one line. Nothing here calls a model.

Every function accepts None and returns None (or the neutral value) rather than raising, so a
runner can score an empty answer as a miss instead of a crash. The measurement strings these
functions read are French; the code is not.
"""
import datetime, re, unicodedata

# ---------------------------------------------------------------- numbers

# Group separators seen in French and Swiss writing: the space, the no-break space (U+00A0),
# the narrow no-break space (U+202F), the ASCII apostrophe and the typographic one (U+2019).
_SEP_GROUPE = "   '’"
_RE_NOMBRE = re.compile(r"(?P<signe>[-−–+])?\s*(?P<corps>\d(?:[\d   '’.,]*\d)?)")
# Units read after a number (or, for currencies, before it). Any other word that follows a number is
# prose, not a unit, and reads as None: "42 est la réponse" carries no unit, so it still matches the
# truth "42 km". French long forms map to the short canonical code ("42 kilomètres" equals "42 km");
# keys are lowercase and accent-free. A caller extends the table with unites={word: canonical}.
_UNITES = {
    "%": "%", "pour cent": "%", "pourcent": "%", "pct": "%",
    "chf": "CHF", "fr": "CHF", "frs": "CHF", "franc": "CHF", "francs": "CHF", "sfr": "CHF",
    "€": "EUR", "eur": "EUR", "euro": "EUR", "euros": "EUR",
    "$": "USD", "usd": "USD", "dollar": "USD", "dollars": "USD",
    "km": "km", "kilometre": "km", "kilometres": "km", "m": "m", "metre": "m", "metres": "m", "cm": "cm", "mm": "mm",
    "kg": "kg", "kilo": "kg", "kilos": "kg", "kilogramme": "kg", "kilogrammes": "kg", "g": "g", "gramme": "g", "grammes": "g",
    "l": "l", "litre": "l", "litres": "l", "ml": "ml",
    "h": "h", "heure": "h", "heures": "h", "min": "min", "minute": "min", "minutes": "min", "s": "s", "sec": "s", "seconde": "s", "secondes": "s",
    "an": "an", "ans": "an", "annee": "an", "annees": "an", "mois": "mois", "jour": "jour", "jours": "jour", "semaine": "semaine", "semaines": "semaine",
}
# The Swiss ".–" / ".-" after a whole amount ("12 500.– CHF") is skipped before the unit is read.
_RE_UNITE = re.compile(r"^\s*(?:\.[-–—]{1,2})?\s*(?P<u>%|€|\$|[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ.]*(?:\s+cent)?)")


def _unite(brut, table):
    """Canonical form of a unit word, or None when the word is not a known unit.

    Currency words map to ISO codes, percent variants to "%", long forms to the short code; a
    sentence-ending dot glued to the word ("CHF.", "km.") is not part of it.
    """
    k = sans_accents(brut or "").strip().lower()
    if not k: return None
    if k not in table: k = k.rstrip(".")
    return table.get(k)


def nombre(texte, unites=None):
    """First number in a French or Swiss string, as (value, unit) — or None when there is none.

    Group separators are the space, the no-break spaces, and both apostrophes: "1 234,5",
    "1'234.50" and "12 500 CHF" all read as expected. When both "," and "." occur, the last one
    is the decimal mark and the other a group mark ("1.234,56" → 1234.56, "1,234.56" → 1234.56).
    A lone "," is French decimal ("3,5" → 3.5); a lone "." is Swiss or English decimal
    ("3.5" → 3.5): a lone dot is never read as a thousands mark, because "1.234" is ambiguous
    and an oracle must not guess in the model's favour. Signs accepted: "-", "−", "–", "+".

    The unit is the known unit word that directly follows the number ("%", "CHF", "km", and the
    French long forms: "42 kilomètres" reads as km), or a currency written before it ("CHF 12 500");
    currency words map to ISO codes, percent variants to "%". Any other following word is prose
    and the unit is None ("42 est la réponse"), so a bench truth carrying a unit still matches an
    answer that spells the value without it. unites={word: canonical} extends the known units.
    Returns (float, str | None), or None when no digit is found.
    """
    if texte is None: return None
    s = str(texte)
    table = dict(_UNITES, **{sans_accents(k).strip().lower(): v for k, v in (unites or {}).items()})
    m = _RE_NOMBRE.search(s)
    if not m: return None
    corps = m.group("corps")
    for c in _SEP_GROUPE: corps = corps.replace(c, "")
    if "," in corps and "." in corps:
        dec = "," if corps.rfind(",") > corps.rfind(".") else "."
        corps = corps.replace("." if dec == "," else ",", "").replace(",", ".")
    elif "," in corps:
        if corps.count(",") > 1: return None  # "1,234,567": several commas, no decimal reading
        corps = corps.replace(",", ".")
    elif corps.count(".") > 1:
        return None  # "1.234.567": several dots, same refusal
    try: val = float(corps)
    except ValueError: return None
    if m.group("signe") in ("-", "−", "–"): val = -val
    apres = _RE_UNITE.match(s[m.end():])
    unite = _unite(apres.group("u"), table) if apres else None
    if unite is None:
        avant = re.search(r"(CHF|EUR|USD|Fr\.?|€|\$)\s*$", s[:m.start()], re.I)
        if avant: unite = _unite(avant.group(1), table)
    return (val, unite)


def meme_nombre(attendu, obtenu, tolerance=0.0, unites=None):
    """True when both strings carry the same number, within an absolute tolerance, and compatible units.

    Units must match when both sides carry one; a side without a unit matches any unit, so the
    truth "12 500 CHF" accepts "12'500" and "12 500 CHF." but rejects "12 500 EUR". None on either
    side is False. unites= is passed through to nombre.
    """
    a, b = nombre(attendu, unites), nombre(obtenu, unites)
    if a is None or b is None: return False
    if a[1] and b[1] and a[1] != b[1]: return False
    return abs(a[0] - b[0]) <= tolerance


# ---------------------------------------------------------------- dates

_MOIS = {
    "janvier": 1, "janv": 1, "jan": 1, "fevrier": 2, "fevr": 2, "fev": 2, "mars": 3, "avril": 4, "avr": 4,
    "mai": 5, "juin": 6, "juillet": 7, "juil": 7, "aout": 8, "septembre": 9, "sept": 9, "sep": 9,
    "octobre": 10, "oct": 10, "novembre": 11, "nov": 11, "decembre": 12, "dec": 12,
}
_RE_DATE_LETTRES = re.compile(r"\b(?P<j>\d{1,2})(?:er|e)?\s+(?P<m>[a-z]+)\.?\s+(?P<a>\d{4})\b")
_RE_DATE_CHIFFRES = re.compile(r"\b(?P<j>\d{1,2})[/.\-](?P<m>\d{1,2})[/.\-](?P<a>\d{4})\b")
_RE_DATE_ISO = re.compile(r"\b(?P<a>\d{4})-(?P<m>\d{2})-(?P<j>\d{2})\b")


# Latin letters NFKD leaves whole (no decomposition), mapped to their plain forms so a name keeps them.
_LETTRES_ENTIERES = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D"})


def sans_accents(texte):
    """The string with its diacritics removed (NFKD, combining marks dropped) and the letters NFKD
    cannot decompose (ø, æ, œ, ł, đ) replaced by their plain forms ("Øst" → "Ost"); None → ""."""
    t = "".join(c for c in unicodedata.normalize("NFKD", texte or "") if not unicodedata.combining(c))
    return t.translate(_LETTRES_ENTIERES)


def _iso(a, m, j):
    try: return datetime.date(int(a), int(m), int(j)).isoformat()
    except ValueError: return None


def date_iso(texte):
    """First date in a French string, as ISO "YYYY-MM-DD" — or None.

    Read forms: "12 mars 2026", "1er janvier 2026", "12 sept. 2026" (accents and case ignored),
    "12/03/2026", "12.03.2026", "12-03-2026" (always day, month, year: the French reading),
    and ISO "2026-03-12". Refused, as ambiguous or incomplete: two-digit years ("12/03/26"),
    a month without a day ("mars 2026"), and any calendar-invalid date ("31/02/2026",
    "03/13/2026" — the month is never swapped with the day to rescue it).
    """
    if texte is None: return None
    s = sans_accents(str(texte)).lower()
    m = _RE_DATE_ISO.search(s)
    if m: return _iso(m.group("a"), m.group("m"), m.group("j"))
    m = _RE_DATE_CHIFFRES.search(s)
    if m: return _iso(m.group("a"), m.group("m"), m.group("j"))
    m = _RE_DATE_LETTRES.search(s)
    if m and m.group("m") in _MOIS: return _iso(m.group("a"), _MOIS[m.group("m")], m.group("j"))
    return None


# ---------------------------------------------------------------- names

_RE_NON_LETTRE = re.compile(r"[^a-z0-9]+")


def normalise_nom(texte):
    """A person's name reduced to comparable form: casefolded, accents stripped, punctuation and
    hyphens turned into single spaces ("Jean-Pierre DUBOIS" → "jean pierre dubois"); None → ""."""
    return _RE_NON_LETTRE.sub(" ", sans_accents(texte).casefold()).strip()


def jetons_nom(texte):
    """The set of tokens of a normalised name (order-free, so "Dubois Jean" equals "Jean Dubois")."""
    return frozenset(normalise_nom(texte).split())


def meme_nom(a, b):
    """Token-set equality of two names; two empty names are not the same name (False)."""
    ta, tb = jetons_nom(a), jetons_nom(b)
    return bool(ta) and ta == tb


def jaccard_nom(a, b):
    """Jaccard similarity of the two token sets, 0.0 to 1.0 (0.0 when both are empty)."""
    ta, tb = jetons_nom(a), jetons_nom(b)
    if not ta and not tb: return 0.0
    return len(ta & tb) / len(ta | tb)


# ---------------------------------------------------------------- error rates

def levenshtein(a, b):
    """Edit distance between two sequences (strings or lists of tokens), two-row dynamic programming."""
    a, b = a or "", b or ""
    if len(a) < len(b): a, b = b, a
    prec = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cour = [i]
        for j, cb in enumerate(b, 1):
            cour.append(min(prec[j] + 1, cour[j - 1] + 1, prec[j - 1] + (ca != cb)))
        prec = cour
    return prec[-1]


def cer(reference, hypothese):
    """Character error rate: edit distance over the reference length, on the raw characters.

    No normalisation is applied here; the caller decides what counts (an OCR bench compares the
    exact page, a spoken bench normalises first). With an empty reference the rate is 0.0 when
    the hypothesis is empty and 1.0 otherwise. Can exceed 1.0 when the hypothesis is much longer.
    """
    reference, hypothese = reference or "", hypothese or ""
    if not reference: return 0.0 if not hypothese else 1.0
    return levenshtein(reference, hypothese) / len(reference)


def normalise_texte(texte, accents=True):
    """Text reduced for word comparison: casefolded, punctuation turned into spaces, spaces
    collapsed; accents are kept by default (French keeps them meaningful), dropped with accents=False."""
    t = (texte or "").casefold()
    if not accents: t = sans_accents(t)
    t = re.sub(r"[^\w\s]|_", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def wer(reference, hypothese, accents=True):
    """Word error rate: edit distance over words, after normalise_texte on both sides.

    Same empty-reference convention as cer. The unit is the whitespace-separated word.
    """
    r, h = normalise_texte(reference, accents).split(), normalise_texte(hypothese, accents).split()
    if not r: return 0.0 if not h else 1.0
    return levenshtein(r, h) / len(r)


# ---------------------------------------------------------------- final answer

_RE_FINALE = re.compile(r"r[eé]ponse\s+finale[\s*_]*[:：][\s*_]*(?P<r>[^\n]*)", re.I)
_RE_BORDS = re.compile(r"^[\s*_]+|[\s*_.]+$")        # emphasis and spaces around the answer, a final dot
_RE_PUCE = re.compile(r"^(?:[-–•]\s+|\d+[.)]\s+)")  # a list marker opening the fallback line ("- 42", "1. 42")


def reponse_finale(texte):
    """The text after the last "Réponse finale :" of an answer, or None.

    Case and accent tolerant ("REPONSE FINALE:", "réponse finale :"), tolerant of Markdown
    emphasis around the label and of the full-width colon. Emphasis marks and spaces around the
    answer and a sentence-ending dot are stripped ("**42**." → "42", "12 500 CHF." → "12 500 CHF").
    When nothing follows the colon on its line, the next non-empty line is taken, without its list
    marker if any ("- 42" → "42"; a same-line "- 12" keeps its sign). None when the label is absent
    or nothing follows it.
    """
    if not texte: return None
    occ = list(_RE_FINALE.finditer(texte))
    if not occ: return None
    m = occ[-1]; r = m.group("r").strip()
    # the label's trailing [\s*_]* eats line breaks, so r is already the next non-empty line
    # when the label's own line is empty; only then is a list marker part of the layout, not the answer
    if "\n" in m.group(0)[:len(m.group(0)) - len(m.group("r"))]: r = _RE_PUCE.sub("", r)
    return _RE_BORDS.sub("", r) or None
