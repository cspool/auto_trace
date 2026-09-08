"""Immutable CPU closure primitives. Exact listed relocation, no implicit escapes."""
from pathlib import Path
import os,json,hashlib,subprocess,datetime,collections
ROOT=Path(__file__).parents[2];PROJECT=Path('/public/home/accl15ptg7/auto_trace');CONTROL=Path('/public/home/accl15ptg7/run_R08_R10');RUN=PROJECT/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003';RUN_ID='batch8-dp2-fresh-003';OLD=Path('/public/home/tangyu408/Qwen_DCU_Worker_0');PROFILE='3b4c952063f48ae662b48b5ce9d8fd76e0ac4d74e170bdb1839ae8b1aaa23cce'
ANCHORS={'vllm/model_executor/models/qwen3_5.py':'f3c0479dbc37a8794c4d6b1c4c01906ae341b3276ed43e588c17d92b1ddb94d6','vllm/model_executor/models/qwen3_next.py':'5a14b14a40fcf6382f9a20be4ca0f850b2b19b2840a3c57488821f0952d96053','vllm/v1/worker/gpu_model_runner.py':'d63424d3cbe81bfaa2c0967a5c81b8c980c2d76bc7eb3b2f8fe2a079af825bce','vllm/utils/nvtx_pytorch_hooks.py':'e9711444f33242ce1864d6a32d051bbf0ba0b37b5f17965de6e5dbba0c0c75ff','vllm/compilation/wrapper.py':'b4dca93456e945ce8231e9a954792c8f687d5d48b427ed38bfb96011015d4090','scripts/serve_cscc_dp2.sh':'233bb2ce6fee3654bc870e37e65b7ecf4de6874cb6c7fd1a6bd5687a40783699','scripts/bench_cscc_multi_request.sh':'9b5e02116911729e901077866389e448c0e4a055e8bb901ed160dcdc7664a595','scripts/cscc_gfx936_env.sh':'58d483450c23e9c4fa87fb981b5e63cf4babf5e8d230fe93e400563596dfc18a','docs/cscc/DP2_MULTI_REQUEST.md':'f83ebea84fd570908be0df58255eca371ad4c28c4dc9d70ec3db0401b1143569'}
def check(v,m):
 if not v:raise RuntimeError(m)
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def rec(p):return {'path':str(p),'size':Path(p).stat().st_size,'sha256':sha(p)}
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(p,x):
 p=Path(p);check(p.is_relative_to(ROOT) and '..' not in p.parts,'assigned CPU output root');p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(x,f,indent=2,ensure_ascii=False,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
def memory_mappings():
 mappings={};records=[]
 for suffix in ['', '_002']:
  p=CONTROL/('MEMORY_STORAGE_RELOCATION_COMPLETE'+suffix+'.json');a=CONTROL/('MEMORY_STORAGE_RELOCATION_AUTHORIZATION'+suffix+'.json');x=read(p);check(x['status']=='complete' and sha(a)==x['authorization_sha256'] and not x['predecessor_content_changed'],'exact same-byte storage authorization');records.extend([rec(a),rec(p)])
  for item in x['file_mappings']:
   key=Path(item['source_path']);check(key not in mappings,'unique file relocation');mappings[key]=item
 return mappings,records
def localize(value):
 p=Path(value);check('..' not in p.parts,'path traversal')
 if p.is_relative_to(OLD):return PROJECT/p.relative_to(OLD)
 expanded=Path('/perf_trace_batch8_r01_r06')/RUN_ID/'expanded_artifacts'
 if p.is_relative_to(expanded):return RUN/'artifacts'/p.relative_to(expanded)
 return p if p.is_absolute() else PROJECT/p
def validate_path(value):
 p=localize(value);resolved=p.resolve()
 for i in range(1,7):
  lexical=RUN/'artifacts'/('R%02d'%i);backing=Path('/dev/shm/r08_continuation_predecessors/artifacts')/('R%02d'%i)
  if p.is_relative_to(lexical):
   check(lexical.is_symlink() and os.readlink(lexical)==str(backing),'exact predecessor directory relocation');mapped=backing/p.relative_to(lexical)
   if resolved==mapped:return p
   maps,_=memory_mappings();check(mapped in maps,'unlisted nested predecessor link');item=maps[mapped];check(mapped.is_symlink() and os.readlink(mapped)==item['resolved_destination'] and resolved==Path(item['resolved_destination']),'exact nested file storage map');check(p.stat().st_size==item['size'],'relocated source size');return p
 for stage in ['R08','R09','R10']:
  sroot=RUN/'artifacts'/stage/'continuation_001'
  if p.is_relative_to(sroot):
   auth=sroot/'authorization/bulk_storage_authorization.json'
   if auth.exists():
    for lexical,dest in read(auth)['paths'].items():
     if p.is_relative_to(Path(lexical)):
      check(Path(lexical).is_symlink() and os.readlink(lexical)==dest and resolved==Path(dest)/p.relative_to(Path(lexical)),'exact business bulk storage');return p
   check(resolved.is_relative_to(sroot),'unlisted stage output symlink');return p
 check(resolved.is_relative_to(PROJECT) or resolved.is_relative_to(CONTROL),'explicit read-only project/control input');return p
def verify(item):
 p=validate_path(item.get('path',item.get('local_path')));check(p.is_file(),'required source exists');size=item.get('size',item.get('size_bytes'));check(size is None or p.stat().st_size==size,'source size');check(sha(p)==item['sha256'],'source SHA-256 '+str(p));return p

def target_state():
 target=PROJECT/'pra2026-bh408-gqa-page784-k5120-batch8'
 def git(*args):return subprocess.check_output(['git','-C',str(target),*args],text=True).strip()
 commit=git('rev-parse','HEAD');branch=git('branch','--show-current');check(commit=='2b4b2119ae3cc2c4c626dc5690ef9593c1477f66' and branch=='repro-gqa-page784-k5120-batch8-final','immutable target commit and branch');check(not git('status','--porcelain','--untracked-files=all'),'source worktree index and untracked clean')
 # Source identities are read without importing vLLM or its native modules.
 sources=[]
 for name,expected in ANCHORS.items():
  p=target/name;check(sha(p)==expected,'source anchor '+name);sources.append(rec(p))
 return {'root':str(target),'commit':commit,'branch':branch,'clean':True,'source_anchors':sources}
def closed_process_proof(match_roots,exclude=()):
 matches=[]
 for path in Path('/proc').iterdir():
  if not path.name.isdigit() or int(path.name) in {os.getpid(),*exclude}:continue
  try:
   cmd=(path/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace');stat=(path/'stat').read_text();state=stat.split(') ',1)[1].split()[0]
  except (FileNotFoundError,PermissionError,ProcessLookupError):continue
  if state!='Z' and any(str(root) in cmd for root in match_roots):matches.append({'pid':int(path.name),'cmdline':cmd})
 check(not matches,'owned stage processes must have exited before closure: '+str([x['pid'] for x in matches]));return {'status':'none_alive','checked_utc':now(),'excluded_current_sealer_pid':os.getpid(),'explicit_excluded_outer_process_pids':list(exclude),'matched_owned_roots':[str(x) for x in match_roots],'live_processes':[]}
