---
name: api-docs-writer
description: Produce accurate HTTP API reference documentation from actual route handlers, validation logic, response schemas, errors, and tests.
version: 1.0.0
---

# API Documentation Writer

Use this skill when documenting or changing an HTTP API, endpoint, request schema, response, error, or integration contract.

## Procedure

1. Inspect the actual route handler, validation, authentication/authorization checks, response-writing code, and relevant tests.
2. Record the HTTP method, path, content type, required headers, authentication, request fields, limits, and defaults.
3. Document successful responses and error responses using the status codes and payloads implemented by the code. Include rate limits and side effects when present.
4. Add minimal request and response examples based on the real contract. Never include real credentials, personal data, or fabricated fields.
5. Link each endpoint description to its source module and relevant tests where practical.
6. Compare the draft with the implementation and tests. If behavior is ambiguous or untested, label it as unknown instead of guessing.
7. When implementation changes, update the documentation and run the focused regression suite.
8. Report changed files and any contract details that remain unverified.

## Boundaries

- Do not infer a route or schema from a UI label, README, or function name alone.
- Do not publish secrets or private customer data in examples.
- Do not describe a mocked integration as live.
- Keep documentation aligned with the actual deployed version; state when deployment has not been checked.

## Upstream provenance

Adapted from api-docs-writer in the MIT-licensed zhuyansen/agent-skills-hub repository. See ATTRIBUTION.md and UPSTREAM_LICENSE.txt.
