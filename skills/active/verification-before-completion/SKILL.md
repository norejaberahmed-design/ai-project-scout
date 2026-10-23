---
name: verification-before-completion
description: Verify implementation, test, build, and integration claims against fresh evidence before reporting success or marking work complete.
version: 1.0.0
---

# Verification Before Completion

## Core rule

Do not claim that a change works, a test passes, a bug is fixed, or a task is complete unless the relevant verification has actually been run and its result inspected.

## Verification procedure

1. Identify the exact observable behavior or claim that needs proof.
2. Select the narrowest command or check that can verify it, plus broader checks required by the repository.
3. Run the check on the current code state. A previous run does not prove later edits.
4. Read the output and exit status; confirm the result matches the claim.
5. If the check fails, report the failure accurately, diagnose it, make a focused fix, and rerun the relevant checks.
6. Inspect the final diff and ensure it contains the intended change, tests, source attribution, and no secrets or unrelated edits.
7. Distinguish unit tests, mocked external services, live integrations, successful builds, and actual deployment health. They prove different things.
8. Report what was verified, what was not run, and any remaining blocker.

## Common evidence requirements

- Tests pass: provide the actual test run showing zero failures.
- Build succeeds: run the build and inspect its exit status.
- Bug fixed: reproduce or test the original failure mode and confirm it now passes.
- External service works: perform a real request; mocked tests alone are insufficient.
- Deployment works: check the deployed URL and health endpoint.
- Task complete: compare the requested behavior with the actual final tree and relevant verification results.

## Boundaries

- Never invent test output, URLs, sources, or deployment status.
- Do not weaken or delete tests simply to get a green result.
- Do not claim success while a required check is pending or failing.
- Keep verification proportional to risk; avoid needless commands that do not add evidence.
- Report uncertainty plainly and continue fixing issues when authorized.

## Upstream provenance

Adapted from verification-before-completion in the MIT-licensed obra/superpowers repository. The original skill was shortened and adjusted for this agent's tools and workflow. See ATTRIBUTION.md and UPSTREAM_LICENSE.txt.
