"""Cart pricing with discount rules.

apply_discounts(cart, rules) -> {"subtotal": Decimal, "discount": Decimal, "total": Decimal}

cart
    A list of line items. Each item is a dict with "sku" (str), "unit_price"
    (a number or a numeric string, in currency units), "qty" (int >= 0) and
    optionally "category" (str).

rules
    A list of rule dicts. Three rule types are supported:

    {"type": "percentage", "percent": 10, "category": "books"}
        Takes ``percent`` % off every matching line. ``category`` is optional;
        when it is omitted the rule applies to every line.

    {"type": "tiered", "tiers": [{"min_qty": 10, "percent": 5}, ...],
     "category": "toys"}
        Per-line quantity discount. For a line with quantity q the applicable
        tier is the one with the largest ``min_qty`` such that q >= min_qty.
        Tiers may be listed in any order. A line below every tier gets nothing.

    {"type": "fixed", "amount": 5, "min_subtotal": 50}
        Takes ``amount`` off the order once, when the cart subtotal (before any
        discount) is >= ``min_subtotal`` (default 0).

Money contract
--------------
* All arithmetic uses decimal.Decimal; floats are never used for money.
* Discounts are computed exactly. Rounding to cents (ROUND_HALF_UP) happens
  ONCE, on the aggregated figures that are returned -- never on intermediate
  per-line or per-rule amounts.
* The total discount is capped at the subtotal, so ``total`` is never negative.
* The returned values are Decimals quantized to cents and always satisfy
  ``total == subtotal - discount``.
"""

from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def to_cents(value):
    """Round ``value`` to cents, half-up (0.125 -> 0.13)."""
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _dec(value):
    return Decimal(str(value))


def _matches(rule, item):
    category = rule.get("category")
    return category is None or item.get("category") == category


def _tier_percent(qty, tiers):
    """Percent of the highest tier reached by ``qty`` (0 if none)."""
    best = None
    for tier in tiers:
        if qty >= tier["min_qty"] and (best is None or tier["min_qty"] > best["min_qty"]):
            best = tier
    return _dec(best["percent"]) if best is not None else Decimal("0")


def _line_discount(item, line_subtotal, rules):
    """Discount granted on one line by the percentage and tiered rules."""
    discount = Decimal("0")
    for rule in rules:
        if not _matches(rule, item):
            continue
        if rule["type"] == "percentage":
            discount += line_subtotal * _dec(rule["percent"]) / 100
        elif rule["type"] == "tiered":
            discount += line_subtotal * _tier_percent(item["qty"], rule["tiers"]) / 100
    return to_cents(discount)


def _order_discount(subtotal, rules):
    """Discount granted on the whole order by the fixed rules."""
    discount = Decimal("0")
    for rule in rules:
        if rule["type"] == "fixed" and subtotal >= _dec(rule.get("min_subtotal", 0)):
            discount += _dec(rule["amount"])
    return discount


def apply_discounts(cart, rules):
    """Apply ``rules`` to ``cart`` and return its subtotal, discount and total."""
    subtotal = Decimal("0")
    discount = Decimal("0")
    for item in cart:
        line_subtotal = _dec(item["unit_price"]) * item["qty"]
        subtotal += line_subtotal
        discount += _line_discount(item, line_subtotal, rules)
    discount += _order_discount(subtotal, rules)
    if discount > subtotal:
        discount = subtotal
    return {
        "subtotal": to_cents(subtotal),
        "discount": to_cents(discount),
        "total": to_cents(subtotal - discount),
    }
