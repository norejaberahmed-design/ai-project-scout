---
name: code-review-loop
description: "Complete an authorized pull or merge request review loop: fix findings, validate and push changes, link fix commits in replies, resolve addressed threads, and request another review. Use for end-to-end review remediation or repeated review until clean, across review platforms."
license: MIT
metadata:
  author: dpalfery
  version: 0.1.0
---

# Code Review Loop

Follow [code-review-loop.md](code-review-loop.md) for the workflow. Preserve the user's
chosen PR, reviewer, and authorization scope. Do not resolve a finding until its fix
is verified on the PR branch and its reply links to the pushed commit.

## Source provenance
- Original repository: https://github.com/dpalfery/kyber-weave
- Original file: https://github.com/dpalfery/kyber-weave/blob/0351a45c1a78021886d7e3a48c6b3dcd46076dba/products/kyber-squad/skills/code-review-loop/SKILL.md
- Immutable source revision: 0351a45c1a78021886d7e3a48c6b3dcd46076dba
- Declared SPDX license: MIT
- Import status: untrusted proposal; not executed, installed, or activated.
- The original license text is preserved in UPSTREAM_LICENSE.txt.
- Related source/document files are bundled under bundle/ for review only.
