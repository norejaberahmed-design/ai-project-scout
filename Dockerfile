FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV SCOUT_API_HOST=0.0.0.0
ENV SCOUT_API_PORT=8787
WORKDIR /app
COPY api_server.py web_search.py skill_runtime.py ./
COPY skills/active ./skills/active
EXPOSE 8787
CMD ["python", "api_server.py"]
