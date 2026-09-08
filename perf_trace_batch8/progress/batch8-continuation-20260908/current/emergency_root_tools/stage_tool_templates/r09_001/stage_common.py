"""CPU-only, explicit continuation lineage and immutable output primitives."""
from pathlib import Path
import csv,json,hashlib,os,subprocess
csv.field_size_limit(2**63-1)
ROOT=Path(__file__).parents[2]
PROJECT=Path('/public/home/accl15ptg7/auto_trace')
RUN=PROJECT/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003'
RUN_ID='batch8-dp2-fresh-003'
PROFILE='3b4c952063f48ae662b48b5ce9d8fd76e0ac4d74e170bdb1839ae8b1aaa23cce'
R07=RUN/'artifacts/R07/resume-042';R08=RUN/'artifacts/R08/continuation_001'
CONTROL=Path('/public/home/accl15ptg7/run_R08_R10')
TABLES=['request_timeline','process_timeline','kernel_timeline','live_utilization_aligned','process_live_utilization','kernel_concurrency','queue_concurrency','launch_gaps','high_latency_processes','dependency_state','traffic_resource_attachment','opportunity_candidates']
def check(v,m):
 if not v:raise ValueError(m)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def rec(p):return {'path':str(p),'size':Path(p).stat().st_size,'sha256':sha(p)}
def js(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(v):return hashlib.sha256(js(v).encode()).hexdigest()
def save(p,v):
 p=Path(p);check(p.is_relative_to(ROOT) and '..' not in p.parts,'output containment');p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,indent=2,ensure_ascii=False,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
def rows(p):
 with Path(p).open(newline='') as f:yield from csv.DictReader(f)
def validate_source(p):
 p=Path(p);check(p.is_absolute() and '..' not in p.parts,'input lexical path')
 if p.is_relative_to(R08):
  authorization=read(R08/'authorization/bulk_storage_authorization.json');assignment=read(R08/'authorization/continuation_assignment.json');check(sha(R08/'authorization/bulk_storage_authorization.json')==assignment['bulk_storage_authorization_sha256'],'R08 bulk hash')
  for lexical,dest in authorization['paths'].items():
   if p.is_relative_to(Path(lexical)):
    check(Path(lexical).is_symlink() and os.readlink(lexical)==dest,'R08 bulk symlink');check(p.resolve()==Path(dest)/p.relative_to(Path(lexical)),'R08 nested path');return
 check(p.resolve().is_relative_to(PROJECT) or p.is_relative_to(CONTROL/'r07_additional_inputs'),'explicit source owner')
def verify(x):
 p=Path(x['path']);validate_source(p);check(p.stat().st_size==x.get('size',p.stat().st_size) and sha(p)==x['sha256'],'source bytes: '+str(p));return p
def source_state():
 t=PROJECT/'pra2026-bh408-gqa-page784-k5120-batch8'
 def git(*args):return subprocess.check_output(['git','-C',str(t),*args],text=True).strip()
 check(git('rev-parse','HEAD')=='2b4b2119ae3cc2c4c626dc5690ef9593c1477f66','source commit');check(not git('status','--porcelain','--untracked-files=all'),'immutable target')
 return {'commit':git('rev-parse','HEAD'),'branch':git('branch','--show-current'),'clean':True}
def admission():
 a=read(ROOT/'authorization/assignment.json');check(a['runtime_goal']=='R09' and a['runtime_run_id']==RUN_ID,'R09 assigned stage');check(a['predecessor_stages']==['R%02d'%i for i in range(1,9)],'ordered R01-R08')
 for x in a['predecessor_handoffs']:
  p=Path(x['path']);check(sha(p)==x['sha256'],'direct handoff');h=read(p)
  if h['runtime_goal']=='R07':check(h['status']=='complete_recovered_offline' and not h['native_controller_lifecycle_completion_claimed'],'explicit recovery exception')
  else:check(h['status']=='complete','complete predecessor')
 h=read(RUN/'handoffs/R08.continuation.json')
 for k,v in {'status':'complete','execution_status':'complete','evidence_status':'complete','coverage_target_met':True,'next_authorization_required':False,'all_started_processes_terminated':True}.items():check(h[k]==v,'R08 advance '+k)
 check(h['lineage_id']==RUN_ID and h['trace_profile_sha256']==PROFILE,'R08 lineage')
 # The outer scheduler seals the complete transitive validation at assignment.
 # Re-read/hash every actual consumed source here and in the independent audit.
 for x in a['consumed_sources']:verify(x)
 return a,source_state()
def common(source,kind,sid,request='',rank='',evidence='observed_r07'):
 return {'schema_version':1,'runtime_run_id':RUN_ID,'lineage_id':RUN_ID,'trace_profile_sha256':PROFILE,'request_id':request,'rank':rank,'physical_device_id':rank,'source_record_kind':kind,'source_path':source['path'],'source_sha256':source['sha256'],'source_row_id':sid,'evidence_class':evidence,'availability_state':'available','availability_reason':''}
def write_table(name,values,fields,sort_key,source_records):
 check(name in TABLES,'logical table');p=ROOT/'tables'/f'{name}.csv';p.parent.mkdir(exist_ok=True);count=0;coverage={'requests':set(),'ranks':set(),'devices':set()};ec={};states={}
 with p.open('x',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader()
  for x in values:
   w.writerow({k:(js(v) if isinstance(v,(dict,list,tuple)) else v) for k,v in x.items()});count+=1
   for key,field in [('requests','request_id'),('ranks','rank'),('devices','physical_device_id')]:
    if str(x.get(field,'')):coverage[key].add(str(x[field]))
   for bag,key in [(ec,'evidence_class'),(states,'availability_state')]:bag[str(x.get(key,''))]=bag.get(str(x.get(key,'')),0)+1
 return {'logical_name':name,**rec(p),'row_count':count,'schema':fields,'schema_sha256':digest(fields),'stable_sort_key':sort_key,'null_encoding':'empty CSV cell; original source values preserved as strings','integer_time_encoding':'decimal integer nanoseconds; no float conversion','lineage_id':RUN_ID,'coverage':{k:sorted(v) for k,v in coverage.items()},'evidence_class_counts':ec,'availability_counts':states,'sources':source_records}
def fields_of(values):return list(dict.fromkeys(k for x in values for k in x))
