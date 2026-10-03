#!/usr/bin/env python3
"""Print a stock report for a plain-text inventory file.

Usage: python3 bin/report.py FILE [--threshold N]
"""

import argparse
import os
import sys

# Make the package importable no matter where the script is run from.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from inventory.core import DEFAULT_THRESHOLD, ParseError, format_report, load_file  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(prog="report.py", description="Print a stock report.")
    parser.add_argument("file", help="stock file to read")
    parser.add_argument(
        "--threshold",
        type=int,
        default=DEFAULT_THRESHOLD,
        help="quantity at or below which an item is low stock (default: %(default)s)",
    )
    args = parser.parse_args(argv)
    try:
        records = load_file(args.file)
    except OSError as exc:
        print("error: cannot read %s: %s" % (args.file, exc.strerror), file=sys.stderr)
        return 2
    except ParseError as exc:
        print("error: %s: %s" % (args.file, exc), file=sys.stderr)
        return 2
    print(format_report(records, args.threshold))
    return 0


if __name__ == "__main__":
    sys.exit(main())
