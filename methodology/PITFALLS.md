# Ampere pitfalls

The RTX 3090 is sm86, not sm90. Most "it does not work on my 3090" reports come
from a short list of causes, and each one below cost this lab real time
before it was understood. They are written for vLLM and llama.cpp as pinned
here (`vllm/vllm-openai:v0.29.0`, llama.cpp `server-cuda-b10830`); newer
releases may have moved, so check before you rely on an exact message. This
page is part of v0 (2026-10-02).

## Formats and kernels

**1. There is no native FP8 on Ampere.** vLLM accepts `--quantization fp8`,
then sends some dense layers to a CUTLASS kernel built for sm80 and dies while
profiling memory. Forcing the Marlin path with `VLLM_TEST_FORCE_FP8_MARLIN=1`
did not change that on 0.29. Use W4A16 (AWQ or GPTQ, both served by Marlin
kernels) or plain bf16. A checkpoint published with FP8 *weights* does load,
because the weights are dequantised on the fly: you save memory, never time.

**2. MXFP4 is not native either, but the famous error is out of date.** The
widely quoted refusal "Minimum capability: 100. Current capability: 86" no
longer applies: vLLM's own gpt-oss recipe now lists Ampere support, through
the Triton attention backend and Marlin MXFP4 kernels for the experts, with
Triton upcasting to bf16 on the fly. The Ampere card that recipe was checked
on is an A100, so on a 3090 treat it as expected to work, not as validated.
This lab did serve gpt-oss-20b in its native MXFP4 on one 3090 pair in tensor
parallel 2 in August 2026, before the engines were pinned, but no measurement
of that service is published here: the one exported run of the model is a
failed start.
llama.cpp reads MXFP4 natively on CUDA. What to avoid is an MXFP4 or NVFP4
*re-quantisation* of a model that was not trained in that format: on Ampere
those formats save memory and never speed.

**3. bitsandbytes will not rescue a mixture-of-experts model.** Two separate
problems: since vLLM 0.28 bitsandbytes support lives out of tree (a plugin
that is not in the official image), and it does not quantise fused MoE
experts at all (the upstream feature request was closed as not planned). The
Ampere tick in its support matrix is about the GPU, not about MoE.

**4. FlashInfer is not universal.** On a block-diffusion model it evaluated a
tensor as a boolean and crashed with `Boolean value of Tensor with more than
one element is ambiguous`. `--attention-backend TRITON_ATTN` fixed it.

**5. A fork-private weight format can fail silently.** Some ternary GGUF
checkpoints use ggml type ids that only exist in their publisher's fork of
llama.cpp. A stock build either rejects them or, worse, loads whatever type
now owns that id and serves fluent nonsense with no error anywhere. If a model
card tells you to use its own build, that sentence is the whole warning:
check that the first answer is coherent before you trust any score. This lab
wraps such a fork's own CUDA release in a house image pinned to an exact tag.

## Memory and parallelism

**6. Leave headroom for compiled kernels.** At
`--gpu-memory-utilization 0.95` a model that loads can still die during
warm-up, when the compiled kernels ask for their workspace. Between 0.85 and
0.90 is the sane range on a 24 GB card.

**7. Tensor parallel needs shared memory.** Run vLLM with `--ipc=host` (or a
large `--shm-size`). Without it, tensor parallel 2 hangs or dies inside NCCL.
Every vLLM container in this lab runs with `--ipc=host`.

**8. vLLM 0.29 turns on FlashInfer all-reduce by default** for
tensor-parallel CUDA groups, which is exactly what a bridged pair is. If
tensor parallel 2 becomes unstable after an upgrade, try
`VLLM_ALLREDUCE_USE_FLASHINFER=0` before suspecting the model.

**9. A 4-bit checkpoint can refuse to shard.** A quantisation with group-wise
scales requires each tensor-parallel shard of the MoE intermediate size to be
a multiple of the group size. One checkpoint tested here has an intermediate
size of 1856 and groups of 64: split over two cards that is 928 per shard,
which 64 does not divide, and vLLM stops with "CompressedTensors WNA16 MoE
with static group scales requires the MoE intermediate size per
tensor-parallel partition to be divisible by group_size". The fix is not a
smaller tensor-parallel size but `--enable-expert-parallel`, which gives each
card whole experts instead of slices of every expert. Check
`moe_intermediate_size ÷ TP ÷ group_size` in the model's config before you
download it.

**10. `--cpu-offload-gb` works in tensor parallel.** It is the most useful
single flag on a 3090 pair: it turns "does not fit" into "runs slower". Upstream
reports it failing on some MoE models, and dedicated expert offload in vLLM is
still at the proposal stage; it nevertheless carried a 26B-A4B block-diffusion
model here without complaint. For models far larger than the cards, llama.cpp
is the mature path: `--n-cpu-moe N`, `--cpu-moe` and `--override-tensor` give
control vLLM does not have, and a GGUF too large for the cards spills into
RAM on its own. See [TOPOLOGY.md](TOPOLOGY.md).

## Operations

**11. Never serve from a floating tag.** The llama.cpp `server-cuda` tag moved
between two measurement campaigns here and silently changed a result. Every
engine in this lab has been pinned to an exact tag since 2026-09-10, and a
rollback is a tag change. Runs from before the pin are labelled pre-pin
([METHODOLOGY.md](METHODOLOGY.md#engine-pins-and-the-pre-pin-label)).

**12. Idle cards can get stuck in a higher power state.** After long vLLM
sessions the GPUs stayed at a noticeably higher idle draw than normal, with
no load, and did not come back down by themselves. On this rig each pair is
passed through to a virtual machine. A reboot of that virtual machine issued
from the hypervisor host cleared it every time it was tried, because the host
re-initialises the passed-through cards; a cold cycle of the virtual machine
(a full shutdown, wait until it is stopped, then start) cleared it too, and is
the fallback when a card does not come back after the reboot. A reboot issued
from inside the guest is a different gesture and did not clear it. After
either, check that both cards are listed (`nvidia-smi -L`) and that NVLink is
back at full rate (`nvidia-smi nvlink -s`) before a tensor-parallel run.

**13. Do not run `docker system prune -a` on a serving machine.** It deletes
the pinned engine images, which are large and slow to pull again, together
with the build cache you wanted to keep.

## Two more, from the NVLink campaigns

**14. `NCCL_P2P_DISABLE=1` alone is a false negative** when you try to measure
what the bridge is worth under vLLM: its custom all-reduce still uses the
bridge. Add `--disable-custom-all-reduce`. Measured here: with NCCL
peer-to-peer off alone the dense model barely moved, and the cost only
appeared with both switches
([TOPOLOGY.md](TOPOLOGY.md#does-the-nvlink-bridge-matter)).

**15. Advice, not measured here: give a tensor-parallel container two cards
that share a bridge.** On a single machine with four cards, a container given
one card from each pair talks through the host while believing its cards are
peers. This rig never ran that case, because each virtual machine only sees
its own bridged pair; the advice follows from how the bridge works, not from
a measurement ([TOPOLOGY.md](TOPOLOGY.md#does-the-nvlink-bridge-matter)).
