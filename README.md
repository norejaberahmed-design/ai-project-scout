# AI Project Scout — Rebuild V2

A mobile-first Arabic AI agent focused on real web research and discovering reusable agent skills, validating them, and applying approved skills to user tasks.

## Run locally
Python 3.11+: `pip install -r requirements.txt`, copy `.env.example` to `.env`, configure server-side keys, then `python app.py`. Open http://127.0.0.1:8080.

## Server environment
- `SCOUT_LLM_API_KEY`, `SCOUT_LLM_MODEL`, optional `SCOUT_LLM_API_URL`
- Optional `TAVILY_API_KEY` for Tavily search; without it, the app attempts free DuckDuckGo search
- optional `GITHUB_TOKEN` to increase GitHub API limits for skill discovery

## API
- `GET /api/health`
- `POST /api/search` — Tavily search with source URLs
- `POST /api/chat` — model response with optional search evidence and active skills
- `GET /api/skills`
- `POST /api/skills/discover`
- `POST /api/skills/<name>/approve`

## Recent agent improvements

- The chat agent now detects Arabic and English research intent automatically, even when the optional chat search toggle is off.
- If web search fails, the response explicitly warns that sources were not verified; it does not silently present the answer as researched.
- If the model provider is unavailable but web results were found, the UI can still display the real source links and snippets instead of discarding the search.
- When `GITHUB_TOKEN` is configured on the server, discovery searches GitHub Code Search for actual `SKILL.md` files, then checks repository licensing and pinned revisions. Without a token, public repository search remains the fallback.
- A generic builder/research skill no longer blocks discovery of a more specialized skill; discovered procedures remain proposals and are never executed as imported code.

## Principles
Search results are real backend calls, not simulated. General web search and GitHub skill discovery are separate. Only Markdown SKILL.md files can be proposed. External code is never executed or installed. Proposals preserve immutable source revision, attribution, license text and SHA-256; explicit approval is required before use. Secrets remain server-side.

See [PLAN.md](PLAN.md), [ARCHITECTURE.md](ARCHITECTURE.md), [SECURITY.md](SECURITY.md), and [DEPLOYMENT.md](DEPLOYMENT.md).

Built-in provider skill list: [SKILLS_CATALOG.md](SKILLS_CATALOG.md). The four initial public-API integration skills cover OpenAI/ChatGPT, DeepSeek, Google Gemini, and Anthropic Claude. External skill discovery supports up to 10 proposals per run. The main search interface is conversational: it sends questions to the model with web search enabled and shows the answer with source links.

GitHub Pages cannot run the Python API. Deploy to Render or another Python-capable host, then enter its HTTPS API URL in the interface under «إعداد اتصال خادم الذكاء الاصطناعي». A successful build does not prove live provider connectivity; verify health, search and chat after deployment. Free-host filesystems may be ephemeral.
