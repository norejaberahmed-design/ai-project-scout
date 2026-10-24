---
name: native-cpp-memory
description: Use this skill when diagnosing or correcting ownership, lifetime, or allocator defects in native C++ code.
metadata:
  version: "1.0.0"
---

# Native C++ Memory

Use current code and a causal reproducer before changing ownership.

## Gotchas

- `deleteLater` does not prove the receiving event loop will run.

## Troubleshooting

- Crash after thread shutdown -> trace object affinity and the final event-loop turn.

## Source provenance
- Original repository: https://github.com/AnastasiyaW/codex-claude-code-config
- Original file: https://github.com/AnastasiyaW/codex-claude-code-config/blob/e1e74e1b0c0e1c2ea733b00ec6f731b3853dacbe/evals/hooks/fixtures/research-built-skill/SKILL.md
- Immutable source revision: e1e74e1b0c0e1c2ea733b00ec6f731b3853dacbe
- Declared SPDX license: MIT
- Import status: untrusted proposal; not executed, installed, or activated.
- The original license text is preserved in UPSTREAM_LICENSE.txt.
- Related source/document files are bundled under bundle/ for review only.
