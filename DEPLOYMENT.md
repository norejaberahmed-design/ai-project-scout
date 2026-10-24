# Deployment

## Important architecture fact

GitHub Pages is a static file host. It cannot run Flask/Python, search GitHub on behalf of the app, call a model with server-held secrets, or persist acquired skill files. The interface therefore defaults to the Render service URL `https://ai-project-scout-v2.onrender.com`, but this URL only works after the Render Blueprint has actually been created and deployed.

## Create the backend service

1. Open [Render Dashboard](https://dashboard.render.com/).
2. Choose **New → Blueprint** and connect this repository: `norejaberahmed-design/ai-project-scout`.
3. Let Render read the repository's `render.yaml` and create the `ai-project-scout-v2` web service.
4. In the Render service's Environment settings, set:
   - `SCOUT_LLM_API_KEY`: secret API key for a compatible model provider.
   - `SCOUT_LLM_MODEL`: exact model identifier enabled for that key.
   - `SCOUT_ADMIN_TOKEN`: a strong random administrative token.
   - Optional `GITHUB_TOKEN`: improves GitHub API rate limits and code search access.
5. Deploy and wait for the service to become **Live**.
6. Open `https://ai-project-scout-v2.onrender.com/api/health`. It should return JSON with `status: "ok"` and `model_configured: true`.
7. Open [the GitHub Pages interface](https://norejaberahmed-design.github.io/ai-project-scout/). It automatically tries the default Render URL. If you use another Render hostname, open **إعداد اتصال الخادم** and save that HTTPS base URL.

## Verify the complete workflow

1. Check that the interface status changes to **الخادم متصل**.
2. Click **اكتشاف مهارات جديدة من GitHub**. The report must show the repositories considered, skill documents inspected, and any new proposals.
3. Submit a real task, e.g. ask it to implement a small Python function and tests. Confirm the response lists skills used when applicable.
4. Inspect the skill cards and verify the original source link and license evidence for any discovered procedure.

## Limitations to understand

- A successful GitHub Pages workflow only deploys the static interface; it does not deploy the Flask API.
- This repository includes a Render Blueprint, but committing `render.yaml` does not create a Render service by itself. The service must be created from the Render dashboard.
- Model credentials must be configured on Render. Without them, the agent cannot generate task responses.
- The free Render filesystem may be ephemeral. Skills discovered during a running instance may disappear after restart or redeploy. Durable skill retention requires persistent storage or a repository-backed persistence mechanism.
- General web search is intentionally not part of the primary interface; discovery focuses on public GitHub skill repositories.
- Do not put API keys or administrative tokens in GitHub Pages, the repository, or the browser's local storage.
