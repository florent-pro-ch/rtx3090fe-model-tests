# pricing

Tiny cart pricing library: `apply_discounts(cart, rules)` in `pricing.py`.

Rule types: `percentage` (optionally restricted to a category), `tiered`
(per-line quantity tiers, the highest tier reached wins) and `fixed` (an
order-level amount granted once `min_subtotal` is reached). The module
docstring is the contract, including how money is rounded.

Run the tests from this directory:

    python3 -m unittest discover -v
