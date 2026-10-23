---
name: changelog-writer
description: Write evidence-based release notes from actual code changes, commits, tests, and version history.
version: 1.0.0
---

# Changelog Writer

Use this skill when preparing a CHANGELOG entry, release notes, a version summary, or a user-facing explanation of changes.

## Procedure

1. Inspect the actual diff and commit history for the requested release range. Use the last release tag when one exists; otherwise state the comparison range used.
2. Group verified changes under Added, Changed, Fixed, and Security when those headings are relevant.
3. Describe user-visible behavior rather than internal refactors alone. Keep each entry concise and actionable.
4. Confirm bug-fix claims against the relevant test or verification result. A commit title alone is not proof that a defect is fixed.
5. Mention compatibility changes, configuration requirements, migrations, removed features, and known limitations.
6. Exclude secrets, private data, speculative improvements, and changes not present in the diff.
7. Preserve the project's existing changelog format and ordering. Do not invent version numbers or release dates.
8. Compare every entry with the source diff before finalizing.

## Boundaries

- Do not claim deployment or release publication unless it was verified.
- Distinguish implemented, tested, merged, and deployed changes.
- If the comparison range or release version is unknown, state the uncertainty instead of guessing.

## Upstream provenance

Adapted from changelog-writer in the MIT-licensed zhuyansen/agent-skills-hub repository. See ATTRIBUTION.md and UPSTREAM_LICENSE.txt.
