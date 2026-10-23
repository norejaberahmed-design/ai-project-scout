# Algorithms

## General search
Validate the query, call Tavily with a bounded result count, normalize title/URL/snippet/date, deduplicate URLs, and surface provider errors without fabricating results.

## Skill discovery
Search GitHub repository metadata with several queries; skip forks and archived repos; allow only MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, and 0BSD; pin the current commit SHA; read the repository license text and tree at that SHA; retrieve bounded SKILL.md files; validate YAML frontmatter, name, description, size, and suspicious instructions; store a proposal with provenance, hash, attribution, and license. Never execute imported code.

## Reverse engineering
Create a capability profile from public docs and inspectable code: task, input/output contract, workflow, dependencies, limitations, and risks. Reimplement documented behavior where practical. Never claim knowledge of closed internals or copy code without license permission.

## Skill use
Rank active skills lexically against the user query, select at most three, add them as untrusted context, and report which were used. Trusted policy always wins.
