import unittest

from autodev import AutoDevError, parse_model_json, validate_changes


class AutoDevTests(unittest.TestCase):
    def test_parse_json_and_fenced_json(self):
        self.assertEqual(parse_model_json('{"summary":"ok","changes":[]}')["summary"], "ok")
        fenced = chr(96) * 3 + 'json\n{"summary":"ok","changes":[]}' + chr(96) * 3
        self.assertEqual(parse_model_json(fenced)["summary"], "ok")

    def test_rejects_invalid_json(self):
        with self.assertRaises(AutoDevError):
            parse_model_json("not json")

    def test_accepts_exact_module_test_pair(self):
        paths = ("feature_hunter.py", "tests/test_feature_hunter.py")
        payload = {"changes": [
            {"path": paths[0], "content": "def f():\n    return True\n"},
            {"path": paths[1], "content": "def test_f():\n    assert True\n"},
        ]}
        result = validate_changes(payload, paths)
        self.assertEqual(set(result), set(paths))
        self.assertTrue(result[paths[0]].endswith("\n"))

    def test_rejects_extra_or_unexpected_file(self):
        paths = ("feature_hunter.py", "tests/test_feature_hunter.py")
        payload = {"changes": [
            {"path": paths[0], "content": "x = 1"},
            {"path": ".github/workflows/daily-scout.yml", "content": "permissions: write"},
        ]}
        with self.assertRaises(AutoDevError):
            validate_changes(payload, paths)

    def test_rejects_duplicate_paths(self):
        paths = ("feature_hunter.py", "tests/test_feature_hunter.py")
        payload = {"changes": [
            {"path": paths[0], "content": "x = 1"},
            {"path": paths[0], "content": "x = 2"},
        ]}
        with self.assertRaises(AutoDevError):
            validate_changes(payload, paths)

    def test_rejects_oversized_content(self):
        paths = ("feature_hunter.py", "tests/test_feature_hunter.py")
        payload = {"changes": [
            {"path": paths[0], "content": "x" * 60001},
            {"path": paths[1], "content": "y"},
        ]}
        with self.assertRaises(AutoDevError):
            validate_changes(payload, paths)

    def test_no_change_is_not_a_patch(self):
        with self.assertRaises(AutoDevError):
            validate_changes({"changes": []}, ("feature_hunter.py", "tests/test_feature_hunter.py"))


if __name__ == "__main__":
    unittest.main()
