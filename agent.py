"""AI Project Scout research agent: public-web leads + GitHub signals, without fake market claims."""
import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from scout import collect, init_db

ROOT = Path(__file__).resolve().parent
REPORT_DIR = Path(os.getenv("SCOUT_REPORT_DIR", str(ROOT / "reports")))
USER_AGENT = "AI-Project-Scout/0.2 (market research; contact: repository README)"
MAX_RESULTS_PER_QUERY = 5


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_queries(idea, buyer="الشركات الصغيرة والمتوسطة", market="السعودية"):
    """Create bounded search queries; they are search leads, not verified evidence."""
    idea = " ".join(idea.split()).strip()
    buyer = " ".join(buyer.split()).strip() or "الشركات"
    market = " ".join(market.split()).strip() or "السعودية"
    if not idea:
        raise ValueError("يجب إدخال فكرة أو مشكلة للبحث عنها.")
    return [
        f'"{idea}" {market} شركة مشكلة',
        f'"{idea}" {buyer} تكلفة حل',
        f'{idea} software pricing competitors',
        f'{idea} alternative manual process business',
        f'{idea} customer complaints review',
        f'{idea} SaaS pricing',
    ]


def fetch_search_rss(query, timeout=15):
    """Fetch Bing RSS search results using only Python standard library."""
    url = "https://www.bing.com/search?format=rss&q=" + urllib.parse.quote(query)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(2_000_000)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        raise RuntimeError(f"تعذر الوصول إلى بحث الويب: {exc}") from exc
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise RuntimeError("استجابة البحث ليست RSS/XML صالحًا.") from exc
    items = []
    for item in root.findall(".//item")[:MAX_RESULTS_PER_QUERY]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = re.sub(r"\s+", " ", (item.findtext("description") or "")).strip()
        if title and link.startswith(("https://", "http://")):
            items.append({"title": title, "url": link, "snippet": description, "query": query})
    return items


def deduplicate_results(results):
    unique = {}
    for item in results:
        url = item.get("url", "").strip()
        if url and url not in unique:
            unique[url] = item
    return list(unique.values())


def commercial_scorecard(web_results):
    """Score observable search signals; never infer payment willingness from snippets."""
    all_text = [(r.get("title", "") + " " + r.get("snippet", "")).lower() for r in web_results]
    pricing_terms = ("pricing", "price", "سعر", "أسعار", "اشتراك", "cost", "تكلفة")
    complaint_terms = ("complaint", "problem", "issue", "مشكلة", "معاناة", "شكوى", "review")
    competitor_terms = ("alternative", "competitor", "بديل", "منافس")
    pricing_count = sum(any(term in item for term in pricing_terms) for item in all_text)
    complaint_count = sum(any(term in item for term in complaint_terms) for item in all_text)
    competitor_count = sum(any(term in item for term in competitor_terms) for item in all_text)
    dimensions = [
        {"name": "إشارات تسعير", "score": min(25, pricing_count * 5), "max": 25, "evidence_count": pricing_count},
        {"name": "إشارات مشكلة أو شكاوى", "score": min(30, complaint_count * 6), "max": 30, "evidence_count": complaint_count},
        {"name": "إشارات بدائل أو منافسين", "score": min(20, competitor_count * 5), "max": 20, "evidence_count": competitor_count},
        {"name": "نتائج مرتبطة بالبحث", "score": 10 if web_results else 0, "max": 10, "evidence_count": len(web_results)},
        {"name": "دليل مباشر على الاستعداد للدفع", "score": 0, "max": 15, "evidence_count": 0},
    ]
    return {
        "score": sum(d["score"] for d in dimensions), "max_score": 100,
        "label": "إشارات بحث أولية — ليست احتمال نجاح", "dimensions": dimensions,
        "verified_paying_customers": 0, "willingness_to_pay_verified": False,
        "interpretation": "الدرجة لترتيب أولوية البحث فقط. لا تثبت الطلب أو الربح؛ يلزم التحقق مع مشترين ودليل دفع فعلي."
    }


def make_report(idea, buyer, market, web_results, github_stats, errors, generated_at=None):
    """Conservative conclusions: search snippets are leads, never proof of willingness to pay."""
    generated_at = generated_at or utc_now()
    scorecard = commercial_scorecard(web_results)
    competitors = [r for r in web_results if any(word in (r["title"] + " " + r["snippet"]).lower()
                   for word in ("pricing", "price", "سعر", "أسعار", "اشتراك", "cost", "alternative", "بديل"))]
    complaints = [r for r in web_results if any(word in (r["title"] + " " + r["snippet"]).lower()
                  for word in ("complaint", "problem", "issue", "مشكلة", "معاناة", "شكوى", "review"))]
    return {
        "generated_at": generated_at,
        "idea": idea,
        "target_buyer": buyer,
        "market": market,
        "agent_mode": "research_assistant",
        "sources": {"web_search": "Bing RSS search", "technical_discovery": "GitHub Search API"},
        "web_results": web_results,
        "commercial_scorecard": scorecard,
        "possible_competitor_or_pricing_leads": competitors,
        "possible_problem_or_review_leads": complaints,
        "github_scan": github_stats,
        "errors": errors,
        "market_evidence": "LEADS_ONLY_NOT_VERIFIED",
        "willingness_to_pay": "NOT_VERIFIED",
        "build_decision": "DO_NOT_BUILD_YET",
        "decision_reason": "Search results are leads, not proof of paying customers. Interview buyers and test a paid pilot before building.",
        "next_actions": [
            "Contact at least 10 target buyers and record their exact problem and current workaround.",
            "Verify each competitor, pricing page, and source URL manually; search snippets may be incomplete.",
            "Ask qualified buyers for a paid pilot or deposit; compliments and survey interest are not payment evidence.",
            "Estimate acquisition, hosting, API, support, and delivery costs before calculating profit.",
        ],
    }


def render_markdown(report):
    lines = [
        "# تقرير وكيل كشاف الفرص",
        "",
        f"- الفكرة: {report['idea']}",
        f"- المشتري المستهدف: {report['target_buyer']}",
        f"- السوق: {report['market']}",
        f"- وقت التقرير: {report['generated_at']}",
        "",
        "## القرار الحالي: DO_NOT_BUILD_YET",
        "",
        "نتائج البحث إشارات أولية فقط. لم يتم إثبات وجود مشترين يدفعون أو وجود ربح.",
        "",
        "## نتائج البحث على الويب",
        "",
    ]
    if not report["web_results"]:
        lines.append("لم تُسترجع نتائج ويب. لا تعتبر ذلك دليلًا على غياب السوق؛ تحقق من الاتصال وأعد المحاولة.")
    for i, item in enumerate(report["web_results"], 1):
        lines += [f"### {i}. [{item['title']}]({item['url']})", f"- استعلام البحث: {item['query']}",
                  f"- المقتطف: {item['snippet'] or 'لا يوجد مقتطف'}", ""]
    lines += ["## اكتشاف GitHub التقني", "",
              f"- الاستعلامات الناجحة: {report['github_scan'].get('successful_queries', 0)}/{report['github_scan'].get('queries', 0)}",
              f"- مستودعات فريدة في قاعدة البيانات: {report['github_scan'].get('unique_repositories', 0)}",
              "- النجوم والتفرعات ليست دليلًا على الطلب التجاري.", "",
              "## بوابة التحقق قبل البناء", ""]
    lines.extend(f"{i}. {action}" for i, action in enumerate(report["next_actions"], 1))
    if report["errors"]:
        lines += ["", "## أخطاء أثناء البحث", ""] + [f"- {e}" for e in report["errors"]]
    lines += ["", "## حدود الوكيل", "",
              "- يبحث في Bing RSS وGitHub فقط؛ لا يقرأ الويب كله.",
              "- لا يتصل بالعملاء ولا يرسل رسائل نيابة عنك.",
              "- لا يثبت الاستعداد للدفع ولا يضمن الربح.",
              "- لا ينفذ مستودعات أو شيفرات خارجية.",
              "- تحقق من المصادر والأسعار وتاريخها بنفسك.", ""]
    return "\n".join(lines)


def run_agent(idea, buyer="الشركات الصغيرة والمتوسطة", market="السعودية", search_fn=None, github_fn=None, report_dir=None):
    queries = build_queries(idea, buyer, market)
    search_fn = search_fn or fetch_search_rss
    github_fn = github_fn or _scan_github
    errors, results = [], []
    for query in queries:
        try:
            results.extend(search_fn(query))
        except (RuntimeError, ValueError, urllib.error.URLError) as exc:
            errors.append(f"بحث الويب [{query}]: {exc}")
    try:
        github_stats = github_fn()
    except Exception as exc:
        github_stats = {"queries": 0, "successful_queries": 0, "unique_repositories": 0, "errors": [str(exc)]}
        errors.append(f"مسح GitHub: {exc}")
    report = make_report(idea, buyer, market, deduplicate_results(results), github_stats, errors)
    output_dir = Path(report_dir or REPORT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", idea).strip("-")[:35] or "idea"
    json_path = output_dir / f"agent-{safe_name}-{stamp}.json"
    md_path = output_dir / f"agent-{safe_name}-{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return report, md_path, json_path


def _scan_github():
    db_path = Path(os.getenv("SCOUT_DB_PATH", str(ROOT / "data" / "scout.sqlite")))
    conn = init_db(db_path)
    try:
        return collect(conn)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="وكيل بحث فرص السوق: نتائج أولية لا تثبت الربح")
    parser.add_argument("--idea", required=True, help="المشكلة أو فكرة المنتج التي تريد التحقق منها")
    parser.add_argument("--buyer", default="الشركات الصغيرة والمتوسطة", help="المشتري المستهدف")
    parser.add_argument("--market", default="السعودية", help="السوق المستهدف")
    args = parser.parse_args()
    report, md_path, json_path = run_agent(args.idea, args.buyer, args.market)
    print(json.dumps({
        "decision": report["build_decision"],
        "web_leads": len(report["web_results"]),
        "errors": len(report["errors"]),
        "markdown_report": str(md_path),
        "json_report": str(json_path),
    }, ensure_ascii=False, indent=2))
    return 0 if report["web_results"] or report["github_scan"].get("successful_queries", 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
