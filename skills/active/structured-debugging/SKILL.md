---
name: structured-debugging
description: Diagnose software failures from reproducible evidence, logs, environment details, and minimal experiments instead of guessing.
version: 1.0.0
---

# Structured debugging

## Purpose
Find the root cause of a failure efficiently while preserving existing work and avoiding random edits.

## Procedure
1. Capture the exact error, stack trace, command, expected behavior, actual behavior, environment, and most recent change.
2. Reproduce the failure with the smallest reliable command or test. If it cannot be reproduced, state that limitation.
3. Identify the failing layer: UI, network, API, database/schema, dependency, environment, permissions, configuration, or external provider.
4. Form a short list of hypotheses and choose a diagnostic that distinguishes among them. Prefer logs, health checks, schema inspection, and read-only commands before modifying code.
5. Trace the failing value or call through the relevant code path. Do not assume the first error line is the root cause.
6. Make one focused change at a time and preserve a rollback path. Avoid changing multiple unrelated files before retesting.
7. Run the original reproduction, targeted regression tests, and broader checks where practical.
8. Explain root cause, evidence, fix, validation performed, and remaining uncertainty in plain language.

## Safety
- Back up important data before migrations or destructive changes.
- Never recommend deleting databases, resetting repositories, or overwriting configuration as a first diagnostic step.
- Do not ask users to expose API keys, passwords, tokens, or private records.
- Redact sensitive values in logs and screenshots.
- Separate a confirmed root cause from a plausible hypothesis.

## Tests
Give the skill an error whose cause is a missing database table and verify that it inspects schema/migrations before proposing data deletion. Give it a provider timeout and verify it checks network/configuration and bounded retries rather than rewriting the application.

## Provenance and license
Original first-party workflow written for AI Project Scout; not copied from a third-party skill. License: project-owned contribution, subject to the repository's eventual license.
