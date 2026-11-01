"""Read-only Flask API for the local GitHub AI-agent catalog."""
import time
from flask import Blueprint, jsonify, request
from . import catalog

agents_api = Blueprint("agents_api", __name__)
COOLDOWN = 900
_last_run = 0.0

@agents_api.get("/api/agents")
def list_agents():
    try:
        return jsonify(catalog.list_agents(
            query=request.args.get("q", ""), category=request.args.get("category", ""),
            kind=request.args.get("kind", ""), sort=request.args.get("sort", "relevance"),
            limit=int(request.args.get("limit", "50")), offset=int(request.args.get("offset", "0"))))
    except (ValueError, TypeError) as exc:
        return jsonify({"error": "INVALID_REQUEST", "message": str(exc)}), 400

@agents_api.get("/api/agents/<int:github_id>")
def agent_detail(github_id):
    item = catalog.get_agent(github_id)
    if item is None:
        return jsonify({"error": "NOT_FOUND", "message": "Agent not found in the local catalog."}), 404
    return jsonify(item)

@agents_api.get("/api/agents/status")
def agents_status():
    return jsonify(catalog.discovery_status())

@agents_api.post("/api/agents/discover")
def discover_agents():
    global _last_run
    try:
        body = request.get_json(silent=False)
        if not isinstance(body, dict):
            return jsonify({"error": "INVALID_REQUEST", "message": "JSON object required"}), 400
        query, limit = body.get("query", ""), body.get("max_results", 60)
        if not isinstance(query, str) or len(query) > 180:
            return jsonify({"error": "INVALID_QUERY", "message": "query must be text up to 180 characters"}), 400
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            return jsonify({"error": "INVALID_LIMIT", "message": "max_results must be 1–100"}), 400
        now = time.monotonic()
        remaining = COOLDOWN - (now - _last_run)
        if _last_run and remaining > 0:
            return jsonify({"error": "DISCOVERY_COOLDOWN", "message": f"Try again in about {int(remaining)+1} seconds."}), 429
        _last_run = now
        return jsonify(catalog.discover_agents(query=query, max_results=limit))
    except catalog.DiscoveryError as exc:
        return jsonify({"error": "AGENT_DISCOVERY_FAILED", "message": str(exc)}), 502
    except (ValueError, TypeError) as exc:
        return jsonify({"error": "INVALID_REQUEST", "message": str(exc)}), 400
