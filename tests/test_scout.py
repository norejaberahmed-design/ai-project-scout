import json, tempfile, unittest
from pathlib import Path
from scout import build_report, init_db, technical_score, upsert_repo

def sample(**changes):
 data={'id':123,'full_name':'example/ai-tool','html_url':'https://github.com/example/ai-tool','description':'AI developer tool','language':'Python','stargazers_count':500,'forks_count':30,'license':{'spdx_id':'MIT'},'created_at':'2024-01-01T00:00:00Z','updated_at':'2026-10-20T00:00:00Z','pushed_at':'2026-10-20T00:00:00Z','topics':['ai','automation']}; data.update(changes); return data
class ScoutTests(unittest.TestCase):
 def test_score_bounded(self): self.assertTrue(0<=technical_score(sample())<=100)
 def test_missing_data(self): self.assertIsInstance(technical_score({'id':1}),int)
 def test_dedup_and_history(self):
  with tempfile.TemporaryDirectory() as tmp:
   c=init_db(Path(tmp)/'db.sqlite'); upsert_repo(c,sample(),['topic:llm'],'2026-10-21T00:00:00+00:00'); upsert_repo(c,sample(stargazers_count=501),['topic:automation'],'2026-10-22T00:00:00+00:00'); c.commit()
   self.assertEqual(c.execute('SELECT COUNT(*) FROM repositories').fetchone()[0],1); row=c.execute('SELECT stars,first_seen,query_tags,commercial_status FROM repositories').fetchone(); self.assertEqual(row[0],501); self.assertEqual(row[1],'2026-10-21T00:00:00+00:00'); self.assertEqual(set(json.loads(row[2])),{'topic:llm','topic:automation'}); self.assertEqual(row[3],'NEEDS_VALIDATION'); self.assertEqual(c.execute('SELECT COUNT(*) FROM observations').fetchone()[0],2); c.close()
 def test_report_does_not_claim_demand(self):
  with tempfile.TemporaryDirectory() as tmp:
   c=init_db(Path(tmp)/'db.sqlite'); upsert_repo(c,sample(),['topic:llm'],'2026-10-22T00:00:00+00:00'); c.commit(); md,js=build_report(c,{'queries':1,'successful_queries':1,'repositories_seen':1,'unique_repositories':1,'new_today':1,'errors':[]},Path(tmp)/'reports'); self.assertIn('NEEDS_VALIDATION',md.read_text(encoding='utf-8')); data=json.loads(js.read_text(encoding='utf-8')); self.assertEqual(data['repositories'][0]['market_evidence'],'NOT_COLLECTED'); self.assertEqual(data['repositories'][0]['build_decision'],'DO_NOT_BUILD_YET'); c.close()
if __name__=='__main__': unittest.main()
