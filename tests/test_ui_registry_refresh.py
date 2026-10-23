import unittest
from pathlib import Path


class SkillRegistryRefreshTests(unittest.TestCase):
    def test_registry_refresh_clears_old_live_state_before_network_requests(self):
        source = (Path(__file__).resolve().parents[1] / "site" / "index.html").read_text(encoding="utf-8")
        start = source.index("async function loadSkillRegistry(){")
        end = source.index('\n}\n$("tab-chat")', start)
        function = source[start:end]
        clear_active = function.index('activeEl.replaceChildren();')
        clear_candidates = function.index('candidateEl.replaceChildren();')
        first_request = function.index('await fetch(apiBase+"/api/skills"')
        self.assertLess(clear_active, first_request)
        self.assertLess(clear_candidates, first_request)
        self.assertIn('summary.textContent="جارٍ تحديث سجل المهارات…";', function)
        self.assertIn('updated.textContent="يتم التحقق من المصدر الحالي قبل عرض حالة المهارات.";', function)


if __name__ == "__main__":
    unittest.main()
