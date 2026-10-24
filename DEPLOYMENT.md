# Deployment

## Local
Install Python 3.11+, run `pip install -r requirements.txt`, copy `.env.example` to `.env`, configure server-only values, then run `python app.py`.

## Render
Connect this repository to Render using `render.yaml`. In the host dashboard set `SCOUT_LLM_API_KEY`, `SCOUT_LLM_MODEL`, and `TAVILY_API_KEY`. Never commit them.

After deployment verify `/api/health`, perform a real search, and send a real chat request. A successful build alone does not prove provider connectivity. Free-host storage may be ephemeral; configure a persistent disk before relying on durable skill history.
