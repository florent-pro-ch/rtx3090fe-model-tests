# inventory

A tiny, dependency-free toolkit for plain-text stock files (Python 3 stdlib only).

- `inventory/` -- the package (`core.py` currently holds everything).
- `bin/report.py` -- CLI: `python3 bin/report.py samples/stock.txt [--threshold N]`
- `samples/stock.txt` -- example input.
- `tests/` -- unit tests: `python3 -m unittest discover -s tests -v`

See `REFACTOR.md` for the pending module split.
