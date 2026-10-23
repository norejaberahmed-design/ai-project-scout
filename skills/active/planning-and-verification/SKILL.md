---
name: planning-and-verification
description: Turn a proposed agent improvement into a small evidence-backed plan with measurable acceptance criteria and a verified result.
---

# Planning and verification

1. State the concrete user or system capability gap before proposing a change.
2. Link the gap to evidence from this repository or a source URL; popularity alone is not evidence of a capability gap.
3. Inspect the existing implementation and tests before changing anything. Prefer the smallest compatible change.
4. Define observable acceptance criteria before implementation.
5. Preserve current data, interfaces, and behavior unless the task explicitly requires a change.
6. After implementation, run the narrow regression test and the complete offline suite.
7. Report exactly what changed, which commands actually ran, their results, and what remains unverified.
8. If the evidence does not justify a useful change, return NO_CHANGE instead of inventing work.
