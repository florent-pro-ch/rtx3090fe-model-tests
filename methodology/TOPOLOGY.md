# Topology: one card, one NVLink pair, two pairs

Every run record says how many cards served the model and how they were used
(`hardware` and `topology` in [data/runs/](../data/runs/)). This page explains
those fields, the rig behind them, and what the evidence does **not** show,
as of v0 (2026-10-02).

## The rig

- **Four NVIDIA GeForce RTX 3090 Founders Edition** cards, 24 GB each,
  compute capability sm86 (Ampere), all in one host, each at its stock 350 W
  power limit. The Founders Edition has no dual BIOS.
- Wired as **two NVLink pairs**, each joined by a 4-slot NVLink bridge.
  `nvidia-smi nvlink -s` reports four links per card at 14.062 GB/s each,
  about 56 GB/s in each direction (`NV4` in `nvidia-smi topo -m`).
- **Each pair is passed whole to its own virtual machine** (8 vCPU, 64 GB of
  RAM). The two machines are called **pair A** and **pair B** here. A model
  served on a pair sees exactly two GPUs and the RAM of that machine.
- The host: one AMD EPYC 7F52 CPU (16 cores, 32 threads) and 256 GB of ECC
  DDR4 (8 × 32 GB DDR4-3200, eight channels), of which each pair's machine gets
  8 vCPU and 64 GB; two power supplies (Corsair HX1500i and HX1000i) started
  together by a dual-PSU adapter.
- NVIDIA driver 580.173.02, CUDA 13.0.
- PCIe: one card's link was read at 16 GT/s x16 (PCIe 4.0), attached to the
  CPU; the links of the other three cards were not recorded.
- Some scoring work that needs no GPU (3D metrics, the agent-loop harness)
  runs on CPU only, off the cards, calling the model served on a pair.

The rig is described fact by fact, with what was not recorded, in
[data/rig.json](../data/rig.json). The three configurations are described as
records in [data/hardware/](../data/hardware/).

## The topology fields

| Field | Values | Meaning |
|---|---|---|
| `gpus` | 0, 1, 2 | Cards the model was given; 0 on a run served on the CPU alone. |
| `tp` | 1, 2 | Tensor-parallel size (vLLM). |
| `pp` | usually null | Pipeline-parallel size; never used on this rig. |
| `split` | `none`, `tensor`, `layer`, `row`, `unknown` | How the model is divided between cards. |
| `nvlink_used` | true, false, null | Whether the bridge carried the traffic. |
| `p2p` | `nvlink`, `off-software`, `n/a`, `unknown` | Peer-to-peer state; `off-software` is the NVLink A/B proxy below. |
| `cpu_offload_gb` | number or null | Weights deliberately held in system RAM by a flag (vLLM `--cpu-offload-gb`), in GB; null when the size is unknown. |
| `ram_spill` | true, false, null | Whether part of the model sat in system RAM during the run, by a flag or because llama.cpp kept on the cards only what fits; null when unknown. A run with `ram_spill: true` does not show that the model fits on the cards. |
| `expert_parallel` | true, false, null | Whole experts per card instead of slices of every expert. |

A run whose topology cannot be read from its evidence says `unknown` and is
left out of the configuration pages. A run served on the CPU alone, with no
card used (hardware `cpu-only`, `gpus: 0`; one so far, since 2026-10-04), is
left out of them too: it has speed figures, in French and English, but no
VRAM and no energy figure, since the card its container could see sat idle.

## One card (`1x3090fe`)

One model, one card, 24 GB, nothing to communicate. This is the configuration
most owners have, and it holds more than it used to: mixture-of-experts models
whose active parameters are small, dense models up to the high 20s of billions
in aggressive 4-bit or lower quantisations, and small models with room to
spare for a large KV cache. Two cards running two independent copies or two
different engines are two one-card runs, not a pair.

## One NVLink pair (`2x3090fe-nvlink`)

Two cards of the same pair serve one model, 48 GB in total. How they share
the work matters more than the number:

- **Tensor parallel 2** (`split: tensor`, vLLM `--tensor-parallel-size 2`).
  Every layer is split across both cards, and the cards exchange partial
  results (all-reduce) on every layer of every token. This is the case where
  the bridge matters (see below). vLLM needs shared memory for it
  (`--ipc=host`, see [PITFALLS.md](PITFALLS.md)).
- **Layer split** (`split: layer`, llama.cpp's default `-sm layer` over two
  devices). Each card holds a contiguous block of layers; one activation crosses
  between the cards per token. **This is not tensor parallelism**: it does not
  all-reduce, the two cards work one after the other rather than at the same
  time, and a layer-split run is never labelled TP2 here. Its point is memory:
  a model too big for one card fits on two. llama.cpp's row split (`-sm row`)
  is recorded as `row` when used.
- **Expert parallel** (`expert_parallel: true`, vLLM
  `--enable-expert-parallel`). Each card holds whole experts of a
  mixture-of-experts model. Sometimes the only way a quantised checkpoint
  loads at all ([PITFALLS.md](PITFALLS.md)).
- **Bigger than the cards: CPU offload and RAM spill.** A pair has 64 GB of
  system RAM beside its 48 GB of VRAM, and both engines can use it. vLLM's
  `--cpu-offload-gb N` holds N GB of weights per card in RAM and streams them
  in at every step (`cpu_offload_gb`). llama.cpp keeps whatever does not fit
  in RAM on its own, or exactly what you tell it (`--n-cpu-moe`,
  `--override-tensor`, a lower `-ngl`). Throughput drops to what RAM bandwidth
  allows, which is too slow for chat and fine for a batch job or a judge. The
  lab's local judge runs this way ([JUDGE.md](JUDGE.md)). A run that kept part
  of the model in system RAM says so in `ram_spill`, whatever the cause.

The only like-for-like comparison of one model on one card and on a pair is
the base arm of the speculative-decoding campaign, Gemma 4 26B-A4B served both
ways ([data/comparisons/gemma4-26b-1-vs-2-cards.json](../data/comparisons/gemma4-26b-1-vs-2-cards.json),
runs in [data/runs/2026-09-25-spec-ab/](../data/runs/2026-09-25-spec-ab/)).
The 2026-10-03 speed campaign measured the same model both ways again under
the house protocol, from the launch lines of its two headline runs, which
differ in more than the card count (prefix caching off on the pair only,
memory share 0.92 against 0.90, the image limit): 139.9 against 193.4 tok/s
single stream and 775.2 against 1118.4 at eight requests
([data/runs/2026-10-03-vitesse-en/](../data/runs/2026-10-03-vitesse-en/)).
Every other "one card versus two" reading compares different models.

## Does the NVLink bridge matter?

Two campaigns on 2026-09-13 measured it on the same pair, with the house speed
pass ([SPEED-PROTOCOL.md](SPEED-PROTOCOL.md)), one model in tensor parallel 2
per campaign, three arms per model:

| Arm | NCCL peer-to-peer | vLLM custom all-reduce | Stands for |
|---|---|---|---|
| `with-nvlink` | on (default) | on (default) | the pair as built |
| `no-p2p` | off (`NCCL_P2P_DISABLE=1`) | on | a partial cut, kept on purpose |
| `no-p2p-no-car` | off (`NCCL_P2P_DISABLE=1`) | off (`--disable-custom-all-reduce`) | the proxy for "no bridge" |

In the run records, the `with-nvlink` arm carries `engine_args.ab_arm:
"reference"` and the two others `"treatment"`. A treatment arm is never a
model's headline figure ([headline-rule.md](headline-rule.md)): its launch line
switches part of the bridge off on purpose, and nobody should copy it.

**Why this is a fair proxy.** A consumer Ampere pair without a bridge has no
CUDA peer-to-peer at all: the cards do not do P2P over PCIe. Every collective
is then staged through host memory. Closing both peer-to-peer paths in
software on bridged cards forces exactly that fallback.

**Why it is only a proxy.** The bridge was **never physically removed**.
Both paths were closed in software. A physical A/B could still differ.

**The false negative to avoid.** Setting `NCCL_P2P_DISABLE=1` alone looks like
a clean experiment and measures almost nothing on a dense model, even though
NCCL visibly reconfigures itself. vLLM has its own custom all-reduce over CUDA
IPC, on by default, and CUDA IPC uses the bridge whatever NCCL was told. The
cost only appears with `--disable-custom-all-reduce` as well.

**Results**, against the bridged pair (time to first token did not move in
either campaign):

| Model (vLLM, TP2) | Arm | Solo tok/s | Aggregate tok/s @ 8 | p50 latency @ 8 | Runs |
|---|---|---|---|---|---|
| Qwen3.8-27B Cold-Fusion, dense, GPTQ 4-bit (one pass per arm) | `no-p2p` | −0.3 % | −1.3 % | +0.6 % | [data](../data/runs/2026-09-13-nvlink-ab/no-p2p.json) · [evidence](../evidence/2026-09-13-nvlink-ab/no-p2p/) |
| | `no-p2p-no-car` | **−10.1 %** | **−22.1 %** | **+34.3 %** | [data](../data/runs/2026-09-13-nvlink-ab/no-p2p-no-car.json) · [evidence](../evidence/2026-09-13-nvlink-ab/no-p2p-no-car/) |
| Qwen3.6-35B-A3B, MoE, about 3B active, AWQ 4-bit (means of three passes) | `no-p2p` | −1.0 % | −7.2 % | +7.7 % | [data](../data/runs/2026-09-13-nvlink-ab-moe/no-p2p.json) · [evidence](../evidence/2026-09-13-nvlink-ab-moe/no-p2p/) |
| | `no-p2p-no-car` | **−11.5 %** | **−24.5 %** | **+32.5 %** | [data](../data/runs/2026-09-13-nvlink-ab-moe/no-p2p-no-car.json) · [evidence](../evidence/2026-09-13-nvlink-ab-moe/no-p2p-no-car/) |

The reference arms are [`2026-09-13-nvlink-ab/with-nvlink`](../data/runs/2026-09-13-nvlink-ab/with-nvlink.json)
and [`2026-09-13-nvlink-ab-moe/with-nvlink`](../data/runs/2026-09-13-nvlink-ab-moe/with-nvlink.json).
The percentages, with their method and caveats, are in the comparison records
[nvlink-ab-dense.json](../data/comparisons/nvlink-ab-dense.json) and
[nvlink-ab-moe.json](../data/comparisons/nvlink-ab-moe.json) (from the
unrounded means of the three passes for the MoE model).

All three arms of both campaigns ran with NCCL's debug logging on
(`NCCL_DEBUG=INFO`). The dense model's reference arm,
`2026-09-13-nvlink-ab/with-nvlink`, gave 78.6 tok/s single stream and 396.6
at eight requests; its launch line without the logging, measured again on
2026-10-03, gave 79.1 and 528.7. That later run, not the reference arm, is
now the model's headline. The percentages above compare arms that all had the
logging on; whether the logging alone explains the gap was not tested.

**Reading.** Without the bridge, a tensor-parallel pair loses roughly a tenth
of its single-stream speed and roughly a quarter of its batched throughput,
for a dense model and for a sparse one alike. The bridge changes **no memory
figure** (the loaded snapshots of the three arms are within a few hundred MiB
of each other) and makes no model fit that did not fit before. On the MoE model, cutting NCCL peer-to-peer alone already
costs some batched throughput, so part of its traffic goes through NCCL even
with the custom all-reduce on; which part is not established.

**What these campaigns do not cover:** a physical unplug of the bridge;
`nccl-tests` or `nvbandwidth` measurements of the link; any llama.cpp run
(layer split does not all-reduce, so they say nothing about it); a table of KV
cache size and maximum context on one card versus two.

**If you build a four-card machine yourself:** give a tensor-parallel
container two cards that share a bridge. A pair made of one card from each
bridge has to talk through the host while believing its cards are peers.
`nvidia-smi topo -m` shows `NV4` between bridged cards. On this rig the
question does not arise: each machine only ever sees its own bridged pair.

## Two pairs (`2x2x3090fe-nvlink`)

**Two independent 48 GB machines. No model has run on four cards here.**

The two pairs have only ever worked **in parallel**, each serving its own
model ([data/comparisons/two-pairs-parallel.json](../data/comparisons/two-pairs-parallel.json)):

- the local model judge served on one pair, grading answers from candidates served
  on the other;
- two candidates benchmarked at the same time, one per pair;
- one 3D-generation engine per card, on both pairs at once;
- one medical-imaging engine per card (its timing only; its scores are withheld at present).

Never measured here, and not planned: tensor parallel 4; tensor parallel 2
combined with pipeline parallel 2; llama.cpp RPC across the two machines; two
tensor-parallel replicas behind one endpoint; the power draw of the whole
rig. The two pairs sit in separate virtual machines, so a four-card run would
first need a different setup. The page for this configuration shows what
exists and lists what is missing.

## Not measured on any configuration

- **Power-limit sweeps and power at the wall**: every card ran at its stock
  350 W limit. Energy is read per card from NVIDIA's counter during the speed
  passes run since 2026-10-03 ([SPEED-PROTOCOL.md](SPEED-PROTOCOL.md)), never
  for the host, its CPU and RAM or the power supplies; no run measured
  earlier has an energy figure, and none is estimated.
- **Sustained thermals**: no long-run temperature series under load.
- **PCIe link width or generation effects** (x8 versus x16, Gen3 versus Gen4).
- **English speed under the house protocol for runs measured before
  2026-10-03**: the 2026-10-03 campaign measured the house pass's English twin
  beside a French pass on 18 headline rows, and since 2026-10-04 model-watch
  runs take it after their French pass, with no second French pass, so no
  language difference is called or ruled out for them
  ([SPEED-PROTOCOL.md](SPEED-PROTOCOL.md)); every house-protocol run measured
  before 2026-10-03 has French figures only. The earlier English
  figures come from speculative-decoding tests, each under its own protocol:
  the speculative-decoding A/B (`spec-ab/v1`), which reports French and
  English apart, and one DSpark probe (`dspark-probe/v1`).
