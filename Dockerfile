FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SCOUT_API_HOST=0.0.0.0 \
    SCOUT_API_PORT=8787

RUN addgroup --system scout && adduser --system --ingroup scout scout
WORKDIR /app

# api_server imports all four modules below; keep the runtime image self-contained.
COPY --chown=scout:scout api_server.py web_search.py skill_runtime.py github_discovery.py ./
COPY --chown=scout:scout skills/active ./skills/active

USER scout
EXPOSE 8787
CMD ["python", "-u", "api_server.py"]
