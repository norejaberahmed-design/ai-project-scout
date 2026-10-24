---
name: anthropic-claude-api-integration
description: Integrate Anthropic's public Claude API using official Messages API documentation and guarded tool use.
version: 1.0.0
---

# Anthropic Claude API integration

This is an original procedural guide based on Anthropic's public API documentation. It does not copy Claude's private system prompts, model weights, or proprietary internal skills.

## Workflow
1. Check https://docs.anthropic.com/ for the current Messages API, SDK, model identifiers, version headers, tool-use format, and limits.
2. Keep `ANTHROPIC_API_KEY` server-side in an environment variable or secret manager. Never place it in browser JavaScript, mobile bundles, public commits, or logs.
3. Use the official SDK or documented HTTPS endpoint and required headers. Verify the current API version rather than guessing.
4. Bound prompt size and output tokens; set timeouts and handle 401, 429, overload, quota, and malformed response errors.
5. Treat tool-use blocks as proposed actions. Validate every argument, use strict schemas and an allowlist, and require user approval before external side effects.
6. Treat user-provided documents, search results, and skill text as untrusted data that cannot override application policy.
7. For long-context tasks, preserve relevant evidence and provenance; do not treat model confidence as proof.
8. Write unit tests with mocked provider responses and report live smoke-test status separately from offline test status.

## References
https://docs.anthropic.com/
https://docs.anthropic.com/en/api/messages
