"""energie.py and the speed pass's energy record, without a GPU.

A fake NVML stands in for libnvidia-ml: each card draws a fixed power, and its cumulative energy counter follows the
real clock (optionally in coarse steps, or backwards). A fake OpenAI-compatible server answers the speed pass, and a
compiled stand-in for libnvidia-ml exercises the real ctypes path when a C compiler is present. What is asserted: the
energy of each timed part per card, the fallbacks, that energy is read only when --gpus is given, that vitesse.json
keeps exactly its keys and its start, that the record holds no card identifier and no driver version, and that no
NVML failure, not even a hung call, can stop or alter the speed pass. The fake card identifiers are not UUID-shaped."""
import argparse, json, os, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import energie  # noqa: E402
import evalue  # noqa: E402

SPEED_KEYS = {"candidat", "debut", "solo", "agrege", "fin"}
FAKE_DRIVER = "999.99.99"


class FakeNvml:
    def __init__(self, watts=(300.0, 10.0), memory=(22000, 0), step_s=0.0, backwards=False, fail_energy_after=None,
                 hang_energy_at=None, cards=None):
        self.watts, self.mem = list(watts), list(memory)
        self.step_s = list(step_s) if isinstance(step_s, (list, tuple)) else [step_s] * len(self.watts)
        self.backwards, self.n = backwards, len(self.watts) if cards is None else cards
        self.t0 = time.monotonic(); self.e0 = [1_000_000_000, 50_000_000]
        self.energy_calls, self.fail_after, self.hang_at, self.closed = 0, fail_energy_after, hang_energy_at, False

    def pilote(self): return FAKE_DRIVER  # present on the fake only: the harness must never ask for it
    def nombre(self): return self.n
    def carte(self, i):
        if i >= self.n: raise energie.NvmlErreur("bad index")
        return i
    def energie_mj(self, h):
        self.energy_calls += 1
        if self.hang_at is not None and self.energy_calls == self.hang_at: time.sleep(5)
        if self.fail_after is not None and self.energy_calls > self.fail_after: raise energie.NvmlErreur("GPU is lost")
        t = time.monotonic() - self.t0
        if self.step_s[h]: t = (t // self.step_s[h]) * self.step_s[h]
        return int(self.e0[h] + (-1 if self.backwards else 1) * self.watts[h] * t * 1000)
    def puissance_mw(self, h): return int(self.watts[h] * 1000)
    def temperature_c(self, h): return 60
    def horloge_sm_mhz(self, h): return 1695
    def limite_mw(self, h): return 350000
    def memoire_mib(self, h): return self.mem[h]
    def uuid(self, h): return f"GPU-fake-{h}"
    def nom(self, h): return "NVIDIA GeForce RTX 3090"
    def fermer(self): self.closed = True


def test_gpus_read_like_docker():
    assert energie.lire_gpus("device=0,1") == [0, 1]
    assert energie.lire_gpus('"device=1"') == [1]
    assert energie.lire_gpus("device=0,0") == [0]
    assert energie.lire_gpus("0,1") == [0, 1]
    assert energie.lire_gpus("2") == [0, 1]  # a bare number is a count in docker
    assert energie.lire_gpus("device=GPU-fake-1") == ["GPU-fake-1"]
    for nothing in (None, "", "all", "device=all"): assert energie.lire_gpus(nothing) is None


def test_choice_of_cards():
    m = energie.Mesureur(FakeNvml(memory=(22000, 0)))
    assert m.indices == [0] and "1024" in m.choix
    assert energie.Mesureur(FakeNvml(memory=(21000, 21000))).indices == [0, 1]
    m = energie.Mesureur(FakeNvml(memory=(0, 0)))
    assert m.indices == [0, 1] and "every card" in m.choix
    assert energie.Mesureur(FakeNvml(), choix=[1]).indices == [1]
    assert energie.Mesureur(FakeNvml(), choix=["GPU-fake-1"]).indices == [1]
    with pytest.raises(energie.NvmlErreur): energie.Mesureur(FakeNvml(), choix=[2])
    with pytest.raises(energie.NvmlErreur): energie.Mesureur(FakeNvml(), choix=["GPU-unknown"])
    with pytest.raises(energie.NvmlErreur, match="no card"): energie.Mesureur(FakeNvml(cards=0))
    assert all(set(d) == {"index", "nom", "limite_w", "memoire_mib"} for d in m.description)


def test_an_unmatched_identifier_is_never_written(tmp_path):
    """A --gpus entry given as an identifier that matches no card is reported without its value: that error text goes
    into the record (nvml.raison). The fake identifier is not UUID-shaped, so no scanner flags this file."""
    with pytest.raises(energie.NvmlErreur, match=r"entry 1 \(an identifier"):
        energie.Mesureur(FakeNvml(), choix=["GPU-nomatch-zz"])
    with pytest.raises(energie.NvmlErreur, match="index 2"):
        energie.Mesureur(FakeNvml(), choix=[2])  # an index is still named
    r = energie.Rapport("x", gpus="device=0,GPU-nomatch-zz", ouvrir=lambda: FakeNvml())
    r.ecrire(tmp_path / "e.json")
    raw = (tmp_path / "e.json").read_text()
    doc = json.loads(raw)
    assert doc["nvml"]["disponible"] is False and "no card matches --gpus entry 2" in doc["nvml"]["raison"]
    assert "GPU-" not in raw and "nomatch" not in raw


def test_error_texts_are_cleared_of_identifiers():
    shaped = "GPU-" + "-".join(("0123abcd", "0123", "4567", "89ab", "0123456789ab"))  # built here, not written out
    t = energie._texte_erreur(energie.NvmlErreur(f"lost {shaped} (MIG-{shaped[4:]})"))
    assert "0123abcd" not in t and "89ab" not in t and t.startswith("lost GPU-")
    assert len(energie._texte_erreur("e" * 400)) == 300


def test_energy_of_a_part_from_the_counter():
    m = energie.Mesureur(FakeNvml(watts=(300.0, 10.0)), periode_s=0.05)
    with m.mesurer("solo") as p:
        time.sleep(0.3)
    r = p.resultat
    assert r["source"] == "compteur" and r["desaccord"] is False
    assert r["energie_j"] == pytest.approx(300 * r["duree_s"], rel=0.05)
    assert r["watts_moyens"] == pytest.approx(300, rel=0.05) and r["watts_pic_moyennes_1s"] == 300.0
    c = r["par_gpu"][0]
    assert c["index"] == 0 and c["lectures"] >= 5 and c["mises_a_jour_compteur"] >= 4
    assert c["energie_echantillons_j"] == pytest.approx(c["energie_compteur_j"], rel=0.1)


def test_a_still_or_backward_counter_leaves_the_read_power_to_decide():
    m = energie.Mesureur(FakeNvml(watts=(200.0, 10.0), step_s=60), periode_s=0.05)
    with m.mesurer("solo") as p:
        time.sleep(0.25)
    r = p.resultat
    assert r["source"] == "puissance lue" and r["par_gpu"][0]["compteur_a_bouge"] is False
    assert r["energie_j"] == pytest.approx(200 * r["duree_s"], rel=0.1)
    m = energie.Mesureur(FakeNvml(watts=(200.0, 10.0), backwards=True), periode_s=0.05)
    with m.mesurer("solo") as p:
        time.sleep(0.2)
    c = p.resultat["par_gpu"][0]
    assert c["compteur_recule"] and c["source"] == "puissance lue" and c["energie_j"] > 0


def test_one_card_still_the_other_not_each_its_source():
    m = energie.Mesureur(FakeNvml(watts=(300.0, 100.0), memory=(22000, 22000), step_s=(0, 60)), periode_s=0.05)
    with m.mesurer("agrege") as p:
        time.sleep(0.3)
    r = p.resultat
    assert r["source"] == "mixte"
    c0, c1 = r["par_gpu"]
    assert c0["source"] == "compteur" and c1["source"] == "puissance lue"
    assert r["energie_j"] == pytest.approx(400 * r["duree_s"], rel=0.1)


def test_no_nvml_or_no_card_blocks_nothing(tmp_path):
    with pytest.raises(energie.NvmlErreur): energie.Nvml("libnvidia-ml-absent.so.1")
    def ouvrir(): raise energie.NvmlErreur("cannot load libnvidia-ml.so.1")
    for o, why in ((ouvrir, "cannot load libnvidia-ml.so.1"), (lambda: FakeNvml(cards=0), "NVML sees no card")):
        r = energie.Rapport("x", ouvrir=o)
        r.repos(0.01)
        with r.passage("solo"): pass
        r.tokens("solo", 512)
        r.ecrire(tmp_path / "e.json")
        doc = json.loads((tmp_path / "e.json").read_text())
        assert doc["nvml"] == {"disponible": False, "raison": why} and doc["passages"] == {} and "repos" not in doc


def test_zero_energy_no_total(tmp_path):
    r = energie.Rapport("x", ouvrir=lambda: FakeNvml(watts=(0.0, 0.0)), periode_s=0.05)
    for nom in ("solo", "agrege"):
        with r.passage(nom): time.sleep(0.05)
        r.tokens(nom, 512)
    r.ecrire(tmp_path / "e.json")
    doc = json.loads((tmp_path / "e.json").read_text())
    assert "bilan_solo_et_agrege" not in doc and "tokens_par_joule" not in doc["passages"]["solo"]


def test_a_hung_nvml_call_costs_at_most_its_deadline(tmp_path):
    t = time.monotonic()
    r = energie.Rapport("x", ouvrir=lambda: FakeNvml(hang_energy_at=1), periode_s=0.05, delai_s=0.3)
    for nom in ("solo_flux", "solo", "agrege"):
        with r.passage(nom): time.sleep(0.05)
    r.ecrire(tmp_path / "e.json")
    assert time.monotonic() - t < 2.0
    doc = json.loads((tmp_path / "e.json").read_text())
    assert "took more than 0.3 s" in doc["nvml"]["abandonne"]
    assert all("erreur" in p for p in doc["passages"].values())


def test_minimum_period():
    with pytest.raises(argparse.ArgumentTypeError): evalue._periode("0")
    assert evalue._periode("1") == 1.0
    assert energie.Mesureur(FakeNvml(), periode_s=0).periode_s == energie.PERIODE_MIN_S


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        time.sleep(0.05)
        if body.get("stream"):
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            for k in range(5):
                self.wfile.write(b"data: " + json.dumps({"choices": [{"delta": {"content": f"word{k} "}}]}).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n"); return
        rep = {"choices": [{"message": {"content": "text"}, "finish_reason": "length"}], "usage": {"completion_tokens": 512}}
        b = json.dumps(rep).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)


@pytest.fixture()
def server():
    s = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}/v1"
    s.shutdown()


def args(out, base, **kw):
    a = dict(candidat="t", base_url=base, model="m", conc=8, out=str(out), gpus="device=0", energie_periode_s=0.05, repos_s=0,
             prompt_lang="fr", sortie=None)
    a.update(kw); return argparse.Namespace(**a)


def with_fake(monkeypatch, fake, **kw):
    real = energie.Rapport
    monkeypatch.setattr(energie, "Rapport", lambda *a, **k: real(*a, ouvrir=lambda: fake, **{**k, **kw}))


def test_the_speed_pass_writes_its_energy(tmp_path, server, monkeypatch):
    fake = FakeNvml(watts=(320.0, 9.0), memory=(22000, 0)); with_fake(monkeypatch, fake)
    evalue.run_vitesse(args(tmp_path, server, repos_s=0.1), {})
    v = json.loads((tmp_path / "vitesse.json").read_text())
    assert set(v) == SPEED_KEYS and v["solo"]["completion_tokens"] == 512 and v["agrege"]["ok"] == 8
    raw = (tmp_path / "vitesse-energie.json").read_text()
    e = json.loads(raw)
    assert e["protocole"] == "nvml-energy/v1" and e["nvml"]["disponible"] and e["nvml"]["gpus"][0]["index"] == 0
    assert set(e["nvml"]) == {"disponible", "choix_gpus", "gpus"} and e["nvml"]["choix_gpus"] == "argument --gpus"
    assert "uuid" not in raw and "GPU-fake" not in raw and FAKE_DRIVER not in raw  # no card identifier, no driver
    assert (e["debut"], e["fin"]) == (v["debut"], v["fin"])
    assert e["repos"]["duree_s"] >= 0.1 and e["repos"]["watts_moyens"] == pytest.approx(320, rel=0.1)
    assert set(e["passages"]) == {"solo_flux", "solo", "agrege"}
    assert e["passages"]["solo_flux"]["deltas"] == 5 and "tokens" not in e["passages"]["solo_flux"]
    assert e["passages"]["solo"]["tokens"] == 512 and e["passages"]["agrege"]["tokens"] == 8 * 512
    for nom in ("solo_flux", "solo", "agrege"):
        p = e["passages"][nom]
        assert p["energie_j"] > 0 and p["secondes_requete"] > 0 and p["relance_probable"] is False
    for nom in ("solo", "agrege"):
        p = e["passages"][nom]
        assert p["tokens_par_joule"] == pytest.approx(p["tokens"] / p["energie_j"], rel=1e-3)
    b = e["bilan_solo_et_agrege"]
    assert b["tokens"] == 9 * 512 and b["energie_j"] == pytest.approx(e["passages"]["solo"]["energie_j"] + e["passages"]["agrege"]["energie_j"], abs=0.01)
    assert fake.closed


def test_the_idle_reading_comes_after_the_end(tmp_path, server, monkeypatch):
    """The passes start as they do without energy: the optional idle reading follows `fin`."""
    import datetime as dt
    with_fake(monkeypatch, FakeNvml())
    t = time.time()
    evalue.run_vitesse(args(tmp_path, server, repos_s=1.5), {})
    v = json.loads((tmp_path / "vitesse.json").read_text())
    debut = dt.datetime.strptime(v["debut"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()
    assert debut <= t + 1  # not delayed by the idle reading
    e = json.loads((tmp_path / "vitesse-energie.json").read_text())
    assert e["repos"]["duree_s"] >= 1.5


def test_without_gpus_or_without_the_module_nothing_changes(tmp_path, server, monkeypatch):
    calls = []
    monkeypatch.setattr(energie, "Rapport", lambda *a, **k: calls.append(1))
    evalue.run_vitesse(args(tmp_path, server, gpus=None), {})
    assert set(json.loads((tmp_path / "vitesse.json").read_text())) == SPEED_KEYS
    assert not (tmp_path / "vitesse-energie.json").exists() and calls == []   # no --gpus: NVML is never touched
    monkeypatch.setitem(sys.modules, "energie", None)  # as if energie.py were missing from a hand copy
    os.makedirs(tmp_path / "b")
    evalue.run_vitesse(args(tmp_path / "b", server), {})
    assert set(json.loads((tmp_path / "b" / "vitesse.json").read_text())) == SPEED_KEYS
    assert not (tmp_path / "b" / "vitesse-energie.json").exists()


def test_an_nvml_failure_during_the_pass_does_not_touch_it(tmp_path, server, monkeypatch):
    with_fake(monkeypatch, FakeNvml(fail_energy_after=3))
    evalue.run_vitesse(args(tmp_path, server), {})
    v = json.loads((tmp_path / "vitesse.json").read_text())
    assert set(v) == SPEED_KEYS and v["agrege"]["ok"] == 8
    e = json.loads((tmp_path / "vitesse-energie.json").read_text())
    assert any("erreur" in p for p in e["passages"].values())
    assert "bilan_solo_et_agrege" not in e


def test_a_call_hung_during_the_speed_pass(tmp_path, server, monkeypatch):
    with_fake(monkeypatch, FakeNvml(hang_energy_at=2), delai_s=0.3)
    t = time.monotonic()
    evalue.run_vitesse(args(tmp_path, server), {})
    assert time.monotonic() - t < 4.0
    assert set(json.loads((tmp_path / "vitesse.json").read_text())) == SPEED_KEYS
    assert "abandonne" in json.loads((tmp_path / "vitesse-energie.json").read_text())["nvml"]


def test_gpus_given_on_the_command_line(tmp_path, server, monkeypatch):
    with_fake(monkeypatch, FakeNvml(memory=(22000, 21000)))
    evalue.run_vitesse(args(tmp_path, server, gpus="device=1"), {})
    e = json.loads((tmp_path / "vitesse-energie.json").read_text())
    assert [g["index"] for g in e["nvml"]["gpus"]] == [1] and e["nvml"]["choix_gpus"] == "argument --gpus"


FAKE_NVML_C = r"""
#include <string.h>
typedef struct { unsigned long long total, free, used; } mem_t;
static int idx(void *h) { return (int)(unsigned long)h - 1; }
int nvmlInit_v2(void) { return 0; }
int nvmlShutdown(void) { return 0; }
const char *nvmlErrorString(int c) { return "Invalid Argument"; }
int nvmlDeviceGetCount_v2(unsigned int *c) { *c = 2; return 0; }
int nvmlDeviceGetHandleByIndex_v2(unsigned int i, void **h) { if (i >= 2) return 2; *h = (void *)(unsigned long)(i + 1); return 0; }
int nvmlDeviceGetTotalEnergyConsumption(void *h, unsigned long long *e) { *e = 5000000000ULL + idx(h); return 0; }
int nvmlDeviceGetPowerUsage(void *h, unsigned int *p) { *p = idx(h) == 0 ? 321000 : 9000; return 0; }
int nvmlDeviceGetTemperature(void *h, int s, unsigned int *t) { if (s != 0) return 2; *t = 61; return 0; }
int nvmlDeviceGetClockInfo(void *h, int c, unsigned int *m) { if (c != 1) return 2; *m = 1695; return 0; }
int nvmlDeviceGetEnforcedPowerLimit(void *h, unsigned int *p) { *p = 350000; return 0; }
int nvmlDeviceGetMemoryInfo(void *h, mem_t *m) { m->total = 25769803776ULL; m->used = idx(h) == 0 ? 23085449216ULL : 0; m->free = m->total - m->used; return 0; }
int nvmlDeviceGetUUID(void *h, char *b, unsigned int l) { strncpy(b, idx(h) == 0 ? "GPU-aaaa" : "GPU-bbbb", l); return 0; }
int nvmlDeviceGetName(void *h, char *b, unsigned int l) { strncpy(b, "NVIDIA GeForce RTX 3090", l); return 0; }
"""


def test_the_ctypes_path_against_a_compiled_library(tmp_path):
    """The real Nvml class, behind its deadline, against a compiled stand-in for libnvidia-ml: argument types, the
    64-bit counter, the enums, the error string."""
    import shutil, subprocess
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if not cc: pytest.skip("no C compiler")
    src = tmp_path / "fake_nvml.c"; src.write_text(FAKE_NVML_C)
    lib = tmp_path / ("libfakenvml" + (".dylib" if sys.platform == "darwin" else ".so"))
    subprocess.run([cc, "-shared", "-fPIC", "-o", str(lib), str(src)], check=True, capture_output=True)
    nv = energie.Borne(energie.Nvml(str(lib)))
    assert nv.nombre() == 2
    h0, h1 = nv.carte(0), nv.carte(1)
    assert nv.energie_mj(h0) == 5_000_000_000 and nv.energie_mj(h1) == 5_000_000_001
    assert nv.puissance_mw(h0) == 321000 and nv.temperature_c(h0) == 61 and nv.horloge_sm_mhz(h0) == 1695
    assert nv.limite_mw(h0) == 350000 and nv.memoire_mib(h0) == 22016 and nv.memoire_mib(h1) == 0
    assert nv.uuid(h0) == "GPU-aaaa" and nv.nom(h1) == "NVIDIA GeForce RTX 3090"
    with pytest.raises(energie.NvmlErreur, match="Invalid Argument"): nv.carte(5)
    with pytest.raises(AttributeError): nv.pilote  # the driver version is never read
    m = energie.Mesureur(nv, periode_s=0.05)
    assert m.indices == [0] and m.description[0]["limite_w"] == 350.0 and "uuid" not in m.description[0]
    assert energie.Mesureur(nv, choix=["GPU-bbbb"]).indices == [1]
    with m.mesurer("solo") as p:
        time.sleep(0.1)
    assert p.resultat["source"] == "puissance lue" and p.resultat["watts_pic_moyennes_1s"] == 321.0
    nv.fermer()
