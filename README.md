# SkillForge — AI Agent Skill Acquisition

SkillForge is a focused AI agent that discovers reusable English-language agent skills from public GitHub repositories, checks source/license metadata and skill structure, stores eligible procedures as proposals, and selects relevant skills to help carry out a user's task.

## Product scope
1. User submits a task in Arabic or English.
2. The agent selects the most relevant available skills.
3. If no specialized skill fits, it searches public GitHub repositories for `SKILL.md` files and proposes eligible skills.
4. It validates metadata, license evidence, provenance, and basic prompt-injection markers.
5. It supplies relevant skill procedures to the configured language model to assist with the task.
6. It reports which skills were used and whether discovery succeeded.

This is **not** a general web-search product. Skill discovery targets GitHub repositories. The task interface does not silently search the wider web.

## Run locally
Python 3.11+: `pip install -r requirements.txt`, copy `.env.example` to `.env`, configure server-side keys, then run `python app.py`. Open http://127.0.0.1:8080.

## Server environment
- `SCOUT_LLM_API_KEY`, `SCOUT_LLM_MODEL`, optional `SCOUT_LLM_API_URL`
- Optional `GITHUB_TOKEN` to improve GitHub API access and skill discovery limits
- `SCOUT_ADMIN_TOKEN` for administrative approval endpoints; keep it server-side
- `SCOUT_ALLOWED_ORIGINS` for browser CORS

## Main API
- `GET /api/health`
- `POST /api/chat` — task execution using selected skill procedures
- `GET /api/skills`
- `POST /api/skills/discover` — search GitHub for public skill documents
- `POST /api/skills/<name>/approve` — administrative approval

## Safety and limits
- Each imported skill proposal includes a static reverse-engineering report (procedure headings/steps, repository structure, dependency manifests, tests, and likely entry points), source attribution, immutable revision, verified license text, and hashes. A bounded set of related text/source files from the skill directory may be preserved under `supporting_files/`; those files are hash-checked before being supplied as context and are never executed.
- General executable libraries are not yet auto-installed or run. That requires a separate isolated package sandbox and explicit activation; discovery must not execute arbitrary upstream code.
- Only public GitHub repositories and eligible `SKILL.md` documents are considered.
- A source must have an allowlisted license with matching license text.
- Source revision, attribution, and a content digest are preserved where available.
- Imported procedures are untrusted instructions. External source code is never installed or executed automatically.
- A discovered procedure can inform a task before permanent approval, but is clearly marked as proposed.
- A language-model API key and model name are required for task execution. Keep secrets on the server, never in the browser.
- Free hosting may use ephemeral filesystems; locally discovered skills can be lost on restart unless persistent storage or repository-backed persistence is configured.

## Deployment
See [DEPLOYMENT.md](DEPLOYMENT.md) and [render.yaml](render.yaml). GitHub Pages serves only the static interface; the Flask API must be deployed separately. The interface defaults to the Render service URL declared by this project and checks its health automatically. A configured URL does not prove the service has been created or is online: verify `/api/health` and run a task after deployment.

## Architecture and testing
See [ARCHITECTURE.md](ARCHITECTURE.md), [SECURITY.md](SECURITY.md), [PLAN.md](PLAN.md), and [SKILLS_CATALOG.md](SKILLS_CATALOG.md). Tests run in GitHub Actions via `pytest`.


## GitHub AI Ecosystem Catalog (catalog-only mode)

The `/agents` page provides a broad catalog of public open-source AI projects. Discovery lanes include agents, MCP servers/tools, developer tools, frameworks/SDKs, RAG and knowledge systems, vector search, local models and inference servers, evaluation/observability, voice/audio, vision, and AI applications. It searches GitHub repository metadata and a bounded number of README files, classifies results by project type and category, and stores findings in SQLite at `data/agents.sqlite3` (override with `SCOUT_AGENT_DB_PATH`). The catalog works without an LLM key; a model is only needed for SkillForge chat/task execution.

- `POST /api/agents/discover` — bounded public GitHub ecosystem discovery; request JSON: `{"query":"","max_results":100}`. Up to eight discovery lanes and 35 README inspections are used per run to stay within unauthenticated GitHub API quotas.
- `GET /api/agents` — search/filter catalog with `q`, `category`, `kind`, `sort`, `limit`, and `offset`.
- `GET /api/agents/<github_id>` — one catalog record and its evidence.
- `GET /api/agents/status` — local catalog and latest discovery-run status.

Discovery is metadata and README inspection only. It does not clone repositories, install dependencies, execute upstream code, contact maintainers, or integrate agents. Categories and scores are heuristic signals, not proof of capability, safety, or runtime behavior. This GitHub-first catalog does not cover every proprietary SaaS product; a separate web-research source is needed for closed commercial services. GitHub's declared SPDX license is recorded as metadata, not independently certified by this catalog.

In catalog-only mode, normal chat requests no longer trigger background skill harvesting. Existing approved active skills remain available to the current assistant workflow.
