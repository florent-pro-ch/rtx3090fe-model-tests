#!/usr/bin/env bash
# check_all.sh — every public quality gate, in one go (what CI runs first).
#
#   G2 scan_public.py     generic leak patterns (addresses, home paths, tokens, e-mails)
#   G3 check_size.py      file and repo size, no media/log/weights
#      validate.py        data/**/*.json against schema/*.schema.json, --strict (0 warnings)
#   G4 verify_benches.py  frozen benches: SHA-256 recomputed, withheld files listed
#   G5 verify_numbers.py  every <Num> of site/dist traced to data/; README block fresh
#   G6 check_links.py     relative Markdown links and anchors resolve to files git ships
#      check_version.py   every copy of the release label in the prose equals VERSION_LABEL
#      site links         every internal link of site/dist resolves (site/scripts/check-links.mjs;
#                         needs node and a built site)
#      site contrast      every text/background token pair reaches WCAG AA in both themes
#                         (site/scripts/contrast.mjs; needs node)
#      font glyphs        every character of the built pages and the figure specs is in the
#                         self-hosted font subsets (site/public/fonts, site/fonts-og), emoji
#                         apart (site/scripts/check-glyphs.mjs; needs node and a built site)
#      figures fresh      figures/ (README banner pair, social preview) and the README banner
#                         block match data/ (tools/build_figures.mjs --check; needs Node >= 22.18)
#   G7 check_media.py     no GPS/camera/author/path metadata in images and PDFs
#   G8 check_language.py  no French in English prose and data fields
#      harness tests      python3 -m pytest harness/tests (the vendored bench harness; needs
#                         pytest, skipped and said so when it is not installed)
#   G9 gitleaks           the git history (only when gitleaks is installed; required
#                         before any publication, see tools/README.md)
#
# G5 and the site link check need the built site: --build runs `npm ci` in site/ when
# site/node_modules is missing, then `npm run build`; without --build, a missing
# site/dist skips them (the README check still runs) and says so.
# Every gate runs even when an earlier one fails; the exit status is non-zero if any
# failed. usage: tools/check_all.sh [-h|--help] [--build]
set -u

build=0
for arg in "$@"; do
  case "$arg" in
    -h|--help) sed -n '2,/^set -u/{/^#/p;}' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    --build) build=1 ;;
    *) echo "check_all: unknown argument $arg (see --help)" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.." || exit 2
PY="${PYTHON:-python3}"
failed=()
skipped=()

run() {
  local name="$1"; shift
  [ -n "${GITHUB_ACTIONS:-}" ] && echo "::group::${name}"
  echo "== ${name}"
  if "$@"; then
    echo "-- ${name}: ok"
  else
    echo "-- ${name}: FAILED"
    failed+=("$name")
  fi
  [ -n "${GITHUB_ACTIONS:-}" ] && echo "::endgroup::"
  return 0
}

run "scan_public (G2)"    "$PY" tools/scan_public.py
run "check_size (G3)"     "$PY" tools/check_size.py
run "validate (schema)"   "$PY" tools/validate.py --strict --quiet
if [ -f tools/verify_benches.py ]; then
  run "verify_benches (G4)" "$PY" tools/verify_benches.py
else
  echo "== verify_benches (G4)"; echo "-- verify_benches (G4): FAILED (tools/verify_benches.py missing)"
  failed+=("verify_benches (G4)")
fi

# G5 — numbers of the built site
if [ "$build" = 1 ]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "== site build (for G5)"; echo "-- site build (for G5): FAILED (npm not installed; Node >= 22.12 is required)"
    failed+=("site build (for G5)")
  else
    if [ ! -d site/node_modules ]; then
      run "site dependencies (npm ci)" sh -c 'cd site && npm ci --no-audit --no-fund --silent'
    fi
    run "site build (for G5)" sh -c 'cd site && npm run build --silent >/dev/null'
  fi
fi
if [ -f site/dist/index.html ]; then
  run "verify_numbers (G5)" "$PY" tools/verify_numbers.py
else
  echo "== verify_numbers (G5)"
  echo "-- verify_numbers (G5): SKIPPED — site/dist is missing; build the site first"
  echo "   (cd site && npm ci && npm run build) or run tools/check_all.sh --build"
  skipped+=("verify_numbers (G5)")
  run "README block (G5)" "$PY" tools/build_readme.py --check
fi

# the built site's own links, and the colour contrast of its theme tokens (Node scripts)
if command -v node >/dev/null 2>&1; then
  if [ -f site/dist/index.html ]; then
    run "site links (site/dist)" sh -c 'cd site && node scripts/check-links.mjs dist'
    run "font glyphs (subsets)" sh -c 'cd site && node scripts/check-glyphs.mjs dist'
  else
    echo "== site links (site/dist)"; echo "-- site links (site/dist): SKIPPED — site/dist is missing"
    echo "== font glyphs (subsets)"; echo "-- font glyphs (subsets): SKIPPED — site/dist is missing"
    skipped+=("site links (site/dist)" "font glyphs (subsets)")
  fi
  run "site contrast (AA)" sh -c 'cd site && node scripts/contrast.mjs'
else
  echo "== site links and contrast"; echo "-- site links and contrast: SKIPPED — node is not installed"
  skipped+=("site links and contrast")
fi

# the generated figures: fresh against data/ (no renderer needed for the check)
if command -v node >/dev/null 2>&1 && node -e 'process.exit(process.features.typescript ? 0 : 1)' >/dev/null 2>&1; then
  run "figures fresh" node tools/build_figures.mjs --check
else
  echo "== figures fresh"; echo "-- figures fresh: SKIPPED — Node >= 22.18 (TypeScript type stripping) is not installed"
  skipped+=("figures fresh")
fi

run "check_links (G6)"    "$PY" tools/check_links.py
run "check_version"       "$PY" tools/check_version.py
run "check_media (G7)"    "$PY" tools/check_media.py
run "check_language (G8)" "$PY" tools/check_language.py

# the vendored bench harness (harness/): its own tests, against the published benches
if "$PY" -c "import pytest" >/dev/null 2>&1; then
  run "harness tests (pytest)" "$PY" -m pytest -q -p no:cacheprovider harness/tests
else
  echo "== harness tests (pytest)"; echo "-- harness tests (pytest): SKIPPED — pytest is not installed (python3 -m pip install pytest)"
  skipped+=("harness tests (pytest)")
fi

# G9 — secrets and leak shapes in every commit (gitleaks is not a Python gate)
if command -v gitleaks >/dev/null 2>&1 && [ -d .git ]; then
  run "gitleaks history (G9)" gitleaks git . --config .gitleaks.toml --redact --no-banner --log-level warn
else
  echo "== gitleaks history (G9)"
  echo "-- gitleaks history (G9): SKIPPED — gitleaks not installed or no .git; it must pass before any publication"
  skipped+=("gitleaks history (G9)")
fi

echo
if [ "${#failed[@]}" -gt 0 ]; then
  echo "check_all: ${#failed[@]} gate(s) failed: ${failed[*]}"
  exit 1
fi
if [ "${#skipped[@]}" -gt 0 ]; then
  echo "check_all: every gate that ran passed; skipped: ${skipped[*]}"
else
  echo "check_all: every gate passed"
fi
