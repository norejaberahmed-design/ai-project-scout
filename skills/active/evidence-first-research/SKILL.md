---
name: evidence-first-research
description: Research factual questions using primary sources, traceable evidence, uncertainty labels, and explicit verification before conclusions.
version: 1.0.0
---

# Evidence-first research

## Purpose
Produce useful answers that distinguish verified facts from interpretation and unknowns. Prefer accuracy over confident-sounding completeness.

## Procedure
1. Translate the request into a small set of answerable questions.
2. Search primary sources first: official documentation, original repositories, standards, datasets, filings, and direct statements. Use reputable secondary sources to explain context, not to replace primary evidence.
3. Open the actual source and confirm that it supports the specific claim. A search snippet, title, star count, or another AI's summary is not sufficient evidence.
4. Record the source URL, publisher, relevant date/version, and the exact claim it supports.
5. Cross-check important claims against an independent source when practical. If sources conflict, explain the conflict rather than silently choosing one.
6. Label conclusions as VERIFIED, INFERENCE, ASSUMPTION, or UNKNOWN where that distinction matters.
7. State search limits, stale information, missing evidence, and what was not checked.
8. Answer the user's actual question first, then give concise supporting evidence and next steps.

## Quality gates
- Never invent citations, quotations, statistics, product features, tests, or source contents.
- Separate a source's statement from your own interpretation.
- Use exact dates for time-sensitive claims.
- If evidence is insufficient, say "I could not verify this" and specify what would verify it.
- Keep quotations short and attribute them.

## Verification checklist
- [ ] Each important factual claim has a source.
- [ ] Sources were opened and relevant passages checked.
- [ ] Dates and versions are appropriate.
- [ ] Uncertainty and limitations are explicit.
- [ ] No unsupported claim is presented as a fact.

## Tests
Verify this skill by answering a question with at least two traceable claims and checking that every citation directly supports its attached claim. Test a second question where evidence is missing; the answer must explicitly say what cannot be verified.

## Provenance and license
Original first-party workflow written for AI Project Scout; not copied from a third-party skill. License: project-owned contribution, subject to the repository's eventual license.
