import tempfile
import unittest
from pathlib import Path

from self_improve import build_plan, scan_existing_features, write_report


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


    def test_static_scan_marks_present_and_missing_feature_signatures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sample.py").write_text(
                "def retrieve_documents(query):\\n    return []\\nclass VectorStore:\\n    pass\\n",
                encoding="utf-8",
            )
            scan = scan_existing_features(root)
            self.assertEqual(scan["RAG / البحث في المستندات"]["status"], "present")
            self.assertEqual(scan["استخدام الأدوات واستدعاء الوظائف"]["status"], "missing")
            self.assertEqual(scan["استخدام الأدوات واستدعاء الوظائف"]["matched_signatures"], [])

    def test_candidate_gaps_are_reported_as_unverified_missing_signatures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sample.py").write_text("def retrieve_documents(query):\\n    return []\\n", encoding="utf-8")
            plan = build_plan({"candidates": [{
                "repository": "example/agent", "url": "https://github.com/example/agent",
                "feature_candidates": [
                    {"feature": "RAG / البحث في المستندات"},
                    {"feature": "استخدام الأدوات واستدعاء الوظائف"},
                ],
                "license_spdx": "MIT", "license_status": "permissive_review_required",
                "priority_score": 70,
            }]}, generated_at="2026-01-01T00:00:00+00:00", root=root)
            self.assertEqual(len(plan["verified_feature_gaps"]), 1)
            self.assertEqual(plan["verified_feature_gaps"][0]["feature"], "استخدام الأدوات واستدعاء الوظائف")
            self.assertEqual(plan["repository_review_queue"][0]["feature_verification"]["RAG / البحث في المستندات"]["status"], "partial")

    def test_report_files_are_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            md, js = write_report(build_plan({}), Path(tmp))
            self.assertTrue(md.exists())
            self.assertTrue(js.exists())
            self.assertIn("تغييرات كود نفذها هذا المخطط: 0", md.read_text(encoding="utf-8"))
            self.assertIn("no_external_code_execution", js.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
