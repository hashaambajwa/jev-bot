import unittest

from jev.jsonutil import strict_loads


class JsonValidationTests(unittest.TestCase):
    def test_reject_duplicate_nested_object_keys(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            strict_loads('{"outer":{"tool":"search","tool":"delete"}}')

    def test_reject_non_standard_numbers(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                strict_loads('{"cost":' + value + "}")

    def test_standard_json(self):
        self.assertEqual(strict_loads('{"ok": true, "value": null}'), {"ok": True, "value": None})


if __name__ == "__main__":
    unittest.main()
