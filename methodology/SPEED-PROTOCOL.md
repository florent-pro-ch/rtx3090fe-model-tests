# The house speed protocol

Every throughput figure in this repository either comes from the protocol
below (`protocol: "speed-house/v1"` in a run record; its English twin sits in
the same record's `en_*` keys) or says which other protocol produced it.
It is deliberately simple: one prompt (French; since 2026-10-03 also its
English twin, measured apart), one solo request, then eight requests
at once, against the model exactly as it is served for the quality benches.
The speed pass itself, with its energy record, is `harness/evalue.py --mode vitesse` and
`harness/energie.py` ([harness/](../harness/)); the lab's launcher, which starts the server,
takes the nvidia-smi snapshots (steps 1 to 4 and 7 below) and, on 2026-10-03, sent a warm-up
request, is not published.
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
   2026-09-04 campaigns and in the 2026-10-03 speed campaign), before the
   first request, `nvidia-smi` records
   memory again (`nvidia-smi-charge`). This is the VRAM figure of the run: an
   after-load snapshot; for vLLM a reservation. It is not a peak.
5. **Quality benches**, if the run has any (see
   [METHODOLOGY.md](METHODOLOGY.md)).
6. **Speed pass** (below), on the same server, after the benches.
7. **Snapshot after**, then the container is stopped and removed.

The 2026-10-03 speed campaign ran no bench. After the loaded snapshot it sent
one discarded warm-up request ("Say OK.", at most 8 tokens, the same request
options), so that the first measured request was not the server's first, then
ran the French pass, the English pass and the French pass again on the same
server.

## The speed pass

One fixed French prompt, sent as a single user message with no system
prompt. It is measurement material and stays in French (`lang: "fr"`):

<!-- lang: fr -->
> Rédige un texte suivi d'environ 400 mots sur l'histoire du chemin de fer en Suisse, sans titres.
<!-- /lang -->

(It asks for a continuous text of about four hundred words on the history of
the railway in Switzerland, without headings.)

**The English twin** (`speed-house/v1-en`, since 2026-10-03) sends this
rendering of the prompt instead, everything else unchanged:

> Write a continuous text of about 400 words on the history of the railway in Switzerland, without headings.

It is a second instrument with its own protocol name, measured beside the
French pass on the same server; it replaces nothing, and no French figure is
converted into an English one.

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

The result is written as `vitesse.json` (the English twin's as
`vitesse-en.json`, the repeated French pass as `vitesse-fr2.json`); a run
record carries the English figures in its `en_*` keys and the repeat in its
`fr2_*` keys, and the energy of each pass is published as `energy.json`
(`energy-en.json`, `energy-fr2.json`). [GLOSSARY.md](../GLOSSARY.md) maps the
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
  caching can reuse its prefill from one request to the next. In the
  2026-10-03 campaign the first French pass, which followed a warm-up
  request, had a higher time to first token than the English pass on all 18
  rows and than the second French pass on 17: a TTFT depends on what the
  server answered just before. The headline TTFT is that first French
  pass's.
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
- **Two languages, measured apart.** The speed of a model on English text,
  on code or on a long document can differ, and with speculative decoding
  the language changes the result a lot (its protocol, below, reports French
  and English apart). Without speculation, the 2026-10-03 campaign measured
  French, English and French again on 18 rows of the one-card and pair
  pages. A language difference was called only where the English figure
  differed from the French one by more than twice the gap between the two
  French passes and by more than 3 %, a rule fixed before the first pass. By
  that rule there was none on 15 rows. On the other three (Gemma 4 26B-A4B
  at eight requests, on one card and on the pair; Spark-X2.5-4B, single
  stream and at eight) English answers stopped before the 512-token cap that
  every French answer reached (at eight requests, some or all of the eight),
  so language and answer length are not separated there. Since 2026-10-04,
  model-watch runs take the English twin after their French pass, on the same
  server, with no second French pass, so no language
  difference is called or ruled out for them. The other headline rows, and
  every run measured before 2026-10-03, have French figures only under this
  protocol.
- **One pass.** The house protocol runs once per run, with no repetition and
  no interval. Run-to-run noise was measured where a campaign repeated the pass
  (see below): within an arm the three repeated passes of the
  mixture-of-experts NVLink campaign stayed within about 2 % of each other
  ([data/runs/2026-09-13-nvlink-ab-moe/](../data/runs/2026-09-13-nvlink-ab-moe/)).
  In the 2026-10-03 campaign the French pass, repeated after the English one
  on the same server, stayed within 0.7 % in single-stream speed and 0.9 %
  at eight requests on all 18 rows; the repeat measures the session's drift,
  and the headline is the first French pass.
- **Energy, on the cards only.** Board power was never sampled during
  generation before 2026-10-03. Since then each speed pass reads, for every
  card the model uses, NVIDIA's cumulative energy counter (NVML) at the start
  and end of each timed part, and board power once a second in the same
  process (`nvml-energy/v1`). Energy per token is that energy divided by the
  tokens produced, shown as tokens per joule; it covers the whole request,
  prefill included, and the GPU boards only, not the CPU, the RAM or the
  power supplies, so a run that keeps part of the model in system RAM
  (`ram_spill: true`) looks more efficient than the machine is. The
  counter's resolution is not a limit here: in the 2026-10-03 campaign it
  rose between almost every pair of readings, by as little as about 12 J over the shortest interval, about
  1.6 % of the energy one card drew during the shortest single request
  (`counter_step_min_j`, per card and part in `energy*.json`, is the smallest
  rise between two successive readings). In that campaign's solo and
  eight-request parts most cards averaged about 280 to 350 W against their
  350 W limit (Qwen3.8-Flash-Next about 150 W, part of it in system RAM), and
  eight requests at once gave about 4 to 8 times the tokens per joule of one
  request under vLLM, about twice on the two-slot llama.cpp server, and about
  the same on one-slot servers. The six model-watch runs of 2026-10-04, on
  one card each, averaged about 330 to 350 W in those parts; eight requests
  gave about 4 to 8 times the tokens per joule of one request under vLLM and
  about the same on their one-slot llama.cpp servers. There is no power-limit sweep, no reading at
  the wall, and no energy figure for runs measured before 2026-10-03.

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
- **English twin** (`speed-house/v1-en`): the house pass with the prompt in
  English (above), always run beside a French pass on the same server.
- **Energy** (`nvml-energy/v1`): a record beside a speed pass, not a speed
  protocol (above).

## Reproducing a figure

The run record gives the engine image and tag, the topology and the parsed
engine arguments (context length, `max-num-seqs`, KV cache type,
`gpu-memory-utilization`, slots). The launch file in the evidence folder is
the command as it ran, with machine-specific parts (container name, host
port, host paths) replaced by placeholders such as `$MODELS`. Serve the same
weights with the same command, then send the prompt above (or its English
twin) with the same options, for example `harness/evalue.py --mode vitesse
[--prompt-lang en]`; the 2026-10-03 runs sent one short warm-up request
first.
