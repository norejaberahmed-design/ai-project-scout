"""Flask entry point for AI Project Scout V2."""
from flask import Flask, jsonify, request, send_from_directory
from scout import config
from scout.agent import answer_task
from scout.providers import ProviderError
from scout.search import SearchError, web_search
from scout.skills import SkillError, approve_skill, discover_skills, list_skills

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

@app.after_request
def security_headers(response):
    origin = request.headers.get("Origin", "").rstrip("/")
    if origin and origin in config.allowed_origins():
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    return response

@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error":"REQUEST_TOO_LARGE","message":"Request body exceeds 64 KB."}), 413

@app.get("/")
def index():
    return send_from_directory(config.SITE_DIR, "index.html")

def json_body():
    if not request.is_json:
        raise ValueError("Content-Type must be application/json")
    body = request.get_json(silent=False)
    if not isinstance(body, dict):
        raise ValueError("JSON object required")
    return body

@app.get("/api/health")
def health():
    skills = list_skills()
    return jsonify({"status":"ok",
        "model_configured":bool(config.setting("SCOUT_LLM_API_KEY") and config.setting("SCOUT_LLM_MODEL")),
        "web_search_configured":bool(config.setting("TAVILY_API_KEY")),
        "github_token_configured":bool(config.setting("GITHUB_TOKEN")),
        "active_skills":len(skills["active"]), "proposed_skills":len(skills["proposed"])})

@app.post("/api/search")
def search():
    try:
        body = json_body(); query = body.get("query","")
        if not isinstance(query,str) or not query.strip() or len(query)>500:
            return jsonify({"error":"INVALID_QUERY","message":"Query must contain 1–500 characters."}),400
        count = body.get("max_results")
        if count is not None and (not isinstance(count,int) or isinstance(count,bool) or count not in range(1,9)):
            return jsonify({"error":"INVALID_RESULT_COUNT","message":"max_results must be 1–8"}),400
        results = web_search(query,count)
        return jsonify({"query":query,"results":results,"count":len(results)})
    except ValueError as exc:
        return jsonify({"error":"INVALID_REQUEST","message":str(exc)}),400
    except SearchError as exc:
        return jsonify({"error":str(exc).split(":",1)[0],"message":str(exc)}),503

@app.post("/api/chat")
def chat():
    try:
        body=json_body(); query=body.get("query",""); use_search=body.get("search_web",False)
        if not isinstance(query,str): return jsonify({"error":"INVALID_QUERY","message":"query must be text"}),400
        if not isinstance(use_search,bool): return jsonify({"error":"INVALID_SEARCH_FLAG","message":"search_web must be boolean"}),400
        return jsonify(answer_task(query,body.get("history",[]),use_search))
    except ValueError as exc:
        return jsonify({"error":"INVALID_REQUEST","message":str(exc)}),400
    except SearchError as exc:
        return jsonify({"error":str(exc).split(":",1)[0],"message":str(exc)}),503
    except ProviderError as exc:
        return jsonify({"error":str(exc).split(":",1)[0],"message":str(exc)}),503

@app.get("/api/skills")
def skills():
    return jsonify(list_skills())

@app.post("/api/skills/discover")
def discover():
    try:
        body=json_body(); limit=body.get("max_proposals",2)
        if not isinstance(limit,int) or isinstance(limit,bool) or limit not in (1,2,3):
            return jsonify({"error":"INVALID_LIMIT","message":"max_proposals must be 1, 2, or 3"}),400
        return jsonify(discover_skills(limit))
    except SkillError as exc:
        return jsonify({"error":"SKILL_DISCOVERY_FAILED","message":str(exc)}),502
    except (ValueError,TypeError) as exc:
        return jsonify({"error":"INVALID_REQUEST","message":str(exc)}),400

@app.post("/api/skills/<name>/approve")
def approve(name):
    admin_token = config.setting("SCOUT_ADMIN_TOKEN")
    supplied = request.headers.get("Authorization", "")
    if not admin_token or supplied != "Bearer " + admin_token:
        return jsonify({"error":"UNAUTHORIZED","message":"Admin approval token is missing or invalid."}), 401
    try: return jsonify(approve_skill(name))
    except FileNotFoundError as exc: return jsonify({"error":"PROPOSAL_NOT_FOUND","message":str(exc)}),404
    except FileExistsError as exc: return jsonify({"error":"ALREADY_ACTIVE","message":str(exc)}),409
    except (ValueError,OSError,KeyError) as exc: return jsonify({"error":"APPROVAL_REJECTED","message":str(exc)}),400

if __name__=="__main__":
    app.run(host=config.setting("SCOUT_API_HOST","0.0.0.0"),
        port=int(config.setting("SCOUT_API_PORT","8080")),debug=False)
