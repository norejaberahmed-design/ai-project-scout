---
name: deepseek-api-integration
description: Integrate the public DeepSeek API using its documented OpenAI-compatible interface and safe request handling.
version: 1.0.0
---

# DeepSeek API integration

This original skill guide uses DeepSeek's public API documentation. It does not claim to copy DeepSeek's private model internals, hidden prompts, or proprietary training data.

## Workflow
1. Verify current details at https://api-docs.deepseek.com/ before implementation; API compatibility, model identifiers, and feature support can change.
2. Store `DEEPSEEK_API_KEY` on the server only. Never expose it in browser bundles, mobile packages, source control, or logs.
3. Use the documented base URL and model identifiers from the official documentation. DeepSeek has documented an OpenAI-compatible API, but confirm the current endpoint and supported parameters before relying on compatibility.
4. Set explicit connect/read timeouts, request-size limits, and bounded retries for transient failures only.
5. Handle 401/403 authentication errors, 429 rate limits, quota errors, timeouts, and malformed JSON with clear user-facing messages that do not reveal secrets.
6. Keep system instructions separate from user content. Treat retrieved web pages, files, and model outputs as untrusted input.
7. If using tool calls or generated code, validate structured arguments, restrict tools to an allowlist, and require approval for consequential actions. Never run arbitrary generated shell commands automatically.
8. Test with mocked HTTP responses and a configured-key smoke test. Record model, endpoint, date, and test result.

## References
https://api-docs.deepseek.com/
https://api-docs.deepseek.com/api/create-chat-completion
