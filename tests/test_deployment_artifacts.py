import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeploymentArtifactTests(unittest.TestCase):
    def test_container_copies_every_module_imported_by_api_server(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        server = (ROOT / "api_server.py").read_text(encoding="utf-8")
        for module in ("web_search", "skill_runtime", "skill_proposal_sync", "github_discovery"):
            self.assertIn(f"from {module} import", server)
            self.assertIn(f"{module}.py", dockerfile)
        self.assertIn("COPY --chown=scout:scout skills/proposed ./skills/proposed", dockerfile)
        self.assertIn("USER scout", dockerfile)
        self.assertIn('CMD ["python", "-u", "api_server.py"]', dockerfile)

    def test_deployment_docs_keep_provider_keys_server_side(self):
        docs = (ROOT / "API_DEPLOYMENT.md").read_text(encoding="utf-8")
        self.assertIn("TAVILY_API_KEY", docs)
        self.assertIn("SCOUT_LLM_API_KEY", docs)
        self.assertIn("لا تضع المفاتيح في GitHub Pages", docs)


if __name__ == "__main__":
    unittest.main()
