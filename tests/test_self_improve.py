import tempfile
import unittest
from pathlib import Path

from self_improve import build_plan, write_report


class SelfImproveTests(unittest.TestCase):
    def test_plan_never_claims_implementation(self):
        plan = build_plan({"candidates": [{
            "repository": "example/agent",
            "url": "https://github.com/example/agent",
            "feature_candidates": [{"feature": "RAG"}],
            "license_spdx": "MIT",
            "license_status": "permissive_review_required",
            "priority_score": 70,
        }]}, generated_at="2026-01-01T00:00:00+00:00")
        self.assertEqual(plan["mode"], "planning_only_no_llm_no_external_code_execution")
        self.assertEqual(plan["summary"]["code_changes_made_by_planner"], 0)
        self.assertEqual(plan["repository_review_queue"][0]["implementation_status"], "not_implemented")
        self.assertEqual(plan["repository_review_queue"][0]["next_action"], "review_readme_and_license")

    def test_report_files_are_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            md, js = write_report(build_plan({}), Path(tmp))
            self.assertTrue(md.exists())
            self.assertTrue(js.exists())
            self.assertIn("تغييرات كود نفذها هذا المخطط: 0", md.read_text(encoding="utf-8"))
            self.assertIn("no_external_code_execution", js.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
