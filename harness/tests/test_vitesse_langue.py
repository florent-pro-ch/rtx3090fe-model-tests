"""The speed pass's English twin (speed-house/v1-en): the French default is byte for byte what it was, the English
prompt goes to vitesse-en.json with its protocol, the prompt actually sent is the one recorded, and both prompts are
pinned by their SHA-256. No GPU, no outside network: a fake OpenAI-compatible server runs in-process."""
import argparse, json, os, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import evalue  # noqa: E402
from commun import sha256_texte  # noqa: E402

RECEIVED = []
# The SHA-256 of the two prompts (UTF-8): any change to either breaks every comparison with the published runs.
SHA_FR = "45ea932658af02b2661bfd03a9465859d8e12c933e4c4875604734c110f27aca"
SHA_EN = "217c51fce2b36db22c9402a0757af64f02673fc8bbf6ba35451052bed3e7fd02"


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        RECEIVED.append(body)
        time.sleep(0.02)  # a real server never answers in 0 s (tok_s divides by the request's seconds)
        if body.get("stream"):
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            self.wfile.write(b"data: " + json.dumps({"choices": [{"delta": {"content": "x"}}]}).encode() + b"\n\ndata: [DONE]\n\n"); return
        b = json.dumps({"choices": [{"message": {"content": "x"}, "finish_reason": "length"}], "usage": {"completion_tokens": 512}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)


@pytest.fixture()
def server():
    RECEIVED.clear()
    s = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}/v1"
    s.shutdown()


def args(out, base, **kw):
    a = dict(candidat="t", base_url=base, model="m", conc=8, out=str(out), gpus=None, energie_periode_s=1.0, repos_s=0,
             prompt_lang="fr", sortie=None)
    a.update(kw); return argparse.Namespace(**a)


def test_both_prompts_are_pinned():
    # methodology/SPEED-PROTOCOL.md quotes both; the French one is measurement material and never changes
    assert evalue.PROMPTS_VITESSE["fr"] == "Rédige un texte suivi d'environ 400 mots sur l'histoire du chemin de fer en Suisse, sans titres."
    assert sha256_texte(evalue.PROMPTS_VITESSE["fr"]) == SHA_FR
    assert sha256_texte(evalue.PROMPTS_VITESSE["en"]) == SHA_EN
    assert evalue.PROTOCOLES_VITESSE == {"fr": "speed-house/v1", "en": "speed-house/v1-en"}


def test_the_methodology_quotes_both_prompts():
    texte = open(os.path.join(os.path.dirname(__file__), "..", "..", "methodology", "SPEED-PROTOCOL.md"), encoding="utf-8").read()
    for p in evalue.PROMPTS_VITESSE.values():
        assert f"> {p}" in texte


def test_by_default_nothing_changes(tmp_path, server):
    evalue.run_vitesse(args(tmp_path, server), {})
    assert set(json.loads((tmp_path / "vitesse.json").read_text())) == {"candidat", "debut", "solo", "agrege", "fin"}
    assert {r["messages"][0]["content"] for r in RECEIVED} == {evalue.PROMPTS_VITESSE["fr"]}
    assert all(r["max_tokens"] == 512 and r["temperature"] == 0 for r in RECEIVED) and len(RECEIVED) == 10
    assert sorted(os.listdir(tmp_path)) == ["vitesse.json"]          # no energy file without --gpus


def test_the_english_twin(tmp_path, server):
    evalue.run_vitesse(args(tmp_path, server, prompt_lang="en"), {"chat_template_kwargs": {"enable_thinking": False}})
    assert not (tmp_path / "vitesse.json").exists()
    v = json.loads((tmp_path / "vitesse-en.json").read_text())
    assert v["protocole"] == "speed-house/v1-en" and v["langue"] == "en" and v["prompt_sha256"] == SHA_EN
    assert {r["messages"][0]["content"] for r in RECEIVED} == {evalue.PROMPTS_VITESSE["en"]}
    assert all(r["chat_template_kwargs"] == {"enable_thinking": False} for r in RECEIVED)


def test_a_second_french_pass_apart(tmp_path, server):
    evalue.run_vitesse(args(tmp_path, server, sortie="vitesse-fr2.json"), {})
    v = json.loads((tmp_path / "vitesse-fr2.json").read_text())
    assert v["protocole"] == "speed-house/v1" and v["langue"] == "fr" and v["prompt_sha256"] == SHA_FR
    assert not (tmp_path / "vitesse.json").exists()


def test_the_output_name_is_a_plain_json_file():
    assert evalue._sortie("vitesse-fr2.json") == "vitesse-fr2.json"
    for bad in ("../vitesse.json", "sub/vitesse.json", "vitesse.txt", ".json", "vitesse-energie.json"):
        with pytest.raises(argparse.ArgumentTypeError): evalue._sortie(bad)


def test_the_energy_file_follows_the_output(tmp_path, server, monkeypatch):
    import energie
    monkeypatch.setattr(energie, "Nvml", lambda: (_ for _ in ()).throw(energie.NvmlErreur("no NVML here")))
    evalue.run_vitesse(args(tmp_path, server, prompt_lang="en", gpus="device=0"), {})
    e = json.loads((tmp_path / "vitesse-en-energie.json").read_text())
    assert e["nvml"]["disponible"] is False and e["langue"] == "en" and e["protocole_vitesse"] == "speed-house/v1-en"
    assert not (tmp_path / "vitesse-energie.json").exists()
