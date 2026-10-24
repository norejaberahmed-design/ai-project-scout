# Skills catalogue

This catalogue lists the four built-in provider-integration skills added to the application. They are original procedural guides based on public documentation, not copies of private system prompts, model weights, proprietary training data, or hidden internal skills.

| Skill | What it helps with | Primary public documentation |
|---|---|---|
| `chatgpt-openai-api-integration` | Use the public OpenAI API and documented ChatGPT platform capabilities; protect keys, validate tools, test integrations. | https://platform.openai.com/docs |
| `deepseek-api-integration` | Use DeepSeek's documented API and compatibility surface with secure keys and bounded requests. | https://api-docs.deepseek.com/ |
| `google-gemini-api-integration` | Integrate Google's Gemini API/SDK and safely handle modalities and tool calls. | https://ai.google.dev/gemini-api/docs |
| `anthropic-claude-api-integration` | Integrate Claude's Messages API and guard tool-use operations. | https://docs.anthropic.com/ |

## How skills are stored

- Built-in provider skills: `skills/active/<skill-name>/SKILL.md`.
- Publicly discovered external skills: `skills/proposed/<skill-name>/SKILL.md` until explicitly approved.
- Each built-in skill has a `manifest.json` with the official documentation URL and its authored-guide status.
- The application selects relevant active skills based on the user's task and returns their names in `skills_used`.

## Discover more open-source skills

The skill discovery endpoint searches GitHub repositories for public `SKILL.md` documents. Each candidate must pass repository-license allowlisting, matching license-text checks, immutable revision pinning, metadata validation, size limits, and risk-marker checks. A single discovery request can now propose up to 10 skills. Results that fail checks are skipped with reasons.

External skills remain proposals. They are not automatically trusted or activated, and this app does not execute arbitrary code from a discovered repository.

## Important boundary

ChatGPT, DeepSeek, Gemini, and Claude are products/models; their private internal prompts, model weights, training data, and proprietary internal skills are not public source code to clone. This application integrates their public documented APIs and can collect independently published, license-eligible community skills. It must not claim to have copied proprietary internals.
