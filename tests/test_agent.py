import json
import tempfile
import unittest
from pathlib import Path

from agent import build_queries, deduplicate_results, make_report, render_markdown, run_agent


class AgentTests(unittest.TestCase):
    def test_queries_require_idea_and_include_buyer_market(self):
        with self.assertRaises(ValueError):
            build_queries("  ")
        queries = build_queries("متابعة الفواتير", "المدير المالي", "السعودية")
        self.assertGreaterEqual(len(queries), 5)
        self.assertTrue(any("السعودية" in q for q in queries))
        self.assertTrue(any("المدير المالي" in q for q in queries))

    def test_deduplication_uses_url(self):
        results = [
            {"title": "A", "url": "https://example.com", "snippet": "", "query": "q1"},
            {"title": "A duplicate", "url": "https://example.com", "snippet": "", "query": "q2"},
            {"title": "B", "url": "https://example.org", "snippet": "", "query": "q2"},
        ]
        self.assertEqual(len(deduplicate_results(results)), 2)

    def test_agent_never_claims_payment_proof(self):
        results = [{"title": "Pricing", "url": "https://example.com/pricing", "snippet": "Pricing plan", "query": "pricing"}]
        report = make_report("إدارة الفواتير", "الشركات", "السعودية", results,
                             {"queries": 8, "successful_queries": 8, "unique_repositories": 10}, [])
        self.assertEqual(report["market_evidence"], "LEADS_ONLY_NOT_VERIFIED")
        self.assertEqual(report["willingness_to_pay"], "NOT_VERIFIED")
        self.assertEqual(report["build_decision"], "DO_NOT_BUILD_YET")
        self.assertIn("https://example.com/pricing", render_markdown(report))

    def test_commercial_scorecard_never_claims_payment_proof(self):
        from agent import commercial_scorecard
        scorecard = commercial_scorecard([
            {"title": "Pricing plan", "snippet": "Pricing available", "url": "https://example.com"},
            {"title": "Customer complaint", "snippet": "problem and complaint", "url": "https://example.org"},
        ])
        self.assertGreater(scorecard["score"], 0)
        self.assertLessEqual(scorecard["score"], 100)
        self.assertEqual(scorecard["verified_paying_customers"], 0)
        self.assertFalse(scorecard["willingness_to_pay_verified"])
        self.assertEqual(scorecard["dimensions"][-1]["score"], 0)

    def test_arabic_ideas_get_distinct_report_filenames(self):
        def fake_search(query):
            return []
        def fake_github():
            return {"queries": 0, "successful_queries": 0, "unique_repositories": 0}
        with tempfile.TemporaryDirectory() as tmp:
            _, md_one, json_one = run_agent(
                "تحليل الفواتير", search_fn=fake_search, github_fn=fake_github, report_dir=tmp
            )
            _, md_two, json_two = run_agent(
                "تحليل المبيعات", search_fn=fake_search, github_fn=fake_github, report_dir=tmp
            )
            self.assertNotEqual(md_one.name, md_two.name)
            self.assertNotEqual(json_one.name, json_two.name)
            self.assertIn("تحليل", md_one.name)
            self.assertIn("تحليل", md_two.name)

    def test_run_agent_writes_json_and_markdown(self):
        def fake_search(query):
            return [{"title": "Result", "url": "https://example.com/" + str(len(query)),
                     "snippet": "A search result", "query": query}]
        def fake_github():
            return {"queries": 8, "successful_queries": 8, "unique_repositories": 3}
        with tempfile.TemporaryDirectory() as tmp:
            report, md_path, json_path = run_agent(
                "تحليل فواتير", "المدير المالي", "السعودية",
                search_fn=fake_search, github_fn=fake_github, report_dir=tmp
            )
            self.assertTrue(md_path.exists())
            self.assertTrue(json_path.exists())
            data = json.loads(Path(json_path).read_text(encoding="utf-8"))
            self.assertEqual(data["build_decision"], "DO_NOT_BUILD_YET")
            self.assertEqual(data["idea"], "تحليل فواتير")
            self.assertGreater(len(report["web_results"]), 0)


if __name__ == "__main__":
    unittest.main()
