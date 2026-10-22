import tempfile
import unittest
from pathlib import Path
from ai_updates import write_report

class AIUpdatesTests(unittest.TestCase):
    def test_report_writes_arabic_markdown_and_json(self):
        papers = [{
            "title": "A New AI Method", "url": "https://arxiv.org/abs/2601.00001",
            "abstract": "A research abstract.", "published": "2026-10-21T00:00:00Z",
            "categories": ["cs.AI"], "authors": ["Researcher"], "source": "arXiv Atom API"
        }]
        with tempfile.TemporaryDirectory() as tmp:
            md, js = write_report(papers, tmp)
            self.assertTrue(md.exists())
            self.assertTrue(js.exists())
            self.assertIn("آخر أبحاث الذكاء الاصطناعي", md.read_text(encoding="utf-8"))
            self.assertIn("https://arxiv.org/abs/2601.00001", md.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
