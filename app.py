"""Flask entry point for AI Project Scout V2."""
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify, request, send_from_directory
import time
from scout import config
from scout.agent import answer_task, summarize_search_results
from scout.providers import ProviderError
from scout.search import SearchError, web_search
from scout.skills import SkillError, approve_skill, discover_skills, list_skills

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
_PUBLIC_DISCOVERY_COOLDOWN_SECONDS = 900
_last_public_discovery_at = 0.0

@app.after_request
def security_headers(response):
    origin = request.headers.get("Origin", "").rstrip("/")
    if origin and origin in config.allowed_origins():
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
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
        "web_search_configured":True, "web_search_provider":"tavily" if config.setting("TAVILY_API_KEY") else "duckduckgo-fallback",
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
        payload = {"query":query,"results":results,"count":len(results),"answer":None}
        if config.setting("SCOUT_LLM_API_KEY") and config.setting("SCOUT_LLM_MODEL") and results:
            try:
                payload["answer"] = summarize_search_results(query, results)
            except ProviderError:
                payload["summary_warning"] = "تم جلب نتائج الويب، لكن تعذر إنشاء الملخص الذكي. تحقق من إعداد مزود النموذج."
        elif results:
            payload["summary_warning"] = "تم جلب نتائج الويب. أضف إعداد النموذج على الخادم لتفعيل الملخص الذكي."
        return jsonify(payload)
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

def admin_authorized():
    token = config.setting("SCOUT_ADMIN_TOKEN")
    return bool(token) and request.headers.get("Authorization", "") == "Bearer " + token

@app.post("/api/skills/discover")
def discover():
    global _last_public_discovery_at
    is_admin = admin_authorized()
    try:
        body=json_body(); limit=body.get("max_proposals",2)
        max_allowed = 10 if is_admin else 2
        if not isinstance(limit,int) or isinstance(limit,bool) or limit not in range(1,max_allowed+1):
            return jsonify({"error":"INVALID_LIMIT","message":f"max_proposals must be an integer from 1 to {max_allowed}"}),400
        # Public users can trigger small, bounded GitHub-only discovery runs without
        # an admin token. A process-wide cooldown protects API quota and storage.
        if not is_admin and _last_public_discovery_at > 0:
            now = time.monotonic()
            remaining = _PUBLIC_DISCOVERY_COOLDOWN_SECONDS - (now - _last_public_discovery_at)
            if remaining > 0:
                return jsonify({
                    "error":"DISCOVERY_COOLDOWN",
                    "message":f"Public skill discovery is rate-limited. Try again in about {int(remaining)+1} seconds."
                }),429
        if not is_admin:
            # Start the cooldown before network work so repeated failures cannot
            # hammer GitHub's unauthenticated API quota.
            _last_public_discovery_at = time.monotonic()
        result = discover_skills(limit)
        result["access_mode"] = "admin" if is_admin else "public_limited"
        return jsonify(result)
    except SkillError as exc:
        return jsonify({"error":"SKILL_DISCOVERY_FAILED","message":str(exc)}),502
    except (ValueError,TypeError) as exc:
        return jsonify({"error":"INVALID_REQUEST","message":str(exc)}),400

@app.post("/api/skills/<name>/approve")
def approve(name):
    if not admin_authorized():
        return jsonify({"error":"UNAUTHORIZED","message":"Admin token is required for skill approval."}), 401
    try: return jsonify(approve_skill(name))
    except FileNotFoundError as exc: return jsonify({"error":"PROPOSAL_NOT_FOUND","message":str(exc)}),404
    except FileExistsError as exc: return jsonify({"error":"ALREADY_ACTIVE","message":str(exc)}),409
    except (ValueError,OSError,KeyError) as exc: return jsonify({"error":"APPROVAL_REJECTED","message":str(exc)}),400

if __name__=="__main__":
    app.run(host=config.setting("SCOUT_API_HOST","0.0.0.0"),
        port=int(config.setting("SCOUT_API_PORT","8080")),debug=False)
