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
