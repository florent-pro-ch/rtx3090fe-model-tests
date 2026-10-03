#!/usr/bin/env python3
"""Shared groundwork of the harness (Python standard library only).

English summary: an OpenAI-compatible HTTP client (chat completions, streaming TTFT, model list),
SHA-256 helpers, the frozen-bench loader that VERIFIES a bench before anything runs, JSON writers,
and the small text checks used by every runner (sentence and word counts, reasoning leaks,
length constraints). Identifiers and messages are partly French; see GLOSSARY.md.

Two bench layouts are read:

- the published layout of this repository (benches/<bench>/<version>/MANIFEST.json with a
  "frozen_set" block): every published file present is checked against its frozen SHA-256, every
  derived view (items.public.json) against its own. When the frozen items.json is withheld, the
  public view is loaded instead and its fields are mapped back to the harness names with the
  view's own "fields_kept" table; the bench is then marked incomplete (no answer key), and the
  runners that need the key say so instead of scoring. A file withheld for privacy only (a private
  literal, not an answer key; listed in frozen_set.hash_withheld) carries a null hash: it cannot be
  verified here, and when it is the items file, results name the public view's hash instead.
- the layout written by gele_banc.py for your own benches (a MANIFEST.json with a "fichiers"
  block): every listed file must exist and match.

Environment variables (all optional; command-line arguments win):
  HARNESS_BENCHES   folder of the frozen benches (default: <repo>/benches)
  HARNESS_BASE_URL  OpenAI-compatible base URL of the candidate, ending in /v1
  HARNESS_JUDGE_URL OpenAI-compatible base URL of the judge, ending in /v1
  HARNESS_API_KEY   bearer token sent with every request (or OPENAI_API_KEY); none by default
"""
import hashlib, json, os, re, time, urllib.request, urllib.error

ICI = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ICI)
BANCS_DEFAUT = os.environ.get("HARNESS_BENCHES") or os.path.join(REPO, "benches")


def env(nom, defaut=None):
    """An environment variable, or the default when it is unset or empty."""
    v = os.environ.get(nom)
    return v if v else defaut


def sha256_fichier(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def sha256_texte(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- bench loading

# Values the public views write in English and the harness reads in French.
_TYPE_PUBLIC = {"caution": "prudence"}
_CONSIGNE_PUBLIC = {"max_sentences": "max_phrases", "max_words": "max_mots"}
_FORMAT_PUBLIC = {"list": "liste"}


def _pose(d, chemin, valeur):
    """Sets d["a"]["b"] for the dotted path "a.b"."""
    parties = chemin.split(".")
    for p in parties[:-1]: d = d.setdefault(p, {})
    d[parties[-1]] = valeur


def item_interne(it, champs):
    """Maps one item of a public view back to the harness field names (fields_kept: public name -> harness path)."""
    out = {}
    for cle, val in it.items():
        cible = champs.get(cle, cle)
        if cible == "type" and isinstance(val, str): val = _TYPE_PUBLIC.get(val, val)
        if cible == "consigne" and isinstance(val, dict):
            val = {_CONSIGNE_PUBLIC.get(k, k): (_FORMAT_PUBLIC.get(v, v) if k == "format" else v) for k, v in val.items()}
        _pose(out, cible, val)
    return out


def _liste_items(charge, cle="items"):
    if isinstance(charge, list): return charge
    return charge.get(cle) or charge.get("items") or charge.get("briefs") or []


def _verifie(dossier, nom, sha, obligatoire=True):
    p = os.path.join(dossier, nom)
    if not os.path.exists(p):
        if obligatoire: raise SystemExit(f"MANIFEST: missing file {nom}")
        return False
    if sha is None:                              # withheld for privacy: no published hash to check against
        if obligatoire: raise SystemExit(f"MANIFEST: {nom} has no hash and is not withheld")
        return False
    reel = sha256_fichier(p)
    if reel != sha: raise SystemExit(f"MANIFEST: checksum differs for {nom} ({reel[:12]} != {sha[:12]}): bench modified without a new version")
    return True


def charger_banc(dossier):
    """Loads and VERIFIES a frozen bench; returns {manifest, items, bareme, prompt_juge, sha_items, dossier, complet}.

    complet is True when the items carry their answer key (the frozen items.json is on disk), False when only
    the public view could be loaded. sha_items is the SHA-256 of the frozen items.json (or briefs.json), so
    results produced from the public view still name the frozen set they belong to; when that file is withheld
    for privacy (its hash is null in the MANIFEST), sha_items is the hash of the public view the items were read
    from (sha_items_de says which file it names), the one hash a reader can check."""
    man = json.load(open(os.path.join(dossier, "MANIFEST.json"), encoding="utf-8"))
    if man.get("withheld_entirely"):
        raise SystemExit(f"{dossier}: this bench is withheld entirely (see its CARD.md); nothing can run on it")
    if "frozen_set" in man:                      # published layout of this repository
        fichiers = man["frozen_set"]["files"]
        withheld = man.get("withheld") or {}
        for nom, sha in fichiers.items():
            _verifie(dossier, nom, sha, obligatoire=nom not in withheld)
        for nom, d in (man.get("derived") or {}).items():
            _verifie(dossier, nom, d["sha256"], obligatoire=False)
    else:                                        # layout written by gele_banc.py
        fichiers = man["fichiers"]
        for nom, sha in fichiers.items(): _verifie(dossier, nom, sha)
    nom_items = "items.json" if "items.json" in fichiers else ("briefs.json" if "briefs.json" in fichiers else "items.json")
    p_items = os.path.join(dossier, nom_items)
    nom_vue = nom_items.replace(".json", ".public.json")
    sha_items, sha_de = fichiers.get(nom_items) or "", nom_items
    if nom_items in fichiers and fichiers[nom_items] is None:   # withheld for privacy: name the public view
        sha_items = ((man.get("derived") or {}).get(nom_vue) or {}).get("sha256") or ""
        sha_de = nom_vue if sha_items else None
    complet = os.path.exists(p_items)
    if complet:
        items = _liste_items(json.load(open(p_items, encoding="utf-8")))
    else:
        vue = os.path.join(dossier, nom_vue)
        if not os.path.exists(vue): raise SystemExit(f"{dossier}: neither {nom_items} nor its public view is on disk")
        charge = json.load(open(vue, encoding="utf-8")); champs = charge.get("fields_kept") or {}
        items = [item_interne(it, champs) for it in _liste_items(charge)]
    p_bareme = os.path.join(dossier, "bareme.json")
    bareme = json.load(open(p_bareme, encoding="utf-8")) if os.path.exists(p_bareme) else {}
    p_prompt = os.path.join(dossier, "prompt-juge.md")
    prompt = open(p_prompt, encoding="utf-8").read() if os.path.exists(p_prompt) else ""
    return {"manifest": man, "items": items, "bareme": bareme, "prompt_juge": prompt,
            "sha_items": sha_items, "sha_items_de": sha_de, "dossier": dossier, "complet": complet}


def exige_cle(banc, quoi):
    """Stops with a clear message when a step needs the answer key and only the public view is on disk."""
    if not banc.get("complet"):
        raise SystemExit(f"{quoi} needs the bench's answer key ({os.path.join(banc['dossier'], 'items.json')}), which this "
                         "repository withholds (see the bench's CARD.md). Use a bench of your own frozen with gele_banc.py, "
                         "or a step that needs no key (responses, duels, the refusal level).")


def seuil_erreurs(bareme, defaut=0.1):
    """Error-rate threshold above which a run is 'not rated' (the bareme's, or the default when it is withheld)."""
    return ((bareme or {}).get("mecanique") or {}).get("seuil_non_cote_erreurs", defaut)


# --------------------------------------------------------------------------- writers

def ecrire_exclusif(p, obj):
    """Exclusive write (refuses to overwrite) of a JSON file."""
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "x", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, indent=1)


def ecrire(p, obj):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, indent=1)


def maintenant(): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def partie_image(chemin):
    """OpenAI content part carrying a local image inline (base64 data URL): no file path ever reaches the engine."""
    import base64, mimetypes
    mime = mimetypes.guess_type(chemin)[0] or "image/png"
    b64 = base64.b64encode(open(chemin, "rb").read()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


# --------------------------------------------------------------------------- OpenAI-compatible client

def _entetes():
    h = {"Content-Type": "application/json"}
    cle = env("HARNESS_API_KEY") or env("OPENAI_API_KEY")
    if cle: h["Authorization"] = f"Bearer {cle}"
    return h


# timeout 2,400 s: reasoning-on runs with large budgets need it; chat() below carries the same default.
def post_json(url, body, timeout=2400, essais=3):
    """POST JSON with 3 attempts; returns (dict, seconds)."""
    data = json.dumps(body).encode("utf-8"); derniere = None
    for i in range(essais):
        t0 = time.time()
        try:
            req = urllib.request.Request(url, data=data, headers=_entetes())
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8")), time.time() - t0
        except urllib.error.HTTPError as e:
            derniere = f"HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}"
            if 400 <= e.code < 500: break
        except Exception as e:
            derniere = repr(e)[:300]
        time.sleep(2 * (i + 1))
    raise RuntimeError(derniere)


def chat(base, model, messages, max_tokens=600, temperature=0, tools=None, extra=None, timeout=2400, response_format=None):
    """One chat completion against base + /chat/completions; returns content, reasoning, tool calls, usage, seconds."""
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    if tools: body["tools"] = tools; body["tool_choice"] = "auto"
    if response_format: body["response_format"] = response_format
    if extra: body.update(extra)
    j, dt = post_json(f"{base.rstrip('/')}/chat/completions", body, timeout=timeout)
    ch = j["choices"][0]; m = ch["message"]
    return {"content": m.get("content") or "", "reasoning": m.get("reasoning_content") or m.get("reasoning") or "",
            "tool_calls": m.get("tool_calls") or [], "finish": ch.get("finish_reason"), "usage": j.get("usage") or {}, "secondes": round(dt, 3), "brut": j}


def chat_stream_ttft(base, model, messages, max_tokens=512, extra=None, timeout=900):
    """Measures TTFT (first delta, content or reasoning) and wall time while streaming."""
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0, "stream": True}
    if extra: body.update(extra)
    req = urllib.request.Request(f"{base.rstrip('/')}/chat/completions", data=json.dumps(body).encode(), headers=_entetes())
    t0 = time.time(); ttft = None; n = 0
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for line in r:
            s = line.decode("utf-8", "replace").strip()
            if not s.startswith("data:"): continue
            s = s[5:].strip()
            if s == "[DONE]": break
            try: d = json.loads(s)
            except Exception: continue
            delta = (d.get("choices") or [{}])[0].get("delta") or {}
            if (delta.get("content") or delta.get("reasoning_content") or delta.get("reasoning")):
                if ttft is None: ttft = time.time() - t0
                n += 1
    return {"ttft_s": round(ttft, 3) if ttft else None, "wall_s": round(time.time() - t0, 2), "deltas": n}


def modeles(base, timeout=10):
    req = urllib.request.Request(f"{base.rstrip('/')}/models", headers=_entetes())
    with urllib.request.urlopen(req, timeout=timeout) as r: return json.loads(r.read())


# --------------------------------------------------------------------------- text checks

RE_THINK = re.compile(r"<think>|</think>|<\|channel\|>|<\|start\|>assistant<\|channel\|>analysis", re.I)


def fuite_reflexion(texte):
    """True if a reasoning block leaks into the visible content."""
    if RE_THINK.search(texte or ""): return True
    t = (texte or "")[:400].lower()
    return t.startswith("ok, let") or t.startswith("okay, let") or t.startswith("the user is asking")


def compter_phrases(t):
    t = re.sub(r"\s+", " ", t or "").strip()
    return len([s for s in re.split(r"(?<=[.!?…])\s+", t) if s.strip()])


def compter_mots(t): return len(re.findall(r"\b[\w’'-]+\b", t or "", re.U))


def a_liste(t): return bool(re.search(r"^\s*([-*•]|\d+[.)])\s+", t or "", re.M))


def consigne_respectee(consigne, texte):
    """True/False when the item carries a length or format constraint, None when it carries none."""
    if not consigne: return None
    if "max_phrases" in consigne: return compter_phrases(texte) <= consigne["max_phrases"]
    if "max_mots" in consigne: return compter_mots(texte) <= consigne["max_mots"]
    if consigne.get("format") == "liste": return a_liste(texte)
    return None
