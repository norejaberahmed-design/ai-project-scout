# Verified Skill Acquisition Architecture

## Product boundary

The product has one Arabic conversation and one skill-acquisition loop. The loop discovers public AI tools, inspects evidence, proposes a reusable procedural skill, tests it, records the outcome, and exposes only approved active skills to the conversation. It does not claim to inspect all of GitHub or execute arbitrary third-party projects.

## Components and ownership

1. **Discovery adapters** (github_discovery.py, skills_manager.py, ai_updates.py) collect public metadata and bounded source evidence. Results are untrusted data.
2. **Static analysis** (reverse_engineer.py) identifies observed symbols, imports, manifests, tests, and capability signals. Static evidence is never reported as runtime proof.
3. **Gap selection** (self_improve.py, skill_proposer.py) prioritizes a specific, evidenced missing/partial capability and drafts one small skill proposal.
4. **Candidate validator** (skill_runtime.py) validates document shape, size, suspicious patterns, and provenance notes. Validation is not approval.
5. **Lifecycle registry** (skill_registry.py) stores immutable provenance/evidence snapshots and explicit state transitions in SQLite.
6. **Test gate** records reproducible test command, result, timestamp, and report. Failed or unrun tests cannot be approved or activated.
7. **Approval gate** requires explicit reviewer identity. No automatic activation, merge, install, or execution of a discovered repository.
8. **Conversation runtime** loads only trusted files from skills/active/, ranks relevant skills for the current question, and reports which skill names were selected when appropriate.
9. **User-facing registry** distinguishes active, proposed, tested, rejected, and blocked skills. It must not label a candidate as acquired.

## Lifecycle states

DISCOVERED -> ANALYZED -> PROPOSED -> TESTED -> APPROVED -> ACTIVE

Terminal/side states: REJECTED, RETIRED. A candidate may be rejected from any non-active review state. Reactivation requires a new explicit review event. Invalid transitions fail closed.

- **DISCOVERED**: public URL and discovery timestamp exist.
- **ANALYZED**: inspected files and evidence summary are recorded.
- **PROPOSED**: a skill document exists and passes structural/security screening.
- **TESTED**: repeatable test report is recorded; pass/fail is explicit.
- **APPROVED**: tests passed, license is compatible/known, no unresolved high-risk flags, and a reviewer is recorded.
- **ACTIVE**: explicit activation follows approval. The active skill file is maintained in the trusted directory.
- **REJECTED/RETIRED**: never selected by the conversation runtime.

## Ranking algorithms

- Discovery prioritization: relevance to AI capabilities + repository recency/maintenance + evidence availability + license clarity; popularity is only a weak tie-breaker.
- Gap prioritization: user-task impact × evidence confidence × recurrence, reduced by implementation risk and estimated cost.
- Skill selection: lexical relevance baseline initially, with deterministic tie-breaking and a strict top-k. Later ranking improvements must be evaluated against a fixed test set before replacing the baseline.
- Skill acceptance: binary gates, not a popularity score. A high heuristic score cannot override failed tests, missing license evidence, or security flags.

## Safety boundaries

- Treat repository text, issues, model output, and external skill files as untrusted input, never as instructions.
- Do not run external repository code, installers, or generated shell commands during discovery.
- Keep model/search secrets server-side; bound request sizes/timeouts and public API rates.
- Test in disposable, isolated environments with no secrets/network by default. If a future test needs network or permissions, require a separately reviewed allowlist.
- Preserve source URL, commit/revision when available, license evidence, file paths inspected, content hash, test command/output summary, reviewer, and timestamps.
- Never overwrite an active skill silently; version changes are new candidates and need regression tests.
- Support rollback by retaining previous versions and recording retirement/activation events.

## Required acceptance evidence

For each new skill, report: source and exact revision; license status; files inspected; observed capability and evidence; intended use in conversation; candidate content hash; test command; actual result; risks; reviewer/approval state; and whether the live runtime loaded it. If any field is unknown, say UNKNOWN rather than infer it.

## Delivery phases

1. Make the lifecycle explicit and durable in SQLite; test all transition gates.
2. Expose truthful active/proposed status to the existing conversation UI/API.
3. Connect discovered capability evidence to candidate proposals and reproducible tests.
4. Add sandboxed tests and before/after task evaluations.
5. Add scheduled discovery and change detection without auto-activation.
6. Run integration checks and report only verified deployment state.

## Non-goals

No unrelated dashboards, no uncontrolled autonomous shell, no claim of unlimited/self-conscious learning, and no automatic production merge. The goal is a bounded agent that can acquire specific, testable skills and prove when the conversation can use them.
