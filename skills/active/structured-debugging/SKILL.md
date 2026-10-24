---
name: structured-debugging
description: Debug software errors, inspect tracebacks, identify root causes, fix defects, and verify regression tests.
version: 1.0.0
---
# Structured debugging

1. Reproduce the reported failure and capture the exact error.
2. Trace the error to its first causal condition rather than patching only the visible symptom.
3. Inspect relevant callers, data shapes, configuration, and environment assumptions.
4. Make the smallest safe fix that addresses the root cause.
5. Add a regression test that fails before the fix and passes after it.
6. Run the focused test first, then the full relevant suite.
7. State remaining uncertainties and do not claim success without test evidence.
