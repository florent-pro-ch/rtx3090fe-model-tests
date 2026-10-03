"""inventory.core -- parsing and reporting for plain-text stock files.

A stock file is a small comma-separated text file, one item per line::

    # comments and blank lines are ignored
    sku,name,qty,price          <- optional header, skipped if first
    WID-100, Widget (small), 40, 2.5

Prices are decimal amounts with at most two decimals; internally every
amount is an integer number of cents so that totals are exact.

NOTE: this module has grown to mix two unrelated concerns (parsing and
reporting). See REFACTOR.md at the repository root for the plan.
"""

from collections import namedtuple

__all__ = [
    "Record",
    "ParseError",
    "parse_price",
    "parse_line",
    "parse_text",
    "load_file",
    "DEFAULT_THRESHOLD",
    "total_units",
    "total_value_cents",
    "low_stock",
    "format_cents",
    "format_report",
]

# Items whose quantity is at or below this value are reported as low stock.
DEFAULT_THRESHOLD = 5

# One inventory line. ``price_cents`` is the unit price in integer cents.
Record = namedtuple("Record", ["sku", "name", "qty", "price_cents"])


class ParseError(ValueError):
    """Raised when a stock file cannot be parsed.

    The string form is always ``"line <n>: <message>"`` so that callers can
    show it to the user as-is.
    """

    def __init__(self, lineno, message):
        super().__init__("line %d: %s" % (lineno, message))
        self.lineno = lineno
        self.message = message


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_price(text, lineno=0):
    """Parse a decimal price such as ``"12.50"``, ``"4.5"`` or ``"3"``.

    Returns the amount in integer cents. At most two decimals are accepted;
    negative or otherwise malformed input raises :class:`ParseError`.
    """
    text = text.strip()
    if not text:
        raise ParseError(lineno, "empty price")
    if text.startswith("-"):
        raise ParseError(lineno, "negative price: %r" % text)
    whole, sep, frac = text.partition(".")
    if not whole.isdigit():
        raise ParseError(lineno, "bad price: %r" % text)
    if sep:
        if not frac or not frac.isdigit() or len(frac) > 2:
            raise ParseError(lineno, "bad price: %r" % text)
        frac = frac.ljust(2, "0")
    else:
        frac = "00"
    return int(whole) * 100 + int(frac)


def parse_line(line, lineno=0):
    """Parse one data line ``"SKU, Name, Qty, Price"`` into a :class:`Record`.

    Fields are stripped of surrounding whitespace and the SKU is upper-cased.
    """
    parts = [part.strip() for part in line.split(",")]
    if len(parts) != 4:
        raise ParseError(lineno, "expected 4 fields, got %d" % len(parts))
    sku, name, qty_text, price_text = parts
    if not sku:
        raise ParseError(lineno, "empty sku")
    if not name:
        raise ParseError(lineno, "empty name")
    if not qty_text.isdigit():
        raise ParseError(lineno, "bad quantity: %r" % qty_text)
    return Record(sku.upper(), name, int(qty_text), parse_price(price_text, lineno))


def _is_header(line):
    return line.lower().replace(" ", "") == "sku,name,qty,price"


def parse_text(text):
    """Parse the content of a whole stock file into a list of records.

    Blank lines and lines starting with ``#`` are skipped. If the first data
    line is the header ``sku,name,qty,price`` it is skipped too. When a SKU
    appears several times the quantities are added together and the price of
    the first occurrence is kept; records keep the order of first appearance.
    """
    records = []
    position = {}
    seen_data = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not seen_data and _is_header(line):
            seen_data = True
            continue
        seen_data = True
        record = parse_line(line, lineno)
        if record.sku in position:
            index = position[record.sku]
            previous = records[index]
            records[index] = previous._replace(qty=previous.qty + record.qty)
        else:
            position[record.sku] = len(records)
            records.append(record)
    return records


def load_file(path):
    """Read ``path`` (UTF-8) and parse it with :func:`parse_text`."""
    with open(path, "r", encoding="utf-8") as handle:
        return parse_text(handle.read())


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def total_units(records):
    """Total number of units across all records."""
    return sum(record.qty for record in records)


def total_value_cents(records):
    """Total stock value (quantity times unit price) in integer cents."""
    return sum(record.qty * record.price_cents for record in records)


def low_stock(records, threshold=DEFAULT_THRESHOLD):
    """Records whose quantity is at or below ``threshold``, lowest first.

    Ties are broken by SKU so the result is deterministic.
    """
    return sorted(
        (record for record in records if record.qty <= threshold),
        key=lambda record: (record.qty, record.sku),
    )


def format_cents(cents):
    """Render integer cents as a dollar amount: ``123456 -> "1,234.56"``."""
    whole, frac = divmod(cents, 100)
    return "{:,}.{:02d}".format(whole, frac)


_ROW = "%-10s %-24s %5s %10s %11s"
_RULE = "-" * 64


def format_report(records, threshold=DEFAULT_THRESHOLD):
    """Build the plain-text report printed by ``bin/report.py``.

    Rows are sorted by SKU, names are cut to 24 characters, and a low-stock
    section lists the records returned by :func:`low_stock`.
    """
    lines = [_ROW % ("SKU", "NAME", "QTY", "PRICE", "VALUE"), _RULE]
    for record in sorted(records, key=lambda record: record.sku):
        lines.append(_ROW % (
            record.sku,
            record.name[:24],
            record.qty,
            format_cents(record.price_cents),
            format_cents(record.qty * record.price_cents),
        ))
    lines.append(_RULE)
    lines.append("%d items, %d units, total value %s" % (
        len(records), total_units(records), format_cents(total_value_cents(records)),
    ))
    lines.append("")
    low = low_stock(records, threshold)
    if low:
        lines.append("LOW STOCK (qty <= %d):" % threshold)
        for record in low:
            lines.append("  %-10s %-24s %5d" % (record.sku, record.name[:24], record.qty))
    else:
        lines.append("LOW STOCK (qty <= %d): none" % threshold)
    return "\n".join(lines)
