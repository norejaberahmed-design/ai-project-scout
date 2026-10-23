# Product Roadmap: General Web Research + Agent Skill Learning

## Mission
AI Project Scout has exactly two core responsibilities:
1. Research a user's question across the public web and return a useful synthesized answer with clickable evidence.
2. Discover reusable AI-agent skills and open implementations, preserve provenance/licensing, test candidates safely, and make approved skills available to later user tasks.

It is not a GitHub-only finder. GitHub is one source among many.

## Architecture
- `site/index.html`: mobile-first Arabic chat UI, source cards, loading/error states, configurable API endpoint.
- `api_server.py`: server-side chat orchestration; all provider secrets remain server-side.
- `web_search.py`: provider adapter for broad web search (Tavily initially); return normalized results and honest coverage metadata.
- `github_discovery.py`: supplementary code/repository discovery only, never the sole general search path.
- `skill_harvester.py`: find procedural `SKILL.md` files in licensed public repositories and approved public sources; pin immutable revisions and preserve attribution/license text.
- `skill_registry.py`: lifecycle registry and provenance.
- `skill_runtime.py`: relevance selection and active skill loading. Imported instructions remain untrusted and are never allowed to override system policy.
- `skills/proposed/`: quarantine. `skills/active/`: only reviewed, tested and explicitly activated procedures.
- GitHub Actions: scheduled/manual discovery, regression tests, artifacts and review PRs; no imported code execution.

## Search acceptance criteria
1. A normal question (not containing GitHub/AI/project keywords) must be sent to broad web search.
2. General answers must not fall back to Wikipedia-only or GitHub-only results while pretending to be equivalent to ChatGPT/Gemini/Claude.
3. If backend/API configuration is absent, show an explicit, actionable configuration error; do not return misleading limited results as if they were complete.
4. When configured, return an LLM-synthesized answer, at least one source when search has results, and transparent provider/coverage metadata.
5. A search provider error must be visible and actionable; never silently disguise it as successful search.
6. Secrets must never be placed in the static frontend or repository.

## Skill-learning acceptance criteria
1. Search public agent skill collections and public learning material; GitHub is a useful initial source, not the entire discovery universe.
2. Do not scrape or copy full YouTube videos, paid/private materials, or non-redistributable code. YouTube can be used to discover a tutorial and its linked public source repository; copy only from the original public source after license checks.
3. Every imported skill must have an immutable source revision, content hash, original attribution, and preserved license text.
4. Static prompt-injection and secret checks are required; candidate skill text is untrusted data.
5. Skill documents may be staged automatically, but executable code/dependencies are never installed or executed automatically.
6. A candidate becomes active only after syntax/format checks, capability-specific tests, risk review, license verification, and an explicit lifecycle transition.
7. The runtime should select relevant active skills for the current task, report which skill procedures were used, and never claim a capability merely because a skill document exists.

## Delivery phases
- P0: fix misleading frontend fallback and make search configuration/health state explicit.
- P1: verify general search API integration and answer generation; test ordinary non-GitHub queries.
- P2: strengthen discovery of reusable procedural skills and source attribution; retain quarantine.
- P3: regression tests for search routing, provider failures, prompt injection and skill lifecycle.
- P4: deploy backend, configure provider secrets, and perform a live end-to-end test.
- P5: verify the scheduled workflow and document exact operational limitations.

## Definition of done
The product is done only when the published UI can answer an ordinary non-GitHub question through the deployed broad-web-search backend, provide clickable evidence, discover and stage at least one eligible licensed skill, and pass regression tests. A repository commit or a successful unit test alone is not proof of live deployment.