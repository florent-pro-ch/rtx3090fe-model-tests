import unittest

from inventory.core import (
    ParseError,
    Record,
    format_cents,
    format_report,
    low_stock,
    parse_line,
    parse_price,
    parse_text,
    total_units,
    total_value_cents,
)


class ParsePriceTests(unittest.TestCase):
    def test_whole_and_decimals(self):
        self.assertEqual(parse_price("3"), 300)
        self.assertEqual(parse_price("4.5"), 450)
        self.assertEqual(parse_price("19.99"), 1999)

    def test_rejects_garbage(self):
        with self.assertRaises(ParseError):
            parse_price("abc")


class ParseLineTests(unittest.TestCase):
    def test_basic_line(self):
        self.assertEqual(
            parse_line("wid-1, Widget, 4, 2.5"),
            Record("WID-1", "Widget", 4, 250),
        )

    def test_wrong_field_count(self):
        with self.assertRaises(ParseError):
            parse_line("a, b, c")


class ParseTextTests(unittest.TestCase):
    def test_skips_comments_and_blank_lines(self):
        text = "# comment\n\nA-1, Alpha, 2, 1\n"
        self.assertEqual(parse_text(text), [Record("A-1", "Alpha", 2, 100)])


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            Record("A-1", "Alpha", 2, 100),
            Record("B-2", "Beta", 10, 250),
        ]

    def test_totals(self):
        self.assertEqual(total_units(self.records), 12)
        self.assertEqual(total_value_cents(self.records), 2700)

    def test_low_stock(self):
        self.assertEqual([r.sku for r in low_stock(self.records, 5)], ["A-1"])

    def test_format_cents(self):
        self.assertEqual(format_cents(123456), "1,234.56")

    def test_report_mentions_totals(self):
        self.assertIn("2 items, 12 units, total value 27.00", format_report(self.records))


if __name__ == "__main__":
    unittest.main()
