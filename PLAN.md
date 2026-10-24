# V2 implementation plan

## Mission
Build one useful agent: it searches the public web, answers with evidence, discovers reusable skills, and applies approved skills to later user requests.

## Engineering laws
1. Evidence before assertions: include links when research is requested or facts may have changed.
2. Separation of concerns: UI, API, providers, search, skill discovery, validation, and selection are independent modules.
3. Least privilege: discovery may read public source material; it may not execute or install source code.
4. Provenance: every proposal records canonical repository, immutable commit, file path, SPDX license, license text, and SHA-256.
5. Fail closed: missing keys, unknown licenses, malformed metadata, oversized content, suspicious instructions, and network errors must be explicit.
6. Trust boundary: discovery creates proposals; activation is explicit.
7. Reproducibility: bounded requests, deterministic checks, offline tests, and CI.
8. No false completion: never claim tests or deployment that did not actually happen.

## Architecture
- `site/index.html`: Arabic RTL mobile-first UI; research, agent chat, source cards, skills catalogue.
- `app.py`: Flask routes, request validation, size limits, CORS, explicit API errors.
- `scout/config.py`: server-only environment configuration.
- `scout/search.py`: Tavily adapter, normalized and deduplicated source links.
- `scout/skills.py`: GitHub repository discovery, license checks, SKILL.md validation, quarantine, provenance, approval.
- `scout/agent.py`: select relevant active skills, attach bounded search evidence, call model, return citations.
- `scout/providers.py`: OpenAI-compatible model adapter with timeouts and bounded input.
- `tests/`: offline unit tests.
- `.github/workflows/ci.yml`: compile and test.
- `Dockerfile` and `render.yaml`: deployment path.

## Algorithms
### Web research
Validate query (1–500 chars) → call Tavily with bounded result count and timeout → normalize and deduplicate URLs → pass bounded source evidence to model → return answer and source metadata. If search is unavailable, return an explicit setup error.

### Skill discovery
Search GitHub repositories → skip archived projects and forks → require allowlisted SPDX license → pin default branch to commit SHA → inspect repository tree → select at most three small SKILL.md files → fetch at immutable revision → parse YAML → validate name, description, size and risk markers → compute SHA-256 → save as proposal with attribution and original license text. Never execute imported content.

### Skill selection
Tokenize user request and each active skill's name/description → score lexical overlap → select at most four relevant skills → include instructions as untrusted task guidance under fixed system policy.

### Activation
Require valid metadata, allowlisted license, license text, immutable revision, provenance and matching digest → explicit approval moves proposal to active directory → never overwrite an active skill silently.

## Delivery gates
1. Fresh rebuild branch and architecture.
2. Search/provider adapters and explicit missing-key behavior.
3. Skill harvesting, provenance and quarantine.
4. Agent uses active skills and returns sources.
5. Offline tests and CI.
6. Deployment instructions and real live verification.
A gate is complete only after its checks actually run.
