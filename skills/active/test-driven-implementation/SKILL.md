---
name: test-driven-implementation
description: Implement the smallest maintainable code change using explicit acceptance criteria, focused regression tests, and verified test results.
version: 1.0.0
---

# Test-driven implementation

## Purpose
Turn a request into a small, reviewable change that is demonstrably correct without replacing working architecture unnecessarily.

## Procedure
1. Inspect the existing repository, contribution rules, entry points, tests, and current behavior before editing.
2. Write down acceptance criteria and constraints. Preserve current data, API contracts, authentication, and project structure unless a change is required.
3. Reproduce the reported problem or write a failing regression test before changing implementation when feasible.
4. Make the smallest change that satisfies the acceptance criteria. Avoid unrelated refactors and unnecessary dependencies.
5. Add or update tests for the expected behavior, boundary cases, invalid input, and failure paths.
6. Run targeted tests first, then the full relevant suite, lint/type checks, syntax/build checks, and integration smoke tests available in the environment.
7. Inspect the final diff for accidental deletions, secrets, generated junk, skipped tests, and untested claims.
8. Report exactly what ran and passed, what was mocked, what was skipped, and what remains unverified.

## Completion rules
- A test result must come from an actual command or CI result, not expectation.
- Mocked provider tests do not prove that a live external provider works.
- A successful build does not prove functional correctness.
- Do not hide failures or weaken tests merely to obtain a green run.
- Do not mark work complete while a required check is pending or failing.
- Do not merge unless required checks pass and repository policy permits it.

## Tests
Introduce a controlled bug in a disposable test fixture and verify the regression test fails before the fix and passes after it. Run the relevant suite and ensure no unrelated tests were removed or skipped.

## Provenance and license
Original first-party workflow written for AI Project Scout; not copied from a third-party skill. License: project-owned contribution, subject to the repository's eventual license.
