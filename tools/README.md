# tools/ — the repository's quality gates

Every gate is a standard-library Python script with a `--help`, exits non-zero on a
violation, and runs in CI through [`check_all.sh`](check_all.sh) before the site is
built ([`.github/workflows/critical.yml`](../.github/workflows/critical.yml)); the
gates that need the built site run after the build. Pages deploys only after that
workflow passed on `main`, runs every gate again on the commit it deploys, and stays
off until the repository variable `PAGES_ENABLED` is set to `true`
([`pages.yml`](../.github/workflows/pages.yml)).

| Gate | Script | What fails it |
|---|---|---|
| G2 | [`scan_public.py`](scan_public.py) | private IPv4/IPv6 addresses, MAC addresses, home directories, ssh targets, API tokens, private keys, secret-bearing file names, e-mail addresses outside [`email-allowlist.txt`](email-allowlist.txt) |
| G3 | [`check_size.py`](check_size.py) | a file over 5 MiB, a tree over 50 MiB (without `node_modules`, `dist`, `.git`), any audio, array, log or model-weight file |
| schema | [`validate.py`](validate.py) | a `data/**/*.json` that does not parse, or a record that does not match its `schema/<type>.schema.json`, the type chosen by path: models, builds, runs, benches, hardware, campaigns, rankings, comparisons, item scores, the forge summary and checkpoints, the runs index, the rig, the watchlist, the errata and the judge audit (`validate.py --help` lists the paths); with `--strict`, which `check_all.sh` runs, any warning: a `data/` JSON file whose path matches no type, broken references between records (a comparison row naming a missing run or evidence path included), misnamed files, duplicate ids, a runs index or a count that disagrees with the records |
| G4 | [`verify_benches.py`](verify_benches.py) | a frozen bench file whose SHA-256 differs from its manifest; a null hash on anything but a file withheld for privacy (listed "withheld, not hashed"); a set hash given for a set that holds one |
| G5 | [`verify_numbers.py`](verify_numbers.py) | a number of the built site (`data-num` of `<Num>`) whose text is not its rounding, or whose value is not in the JSON it links to (run, ranking, model, bench, campaign, comparison, config, or the file on GitHub); a stale generated block in `README.md` (`build_readme.py --check`). Numbers in prose on model, config and compare pages, and counts the page computes, are warnings |
| G6 | [`check_links.py`](check_links.py) | a relative Markdown link or anchor that does not resolve, that leaves the repository, or that points at a file git would not ship (ignored, or an empty folder) |
| version | [`check_version.py`](check_version.py) | a copy of the release label in the prose (Markdown, bench cards, `site/src`) that differs from `VERSION_LABEL` in `site/src/lib/data.ts`; in `CHANGELOG.md` only the first release heading counts |
| site links | [`site/scripts/check-links.mjs`](../site/scripts/check-links.mjs) | an internal link of the built site whose page, file or `#fragment` does not exist (needs Node and `site/dist`) |
| site contrast | [`site/scripts/contrast.mjs`](../site/scripts/contrast.mjs) | a text/background colour pair of the site's theme tokens below WCAG AA (4.5:1), in either theme (needs Node) |
| G7 | [`check_media.py`](check_media.py) | a PNG, JPEG, WebP, PDF or SVG (outside `benches/`, built site included) with EXIF GPS or camera fields, an author/artist/creator/copyright field, or metadata text holding a home or absolute path; frozen bench media are reported, never failed |
| G8 | [`check_language.py`](check_language.py) | French in English prose or in the English fields of `data/` |
| G9 | `gitleaks` with [`.gitleaks.toml`](../.gitleaks.toml) | a secret, private address, home directory or MAC address in any commit of the history |

```sh
bash tools/check_all.sh            # every gate, non-zero if any failed
bash tools/check_all.sh --build    # npm ci if needed, build the site, then every gate
python3 tools/scan_public.py site/dist   # the built site only
python3 tools/verify_numbers.py --verbose  # G5, listing prose numbers and page counts
```

G5 and the site link check read `site/dist`: without a built site `check_all.sh`
skips them (and says so) but still checks the README block. `--build` installs the
site's dependencies with `npm ci` when `site/node_modules` is missing (Node 22.12 or
later), then builds. CI runs G2, G3, G5, G7 and the two site checks again after
`npm run build`.

**G9 runs before any publication** — before the first push, before a repository is
made public, and before every release — on the full history, not only the tree:

```sh
gitleaks git . --config .gitleaks.toml --redact     # every commit (gitleaks >= 8.19)
gitleaks dir . --config .gitleaks.toml --redact     # the working tree, untracked files included
```

`check_all.sh` runs the history scan when `gitleaks` is installed and reports it as
skipped otherwise; a skipped G9 is not a pass. CI does not run it: its checkout is
shallow, so a history scan there would see one commit. A finding in history is
fixed by rewriting the history before publication, never by an allowlist entry.

The leak gates hold **generic shapes only**. The lab's own names, addresses and paths
are checked before every export by a private gate that never enters this repository.

**Measurement material stays French** (bench items, prompts sent to models). In
Markdown, tag it so G8 skips it: `<!-- lang: fr -->` … `<!-- /lang -->`, an element
with `lang="fr"`, a « guillemet » quotation, or `lang: fr` in the front matter. In
JSON, an object carrying `"lang": "fr"` is skipped with everything under it, and so
is any key ending in `_fr`.

**Exceptions** are reviewed one by one in [`exceptions.json`](exceptions.json):
`{"tool": "scan_public", "file": "<glob>", "rule": "<rule>", "reason": "<why>"}`.
Rule names: `scan_public.py --list-rules`; `check_size`: `file-size`,
`forbidden-ext`; `check_links`: `broken`, `anchor`, `unshipped`;
`check_language`: `french`; `check_media`: `gps`, `camera`, `author`, `path`;
`verify_numbers`: `rounding`, `source` (its `file` is a page under `site/dist`, and an
optional `"value"` narrows it to one `data-num`; an unused `verify_numbers` exception
fails the gate). An exception without a reason fails the gate.

[`.gitleaks.toml`](../.gitleaks.toml) extends gitleaks' default rules with the same
address, home-directory and MAC shapes, for scans of the git history
(`gitleaks git . --redact`) as well as of the tree (`gitleaks dir . --redact`).
