# Deployment

## Local
Install Python 3.11+, run `pip install -r requirements.txt`, copy `.env.example` to `.env`, configure server-only values, then run `python app.py`.

## Render
Connect this repository to Render using `render.yaml`. In the host dashboard set `SCOUT_LLM_API_KEY`, `SCOUT_LLM_MODEL`, and `SCOUT_ADMIN_TOKEN`. `TAVILY_API_KEY` is optional; without it, the app attempts free DuckDuckGo search. Never commit secrets.

After deployment verify `/api/health`, perform a real search, and send a real chat request. A successful build alone does not prove provider connectivity. Free-host storage may be ephemeral; configure a persistent disk before relying on durable skill history.

## GitHub Pages + remote API

GitHub Pages serves the browser interface only; it cannot run the Flask/Python API. The main search box now works as a conversational assistant: it sends the question and recent conversation to `POST /api/chat` with web search enabled, then displays the model's answer, selected skills, and source links together.

1. Deploy this repository as a Render Blueprint using `render.yaml`.
2. In Render, set `SCOUT_LLM_API_KEY`, `SCOUT_LLM_MODEL`, and `SCOUT_ADMIN_TOKEN` in the service's environment. Keep these secrets on the server. `TAVILY_API_KEY` is optional because DuckDuckGo is the fallback search provider.
3. Wait until the service is live and verify `https://YOUR-SERVICE.onrender.com/api/health`. Then test a real `POST /api/chat` request or use the interface.
4. Open the GitHub Pages site, expand **إعداد اتصال خادم الذكاء الاصطناعي**, enter the service's HTTPS base URL (without a trailing slash), and tap **حفظ واختبار الاتصال**. The browser stores only this public URL, not API secrets.
5. Ask a question in the main box. The assistant should return an answer with web source links. If the server URL is missing, the interface now explains that Pages alone cannot run the API.

CORS must allow `https://norejaberahmed-design.github.io` (already listed in the supplied Render Blueprint). If the browser reports a network/CORS error, check the Render service status, the exact HTTPS URL, and `SCOUT_ALLOWED_ORIGINS`.
