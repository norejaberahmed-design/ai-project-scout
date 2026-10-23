---
name: repository-security-review
description: Review code repositories for security, privacy, secret exposure, unsafe execution, dependency risk, and least-privilege failures.
version: 1.0.0
---

# Repository security review

## Purpose
Identify actionable risks using read-only inspection and evidence. This is a focused review, not a guarantee that software is secure.

## Procedure
1. Establish scope, architecture, entry points, trust boundaries, sensitive data, and deployment model.
2. Inspect configuration, authentication and authorization, input validation, file/network access, subprocess use, deserialization, template rendering, logging, dependency manifests, CI workflows, and secret handling.
3. Search for credentials and risky patterns without reproducing secret values. If a real secret is found, report its file/location safely and recommend revocation and rotation.
4. Trace untrusted inputs to sensitive operations. Distinguish a suspicious pattern from an exploitable vulnerability; state preconditions and impact.
5. Check whether external content (repositories, skill documents, prompts, web pages) can override system rules, trigger tool use, leak secrets, or write to trusted paths.
6. Prefer static inspection and isolated tests. Never execute untrusted code merely to see what it does.
7. Rank findings by severity and practical exploitability. Include file/line evidence, scenario, impact, fix, and regression test.
8. Re-check each proposed fix for new risks and preserve existing behavior.

## Required safeguards
- Never print, commit, or send secrets to an external service.
- Do not run destructive commands or modify production data.
- Do not grant external skills automatic runtime activation.
- Validate hashes/provenance before activating reviewed skill content.
- Use least privilege, bounded input/output, timeouts, and explicit approval for sensitive actions.

## Output
For each finding: severity, confidence, evidence location, exploit scenario, impact, recommended fix, and verification test. Include "no finding observed in inspected scope" rather than "secure" when appropriate.

## Tests
Use safe fixtures containing fake secrets and malicious instruction text. Confirm that scanning detects the fixture without revealing secret values, and verify that untrusted skill content cannot become active without explicit review.

## Provenance and license
Original first-party workflow written for AI Project Scout; not copied from a third-party skill. License: project-owned contribution, subject to the repository's eventual license.
