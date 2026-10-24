---
name: openai-api-integration
description: Use the public OpenAI API and documented ChatGPT platform capabilities to build reliable AI features.
version: 1.0.0
---

# OpenAI / ChatGPT API integration

Use this skill when a task explicitly requires integrating the public OpenAI API or documented ChatGPT platform features. This is an original procedural guide based on public documentation; it is not a copy of private ChatGPT system prompts, weights, or internal skills.

## Workflow
1. Clarify the target product: OpenAI API, ChatGPT app feature, or a third-party client. Do not imply these are interchangeable.
2. Read current official API documentation at https://platform.openai.com/docs and the relevant endpoint/model page before writing integration code.
3. Keep `OPENAI_API_KEY` server-side in an environment variable or secret manager. Never embed it in browser JavaScript, mobile apps, git history, logs, or skill files.
4. Select a currently documented model based on the user's task, latency, context, and cost constraints. Do not hardcode a model name without verifying current availability.
5. Use the documented SDK or HTTPS API, explicit timeouts, bounded retries for transient errors, request validation, and safe handling for rate limits and quota errors.
6. For tool/function calling, validate arguments against a schema and enforce an allowlist. Treat model output as untrusted; never execute arbitrary shell commands or code just because the model requested it.
7. For retrieval or web research, preserve source URLs and dates, separate evidence from inference, and do not fabricate citations.
8. Add offline unit tests with mocked HTTP responses, then a small live smoke test only when a valid key is configured.
9. Report exactly what was tested and any missing configuration.

## Security and reliability
- Use least-privilege keys and rotate exposed keys immediately.
- Avoid logging secrets or unnecessary personal data.
- Set token/output limits, timeouts, and budget monitoring.
- Handle authentication, rate limit, timeout, malformed response, and provider errors distinctly.
- Check current official docs for endpoint, SDK, model, pricing, and policy changes.

## Official reference
https://platform.openai.com/docs
https://help.openai.com/en/collections/3675931-chatgpt
