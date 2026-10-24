# System architecture

```text
Mobile browser (Arabic RTL)
       |
Flask API: validation, size limits, CORS
       |-----------------------|
Tavily web search       GitHub skill discovery
       |                       |
normalized citations    immutable SKILL.md proposal
       |                       |
Agent orchestrator      license + static checks
       |                       |
OpenAI-compatible LLM   proposal --explicit approval--> active skills
       |
answer + citations + selected skill names
```

## Request flow
1. UI submits JSON to Flask.
2. API validates content type, fields, and lengths.
3. Agent optionally searches the web and sends bounded evidence to the model.
4. Relevant active skills are selected and treated as untrusted task guidance subordinate to fixed system policy.
5. Response includes answer, source metadata, and selected skill names.

## Storage
- `skills/active/<slug>/SKILL.md`: approved instruction-only skill.
- `skills/proposed/<slug>/SKILL.md`: quarantined candidate.
- `ATTRIBUTION.md`, `UPSTREAM_LICENSE.txt`, `manifest.json`: provenance and license record.
- Filesystem storage is the initial portable version. Persistent volume/database is required for durable hosted use.

## Trust boundaries
User prompts, search results, and imported skills are untrusted. API keys remain server-side. Upstream executable code is never imported or run. Activation is explicit.
