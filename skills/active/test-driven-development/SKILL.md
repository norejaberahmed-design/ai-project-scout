---
name: test-driven-development
description: Require a focused failing regression test before implementing a new behavior, then prove the change with repeatable tests.
---

# Test-driven development

1. Identify the smallest externally observable behavior that is missing or broken.
2. Add a focused regression test that fails for the current implementation for the intended reason.
3. Implement only the behavior needed to satisfy that test; avoid unrelated refactors.
4. Test normal inputs, missing data, malformed inputs, and boundary conditions relevant to the change.
5. Run the focused test, then the full offline test suite and syntax checks.
6. Do not claim tests passed unless their command output confirms success.
7. If a test cannot run in the current environment, label it NOT RUN and explain why.
