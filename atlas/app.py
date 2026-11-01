import json
import os
import sqlite3
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
DB_PATH = os.environ.get("ATLAS_DB_PATH", "/tmp/atlas_catalog.db")
GITHUB_API = "https://api.github.com/search/repositories"
CATEGORIES = {
    "all": ("كل المجالات", "AI"),
    "agents": ("الوكلاء الذكيون", "AI agent OR autonomous agent"),
    "mcp": ("خوادم وأدوات MCP", "MCP server OR model context protocol"),
    "frameworks": ("الأطر والمكتبات", "AI framework OR LLM framework"),
    "rag": ("البحث والمعرفة RAG", "RAG OR retrieval augmented generation"),
    "models": ("النماذج والتشغيل المحلي", "local LLM OR inference engine"),
    "voice": ("الصوت والرؤية", "voice AI OR speech recognition OR computer vision"),
    "evaluation": ("التقييم والمراقبة", "LLM evaluation OR LLM observability"),
    "apps": ("تطبيقات الذكاء الاصطناعي", "AI application OR generative AI"),
}

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS search_cache (
        cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at INTEGER NOT NULL
    )""")
    return conn

def github_search(query, category, sort):
    key = json.dumps([query, category, sort], ensure_ascii=False)
    now = int(time.time())
    conn = db()
    row = conn.execute("SELECT payload, created_at FROM search_cache WHERE cache_key=?", (key,)).fetchone()
    if row and now - row["created_at"] < 600:
        conn.close()
        return json.loads(row["payload"]), True
    category_query = CATEGORIES.get(category, CATEGORIES["all"])[1]
    terms = query.strip() if query.strip() else category_query
    if category != "all" and query.strip():
        terms = f"({query.strip()}) {category_query}"
    params = urllib.parse.urlencode({
        "q": f"{terms} in:name,description,readme",
        "sort": sort if sort in ("stars", "updated", "help-wanted-issues") else "stars",
        "order": "desc",
        "per_page": 24
    })
    url = GITHUB_API + "?" + params
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Atlas-AI-Discovery/1.0"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(str(exc))
    items = []
    for repo in raw.get("items", []):
        items.append({
            "id": repo.get("id"),
            "name": repo.get("name", ""),
            "full_name": repo.get("full_name", ""),
            "description": repo.get("description") or "لا يوجد وصف منشور لهذا المشروع.",
            "url": repo.get("html_url", ""),
            "stars": repo.get("stargazers_count", 0),
            "language": repo.get("language") or "غير محدد",
            "updated_at": repo.get("updated_at", ""),
            "license": (repo.get("license") or {}).get("spdx_id") or "غير محدد",
            "topics": repo.get("topics", [])[:5],
            "forks": repo.get("forks_count", 0),
            "open_issues": repo.get("open_issues_count", 0),
            "archived": repo.get("archived", False),
            "owner": (repo.get("owner") or {}).get("login", "")
        })
    payload = {"items": items, "total": raw.get("total_count", 0),
               "source": "GitHub Search API", "fetched_at": datetime.now(timezone.utc).isoformat()}
    conn.execute("INSERT OR REPLACE INTO search_cache VALUES (?, ?, ?)",
                 (key, json.dumps(payload, ensure_ascii=False), now))
    conn.commit()
    conn.close()
    return payload, False

@app.get("/")
def home():
    return render_template("index.html", categories=CATEGORIES)

@app.get("/api/health")
def health():
    try:
        conn = db()
        conn.execute("SELECT 1")
        conn.close()
        return jsonify({"status": "ok", "app": "Atlas AI", "database": "ok"})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

@app.get("/api/categories")
def categories():
    return jsonify([{"id": key, "name": value[0]} for key, value in CATEGORIES.items()])

@app.get("/api/discover")
def discover():
    query = request.args.get("q", "")[:120]
    category = request.args.get("category", "all")
    sort = request.args.get("sort", "stars")
    if category not in CATEGORIES:
        category = "all"
    try:
        payload, cached = github_search(query, category, sort)
        payload["cached"] = cached
        return jsonify(payload)
    except Exception as exc:
        message = str(exc)
        status = 429 if "HTTP Error 403" in message or "HTTP Error 429" in message else 502
        return jsonify({"error": "تعذر جلب النتائج الحية من GitHub حالياً.", "detail": message[:240]}), status

@app.get("/robots.txt")
def robots():
    return "User-agent: *\nAllow: /\n", 200, {"Content-Type": "text/plain"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
