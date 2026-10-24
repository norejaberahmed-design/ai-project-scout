# Security policy

- Never commit provider keys or tokens.
- Never expose secrets in browser code, results, skills, logs, or API responses.
- Restrict production CORS to the frontend origin and use HTTPS.
- Bound requests and provider timeouts.
- Accept public repositories only, with allowlisted SPDX metadata and verified license text.
- Copy Markdown SKILL.md documents only; reject invalid YAML, oversized files, unsafe names and suspicious directives.
- Never execute upstream code, install dependencies, or let imported skills invoke tools directly.
- Treat skill text as untrusted and subordinate to fixed system policy.
- Approval must never overwrite an existing active skill.
- Preserve immutable revision, source path, license evidence, and SHA-256.
- On failure, return explicit errors; never invent search results.
