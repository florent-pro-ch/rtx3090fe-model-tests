# site/ — the RTX 3090 FE model tests website

A static [Astro 7](https://astro.build) site built from the repository's `data/`
folder. Output is plain HTML for GitHub Pages under
`https://florent-pro-ch.github.io/rtx3090fe-model-tests/`.

## Run it

Requires Node.js 22.12 or later.

```sh
cd site
npm ci            # or: npm install
npm run dev       # http://localhost:4321/rtx3090fe-model-tests/
npm run build     # writes site/dist/
npm run preview   # serves site/dist/ locally
```

### Local preview build

Until the GitHub repository exists, every link to a source file (evidence,
launch records, `data/*.json`, the "repository" link) points to a URL that does
not resolve yet. A preview build says so on every page:

```sh
PREVIEW_LOCAL=1 npm run build   # adds a one-line banner at the top of every page
```

The banner reads: "Local preview: source and evidence links point to the GitHub
repository and resolve once it exists." Without the flag (the release build,
and what `tools/check_all.sh --build` runs) there is no banner. The flag changes
nothing else: same pages, same links, same numbers.

The build reads `../data`, `../methodology`, `../benches`, `../evidence` and
`../CHANGELOG.md` at build time. To build against another tree (for example a
staging export), set `RTX_REPO_ROOT=/path/to/tree`.

The build works with empty or partial data: a missing folder reads as an empty
list, an unreadable JSON file is skipped with a `[data]` warning, and missing
fields get neutral defaults.

## How it is put together

| Path | Role |
|---|---|
| `src/lib/data.ts` | The only door to the data: typed loaders (models, builds, runs, benches, rankings, campaigns, hardware, comparisons, watchlist, forge summary, errata, per-item scores) and the **headline-run rule** |
| `src/lib/site.ts` | Links (base path, trailing slash), units from key suffixes, labels |
| `src/lib/markdown.ts` | Renders `CARD.md`, `methodology/*.md` and `CHANGELOG.md` with `marked`, rewriting relative links |
| `src/layouts/Layout.astro` | Header, nav, footer (data as of, licences, canary); the only two scripts (theme toggle, table sort and filter) |
| `src/components/` | `Num` (every number), `StatusBadge`, `LicenceBadge`, `GraderBadge`, `PrePinBadge`, `FitBox`, `Table`, `RunsTable`, `Banner`, `BarChart`, `Frame`, `Value` |
| `src/pages/` | One file per route (see below) |
| `integrations/sitemap.mjs` | Writes `sitemap.xml` after the build from the rendered pages, leaving out every page marked `noindex` |

Routes: `/`, `/configs/<hardware>/`, `/models/` and `/models/<vendor>__<name>/`,
`/runs/<campaign>/<run>/`, `/benches/<bench>/<version>/`, `/rankings/<id>/`,
`/compare/<id>/`, `/campaigns/<id>/`, `/methodology/` and `/methodology/<doc>/`,
`/pitfalls/` (`/methodology/pitfalls/` points there), `/rig/`, `/watchlist/`, `/forge/`, `/data/` (with
`/data/all.json`), `/changelog/`.

### Rules the site applies

- **Every number goes through `<Num>`**: monospace, with its unit, linked to its
  run page or its evidence file. A missing value shows as `n/a`, never as zero.
- **Headline-run rule**: the one text is
  [`methodology/headline-rule.md`](../methodology/headline-rule.md), shown under
  every headline table; the code is `compareHeadline()` and `headlineEligible()`
  in `src/lib/data.ts`. On an NVLink pair the rule is applied within each split
  mode (tensor parallel, llama.cpp layer split, part of the model in system
  RAM). Runs are never averaged; the others are listed beside it.
- **Aggregate cells name their slots**: a llama.cpp run started with one slot
  (`parallel_slots` 1, `-np 1`) shows `c=8 · 1 slot (serialised)`, because its
  eight requests were served one after another.
- VRAM is always labelled with its meaning (`vram.kind`): `reserved` (vLLM's
  reservation) or `after load` (nvidia-smi about 3 s after ready, 5 s in the
  2026-09-04 campaigns, before any request), never presented as a peak.
- A run whose topology is unknown stays off the configuration pages.
- Judged scores always carry their judge's banner; rankings checked by code and
  judged rankings are kept apart. Superseded ranking snapshots stay published,
  marked as such.
- Model pages with no number at all are `noindex` and stay out of the sitemap.

### Choices

- **No UI framework, no client bundle**: plain `.astro` components; JavaScript
  only for the theme toggle (stored in `localStorage`, wrapped in try/catch) and
  for sorting and filtering tables. Without JavaScript every page still reads.
- **No external request at runtime**: system fonts, no CDN, no analytics.
- **`marked`** for markdown: the markdown files live outside `src/` and are read
  as strings at build time; one dependency-free package does it synchronously.
- **Data read with `node:fs`** rather than `import.meta.glob`, so that a partial
  or malformed file is skipped instead of failing the build.
- **Own sitemap writer** instead of `@astrojs/sitemap`, so the sitemap follows
  each page's own robots meta.
- `robots.txt` is generated, but crawlers only read it at the host root; on a
  project site it documents intent and points to the sitemap.

### Design

The palette, status colours and console frame follow `../DESIGN.md`: 11 tokens,
dark first with a light variant (`prefers-color-scheme`, overridden by the
toggle), monospace for every number, no drop shadow, no photo. Layouts hold
down to 360 px wide; wide tables scroll inside their own container.

## Checks

```sh
node scripts/contrast.mjs        # WCAG contrast of every text/background token pair, both themes
node scripts/check-links.mjs     # every internal link and #anchor of dist/, and repo paths linked on GitHub
node scripts/screenshots.mjs screenshots http://127.0.0.1:8765   # light/dark, desktop/phone (serve dist/ under the base path first)
```

`?theme=light` or `?theme=dark` forces a theme for one view (screenshots,
shared links) without touching the stored choice. `screenshots/` is ignored by git.

## Licence

Code under MIT; data and bench cards under CC BY 4.0 (see the repository root).
