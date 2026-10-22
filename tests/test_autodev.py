import json
import tempfile
import unittest
from pathlib import Path

from autodev import AutoDevError, DEFAULT_TARGET, TARGETS, load_evidence_context, parse_model_json, validate_changes


class AutoDevTests(unittest.TestCase):
    def test_daily_default_targets_reverse_engineering_module_and_tests(self):
        self.assertEqual(DEFAULT_TARGET, "reverse_engineer")
        self.assertEqual(TARGETS[DEFAULT_TARGET], ("reverse_engineer.py", "tests/test_reverse_engineer.py"))

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


    def test_loads_bounded_feature_evidence_without_source_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "self-improvement-plan.json").write_text(json.dumps({
                "capabilities": [{"id": "memory", "title": "Memory", "status": "missing",
                                  "priority": "high", "why": "Not present", "acceptance": ["test it"],
                                  "risk": "prompt injection"}]
            }), encoding="utf-8")
            (root / "feature-candidates.json").write_text(json.dumps({
                "candidates": [{"repository": "example/project", "url": "https://github.com/example/project",
                                "description": "memory agent", "license_spdx": "MIT",
                                "license_status": "permissive_review_required",
                                "feature_candidates": [{"feature": "memory"}], "priority_score": 60,
                                "evidence": "metadata only", "source_code": "must not be passed"}]
            }), encoding="utf-8")
            (root / "reverse-engineering.json").write_text(json.dumps({
                "results": [{"repository": "example/project", "url": "https://github.com/example/project",
                             "architecture_signals": [{"capability": "memory"}],
                             "source_analysis": [{"path": "src/main.py",
                                                  "signals": [{"signal": "memory", "line_numbers": [5]}]}],
                             "risk_flags": [{"flag": "network"}],
                             "feature_opportunities": [{"title": "Structured outputs", "source_signal": "structured_outputs", "evidence": [{"path": "src/main.py", "line_numbers": [12]}], "risk": "low", "recommended_action": "compare existing implementation", "status": "candidate_requires_gap_check"}],
                             "integration_assessment": "review"}]
            }), encoding="utf-8")
            context = load_evidence_context(root)
        self.assertEqual(context["capability_gaps"][0]["id"], "memory")
        self.assertEqual(context["feature_candidates"][0]["repository"], "example/project")
        self.assertNotIn("source_code", context["feature_candidates"][0])
        self.assertEqual(context["reverse_engineering"][0]["source_signals"][0]["signals"], ["memory"])
        self.assertEqual(context["reverse_engineering"][0]["feature_opportunities"][0]["evidence"][0]["line_numbers"], [12])

    def test_no_change_is_not_a_patch(self):
        with self.assertRaises(AutoDevError):
            validate_changes({"changes": []}, ("feature_hunter.py", "tests/test_feature_hunter.py"))


if __name__ == "__main__":
    unittest.main()
