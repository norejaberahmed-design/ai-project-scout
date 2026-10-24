import os
import unittest
from unittest.mock import patch

from model_providers import any_provider_configured, list_provider_status, normalize_provider, provider_config


class ModelProviderTests(unittest.TestCase):
    def test_deepseek_uses_allowlisted_endpoint_and_default_model(self):
        with patch.dict(os.environ, {"SCOUT_DEEPSEEK_API_KEY": "private-test-key"}, clear=True):
            config = provider_config("deepseek")
        self.assertEqual(config["endpoint"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(config["model"], "deepseek-chat")
        self.assertTrue(config["configured"])
        self.assertEqual(config["api_key"], "private-test-key")

    def test_gemini_supports_google_api_key_alias_and_openai_compatible_endpoint(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "private-test-key"}, clear=True):
            config = provider_config("gemini")
        self.assertEqual(config["endpoint"], "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
        self.assertEqual(config["model"], "gemini-2.5-flash")
        self.assertTrue(config["configured"])

    def test_openai_supports_scoped_key_and_model_override(self):
        with patch.dict(os.environ, {
            "SCOUT_OPENAI_API_KEY": "private-test-key",
            "SCOUT_OPENAI_MODEL": "gpt-test-model",
        }, clear=True):
            config = provider_config("chatgpt")
        self.assertEqual(config["id"], "openai")
        self.assertEqual(config["model"], "gpt-test-model")
        self.assertEqual(config["endpoint"], "https://api.openai.com/v1/chat/completions")

    def test_legacy_configuration_remains_compatible(self):
        with patch.dict(os.environ, {
            "SCOUT_LLM_API_KEY": "legacy-test-key",
            "SCOUT_LLM_MODEL": "legacy-test-model",
            "SCOUT_LLM_API_URL": "https://openrouter.ai/api/v1/chat/completions",
        }, clear=True):
            config = provider_config()
        self.assertEqual(config["id"], "legacy")
        self.assertEqual(config["model"], "legacy-test-model")
        self.assertTrue(config["configured"])

    def test_unknown_provider_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "غير معروف"):
            normalize_provider("arbitrary-url-provider")

    def test_legacy_insecure_endpoint_is_rejected(self):
        with patch.dict(os.environ, {
            "SCOUT_LLM_API_KEY": "test-key",
            "SCOUT_LLM_MODEL": "test-model",
            "SCOUT_LLM_API_URL": "http://127.0.0.1:8787/steal",
        }, clear=True):
            with self.assertRaisesRegex(RuntimeError, "HTTPS"):
                provider_config("legacy")

    def test_client_provider_status_never_exposes_api_keys(self):
        with patch.dict(os.environ, {
            "SCOUT_OPENAI_API_KEY": "do-not-return-this",
            "SCOUT_OPENAI_MODEL": "gpt-test",
            "SCOUT_GEMINI_API_KEY": "another-secret",
        }, clear=True):
            status = list_provider_status()
            serialized = repr(status)
            self.assertTrue(any(item["id"] == "openai" and item["configured"] for item in status))
            self.assertFalse(any(item["id"] == "deepseek" and item["configured"] for item in status))
            self.assertNotIn("do-not-return-this", serialized)
            self.assertNotIn("another-secret", serialized)
            self.assertTrue(any_provider_configured())


if __name__ == "__main__":
    unittest.main()
