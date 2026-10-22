"""Discover AI repositories across GitHub, track releases, and highlight new/active tools."""
import json, os, sqlite3, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("SCOUT_DB_PATH", str(ROOT / "data" / "scout.sqlite")))
REPORT_DIR = Path(os.getenv("SCOUT_REPORT_DIR", str(ROOT / "reports")))
PER_PAGE = max(1, min(int(os.getenv("SCOUT_PER_QUERY", "30")), 100))

# Multiple discovery lenses: topics, frameworks, model tooling, and newly active projects.
QUERIES = [
    "topic:artificial-intelligence", "topic:llm", "topic:ai-agents",
    "topic:generative-ai", "topic:machine-learning", "topic:computer-vision",
    "topic:speech-recognition", "topic:retrieval-augmented-generation",
    "topic:automation", "topic:developer-tools", "topic:inference",
    "topic:multimodal", "topic:open-source-llm", "topic:transformers",
    "AI agent framework", "LLM inference engine", "local AI assistant",
    "RAG evaluation framework", "AI coding agent", "multimodal model",
]
def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def api_get(url, retries=3):
    headers = {"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28","User-Agent":"ai-project-scout/0.2"}
    token = os.getenv("GITHUB_TOKEN")
    if token: headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (403,429) and attempt < retries-1:
                retry = exc.headers.get("Retry-After","")
                time.sleep(min(int(retry),30) if retry.isdigit() else 2**attempt)
                continue
            raise RuntimeError("GitHub API HTTP " + str(exc.code)) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == retries-1: raise RuntimeError("GitHub network error: " + str(exc)) from exc
            time.sleep(2**attempt)
    raise RuntimeError("GitHub API failed after retries")

def technical_score(repo):
    score=0; stars=max(0,int(repo.get("stargazers_count") or 0)); forks=max(0,int(repo.get("forks_count") or 0))
    score += 25 if stars>=1000 else 18 if stars>=250 else 10 if stars>=50 else 5 if stars>=10 else 0
    score += 15 if forks>=100 else 10 if forks>=25 else 5 if forks>=5 else 0
    lic=repo.get("license") or {}
    if lic.get("spdx_id") and lic.get("spdx_id")!="NOASSERTION": score+=15
    if repo.get("description"): score+=10
    if repo.get("language"): score+=5
    if repo.get("topics"): score+=10
    updated=repo.get("pushed_at") or repo.get("updated_at") or ""
    try:
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(updated.replace("Z","+00:00"))).days
        score += 20 if age<=30 else 12 if age<=180 else 5 if age<=365 else 0
    except (ValueError,TypeError): pass
    return min(score,100)

def init_db(path=DB_PATH):
    path.parent.mkdir(parents=True,exist_ok=True); conn=sqlite3.connect(path)
    conn.execute("""CREATE TABLE IF NOT EXISTS repositories (
      repo_id INTEGER PRIMARY KEY, full_name TEXT NOT NULL, url TEXT NOT NULL,
      description TEXT, language TEXT, stars INTEGER NOT NULL, forks INTEGER NOT NULL,
      license TEXT, created_at TEXT, updated_at TEXT, pushed_at TEXT,
      first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, query_tags TEXT NOT NULL,
      technical_score INTEGER NOT NULL, commercial_status TEXT NOT NULL DEFAULT 'NEEDS_VALIDATION')""")
    # Migrate databases created by older versions without deleting history.
    cols={row[1] for row in conn.execute("PRAGMA table_info(repositories)")}
    if "pushed_at" not in cols: conn.execute("ALTER TABLE repositories ADD COLUMN pushed_at TEXT")
    conn.execute("""CREATE TABLE IF NOT EXISTS observations (
      id INTEGER PRIMARY KEY AUTOINCREMENT, repo_id INTEGER NOT NULL, observed_at TEXT NOT NULL,
      stars INTEGER NOT NULL, forks INTEGER NOT NULL, FOREIGN KEY(repo_id) REFERENCES repositories(repo_id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS releases (
      release_id INTEGER PRIMARY KEY, repo_id INTEGER NOT NULL, tag_name TEXT, name TEXT,
      published_at TEXT, url TEXT, observed_at TEXT NOT NULL,
      FOREIGN KEY(repo_id) REFERENCES repositories(repo_id))""")
    conn.commit(); return conn

def upsert_repo(conn, repo, tags, observed):
    if repo.get("id") is None or not repo.get("full_name") or not repo.get("html_url"): return
    rid=int(repo["id"]); old=conn.execute("SELECT first_seen,query_tags FROM repositories WHERE repo_id=?",(rid,)).fetchone()
    first=old[0] if old else observed
    merged=sorted(set(json.loads(old[1]) if old else []) | set(tags))
    lic=repo.get("license") or {}
    conn.execute("""INSERT INTO repositories
      (repo_id,full_name,url,description,language,stars,forks,license,created_at,updated_at,pushed_at,first_seen,last_seen,query_tags,technical_score,commercial_status)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(repo_id) DO UPDATE SET full_name=excluded.full_name,url=excluded.url,
      description=excluded.description,language=excluded.language,stars=excluded.stars,forks=excluded.forks,
      license=excluded.license,created_at=excluded.created_at,updated_at=excluded.updated_at,
      pushed_at=excluded.pushed_at,last_seen=excluded.last_seen,query_tags=excluded.query_tags,
      technical_score=excluded.technical_score""",
      (rid,repo["full_name"],repo["html_url"],repo.get("description"),repo.get("language"),
       int(repo.get("stargazers_count") or 0),int(repo.get("forks_count") or 0),
       lic.get("spdx_id") or lic.get("name"),repo.get("created_at"),repo.get("updated_at"),
       repo.get("pushed_at"),first,observed,json.dumps(merged),technical_score(repo),"NEEDS_VALIDATION"))
    conn.execute("INSERT INTO observations(repo_id,observed_at,stars,forks) VALUES (?,?,?,?)",
      (rid,observed,int(repo.get("stargazers_count") or 0),int(repo.get("forks_count") or 0)))

def collect(conn, queries=None):
    queries=queries or QUERIES; observed=now_utc()
    stats={"queries":len(queries),"successful_queries":0,"repositories_seen":0,"errors":[]}
    for query in queries:
        url="https://api.github.com/search/repositories?"+urllib.parse.urlencode({
            "q":query+" archived:false","sort":"updated","order":"desc","per_page":PER_PAGE})
        try:
            payload=api_get(url); items=payload.get("items",[])
            if not isinstance(items,list): raise ValueError("Invalid GitHub response")
            for item in items:
                if isinstance(item,dict): upsert_repo(conn,item,[query],observed); stats["repositories_seen"]+=1
            stats["successful_queries"]+=1
        except (RuntimeError,ValueError,TypeError,KeyError) as exc:
            stats["errors"].append({"query":query,"error":str(exc)})
    conn.commit()
    stats["unique_repositories"]=conn.execute("SELECT COUNT(*) FROM repositories").fetchone()[0]
    stats["new_today"]=conn.execute("SELECT COUNT(*) FROM repositories WHERE substr(first_seen,1,10)=?",(observed[:10],)).fetchone()[0]
    stats["recently_active"]=conn.execute("SELECT COUNT(*) FROM repositories WHERE pushed_at >= datetime('now','-30 days')").fetchone()[0]
    return stats

def collect_releases(conn, limit=30):
    """Track recent releases of active discovered projects; tolerate public API limits."""
    rows=conn.execute("SELECT repo_id,full_name FROM repositories ORDER BY pushed_at DESC LIMIT ?",(limit,)).fetchall()
    stats={"repos_checked":0,"releases_found":0,"errors":[]}; observed=now_utc()
    for rid, full_name in rows:
        try:
            data=api_get("https://api.github.com/repos/"+full_name+"/releases?per_page=3")
            stats["repos_checked"]+=1
            for rel in data if isinstance(data,list) else []:
                if not rel.get("id"): continue
                conn.execute("""INSERT OR IGNORE INTO releases(release_id,repo_id,tag_name,name,published_at,url,observed_at)
                    VALUES(?,?,?,?,?,?,?)""",(int(rel["id"]),rid,rel.get("tag_name"),rel.get("name"),
                    rel.get("published_at"),rel.get("html_url"),observed))
                stats["releases_found"]+=1
        except Exception as exc: stats["errors"].append({"repository":full_name,"error":str(exc)})
    conn.commit(); return stats

def build_report(conn, stats, release_stats=None, report_dir=REPORT_DIR):
    # Backward compatibility: older callers passed report_dir as the third positional argument.
    if isinstance(release_stats, (str, Path)):
        report_dir, release_stats = release_stats, None
    # Keep reports compatible with older callers and partial/offline test fixtures.
    stats = dict(stats or {})
    stats.setdefault("queries", 0)
    stats.setdefault("successful_queries", 0)
    stats.setdefault("repositories_seen", 0)
    stats.setdefault("unique_repositories", conn.execute("SELECT COUNT(*) FROM repositories").fetchone()[0])
    stats.setdefault("new_today", 0)
    stats.setdefault("recently_active", 0)
    stats.setdefault("errors", [])
    stamp=datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_dir.mkdir(parents=True,exist_ok=True)
    rows=conn.execute("""SELECT full_name,url,description,language,stars,forks,license,updated_at,pushed_at,first_seen,query_tags,technical_score
        FROM repositories ORDER BY technical_score DESC, pushed_at DESC LIMIT 150""").fetchall()
    repos=[]
    for r in rows:
        repos.append({"repository":r[0],"url":r[1],"description":r[2],"language":r[3],"stars":r[4],"forks":r[5],
          "license":r[6],"updated_at":r[7],"pushed_at":r[8],"first_seen":r[9],"discovery_queries":json.loads(r[10]),
          "technical_score":r[11],"market_evidence":"NOT_COLLECTED","build_decision":"DO_NOT_BUILD_YET"})
    releases=conn.execute("""SELECT r.full_name, l.tag_name, l.name, l.published_at, l.url
       FROM releases l JOIN repositories r ON r.repo_id=l.repo_id
       ORDER BY l.published_at DESC LIMIT 60""").fetchall()
    recent_releases=[{"repository":x[0],"tag":x[1],"name":x[2],"published_at":x[3],"url":x[4]} for x in releases]
    payload={"generated_at":now_utc(),"scope":"GitHub repository discovery and release signals; not a market census",
      "stats":stats,"release_scan":release_stats or {},"decision_rule":"Stars/releases are discovery signals, not proof of demand or profit",
      "repositories":repos,"recent_releases":recent_releases}
    jp=report_dir/(stamp+".json"); mp=report_dir/(stamp+".md")
    jp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# تقرير كشاف أدوات الذكاء الاصطناعي — "+stamp,"",
      "> يجمع المستودعات النشطة وإشارات الإصدارات الحديثة. لا يعني ذلك أنها الأفضل أو أن لها مشترين يدفعون.","",
      "## ملخص","- استعلامات ناجحة: {}/{}".format(stats["successful_queries"],stats["queries"]),
      "- مستودعات فريدة في قاعدة البيانات: {}".format(stats["unique_repositories"]),
      "- اكتشافات جديدة اليوم: {}".format(stats["new_today"]),
      "- مستودعات ذات دفع/تحديث خلال 30 يومًا: {}".format(stats["recently_active"]),
      "- نتائج مستودعات مرصودة في هذا التشغيل: {}".format(stats["repositories_seen"]),
      "- أخطاء استعلامات GitHub: {}".format(len(stats["errors"])),
      "- الإصدارات التي رصدها الوكيل: {}".format((release_stats or {}).get("releases_found",0)),"",
      "## إصدارات حديثة — إشارات تستحق المراجعة",""]
    if recent_releases:
        for rel in recent_releases[:30]:
            lines += ["- **{}** — {} ({}) — {}".format(rel["repository"],rel["tag"] or rel["name"] or "إصدار جديد",rel["published_at"] or "التاريخ غير متوفر",rel["url"])]
    else: lines.append("لم تُجمع إصدارات في هذا التشغيل.")
    lines += ["","## مستودعات وأدوات تستحق الفحص",""]
    for i,r in enumerate(repos[:50],1):
        lines += ["### {}. [{}]({})".format(i,r["repository"],r["url"]),
          "- الوصف: "+(r["description"] or "لا يوجد وصف").replace("\n"," "),
          "- اللغة: {} | النجوم: {} | التفرعات: {}".format(r["language"] or "غير محددة",r["stars"],r["forks"]),
          "- الترخيص: {}".format(r["license"] or "غير واضح؛ تحقق من المستودع"),
          "- الحالة التجارية: NEEDS_VALIDATION — لم يتم إثبات الطلب أو الاستعداد للدفع.",
          "- آخر دفع للكود: {} | الدرجة التقنية: {}/100".format(r["pushed_at"] or "غير متوفر",r["technical_score"]),
          "- سبب الاكتشاف: "+", ".join(r["discovery_queries"]),
          "- القرار التجاري: DO_NOT_BUILD_YET — لا يوجد دليل طلب مدفوع مجمّع.",""]
    if stats["errors"] or (release_stats or {}).get("errors"):
        lines += ["## أخطاء أو تغطية ناقصة",""]
        lines += ["- GitHub {}: {}".format(e.get("query",""),e["error"]) for e in stats["errors"]]
        lines += ["- Releases {}: {}".format(e.get("repository",""),e["error"]) for e in (release_stats or {}).get("errors",[])]
    lines += ["","## حدود النسخة","- يكتشف مشاريع عامة عبر GitHub Search API ويتابع آخر الإصدارات لعدد محدود من المستودعات.",
      "- ليس مسحًا شاملًا لكل الإنترنت ولا يثبت أن المشروع جديد عالميًا.",
      "- لا يشغّل الشيفرات المكتشفة ولا يدقق أمانها.",
      "- لا يستخدم نموذجًا لغويًا بعد؛ التصنيف والدرجة قواعد بسيطة.",
      "- لا تجمع هذه النسخة أدلة العملاء أو الإيرادات أو الاستعداد للدفع.",
      "- راجع المصدر الأصلي والترخيص والتبعيات قبل الاستخدام التجاري.",""]
    mp.write_text("\n".join(lines),encoding="utf-8")
    return mp,jp

def main():
    conn=init_db()
    try:
        stats=collect(conn)
        release_stats=collect_releases(conn)
        md,js=build_report(conn,stats,release_stats)
        print(json.dumps({"stats":stats,"release_scan":release_stats,"markdown_report":str(md),"json_report":str(js)},ensure_ascii=False))
        return 0 if stats["successful_queries"] else 1
    finally: conn.close()
if __name__=="__main__": raise SystemExit(main())
