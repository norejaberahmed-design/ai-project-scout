import tempfile
import unittest
from pathlib import Path

from feature_hunter import discover, feature_matches, license_status, write_report


class FeatureHunterTests(unittest.TestCase):
    def test_feature_matching_is_explicit_and_bounded(self):
        matches = feature_matches("Local inference with RAG and tool calling")
        labels = {item["feature"] for item in matches}
        self.assertIn("RAG / البحث في المستندات", labels)
        self.assertIn("استخدام الأدوات واستدعاء الوظائف", labels)
        self.assertIn("تشغيل محلي وخصوصية", labels)

    def test_unknown_license_is_never_marked_safe_to_copy(self):
        self.assertEqual(license_status(""), "unknown_do_not_copy")
        self.assertEqual(license_status("NOASSERTION"), "unknown_do_not_copy")
        self.assertEqual(license_status("MIT"), "permissive_review_required")
        self.assertEqual(license_status("GPL-3.0"), "legal_review_required")

    def test_discovery_deduplicates_and_never_copies_code(self):
        def fake_search(url):
            if "search/repositories" not in url:
                return {}
            return {"items": [{
                "full_name": "example/ai-tool",
                "name": "ai-tool",
                "html_url": "https://github.com/example/ai-tool",
                "description": "Local inference and RAG tool calling",
                "stargazers_count": 800,
                "language": "Python",
                "license": {"spdx_id": "MIT"},
                "topics": ["ai"],
            }]}
        report = discover(search_fn=fake_search, max_per_query=2)
        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["mode"], "discovery_only_no_code_copy_or_execution")
        self.assertIn("not proof", report["safety_note"].lower())
        self.assertTrue(report["candidates"][0]["feature_candidates"])
        with tempfile.TemporaryDirectory() as tmp:
            md, js = write_report(report, Path(tmp))
            self.assertTrue(md.exists())
            self.assertTrue(js.exists())
            self.assertIn("لا نسخ", md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
