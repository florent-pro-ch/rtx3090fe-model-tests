#!/usr/bin/env python3
"""Energy of a speed pass, read from the cards' own counters through NVIDIA's management library (NVML).

English summary. Opt-in: `evalue.py --mode vitesse --gpus device=0` (or `device=0,1`, `0,1`, a card count, or
`all` for every card holding 1 GiB or more) loads this module and writes, beside vitesse.json, vitesse-energie.json
(vitesse-en-energie.json for the English twin, and so on: the speed file's name with -energie). Without --gpus
nothing here runs and the speed pass is exactly what it was. Standard library only (ctypes); Linux with the NVIDIA
driver. Use it only on the machine that serves the model: NVML reads the cards of the machine the harness runs on,
and a client pointed at a remote server would measure its own cards. Nothing here changes a GPU setting.

At the start and end of each timed part of the speed pass (solo_flux: the streamed request that gives the time to
first token; solo: the single request; agrege: the eight requests at once) it reads NVML's cumulative energy counter
(nvmlDeviceGetTotalEnergyConsumption, mJ since the driver loaded) of the chosen cards; the part's energy is the
difference. A light reading in the same process (once a second by default) takes board power
(nvmlDeviceGetPowerUsage, the driver's ~1 s average) and the counter again: the peak of those 1 s averages, a second
energy figure (the integral of the read power) as a check, and how often the counter actually moves on these cards.
No sampler process, no nvidia-smi call. Every counter read sits outside the request timings, so the speed figures
are measured as before.

Per card, the counter decides when it moved forward during the part; when it did not move, or went backwards (a
driver reload), that card's read power decides, and the record says which (`source`). Where NVML cannot be loaded
(macOS, a host without the driver, a test) the record says so and the speed pass runs unchanged. Every NVML call has
a deadline: a hung driver costs the speed pass at most that long once, then the measurement is dropped. Nothing here
can stop a speed pass.

What it counts: the GPU boards of the chosen cards, summed; not the CPU, the RAM or the power supplies, so a model
kept partly in system RAM looks more efficient than the machine is. The counter is read at the start and end of each
part, so how often it updates matters little: pas_min_compteur_j is the smallest rise between two successive readings
of a part (one reading interval of the card's energy, about a second's worth), an upper bound on the counter's
resolution, not the resolution itself; on the lab's cards the counter rose between almost every pair of readings. The
record never holds a card identifier (UUID) or the driver version: a --gpus entry given as an identifier is never
repeated in an error text, and every error text written is cleared of anything shaped like one.

The record's keys are French, as in the lab; the published energy*.json evidence carries the same figures under
English keys, every one of them listed here (a key the same in both languages is listed as is).
Top level: protocole = protocol, protocole_vitesse = speed_protocol, langue = prompt_lang, debut / fin =
started_at / ended_at, periode_s = period_s; nvml.disponible = nvml_available and nvml.gpus = gpus (index,
nom = name, limite_w = power_limit_w, memoire_mib = memory_used_mib_at_start), both moved to the top level;
nvml.abandonne = nvml_stopped (true; its text is not copied).
passages = passes (solo_flux = solo_stream, solo, agrege = aggregate; a part whose read failed, erreur, becomes
measured: false), each with duree_s = duration_s, energie_j = energy_j, source, watts_moyens = mean_w,
watts_pic_moyennes_1s = peak_w_1s (highest 1 s average, summed over the cards), desaccord =
counter_readings_disagree (counter and read power differ by more than 15 % on a card), relance_probable =
restart_likely, secondes_requete = request_s, tokens, tokens_par_joule = tokens_per_j, joules_par_token =
j_per_token, deltas, conc = concurrency, ok, and par_gpu = per_gpu (index, energie_j = energy_j, source,
energie_compteur_j = counter_energy_j, energie_echantillons_j = readings_energy_j, lectures = readings,
mises_a_jour_compteur = counter_updates, pas_min_compteur_j = counter_step_min_j, p_pic_w = peak_w,
ecart_compteur_lectures = counter_vs_readings, desaccord = counter_readings_disagree, compteur_a_bouge =
counter_moved, compteur_recule = counter_went_back, debut / fin = start / end, each with temperature_c and
sm_mhz = sm_clock_mhz). Values of source: compteur / puissance lue / mixte = counter / power-readings / mixed.
bilan_solo_et_agrege = total_solo_and_aggregate (tokens, energie_j = energy_j, tokens_par_joule = tokens_per_j,
joules_par_token = j_per_token).
Never published: candidat, nvml.choix_gpus, nvml.raison, repos, bilan_erreur and every error text.
See also ../GLOSSARY.md."""
import ctypes, json, re, threading, time

NVML_TEMPERATURE_GPU = 0
NVML_CLOCK_SM = 1
SEUIL_CHARGEE_MIB = 1024      # a card holding this much memory or more is "loaded" (for --gpus all)
PERIODE_MIN_S = 0.05          # shortest period between two light readings
DELAI_APPEL_S = 2.0           # deadline of every NVML call
SEUIL_DESACCORD = 0.15        # counter and read power disagree beyond this share


class NvmlErreur(Exception):
    pass


# anything shaped like a card identifier (GPU-/MIG- followed by hex groups), cleared from every error text written
_IDENTIFIANT = re.compile(r"(?i)\b(?:GPU|MIG)-[0-9a-f][0-9a-f-]{7,}")


def _texte_erreur(e):
    """An error text fit for the record: at most 300 characters, never a card identifier."""
    return _IDENTIFIANT.sub("GPU-…", str(e))[:300]


class _Memoire(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("used", ctypes.c_ulonglong)]


class Nvml:
    """The few NVML calls the speed pass needs, through ctypes. Same interface as the fakes used by the tests."""

    def __init__(self, bibliotheque="libnvidia-ml.so.1"):
        try:
            self._lib = ctypes.CDLL(bibliotheque)
        except OSError as e:
            raise NvmlErreur(f"cannot load {bibliotheque}: {e}")
        self._ok(self._lib.nvmlInit_v2(), "nvmlInit_v2")

    def _ok(self, code, appel):
        if code != 0:
            try:
                f = self._lib.nvmlErrorString; f.restype = ctypes.c_char_p; msg = f(code).decode()
            except Exception:
                msg = "?"
            raise NvmlErreur(f"{appel}: NVML error {code} ({msg})")

    def _uint(self, fn, *args):
        v = ctypes.c_uint(); self._ok(getattr(self._lib, fn)(*args, ctypes.byref(v)), fn); return v.value

    def _texte(self, fn, *args, n=96):
        b = ctypes.create_string_buffer(n); self._ok(getattr(self._lib, fn)(*args, b, ctypes.c_uint(n)), fn); return b.value.decode()

    def nombre(self):
        return self._uint("nvmlDeviceGetCount_v2")

    def carte(self, index):
        h = ctypes.c_void_p()
        self._ok(self._lib.nvmlDeviceGetHandleByIndex_v2(ctypes.c_uint(index), ctypes.byref(h)), "nvmlDeviceGetHandleByIndex_v2")
        return h

    def energie_mj(self, h):
        v = ctypes.c_ulonglong()
        self._ok(self._lib.nvmlDeviceGetTotalEnergyConsumption(h, ctypes.byref(v)), "nvmlDeviceGetTotalEnergyConsumption")
        return v.value

    def puissance_mw(self, h):
        return self._uint("nvmlDeviceGetPowerUsage", h)

    def temperature_c(self, h):
        return self._uint("nvmlDeviceGetTemperature", h, ctypes.c_int(NVML_TEMPERATURE_GPU))

    def horloge_sm_mhz(self, h):
        return self._uint("nvmlDeviceGetClockInfo", h, ctypes.c_int(NVML_CLOCK_SM))

    def limite_mw(self, h):
        return self._uint("nvmlDeviceGetEnforcedPowerLimit", h)

    def memoire_mib(self, h):
        m = _Memoire(); self._ok(self._lib.nvmlDeviceGetMemoryInfo(h, ctypes.byref(m)), "nvmlDeviceGetMemoryInfo")
        return m.used // (1024 * 1024)

    def uuid(self, h):
        """Read only to match a card given by its identifier on the command line; never written."""
        return self._texte("nvmlDeviceGetUUID", h)

    def nom(self, h):
        return self._texte("nvmlDeviceGetName", h)

    def fermer(self):
        try: self._lib.nvmlShutdown()
        except Exception: pass


class Borne:
    """Puts a deadline on every NVML call. After one call overruns, every later call fails at once: a hung driver
    costs the speed pass `delai_s` once, never more."""

    METHODES = ("nombre", "carte", "energie_mj", "puissance_mw", "temperature_c", "horloge_sm_mhz", "limite_mw",
                "memoire_mib", "uuid", "nom", "fermer")

    def __init__(self, nvml, delai_s=DELAI_APPEL_S):
        self._nv, self.delai_s, self.mort = nvml, delai_s, None

    def __getattr__(self, nom):
        if nom not in Borne.METHODES: raise AttributeError(nom)
        return lambda *args: self._appel(nom, *args)

    def _appel(self, nom, *args):
        if self.mort: raise NvmlErreur(f"NVML dropped earlier: {self.mort}")
        sortie = {}
        def f():
            try: sortie["v"] = getattr(self._nv, nom)(*args)
            except BaseException as e: sortie["e"] = e
        t = threading.Thread(target=f, daemon=True); t.start(); t.join(self.delai_s)
        if t.is_alive():
            self.mort = f"{nom} took more than {self.delai_s} s"
            raise NvmlErreur(self.mort)
        if "e" in sortie: raise sortie["e"]
        return sortie.get("v")


def lire_gpus(texte):
    """--gpus as docker's --gpus takes it: 'device=0,1' (indices) or 'device=GPU-<uuid>,...'; a bare number is a count,
    as in docker ('2': the first two cards); 'all', 'device=all' or empty: no choice (the cards holding 1 GiB or more)."""
    if texte is None: return None
    t = str(texte).strip().strip('"').strip("'")
    if t in ("", "all", "device=all"): return None
    if not t.startswith("device=") and t.isdigit(): return list(range(int(t)))
    if t.startswith("device="): t = t[len("device="):]
    out = []
    for x in (y.strip() for y in t.split(",")):
        if not x: continue
        v = int(x) if x.isdigit() else x
        if v not in out: out.append(v)
    return out


def _sur(fn, *args):
    try: return fn(*args)
    except Exception: return None


def _w(mw):
    return None if mw is None else round(mw / 1000.0, 1)


class Mesureur:
    """Reads the counters of the chosen cards around each timed part; reads their power and counter lightly meanwhile."""

    def __init__(self, nvml, choix=None, periode_s=1.0, horloge=time.monotonic, dormir=time.sleep):
        self.nvml, self.periode_s, self.horloge, self.dormir = nvml, max(PERIODE_MIN_S, periode_s), horloge, dormir
        tous = list(range(nvml.nombre()))
        if not tous: raise NvmlErreur("NVML sees no card")
        cartes = {i: nvml.carte(i) for i in tous}
        memoire = {i: _sur(nvml.memoire_mib, cartes[i]) for i in tous}
        if choix is not None:
            ids = {i: _sur(nvml.uuid, cartes[i]) for i in tous} if any(not isinstance(c, int) for c in choix) else {}
            indices = []
            for n, c in enumerate(choix, 1):
                i = c if isinstance(c, int) else next((k for k, u in ids.items() if u == c), None)
                if i is None or i not in cartes:
                    # an identifier given on the command line is never repeated: this text goes into the record
                    quoi = f"index {c}" if isinstance(c, int) else f"entry {n} (an identifier, not repeated here)"
                    raise NvmlErreur(f"no card matches --gpus {quoi} (this machine has {len(tous)})")
                if i not in indices: indices.append(i)
            self.indices, self.choix = sorted(indices), "argument --gpus"
        else:
            charge = [i for i in tous if (memoire[i] or 0) >= SEUIL_CHARGEE_MIB]
            self.indices, self.choix = (charge, f"cards with {SEUIL_CHARGEE_MIB} MiB or more") if charge else (tous, "no card loaded: every card")
        if not self.indices: raise NvmlErreur("no card chosen")
        self.cartes = [cartes[i] for i in self.indices]
        # what the record says about each card: no identifier, no driver version
        self.description = [{"index": i, "nom": _sur(nvml.nom, h), "limite_w": _w(_sur(nvml.limite_mw, h)),
                             "memoire_mib": memoire[i]} for i, h in zip(self.indices, self.cartes)]

    def _compteurs(self):
        return [self.nvml.energie_mj(h) for h in self.cartes]

    def _etat(self):
        return [{"temperature_c": _sur(self.nvml.temperature_c, h), "sm_mhz": _sur(self.nvml.horloge_sm_mhz, h)} for h in self.cartes]

    def mesurer(self, nom):
        return _Passage(self, nom)

    def repos(self, duree_s):
        """The loaded card at rest (model resident, no request), read after the passes."""
        with self.mesurer("repos") as p:
            self.dormir(duree_s)
        return p.resultat


class _Passage:
    def __init__(self, m, nom):
        self.m, self.nom, self.resultat, self._ech, self._stop = m, nom, None, [], threading.Event()

    def _lecture(self):
        t = self.m.horloge()
        return (t, [_w(_sur(self.m.nvml.puissance_mw, h)) for h in self.m.cartes], [_sur(self.m.nvml.energie_mj, h) for h in self.m.cartes])

    def _sonde(self):
        while not self._stop.wait(self.m.periode_s):
            self._ech.append(self._lecture())

    def __enter__(self):
        self._etat0 = self.m._etat()
        self._e0 = self.m._compteurs(); self._t0 = self.m.horloge()
        self._ech.append((self._t0, [_w(_sur(self.m.nvml.puissance_mw, h)) for h in self.m.cartes], list(self._e0)))
        self._fil = threading.Thread(target=self._sonde, daemon=True); self._fil.start()
        return self

    def __exit__(self, typ, val, tb):
        self._stop.set(); self._fil.join(timeout=DELAI_APPEL_S * 3)
        e1 = self.m._compteurs(); t1 = self.m.horloge()
        self._ech.append((t1, [_w(_sur(self.m.nvml.puissance_mw, h)) for h in self.m.cartes], list(e1)))
        duree = t1 - self._t0
        etat1 = self.m._etat()
        par, sources = [], set()
        for k, i in enumerate(self.m.indices):
            pts = [(t, w[k]) for t, w, _ in self._ech if w[k] is not None]
            integre = sum((b[0] - a[0]) * (a[1] + b[1]) / 2 for a, b in zip(pts, pts[1:])) if len(pts) > 1 else None
            diff = (e1[k] - self._e0[k]) / 1000.0
            compteurs = [c[k] for _, _, c in self._ech if c[k] is not None]
            pas = [b - a for a, b in zip(compteurs, compteurs[1:]) if b > a]
            carte = {"index": i, "energie_compteur_j": round(diff, 3), "compteur_a_bouge": diff > 0, "compteur_recule": diff < 0,
                     "energie_echantillons_j": round(integre, 3) if integre is not None else None,
                     "lectures": len(pts), "mises_a_jour_compteur": len(pas), "pas_min_compteur_j": round(min(pas) / 1000.0, 3) if pas else None,
                     "p_pic_w": max((w for _, w in pts), default=None), "debut": self._etat0[k], "fin": etat1[k]}
            if diff > 0 or integre is None:
                carte.update({"energie_j": round(max(diff, 0.0), 3), "source": "compteur"})
            else:
                carte.update({"energie_j": round(integre, 3), "source": "puissance lue"})
            if diff > 0 and integre:
                carte["ecart_compteur_lectures"] = round((diff - integre) / integre, 3)
                carte["desaccord"] = abs(carte["ecart_compteur_lectures"]) > SEUIL_DESACCORD
            sources.add(carte["source"]); par.append(carte)
        e = sum(c["energie_j"] for c in par)
        somme = {}
        for t, w, _ in self._ech:
            if all(x is not None for x in w): somme[t] = sum(w)
        self.resultat = {"duree_s": round(duree, 3), "energie_j": round(e, 3),
                         "source": sources.pop() if len(sources) == 1 else "mixte",
                         "watts_moyens": round(e / duree, 1) if duree > 0 else None,
                         "watts_pic_moyennes_1s": max(somme.values(), default=None),
                         "desaccord": any(c.get("desaccord") for c in par), "par_gpu": par}
        return False


class Rapport:
    """What the speed pass writes beside its speed file. Never raises into the speed pass."""

    def __init__(self, candidat, gpus=None, periode_s=1.0, ouvrir=Nvml, delai_s=DELAI_APPEL_S, **mesureur_kw):
        self.doc = {"candidat": candidat, "protocole": "nvml-energy/v1", "periode_s": max(PERIODE_MIN_S, periode_s), "passages": {}}
        self.m, self.borne = None, None
        try:
            self.borne = Borne(_ouvrir_borne(ouvrir, delai_s), delai_s)
            self.m = Mesureur(self.borne, lire_gpus(gpus), periode_s=periode_s, **mesureur_kw)
            self.doc["nvml"] = {"disponible": True, "choix_gpus": self.m.choix, "gpus": self.m.description}
        except Exception as e:
            self.m = None
            self.doc["nvml"] = {"disponible": False, "raison": _texte_erreur(e)}

    def repos(self, duree_s):
        if self.m is None or not duree_s: return
        try: self.doc["repos"] = self.m.repos(duree_s)
        except Exception as e: self.doc["repos"] = {"erreur": _texte_erreur(e)}

    def passage(self, nom):
        return _Garde(self, nom)

    def annoter(self, nom, **champs):
        try:
            p = self.doc["passages"].get(nom)
            if p is None: return
            p.update({k: v for k, v in champs.items() if v is not None})
            if "secondes_requete" in champs and "duree_s" in p and champs["secondes_requete"] is not None:
                p["relance_probable"] = p["duree_s"] - champs["secondes_requete"] > 1.5
        except Exception:
            pass

    def tokens(self, nom, n):
        try:
            p = self.doc["passages"].get(nom)
            if p is None or "energie_j" not in p or not n: return
            p["tokens"] = n
            if p["energie_j"] > 0:
                p["tokens_par_joule"] = round(n / p["energie_j"], 4); p["joules_par_token"] = round(p["energie_j"] / n, 4)
        except Exception:
            pass

    def bilan(self):
        ps = [self.doc["passages"].get(k) for k in ("solo", "agrege")]
        if all(p and p.get("tokens") and p.get("energie_j") for p in ps):
            tok, e = sum(p["tokens"] for p in ps), sum(p["energie_j"] for p in ps)
            if e > 0:
                self.doc["bilan_solo_et_agrege"] = {"tokens": tok, "energie_j": round(e, 3), "tokens_par_joule": round(tok / e, 4),
                                                    "joules_par_token": round(e / tok, 4)}

    def ecrire(self, chemin):
        try: self.bilan()
        except Exception as e: self.doc["bilan_erreur"] = _texte_erreur(e)
        if self.borne is not None and self.borne.mort: self.doc["nvml"]["abandonne"] = _texte_erreur(self.borne.mort)
        elif self.borne is not None: _sur(self.borne.fermer)
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(self.doc, f, ensure_ascii=False, indent=1); f.write("\n")


def _ouvrir_borne(ouvrir, delai_s):
    """Opens NVML under the same deadline as every later call."""
    sortie = {}
    def f():
        try: sortie["v"] = ouvrir()
        except BaseException as e: sortie["e"] = e
    t = threading.Thread(target=f, daemon=True); t.start(); t.join(delai_s)
    if t.is_alive(): raise NvmlErreur(f"NVML init took more than {delai_s} s")
    if "e" in sortie: raise sortie["e"]
    return sortie["v"]


class _Garde:
    """A timed part under measurement; a failing NVML read is recorded and the part goes on unmeasured."""

    def __init__(self, rapport, nom):
        self.r, self.nom, self.p = rapport, nom, None

    def __enter__(self):
        if self.r.m is not None:
            try:
                self.p = self.r.m.mesurer(self.nom); self.p.__enter__()
            except Exception as e:
                self.p = None; self.r.doc["passages"][self.nom] = {"erreur": _texte_erreur(e)}
        return self

    def __exit__(self, typ, val, tb):
        if self.p is not None:
            try:
                self.p.__exit__(typ, val, tb); self.r.doc["passages"][self.nom] = self.p.resultat
            except Exception as e:
                self.r.doc["passages"][self.nom] = {"erreur": _texte_erreur(e)}
        return False
