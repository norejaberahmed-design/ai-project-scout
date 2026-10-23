import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=Path(os.getenv('SCOUT_DATA_DIR',ROOT/'data')).resolve()
SKILLS=Path(os.getenv('SCOUT_SKILLS_DIR',ROOT/'skills')).resolve()
PROPOSED=SKILLS/'proposed'; ACTIVE=SKILLS/'active'; REGISTRY=DATA/'skills.json'
LLM_URL=os.getenv('SCOUT_LLM_API_URL','https://openrouter.ai/api/v1/chat/completions')
LLM_KEY=os.getenv('SCOUT_LLM_API_KEY',''); LLM_MODEL=os.getenv('SCOUT_LLM_MODEL','')
TAVILY_KEY=os.getenv('TAVILY_API_KEY',''); GITHUB_TOKEN=os.getenv('GITHUB_TOKEN','')
LICENSES={'MIT','Apache-2.0','BSD-2-Clause','BSD-3-Clause','ISC','0BSD'}
def ensure_dirs():
 DATA.mkdir(parents=True,exist_ok=True); PROPOSED.mkdir(parents=True,exist_ok=True); ACTIVE.mkdir(parents=True,exist_ok=True)
