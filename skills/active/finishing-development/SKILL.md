---
name: finishing-development
description: Finish an implementation by verifying the actual final tree, preserving work, and reporting the tested result without unnecessary approval loops.
version: 1.0.0
---

# Finishing development

## Core rule
A task is finished only when the required behavior is implemented and the available verification evidence has been checked. A commit, pull request, or green syntax check alone is not proof of product readiness.

## Procedure
1. Re-read the task and acceptance criteria; compare them against the actual diff and current repository state.
2. Run the focused regression tests and the complete relevant test suite on the exact tree being delivered.
3. Run syntax, build, workflow validation, and integration smoke tests that are available in the environment. Record checks that could not run.
4. Inspect the final diff for secrets, accidental deletions, unrelated changes, unlicensed copied material, unsafe execution, and generated artifacts.
5. If a check fails, diagnose the cause, fix it, and rerun the affected check plus the relevant regression suite.
6. Integrate through the repository's established workflow. Prefer a small reviewable change and preserve existing work. Do not force-push, delete user work, or bypass required checks.
7. When authorized and checks pass, create or update a pull request or merge through the supported repository workflow without asking the user to choose among routine technical options.
8. Verify the resulting commit, CI status, and deployment state. Distinguish code committed, tests passed, workflow run, and live service verified as separate facts.
9. Provide a concise delivery report: changed capability, exact links, tests and observed outcomes, deployment state, and any user-only action still required.

## Product readiness gates
- Offline regression suite and static checks pass.
- API and frontend integration are exercised where feasible.
- External providers are only considered operational after a live request succeeds.
- Deployment is only considered complete after the published URL and health endpoint are checked.
- Secrets remain in the hosting provider's secret manager.
- External skills and components retain attribution, immutable source provenance, and license text; untrusted code is not installed or executed during discovery.

## Boundaries
- Never invent test results, service URLs, API credentials, or deployment success.
- Do not ask for confirmation for routine, reversible implementation details.
- Do not perform destructive or externally consequential actions beyond the user's authorization.
- If a user-only step is unavoidable (for example, entering a private API key in their hosting account), finish all repository-side work first and state that exact blocker.

## Upstream attribution
Adapted from obra/superpowers skill finishing-a-development-branch, revision 2ce8aa15d05bd57213e6f746f953aafb7ded7a8b, under the MIT License.
Original: https://github.com/obra/superpowers/blob/2ce8aa15d05bd57213e6f746f953aafb7ded7a8b/skills/finishing-a-development-branch/SKILL.md
See skills/proposed/finishing-a-development-branch/UPSTREAM_LICENSE.txt for the original license text.
