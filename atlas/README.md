# Atlas AI

Arabic-first discovery portal for AI tools and open-source projects.

## Features
- Live discovery through the public GitHub Search API
- Categories for agents, MCP, frameworks, RAG, local models, voice/vision, evaluation and AI applications
- Sort by stars or recently updated
- Project details with repository metadata and license field
- Local browser bookmarks
- SQLite-backed 10-minute search cache
- No cloning, installing, or executing third-party code

## Run locally
```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:10000

## Environment
- PORT (default 10000)
- GITHUB_TOKEN (optional; increases GitHub API rate limit)
- ATLAS_DB_PATH (default /tmp/atlas_catalog.db)

## Deploy
Docker-based web service. The app binds to 0.0.0.0 and reads PORT. SQLite cache and browser bookmarks are not a durable user-account database. On ephemeral hosting, server cache may be lost after restart; bookmarks remain in the user's browser.

## Data integrity and safety
Repository metadata is sourced from GitHub. Stars and descriptions are not endorsements. No third-party repository is executed or installed.


## Business decision API (foundation phase)

The following JSON endpoints are available in the current development branch:

- `POST /api/decision/analyze` — calculate a monthly ROI scenario from customer-supplied assumptions. Required fields: `monthly_volume`, `minutes_per_item`, `hourly_cost`, and `automation_rate` (0–1). Optional: `review_minutes_per_automated_item`, `software_monthly_cost`, `implementation_cost`, `amortization_months`, and `currency`.
- `POST /api/decision/compare` — compare up to 20 solution records by completeness of submitted facts (pricing, license, integration, security, support). It does not rank product quality or certify security.
- `POST /api/decision/report` — compose an unsaved report draft from a problem statement, ROI inputs, and solution records.

Example ROI request:

```json
{
  "monthly_volume": 1000,
  "minutes_per_item": 6,
  "hourly_cost": 35,
  "automation_rate": 0.5,
  "software_monthly_cost": 299,
  "currency": "SAR"
}
```

These calculations are deterministic and do not require an LLM key. Outputs are labeled as scenarios, not verified savings. The report endpoint currently returns `draft_not_saved`; authentication, durable customer/report storage, commercial-source ingestion, evidence verification, and UI integration are not yet implemented. Do not submit confidential customer information to these unauthenticated development endpoints.
