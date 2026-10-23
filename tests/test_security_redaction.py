import io
import unittest
from contextlib import redirect_stdout

import api_server
from security_redaction import REDACTED, redact_text, redact_value


class SecurityRedactionTests(unittest.TestCase):
    def test_redacts_common_credentials_and_sensitive_query_parameters(self):
        private_key = "-----BEGIN RSA PRIVATE KEY-----\nFAKE_PRIVATE_MATERIAL_123\n-----END RSA PRIVATE KEY-----"
        github_token = "ghp_" + "A" * 36
        openai_token = "sk-proj-" + "B" * 32
        jwt = "eyJ" + "C" * 20 + ".eyJ" + "D" * 20 + "." + "E" * 20
        text = (
            private_key + "\n" + github_token + "\n" + openai_token + "\n"
            + "Authorization: Bearer " + "F" * 32 + "\n"
            + jwt + "\nhttps://user:password@example.org/path"
            + "\npassword=hunter2 api_key=FAKE_API_KEY_123"
            + "\nhttps://example.org/?access_token=FAKE_QUERY_TOKEN&ok=1"
        )
        safe = redact_text(text)
        for secret in [
            "FAKE_PRIVATE_MATERIAL_123", github_token, openai_token,
            "F" * 32, jwt, "user:password", "hunter2",
            "FAKE_API_KEY_123", "FAKE_QUERY_TOKEN",
        ]:
            self.assertNotIn(secret, safe)
        self.assertIn(REDACTED, safe)

    def test_redact_value_handles_nested_response_objects(self):
        value = {"error": "api_key=FAKE_SECRET_123", "sources": [{"url": "https://x.test/?token=FAKE_TOKEN_123"}]}
        safe = redact_value(value)
        self.assertNotIn("FAKE_SECRET_123", str(safe))
        self.assertNotIn("FAKE_TOKEN_123", str(safe))
        self.assertEqual(len(safe["sources"]), 1)

    def test_actual_http_log_output_is_redacted_before_stdout(self):
        handler = object.__new__(api_server.AgentHandler)
        handler.client_address = ("127.0.0.1", 1234)
        fake_token = "ghp_" + "Z" * 36
        output = io.StringIO()
        with redirect_stdout(output):
            handler.log_message('request="%s" status=%s', "Authorization: Bearer " + fake_token, 200)
        persisted_log = output.getvalue()
        self.assertNotIn(fake_token, persisted_log)
        self.assertNotIn("Bearer " + fake_token, persisted_log)
        self.assertIn(REDACTED, persisted_log)


if __name__ == "__main__":
    unittest.main()
