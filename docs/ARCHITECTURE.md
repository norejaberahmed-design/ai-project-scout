# Architecture

1. FastAPI serves chat, web search, skill discovery, and registry endpoints.
2. Tavily supplies broad web search; GitHub REST API supplies repository and SKILL.md discovery.
3. An OpenAI-compatible model endpoint provides chat. Credentials stay server-side.
4. Skill harvesting verifies an allowlisted license, pins an immutable commit, checks metadata, and saves proposals with attribution and original license text.
5. Proposed skills are never executed or activated automatically. Active skills are separate and are injected as untrusted bounded context.

Request flow: validate -> search evidence -> select approved skills -> model response -> sources and skills-used report.

GitHub Pages cannot run the API or persist skills. Deploy the Python API separately and configure persistent storage for durable skill records.
