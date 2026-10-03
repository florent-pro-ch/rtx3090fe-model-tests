import unittest
from decimal import Decimal

from pricing import apply_discounts


def money(value):
    return Decimal(str(value))


class ApplyDiscountsTests(unittest.TestCase):
    def test_percentage_on_a_single_line(self):
        cart = [{"sku": "BOOK-1", "unit_price": 20.00, "qty": 1}]
        rules = [{"type": "percentage", "percent": 10}]
        result = apply_discounts(cart, rules)
        self.assertEqual(money(result["total"]), Decimal("18.00"))

    def test_fixed_rule_above_threshold(self):
        cart = [{"sku": "LAMP-1", "unit_price": 30.00, "qty": 1}]
        rules = [{"type": "fixed", "amount": 5, "min_subtotal": 20}]
        result = apply_discounts(cart, rules)
        self.assertEqual(money(result["total"]), Decimal("25.00"))

    def test_percentage_on_two_lines(self):
        # Reported by accounting: this basket comes out one cent too low.
        cart = [
            {"sku": "PEN-A", "unit_price": 1.25, "qty": 1},
            {"sku": "PEN-B", "unit_price": 1.35, "qty": 1},
        ]
        rules = [{"type": "percentage", "percent": 10}]
        result = apply_discounts(cart, rules)
        # 10% of 2.60 is 0.26, so the total must be 2.34.
        self.assertEqual(money(result["total"]), Decimal("2.34"))


if __name__ == "__main__":
    unittest.main()
