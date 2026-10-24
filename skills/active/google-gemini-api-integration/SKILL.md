---
name: google-gemini-api-integration
description: Build features with Google's public Gemini API and official SDK documentation, with secure keys and bounded tool use.
version: 1.0.0
---

# Google Gemini API integration

This is an original procedure based on Google's public Gemini API documentation, not a copy of private Gemini system prompts, model weights, or internal skills.

## Workflow
1. Check current documentation at https://ai.google.dev/gemini-api/docs and verify model names, supported modalities, API version, SDK, quotas, and safety options.
2. Keep `GEMINI_API_KEY` in a server-side environment variable or secret manager. Never ship it in frontend code or commit it to a repository.
3. Use the currently documented Google Gen AI SDK or REST endpoint; do not assume older SDKs or retired model IDs remain supported.
4. Validate input size and supported MIME types before sending text, image, audio, or video content.
5. Apply documented safety settings appropriately, but also enforce application-level policy and output validation.
6. For function calling, validate arguments against strict schemas and allowlisted operations. Model-proposed tool calls are requests, not authorization.
7. Add timeouts, bounded retries, quota/rate-limit handling, and safe logging. Do not log keys or sensitive prompts.
8. Unit-test request construction and error mapping with mocked responses; only claim live verification after a real configured-key test.
9. Cite primary sources for research and label uncertainty rather than inventing facts.

## References
https://ai.google.dev/gemini-api/docs
https://ai.google.dev/gemini-api/docs/quickstart
