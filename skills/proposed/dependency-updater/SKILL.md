---
name: dependency-updater
description: "Plan dependency upgrades: which packages are behind, which have breaking changes, in what order."
---

# Dependency Updater

Plan dependency upgrades: which packages are behind, which have breaking changes, in what order.

## When to use
Use this skill when the user asks for it by name or describes this task. Do not use it for unrelated work.

## Steps
1. Read the input the user points to. If none is given, ask for the file or text.
2. Do the task described above, step by step, and keep the user's own wording where it matters.
3. Show the result, then a short list of what you changed or found, so the user can check it.

## Notes
- Keep changes small and reversible.
- Say plainly when the input is incomplete instead of guessing.

## Source provenance
- Original repository: https://github.com/zhuyansen/agent-skills-hub
- Original file: https://github.com/zhuyansen/agent-skills-hub/blob/55a0c19b4ff2986eaf8ff28e2ff629fd26567e63/ops/skillmgr-runs/in/input/library/dependency-updater/SKILL.md
- Immutable source revision: 55a0c19b4ff2986eaf8ff28e2ff629fd26567e63
- Declared SPDX license: MIT
- Import status: untrusted proposal; not executed, installed, or activated.
- The original license text is preserved in UPSTREAM_LICENSE.txt.
- No additional eligible support files were bundled.
