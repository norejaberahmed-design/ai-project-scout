import json, os, sqlite3, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DB_PATH=Path(os.getenv('SCOUT_DB_PATH',str(ROOT/'data'/'scout.sqlite')))
REPORT_DIR=Path(os.getenv('SCOUT_REPORT_DIR',str(ROOT/'reports')))
QUERIES=['topic:artificial-intelligence','topic:llm','topic:ai-agents','topic:computer-vision','topic:speech-recognition','topic:retrieval-augmented-generation','topic:automation','topic:developer-tools']
PER_PAGE=max(1,min(int(os.getenv('SCOUT_PER_QUERY','20')),100))
def now_utc(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def api_get(url,retries=3):
 headers={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'ai-project-scout/0.1'}
 token=os.getenv('GITHUB_TOKEN')
 if token: headers['Authorization']='Bearer '+token
 req=urllib.request.Request(url,headers=headers)
 for attempt in range(retries):
  try:
   with urllib.request.urlopen(req,timeout=20) as response: return json.loads(response.read().decode('utf-8'))
  except urllib.error.HTTPError as exc:
   if exc.code in (403,429) and attempt<retries-1:
    retry=exc.headers.get('Retry-After',''); time.sleep(min(int(retry),30) if retry.isdigit() else 2**attempt); continue
   raise RuntimeError('GitHub API HTTP '+str(exc.code)) from exc
  except (urllib.error.URLError,TimeoutError) as exc:
   if attempt==retries-1: raise RuntimeError('GitHub network error: '+str(exc)) from exc
   time.sleep(2**attempt)
 raise RuntimeError('GitHub API failed after retries')
def technical_score(repo):
 score=0; stars=max(0,int(repo.get('stargazers_count') or 0)); forks=max(0,int(repo.get('forks_count') or 0))
 score+=25 if stars>=1000 else 18 if stars>=250 else 10 if stars>=50 else 5 if stars>=10 else 0
 score+=15 if forks>=100 else 10 if forks>=25 else 5 if forks>=5 else 0
 lic=repo.get('license') or {}
 if lic.get('spdx_id') and lic.get('spdx_id')!='NOASSERTION': score+=15
 if repo.get('description'): score+=10
 if repo.get('language'): score+=5
 if repo.get('topics'): score+=10
 updated=repo.get('pushed_at') or repo.get('updated_at') or ''
 try:
  age=(datetime.now(timezone.utc)-datetime.fromisoformat(updated.replace('Z','+00:00'))).days
  score+=20 if age<=30 else 12 if age<=180 else 5 if age<=365 else 0
 except (ValueError,TypeError): pass
 return min(score,100)
def init_db(path=DB_PATH):
 path.parent.mkdir(parents=True,exist_ok=True); conn=sqlite3.connect(path)
 conn.execute('CREATE TABLE IF NOT EXISTS repositories (repo_id INTEGER PRIMARY KEY, full_name TEXT NOT NULL, url TEXT NOT NULL, description TEXT, language TEXT, stars INTEGER NOT NULL, forks INTEGER NOT NULL, license TEXT, created_at TEXT, updated_at TEXT, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, query_tags TEXT NOT NULL, technical_score INTEGER NOT NULL, commercial_status TEXT NOT NULL DEFAULT \'NEEDS_VALIDATION\')')
 conn.execute('CREATE TABLE IF NOT EXISTS observations (id INTEGER PRIMARY KEY AUTOINCREMENT, repo_id INTEGER NOT NULL, observed_at TEXT NOT NULL, stars INTEGER NOT NULL, forks INTEGER NOT NULL, FOREIGN KEY(repo_id) REFERENCES repositories(repo_id))'); conn.commit(); return conn
def upsert_repo(conn,repo,tags,observed):
 if repo.get('id') is None or not repo.get('full_name') or not repo.get('html_url'): return
 rid=int(repo['id']); old=conn.execute('SELECT first_seen,query_tags FROM repositories WHERE repo_id=?',(rid,)).fetchone()
 first=old[0] if old else observed; merged=sorted(set(json.loads(old[1]) if old else [])|set(tags)); lic=repo.get('license') or {}
 conn.execute('INSERT INTO repositories (repo_id,full_name,url,description,language,stars,forks,license,created_at,updated_at,first_seen,last_seen,query_tags,technical_score,commercial_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(repo_id) DO UPDATE SET full_name=excluded.full_name,url=excluded.url,description=excluded.description,language=excluded.language,stars=excluded.stars,forks=excluded.forks,license=excluded.license,created_at=excluded.created_at,updated_at=excluded.updated_at,last_seen=excluded.last_seen,query_tags=excluded.query_tags,technical_score=excluded.technical_score,commercial_status=\'NEEDS_VALIDATION\'',(rid,repo['full_name'],repo['html_url'],repo.get('description'),repo.get('language'),int(repo.get('stargazers_count') or 0),int(repo.get('forks_count') or 0),lic.get('spdx_id') or lic.get('name'),repo.get('created_at'),repo.get('updated_at'),first,observed,json.dumps(merged),technical_score(repo),'NEEDS_VALIDATION'))
 conn.execute('INSERT INTO observations(repo_id,observed_at,stars,forks) VALUES (?,?,?,?)',(rid,observed,int(repo.get('stargazers_count') or 0),int(repo.get('forks_count') or 0)))
def collect(conn,queries=None):
 queries=queries or QUERIES; observed=now_utc(); stats={'queries':len(queries),'successful_queries':0,'repositories_seen':0,'errors':[]}
 for query in queries:
  url='https://api.github.com/search/repositories?'+urllib.parse.urlencode({'q':query+' archived:false','sort':'updated','order':'desc','per_page':PER_PAGE})
  try:
   payload=api_get(url); items=payload.get('items',[])
   if not isinstance(items,list): raise ValueError('Invalid GitHub response: items is not a list')
   for item in items:
    if isinstance(item,dict): upsert_repo(conn,item,[query],observed); stats['repositories_seen']+=1
   stats['successful_queries']+=1
  except (RuntimeError,ValueError,TypeError,KeyError) as exc: stats['errors'].append({'query':query,'error':str(exc)})
 conn.commit(); stats['unique_repositories']=conn.execute('SELECT COUNT(*) FROM repositories').fetchone()[0]
 stats['new_today']=conn.execute('SELECT COUNT(*) FROM repositories WHERE first_seen >= ?',(observed[:10],)).fetchone()[0]; return stats
def build_report(conn,stats,report_dir=REPORT_DIR):
 stamp=datetime.now(timezone.utc).strftime('%Y-%m-%d'); report_dir.mkdir(parents=True,exist_ok=True)
 rows=conn.execute('SELECT full_name,url,description,language,stars,forks,license,updated_at,first_seen,query_tags,technical_score,commercial_status FROM repositories ORDER BY technical_score DESC,stars DESC LIMIT 100').fetchall(); repos=[]
 for r in rows: repos.append({'repository':r[0],'url':r[1],'description':r[2],'language':r[3],'stars':r[4],'forks':r[5],'license':r[6],'updated_at':r[7],'first_seen':r[8],'discovery_queries':json.loads(r[9]),'technical_score':r[10],'commercial_status':r[11],'market_evidence':'NOT_COLLECTED','build_decision':'DO_NOT_BUILD_YET','reason':'لا توجد أدلة مستقلة موثقة على مشترين أو استعداد للدفع في هذا الإصدار.'})
 payload={'generated_at':now_utc(),'scope':'GitHub discovery only; not a market census','stats':stats,'decision_rule':'Stars and forks do not prove demand or profit','repositories':repos}
 jp=report_dir/(stamp+'.json'); mp=report_dir/(stamp+'.md'); jp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
 lines=['# كشاف مشاريع الذكاء الاصطناعي — '+stamp,'','> الشعبية التقنية ليست طلبًا مدفوعًا. لا تجمع هذه النسخة أدلة سوق مستقلة؛ لذلك لا توصي بالبناء اعتمادًا على التقرير وحده.','','## ملخص التشغيل','- الاستعلامات الناجحة: {}/{}'.format(stats['successful_queries'],stats['queries']),'- النتائج المرصودة: {}'.format(stats['repositories_seen']),'- المستودعات الفريدة: {}'.format(stats['unique_repositories']),'- الجديدة اليوم: {}'.format(stats['new_today']),'- أخطاء الاستعلامات: {}'.format(len(stats['errors'])),'','## إشارات الاستكشاف التقنية','الدرجة من 100 ترتيب تقني فقط وليست تقييمًا تجاريًا.','']
 for i,r in enumerate(repos[:30],1): lines += ['### {}. [{}]({})'.format(i,r['repository'],r['url']),'- الوصف: '+(r['description'] or 'لا يوجد وصف').replace('\n',' '),'- اللغة: {} | النجوم: {} | التفرعات: {}'.format(r['language'] or 'غير محددة',r['stars'],r['forks']),'- الترخيص: {}'.format(r['license'] or 'غير واضح؛ راجع الترخيص الأصلي'),'- آخر تحديث: {} | الدرجة التقنية: {}/100'.format(r['updated_at'] or 'غير متوفر',r['technical_score']),'- السوق: NEEDS_VALIDATION؛ لا يوجد إثبات طلب مدفوع.','- القرار: DO_NOT_BUILD_YET؛ تحقق من العملاء والتكاليف أولًا.','']
 if stats['errors']: lines+=['## أخطاء وتغطية غير مكتملة','']+['- {}: {}'.format(e['query'],e['error']) for e in stats['errors']]
 lines+=['','## بوابة التحقق التجاري','1. حدد المشتري وصاحب قرار الدفع.','2. اجمع دليلًا مستقلًا موثقًا على مشكلة متكررة أو إنفاق قائم.','3. قارن المنافسين والبدائل، بما فيها العمل اليدوي.','4. احسب تكلفة الاستضافة وواجهات API والدعم والبيع.','5. اختبر عرضًا يدويًا مع عملاء حقيقيين قبل البرمجة.','إذا غابت الأدلة: اترك الفكرة أو أبقها قيد التحقق.','','## الحدود','- البحث مقتصر على GitHub وليس جميع الإنترنت.','- لا نشغّل الكود الخارجي ولا نفحص أمان المستودعات.','- لا نجمع مقابلات أو أسعارًا أو إيرادات في هذه النسخة.','- راجع الترخيص والتبعيات قبل الاستخدام التجاري.']
 mp.write_text('\n'.join(lines)+'\n',encoding='utf-8'); return mp,jp
def main():
 conn=init_db()
 try:
  stats=collect(conn); md,js=build_report(conn,stats); print(json.dumps({'stats':stats,'markdown_report':str(md),'json_report':str(js)},ensure_ascii=False)); return 0 if stats['successful_queries'] else 1
 finally: conn.close()
if __name__=='__main__': raise SystemExit(main())
