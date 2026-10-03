# The house speed protocol

Every throughput figure in this repository either comes from the protocol
below (`protocol: "speed-house/v1"` in a run record) or says which other
protocol produced it.
It is deliberately simple: one prompt, one solo request, then eight requests
at once, against the model exactly as it is served for the quality benches.
The speed pass itself is `harness/evalue.py --mode vitesse` ([harness/](../harness/)); the lab's
launcher, which starts the server and reads the GPUs (steps 1 to 4 and 7 below), is not published.
This page describes every step.

## What happens in one run

1. **Snapshot before start.** `nvidia-smi` records each GPU's memory and
   temperature (`nvidia-smi-avant`).
2. **Start.** The container is started with the exact command recorded in the
   run's launch file. A clock starts.
3. **Ready.** The harness polls the server's OpenAI-compatible model list every
   five seconds. The first successful answer stops the clock: that is the
   **ready time** (`pret-en-secondes.txt`). If the server never answers, the
   run ends as a start failure and its engine log is kept.
4. **Loaded snapshot.** Three seconds after ready (five seconds in the two
   2026-09-04 campaigns), before the first request, `nvidia-smi` records
   memory again (`nvidia-smi-charge`). This is the VRAM figure of the run: an
   after-load snapshot; for vLLM a reservation. It is not a peak.
5. **Quality benches**, if the run has any (see
   [METHODOLOGY.md](METHODOLOGY.md)).
6. **Speed pass** (below), on the same server, after the benches.
7. **Snapshot after**, then the container is stopped and removed.

## The speed pass

One fixed French prompt, sent as a single user message with no system
prompt. It is measurement material and stays in French (`lang: "fr"`):

<!-- lang: fr -->
> Rédige un texte suivi d'environ 400 mots sur l'histoire du chemin de fer en Suisse, sans titres.
<!-- /lang -->

(It asks for a continuous text of about four hundred words on the history of
the railway in Switzerland, without headings.)

Every request uses **temperature 0** and **at most 512 completion tokens**,
plus the model's own request options from the registry (typically
`enable_thinking: false` for models with a reasoning mode). A model may stop
before 512 tokens; the counts below are the tokens it actually produced.

- **Solo, time to first token.** One **streaming** request. TTFT is the time
  from sending it to the first streamed delta that carries content or
  reasoning text, measured by the client. → `solo.ttft_ms`
- **Solo, tokens per second.** One **non-streaming** request with the same
  prompt. `solo.tok_s` = completion tokens ÷ the request's wall-clock time. The
  wall time includes the (short) prefill, so this is end-to-end speed for one
  user, slightly below a pure decode rate.
- **Aggregate.** **Eight identical requests sent at the same moment** from
  eight threads. `agrege.agg_tok_s` = the sum of their completion tokens ÷ the
  wall time from the first send to the last answer. `p50_latency_s` is the
  median wall time of one request in that batch, and `ok` how many of the eight
  succeeded.

The result is written as `vitesse.json`; [GLOSSARY.md](../GLOSSARY.md) maps its
French keys.

### What the numbers mean, and what they do not

- **`solo.tok_s`** is what one user feels while a long answer streams.
- **`agg_tok_s` at concurrency 8** is what the server delivers when it is
  busy, and it depends on how many requests the server may decode at once.
  vLLM batches up to `max_num_seqs` sequences, so its aggregate is several
  times the solo figure. llama.cpp decodes at most one request per **slot**
  (`-np`, `engine_args.parallel_slots` in the run record). On a server
  started with **one slot** (`-np 1`, as most llama.cpp runs here were), the
  eight requests are served one after another: the aggregate is **serialised
  single-stream speed**, close to the solo figure, and **is not a
  concurrency measurement**. It says nothing about whether llama.cpp can
  batch: the llama.cpp runs started with 4 or 8 slots do batch.
- **How the slot count is shown.** Every aggregate figure on the site carries
  the slot count of its run: "1 slot (serialised)" for a one-slot llama.cpp
  server, "N slots" for more, "N sequences at once" for vLLM (its
  `max_num_seqs`), and "slots not recorded" when the launch line does not
  say. Compare two aggregates only when both servers could take the eight
  requests at once.
- **TTFT** is mostly prefill, and the prompt is short. It says how quickly a
  server starts answering a short question, not how it handles a long
  context. The same prompt is sent every time, so an engine with prefix
  caching can reuse its prefill from one request to the next.
- **Ready time** has a resolution of five seconds and includes everything
  between `docker run` and a usable endpoint: loading weights, compiling
  kernels, capturing CUDA graphs. A first start that compiles into an empty
  cache is slower than later starts that reuse it. A ready time measured with
  extra debug logging switched on (some A/B campaigns) is not comparable with
  the others; the run says so.
- **VRAM.** The figure is an after-load snapshot (nvidia-smi a few seconds
  after the server is ready, before the first request: step 4); for vLLM a
  reservation. vLLM
  pre-allocates the KV cache to fill the share of the card set by
  `--gpu-memory-utilization`, so a 3B model can show almost the whole card:
  that is not what the model needs (`vram.kind: "reserved"`). Other engines,
  such as llama.cpp, show the weights and what they allocate at start for
  their configured context (`vram.kind: "after-load"`). Neither is a peak
  under load: memory is not sampled while requests run. Run records give one
  figure per GPU.
- **One prompt, one language.** The speed of a model on English text, on code,
  or on a long document can differ, and with speculative decoding the
  language changes the result a lot. The house protocol has no English
  reference speed; the only English figures are those of the
  speculative-decoding protocol (below), which reports French and English
  apart.
- **One pass.** The house protocol runs once per run, with no repetition and
  no interval. Run-to-run noise was measured where a campaign repeated the pass
  (see below): within an arm the three repeated passes of the
  mixture-of-experts NVLink campaign stayed within about 2 % of each other
  ([data/runs/2026-09-13-nvlink-ab-moe/](../data/runs/2026-09-13-nvlink-ab-moe/)).
- **No power.** Board power was never sampled during generation. A few GPU
  snapshots record it before the start or just after loading, which says
  nothing about power under load. There is no tokens-per-joule figure and no
  power-limit sweep in this repository.

## Other speed protocols

Some campaigns needed more than one pass or a different load. They record
their own `protocol` and are never mixed into a house-protocol table without
saying so:

- **NVLink A/B** ([TOPOLOGY.md](TOPOLOGY.md#does-the-nvlink-bridge-matter)):
  the house pass, once per arm for the dense model and **three times per arm**
  in the same container for the mixture-of-experts model.
- **Speculative decoding** (`spec-ab/v1`): a frozen prompt set identified by its
  hash, French and English apart, an identity check against the base model,
  draft acceptance from the engine's counters, and throughput at
  concurrency 1, 4 and 8 with prefix caching off.
- **Draft-head A/B** (an earlier speculative-decoding probe): repeated house
  passes per arm plus the engine's speculation metrics.
- **Agent loop** (mode 8): bench time per task and per run, not tokens per
  second.

## Reproducing a figure

The run record gives the engine image and tag, the topology and the parsed
engine arguments (context length, `max-num-seqs`, KV cache type,
`gpu-memory-utilization`, slots). The launch file in the evidence folder is
the command as it ran, with machine-specific parts (container name, host
port, host paths) replaced by placeholders such as `$MODELS`. Serve the same
weights with the same command, then send the prompt above with the same
options.
