# Attribution

This repository's own work is licensed as stated in [LICENSE](LICENSE) (code,
MIT) and [LICENSE-DATA](LICENSE-DATA) (data, bench cards, evidence and
documentation, CC BY 4.0). The material below belongs to others and keeps its
own terms. If you reuse a bench, carry these notices with it. This page
describes v0 (2026-10-02).

| Material | Where | Licence | Redistributed here |
|---|---|---|---|
| Comfy-Org `workflow_templates` | `benches/volume/v1/workflows/*.json` | MIT | yes, five files, byte-identical |
| Google Scanned Objects | `volume/v1`, set B | CC BY 4.0 | object names, Fuel model URLs and short descriptions only; meshes and renders: no |
| Poly Haven HDRI | `volume/v1` renders | CC0 | no: name and hash only |
| Thesys `generative-ui-bench` / openui-lang | `interface/v1` protocol | see below | no |
| SIX example QR-IBAN | `document/v1`, two QR-bill pages | documented example value | yes, inside the bench pages |
| YuE2 example by M-A-P | `audio/v1`, one item | upstream terms | no: a pointer only |
| RADAR | medical-imaging reference model | upstream terms | no |
| Merlin (Stanford AIMI) | medical-imaging measurements | data use agreement | no: no score at present; the aggregates published in v0 were withdrawn on 2026-10-03 (see below) |
| Claude Fable 5.1's verdicts (Anthropic) | every tutoring, vision and judged-code score | Anthropic's terms for its outputs | no: only the scores and duel outcomes derived from them |
| GPT-6 Astra's verdicts (OpenAI) | the second-opinion agreement figures of the judge audit | OpenAI's terms for its outputs | no: aggregates computed from them only |
| The local judge's weights | the refusal-probe and forge scores | Qwen licence | no |
| Inter, JetBrains Mono (typefaces) | `site/public/fonts/`, `site/fonts-og/` | SIL OFL 1.1 | yes, Latin subsets, with their licence files |

## Third-party material used by the benches

### Comfy-Org workflow templates (MIT) — `volume/v1/workflows/`

The five JSON files in [benches/volume/v1/workflows/](benches/volume/v1/workflows/)
are verbatim copies of ComfyUI workflow templates from
[Comfy-Org/workflow_templates](https://github.com/Comfy-Org/workflow_templates)
(the `templates/` folder at commit `371a7b7171bbd11e9cc92ef615ba5ad223d7e5b4`,
tag `v0.11.66`, the version pinned by the `comfyui-workflow-templates` Python
package), saved under the bench's candidate names. They are part of the frozen
set, so they are not edited; the MIT licence travels with them:

```
MIT License

Copyright (c) 2023-present Comfy Org

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### Google Scanned Objects (CC BY 4.0) — `volume/v1`, set B

Set B of the 3D-generation bench ([benches/volume/v1/](benches/volume/v1/))
is built from named objects of the **Google Scanned Objects** dataset by
Google Research, distributed through Open Robotics' Gazebo Fuel under the
[Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)
licence (per-object metadata: "Copyright 2020 Google LLC").

> Laura Downs, Anthony Francis, Nate Koenig, Brandon Kinman, Ryan Hickman,
> Krista Reymann, Thomas B. McHugh, Vincent Vanhoucke. *Google Scanned
> Objects: A High-Quality Dataset of 3D Scanned Household Items.* ICRA 2022.
> [arXiv:2204.11918](https://arxiv.org/abs/2204.11918)

**Changes made:** each object is pinned by its Fuel name and version,
converted to a single GLB mesh, and rendered under fixed cameras and lighting
to produce the bench's input images. **What this repository contains:** in
the bench's public view of its items
([benches/volume/v1/items.public.json](benches/volume/v1/items.public.json)),
each object's name, its Fuel model URL, a short English description and the
item definition; the meshes and renders are covered by the hashes of the
bench's withheld files. The meshes and renders themselves are not
redistributed here.

Set A of the same bench is not third-party material: its 40 objects are
procedural, generated in the lab by a seeded script (trimesh 5.1.0 and
manifold3d 3.5.4), with no third-party data. They are part of this
repository's data, under CC BY 4.0 ([LICENSE-DATA](LICENSE-DATA)).

### Poly Haven HDRI (CC0) — `volume/v1` lighting

The renders of the 3D bench are lit by one HDRI environment map from
[Poly Haven](https://polyhaven.com/), `kloofendal_48d_partly_cloudy_puresky`
(2K), dedicated to the public domain under
[CC0](https://creativecommons.org/publicdomain/zero/1.0/). No attribution is
required; it is given anyway. The map is not redistributed here; the bench's
withheld media list pins it by checksum.

### Thesys generative-ui-bench and openui-lang — `interface/v1`

The interface-generation bench follows the openui-lang protocol of Thesys's
[generative-ui-bench](https://github.com/thesysdev/generative-ui-bench) at
commit `fcca05a`: its frozen catalogue of components, the system prompt its
`prompt.ts` generates, and the `@openuidev/lang-core` validator (version
0.2.16). The bench's own briefs are the lab's. Nothing of the upstream
repository is redistributed here; on 2026-10-01 GitHub detected no licence
file in it, so its files keep whatever terms their authors set. Its 46
reference briefs, played in addition in one campaign, are not part of the
bench.

### SIX example QR-IBAN — `document/v1`

The two Swiss QR-bill pages of the document-extraction bench
([benches/document/v1/](benches/document/v1/)) print only the **example
QR-IBAN that SIX publishes** in its Swiss QR-bill implementation guidelines.
It is a documented example value, not a real account, and no bank is named.
Every other page, name and figure in that bench is fictional and generated in
the lab.

### YuE2 example — `audio/v1`

One item of the music-generation bench is a reproducibility anchor: it points
to an official example file of the YuE2 release by M-A-P
(`examples/tonight-awake.json`) instead of carrying its text. The style
prompt and lyrics are read from the upstream file at generation time and are
not reproduced in this repository; they remain under their publisher's terms.

## Medical imaging: scores withheld at present

### RADAR

The reference model of the medical-imaging measurements is **RADAR**:
upstream code at
[github.com/alibaba-damo-academy/damo-radar](https://github.com/alibaba-damo-academy/damo-radar).
Its weights and outputs are not redistributed here.

### Merlin (Stanford AIMI) — under a data use agreement

The medical-imaging measurements use CT exams from the **Merlin** dataset of
the Stanford Center for Artificial Intelligence in Medicine and Imaging
(AIMI), accessed under a data use agreement.

> Since 2026-10-03, medical-imaging scores are withheld until the data-use agreement's publication clause has been reviewed.

Version v0 published two aggregate scores per model for these measurements;
they were withdrawn on 2026-10-03, pending that review, and the withdrawal is
logged in [data/errata.json](data/errata.json). Since then no score of these
measurements is published: only the timing of the run and the hardware it
used. Once the review allows it, at most this is to be published again, in one
ranking file:

- for each model, **two aggregate scores, each with its 95 % confidence
  interval**: the overall Q (100 × the mean area under the ROC curve over the
  evaluable findings of a 400-exam subset), and the same Q over the 15
  findings that the reference model scores;
- counts: the number of exams, the number of evaluable findings, and how many
  missing scores were counted as 0.5;
- nothing per exam, per patient or per finding, and no image, report, label
  or model output derived from the exams; no exam-level data of any kind;
- the medical-imaging bench itself (`imagerie-med/v1`) is withheld.

The scores measure agreement with the dataset's published labels. They say
nothing about clinical value.

## The judges

One judge per table, never two ([methodology/JUDGE.md](methodology/JUDGE.md)).

- **Claude Fable 5.1** (Anthropic, cloud) grades every tutoring, vision and
  judged-code score. It was called through Anthropic's batch API and its
  command-line client; its verdicts are model outputs under Anthropic's terms
  for its services. They are not redistributed here: only the scores and duel
  outcomes the lab's harness derived from the verdicts are published (each
  duel's outcome: candidate, anchor, tie or inconsistent), not the verdict
  texts or their written rationales; these derived scores and outcomes are this lab's
  measurements and are published under CC BY 4.0.
- **GPT-6 Astra** (OpenAI, cloud), the second frontier judge, graded the
  calibration lots and lot B's reduced lot as a second opinion. Its verdicts
  are model outputs under OpenAI's terms for its services; they are not
  redistributed here and no table holds its scores: only aggregate agreement
  figures, computed by the lab, appear in
  [data/judge-audit.json](data/judge-audit.json).
- **Qwen3.8-Flash-Next (local, GGUF UD-Q3_K_XL)**, the local judge, grades
  the refusal probe and the forge bench. It runs from the `UD-Q3_K_XL` files
  of the GGUF build published as `unsloth/Qwen3.8-Flash-Next-GGUF`. Its
  weights are not redistributed here. They are under the Qwen licence (Qwen
  Community 1.0, as recorded in
  [data/models/qwen__qwen3.8-flash-next.json](data/models/qwen__qwen3.8-flash-next.json));
  the upstream model page is the authority. Its scores are this lab's
  measurements and are published under CC BY 4.0; its written rationales are
  not published.

## Models

Every model tested here belongs to its publisher and keeps its own licence:
open weights, gated weights, research-only, non-commercial, territorial
clauses and custom licences all occur. This repository redistributes no
weights and, in v0 (2026-10-02), no model outputs.

- Each model record in [data/models/](data/models/) carries a `licence` field
  (`name`, `flags`, `source`) and an `access` field (`open`, `gated`,
  `unknown`), and points to the upstream model page in `upstream_url`.
- The upstream model page is the authority. Read it before reusing a model or
  anything derived from it; a licence flag here is a reading aid, not legal
  advice.
- Scores, speeds and energy figures are this lab's measurements of those
  models and are published under CC BY 4.0 with the rest of [data/](data/).

## Fonts

The site and the generated images (Open Graph cards, README banner, social
preview) use two typefaces, self-hosted, under the
[SIL Open Font License, Version 1.1](https://openfontlicense.org/):

- **Inter** by Rasmus Andersson and the Inter project (Copyright 2016 The
  Inter Project Authors, [github.com/rsms/inter](https://github.com/rsms/inter)),
  version 4.001: the variable font as WOFF2 for the pages, and the Regular,
  SemiBold and ExtraBold instances as TTF for the images.
- **JetBrains Mono** by JetBrains (Copyright 2020 The JetBrains Mono Project
  Authors, [github.com/JetBrains/JetBrainsMono](https://github.com/JetBrains/JetBrainsMono)),
  version 2.304: Regular and Bold, as WOFF2 for the pages and as TTF for the
  images.

**Changes made:** each file is subset to the Latin character set the site
uses, plus the Greek letters (for Δ and Kendall's τ), the micro sign and the
≤ ≥ signs; nothing else is changed. `tools/check_all.sh` checks that every
character of the built pages is in the subsets. A subset is a Modified Version under the OFL;
neither font declares a Reserved Font Name, so the names are kept. **Where:**
[site/public/fonts/](site/public/fonts/) (WOFF2) and
[site/fonts-og/](site/fonts-og/) (TTF), each folder with the two licence texts
beside the fonts (`LICENSE-Inter.txt`, `LICENSE-JetBrainsMono.txt`). The fonts
are served from the site itself; no page fetches a font from a third party.
The OFL lets the fonts be bundled and redistributed with this repository; it
does not extend to the repository's own code or data, and this repository's
licences do not extend to the fonts.

## Software

The measurements were taken with open-source engines and tools (vLLM,
llama.cpp, ComfyUI, a headless coding agent for the agent-loop bench, Blender
for the 3D renders, faster-whisper for speech recognition, among others).
They are not redistributed here; each keeps its own licence. The engine and
image tag of every run are recorded in its `data/runs/` record. The energy
figures read NVIDIA's management library (NVML), part of the installed
driver; nothing of it is redistributed.
