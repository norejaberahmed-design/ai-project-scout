"""Collect recent AI research-paper announcements from arXiv Atom API."""
import json
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORT_DIR = Path(os.getenv("SCOUT_REPORT_DIR", str(ROOT / "reports")))
ATOM = "{http://www.w3.org/2005/Atom}"
CATEGORIES = [
    ("cs.AI", "الذكاء الاصطناعي"),
    ("cs.LG", "تعلم الآلة"),
    ("cs.CL", "معالجة اللغة والنماذج اللغوية"),
    ("cs.CV", "الرؤية الحاسوبية"),
    ("cs.RO", "الروبوتات"),
]

def fetch_recent_papers(max_results=60, timeout=25, opener=None):
    """Return recent papers; publication dates and abstracts come from arXiv."""
    terms = " OR ".join(f"cat:{category}" for category, _ in CATEGORIES)
    params = urllib.parse.urlencode({
        "search_query": terms,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": min(max(int(max_results), 1), 100),
    })
    request = urllib.request.Request(
        "https://export.arxiv.org/api/query?" + params,
        headers={"User-Agent": "AI-Project-Scout/0.3 (public research discovery)", "Accept": "application/atom+xml"},
    )
    open_url = opener or urllib.request.urlopen
    with open_url(request, timeout=timeout) as response:
        raw = response.read(5_000_000)
    root = ET.fromstring(raw)
    papers = []
    for entry in root.findall(ATOM + "entry"):
        title = " ".join((entry.findtext(ATOM + "title") or "").split())
        summary = " ".join((entry.findtext(ATOM + "summary") or "").split())
        link = ""
        for child in entry.findall(ATOM + "link"):
            if child.attrib.get("rel") == "alternate":
                link = child.attrib.get("href", "")
                break
        categories = [c.attrib.get("term", "") for c in entry.findall(ATOM + "category")]
        authors = [a.findtext(ATOM + "name", default="") for a in entry.findall(ATOM + "author")]
        published = entry.findtext(ATOM + "published", default="")
        if title and link.startswith("https://arxiv.org/"):
            papers.append({
                "title": title, "url": link, "abstract": summary,
                "published": published, "categories": categories, "authors": authors[:8],
                "source": "arXiv Atom API",
            })
    return papers

def write_report(papers, report_dir=None, error=None):
    out = Path(report_dir or REPORT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": "arXiv Atom API",
        "scope": "Recent papers in selected AI research categories; not all AI news",
        "papers": papers,
        "limitations": [
            "A paper announcement is not proof that a method works in production.",
            "The list is not a complete digest of AI industry news or GitHub releases.",
            "Titles and abstracts should be read in context; no independent replication is performed.",
        ],
    }
    if error:
        payload["collection_error"] = str(error)
    json_path = out / f"ai-updates-{stamp}.json"
    md_path = out / f"ai-updates-{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# آخر أبحاث الذكاء الاصطناعي — " + stamp, "",
        "> مصدر التقرير: arXiv. هذه أوراق بحثية حديثة وليست بالضرورة أدوات جاهزة أو نتائج مؤكدة.", "",
        f"- عدد الأوراق المسترجعة: {len(papers)}", "",
    ]
    for index, paper in enumerate(papers, 1):
        lines += [
            f"## {index}. [{paper['title']}]({paper['url']})",
            f"- تاريخ الإرسال: {paper['published'] or 'غير متوفر'}",
            f"- التصنيفات: {', '.join(paper['categories']) or 'غير محددة'}",
            f"- الباحثون: {', '.join(paper['authors']) or 'غير متوفر'}",
            "- الملخص: " + (paper["abstract"] or "لا يوجد ملخص"),
            "",
        ]
    if error:
        lines += ["## تعذر الوصول إلى المصدر في هذا التشغيل", "", "- الخطأ: " + str(error), "- لم تُسترجع أوراق بحثية؛ أعد التشغيل لاحقًا.", ""]
    lines += [
        "## كيف تستخدم هذه القائمة؟", "",
        "1. افتح الورقة واقرأ الملخص والمساهمات والقيود.",
        "2. ابحث عن كود رسمي مرتبط بالورقة قبل اعتمادها كأداة.",
        "3. اختبر الترخيص والمتطلبات والنتائج على بيانات غير حساسة.",
        "4. لا تعتبر الورقة منتجًا جاهزًا ولا دليلًا على وجود طلب تجاري.", "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path, json_path

def main():
    try:
        papers = fetch_recent_papers()
        md_path, json_path = write_report(papers)
        print(json.dumps({"papers": len(papers), "markdown_report": str(md_path), "json_report": str(json_path)}, ensure_ascii=False))
        return 0
    except Exception as exc:
        # A temporary external-source outage must not prevent the dashboard from deploying.
        md_path, json_path = write_report([], error=str(exc))
        print(json.dumps({"papers": 0, "error": str(exc), "source": "arXiv Atom API", "markdown_report": str(md_path), "json_report": str(json_path)}, ensure_ascii=False))
        return 0

if __name__ == "__main__":
    raise SystemExit(main())
