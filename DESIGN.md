# Design

The visual identity of the site and the figures of this repository. One page,
so that any new page or figure looks like it belongs here. If a page or a
figure contradicts this file, the page or the figure is wrong.

## Voice

- **Numbers, not adjectives.** A lab notebook, not a product page.
- **Every figure is measured, dated, and linked to its evidence**: the run
  record in `data/runs/` and the evidence folder in `evidence/`. A figure
  without a date is a decoration and does not ship.
- **Every number says how it was made**: protocol, engine and version, date.
  A pre-pin run carries its label ([methodology/METHODOLOGY.md](methodology/METHODOLOGY.md#engine-pins-and-the-pre-pin-label)).
- **What was not measured is shown as not measured.** An empty cell reads
  "not measured on this configuration", never a blank, a zero or an estimate.
- **An energy figure names its scope.** Tokens per joule is shown only where
  the speed pass measured it (`nvml-energy/v1`, since 2026-10-03), as the GPU
  boards' energy; elsewhere the cell reads "not measured", or links to the
  run that measured it when that run is not the headline, never an estimate.
- **English throughout**, except measurement material (bench items, prompts),
  which is shown in its own language: French, marked `lang="fr"`, apart from
  the English twin of the speed prompt, with an English gloss beside it when
  a reader needs one.
- **Nothing that identifies the machines, in text or in pixels**: no address,
  host name, port, path, container name or account. The two NVLink pairs are
  "pair A" and "pair B".

## Theme

Dark first, with a light theme of equal standing. The site follows the
reader's `prefers-color-scheme`, and a toggle can force either theme
(`data-theme="dark"` or `"light"` on the root element). Every colour comes from
the tokens below; no page or figure uses a raw colour.

| Token | Dark | Light | Use |
|---|---|---|---|
| `--bg` | `#0d1117` | `#ffffff` | page background, inner cards |
| `--panel` | `#161b22` | `#f6f8fa` | containers, chips, table headers |
| `--panel2` | `#21262d` | `#eaeef2` | inset surfaces, GPU slots |
| `--border` | `#30363d` | `#d0d7de` | strokes, separators |
| `--text` | `#e6edf3` | `#1f2328` | primary text |
| `--muted` | `#8b949e` | `#57606a` | labels, captions, greyed speed columns, "not measured" |
| `--green` | `#3fb950` | `#197934` | success, `serves-lane`, kept, run ok |
| `--blue` | `#58a6ff` | `#0862cc` | NVLink, links, the pair |
| `--amber` | `#d29922` | `#8f5f00` | caution: parked, reservations, judged-score banner, pre-pin |
| `--red` | `#f85149` | `#cf222e` | rejected, failed run |
| `--grid` | `#1c2129` | `#eef1f4` | gridlines, dot texture |

Text must meet WCAG AA contrast (4.5:1) in both themes. With this palette,
`--text` and `--muted` pass on every surface, and the four status colours
pass on `--bg` and `--panel` (5.0:1 or more) but only just on `--panel2`
(`--red` 4.59:1 light and 4.54:1 dark, the others 4.7:1 to 6.0:1), so
**coloured text sits on `--bg` or `--panel`**. On `--panel2`, use a status
dot or a border in the status colour and keep the word in `--text`.

### Figures come in pairs

Every standalone figure ships as `<name>-dark.svg` and `<name>-light.svg`,
both generated from a spec in `figures/specs/` and the data it names. Nobody
edits an SVG by hand: the dark file is drawn from the data, and the light file
is the dark one through the token swap of the table above (each dark value
replaced by its light value, in one pass; a colour outside the table fails
the generation). Pages embed the pair with `<picture>` and a
`prefers-color-scheme` source, so the figure matches the page. In v0
(2026-10-02) the standalone figures are the README banner
(`figures/banner-dark.svg`, `figures/banner-light.svg`) and the repository's
social preview (`figures/social-preview.png`, dark only: GitHub shows one
image), all written by `tools/build_figures.mjs`, which also checks them
(`--check`, in CI): a figure older than its data fails the build. Text in a
standalone SVG is turned into outlines, since GitHub draws an SVG as an image
without our fonts; the `<img>` alt text, generated from the same data, carries
the words. The site draws its charts from the data, with the same tokens.

## Status semantics

One meaning per colour, everywhere: tables, badges, figures.

| Meaning | Colour |
|---|---|
| `serves-lane`, `kept`, run `ok` | `--green` |
| `parked`, `reservations`, judged score, pre-pin | `--amber` |
| `rated-no-role`, `not-rated`, not measured | `--muted` |
| `rejected`, `failed-start`, `failed` | `--red` |
| NVLink, a pair, a link | `--blue` |

Colour is never the only carrier: every status also has its word, and every
badge its text (`oracle`, `judge`, `pre-pin`, `TP2`, `layer split`).

## Typography

- **Two typefaces, self-hosted:** **Inter** (by Rasmus Andersson and the Inter
  project) for text and **JetBrains Mono** (by JetBrains) for data, both under
  the SIL Open Font License 1.1, as Latin subsets (plus Greek letters, µ, ≤ and ≥) with their licence files
  beside them: `site/public/fonts/` (WOFF2, for the pages) and
  `site/fonts-og/` (TTF, for the generated images). No font is fetched from a
  third party; see [ATTRIBUTION.md](ATTRIBUTION.md#fonts).
- **Text:** Inter. Display weight (800) only for the site title, a model's
  name on its card and section heads; 600 for card and cell headings.
- **Data:** **JetBrains Mono for every number**, unit, path, run id, model id
  and prompt. If it was measured, it is set in mono.
- **Units live in the label or the key**, never guessed: `tok/s`, `ms`, `s`,
  `MiB`, `GB`. A table column says its unit once, in its header.

## Charts and tables

- **Honest scales.** Throughput and memory bars start at zero. A value beyond
  the axis gets a break glyph and its number, never a rescaled bar. No 3D, no
  dual axes, no smoothing of measured points.
- **One question per figure.** The title states it ("Does the NVLink bridge
  matter?"), the caption gives the date, the protocol and the evidence link.
- **Never merge runs.** A headline figure is chosen by the rule in
  [methodology/headline-rule.md](methodology/headline-rule.md), and a page
  that shows the rule shows that text; other runs are listed beside it, not
  averaged into it.
- **Count distinct runs.** A run counter counts distinct run records; copies
  of earlier runs (`duplicate_of`) are shown apart, as "+N copies", with the
  same words everywhere.
- **Judged scores are visibly judged, and name their judge**: separate tab,
  amber banner with the text of its judge
  ([methodology/judge-banner.md](methodology/judge-banner.md) for Claude
  Fable 5.1's tables, [methodology/judge-banner-local.md](methodology/judge-banner-local.md)
  for the local judge's), a badge that names the judge (`judged · Claude
  Fable 5.1`, `judged · local judge`); a page that is not about one table
  names both judges in one line; "Claude Fable 5.1" is always written in full
  ([methodology/JUDGE.md](methodology/JUDGE.md#how-judged-scores-are-shown)).
- **One version label**, from one place: "v0 (2026-10-02)" in this version
  (`VERSION_LABEL` in `site/src/lib/data.ts`), in the prose, the changelog and
  the site footer alike; `tools/check_version.py` checks every copy.
- **Speed beside quality is greyed** (`--muted`): it breaks ties and never
  adds to a score.
- **Alt text tells the whole figure**: what is compared, every value drawn,
  the date. It is generated from the same data as the figure.

## Motifs

- The **GPU chip**: a slot, a fan circle and the label `3090`.
- The **NVLink bridge**: a short `--blue` bar joining two GPU chips. A pair
  without its bar is a pair whose bridge was disabled in software, drawn
  dashed; no figure shows a physically removed bridge, because none was
  measured.
- The **schematics** of the three configurations, drawn from GPU chips and
  bridges, one per configuration and always the same: **1×** one card;
  **2×** one NVLink pair, two cards joined by the bridge with `NVLink 4-slot`
  beside it; **2×2** the two pairs side by side, each in a dashed `--muted`
  frame labelled `pair A · 48 GB` and `pair B · 48 GB`, with `no link` between
  them and no bar joining them, because no model has run on four cards here.
  The configuration names `1×`, `2×`, `2×2` sit in a `--border` box in
  `--blue`. The design file's Components page holds them with the GPU chip,
  the bridge, the console frame and the badges.
- The **RTX 3090 Founders Edition card**: a flat vector of the card seen from
  the front, in the tokens of this page and nothing else. The angled frame (a
  `--muted` rim around a `--border` face) is cut by the slanted divider: on the
  left the front fan (blades in `--border` on a `--panel` disc, `--panel2` hub,
  `--muted` strokes, on a `--bg` panel); on the right the flow-through fin stack
  (`--bg` slats over the rear fan, its blades in `--muted`, on `--panel2`). Above
  it the top edge in perspective, with the plain lettering `GEFORCE RTX 3090` (Inter,
  `--text`) on a `--bg` bar; at the left the I/O bracket (`--muted`, `--border`
  vents); under it the PCIe contacts. **The pair** is two cards, one behind the
  other, joined across their top edges by the NVLink bridge motif: a flat
  `--blue` block in the same perspective (its side at 60 % opacity, a `--bg`
  inset at 35 %), with `NVLink` beside it in mono `--blue`. It stands for one
  NVLink pair and is captioned from `data/hardware/` (cards and VRAM per card:
  `2 × RTX 3090 Founders Edition · 2 × 24 GB`). Where: the repository's social
  preview, the site's default Open Graph card (`/og/default.png`) and, if
  wanted, the README banner. Not on a page or a chart, where the GPU chip and
  the schematics carry the meaning. Never a photograph, never a vendor logo or
  wordmark (the lettering is plain Inter), never a 3D render with shadows,
  highlights or gradients. Design file: Components page, "Illustration/RTX 3090
  FE pair"; code: `site/src/lib/og/fe-card.ts`, which draws it at the
  component's geometry.
- The **status dot** (`●`) in the status colour, before a status word.
- A **console frame** for figures: rounded outer rectangle (`--bg` fill,
  `--border` stroke), a title bar with a mono title and a right-aligned date
  chip, a separator under it.
- Corner radius 8 to 16 px. No photographs, no gradient orbs, no drop
  shadows. Dot-grid texture (`--grid`) on hero surfaces only.

## Generated images

- **Open Graph cards.** Every model page has a 1200 × 630 card,
  `/og/<slug>.png`, and every other page shares `/og/default.png`. They are
  rendered at build time (resvg, with the TTF files of `site/fonts-og/` and no
  system font) from the SVG templates of `site/src/lib/og/`, after the Figma
  template "OG · model page" of the design file. A model card is a console frame
  (`3090fe · model`, date chip `last tested <date>`): the model's name, id and
  parameters, its badges, one cell per configuration — the headline run's
  single-stream speed, aggregate and VRAM with their units and labels, then
  `protocol · engine · date`, or "Not measured on this configuration." in a
  dashed cell — the verdict with its date, and a footer with the data date
  and the version label. The numbers are the model page's: the same headline
  rule, the same formatting, and nothing from the uncensored lab. The default
  card is the repository's social preview (Figma "Social preview v2 · A")
  fitted to 1200 × 630: the title, the lead, the counts of models, runs and
  benches (the site's counters), the pair with `NVLink` and its caption, the
  data date and the version label.
- **Dark only.** A card is shown by another site, which does not know the
  reader's theme; the dark theme is the default identity.
- **Small.** A card stays under 150 KB; above that it is re-encoded with a
  256-colour palette, which loses nothing on flat token colours. No image
  carries a text chunk or any other metadata (G7).
- **Same rules as every figure.** Each number on a card is dated and comes
  from `data/`; the card says what was not measured; its alt text lists every
  value it draws.

## Do / Don't

Do:
- put a measured value, a date and an evidence link on every figure and every
  headline number;
- show what was not measured, in `--muted`, in words;
- check every page and figure in both themes, element by element, before it
  ships.

Don't:
- invent or round a number for a prettier bar;
- show a figure without its date, or a status without its word;
- print anything that identifies the machines, in text or in an image;
- add a colour or a motif this page does not define without updating this
  page first.
