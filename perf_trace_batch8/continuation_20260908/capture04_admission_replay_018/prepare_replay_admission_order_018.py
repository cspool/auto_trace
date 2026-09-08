from pathlib import Path
import json,hashlib,shutil,os,itertools,types,importlib.util
R=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');BASE=R/'raw/runtime_tools';OLD=BASE/'revision_017';NEW=BASE/'revision_018';C=Path('/public/home/accl15ptg7/run_R08_R10')
def rec(p):return {'path':str(p),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def save(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2);f.write('\n')
source=R.parent.parent/'R07/resume-042/contract/r07_bound_target_sidecar.json';rows=json.loads(source.read_text())['records'];orders={};evidence=[]
for rank in [0,1]:
 xs=[x for x in rows if x['marker_kind']=='process' and x['phase']=='prefill' and x['layer_idx']==0 and x['process_id']=='input_rmsnorm' and x['dp_rank']==rank];xs.sort(key=lambda x:x['runtime_execution_id']);assert len(xs)==4;orders[str(rank)]=[x['request_id'] for x in xs]
 evidence.extend({k:x[k] for k in ['request_id','dp_rank','phase','runtime_execution_id','canonical_target_id']} for x in xs)
contract=BASE/'replay_admission_order_001.json';save(contract,{'schema_version':1,'status':'complete','orders_by_rank':orders,'source_R07_bound_sidecar':rec(source),'first_prefill_order_evidence':evidence,'reason':'Measured client final-byte order does not guarantee EngineCore arrival order; restore observed R07 per-rank admission order for exact compiled-kernel ownership replay','client_request_ids_and_HTTP_commit_order_unchanged':True,'request_prompts_tokens_parameters_unchanged':True,'DP2_eight_requests_concurrency_unchanged':True,'waiting_barrier_only_before_first_measured_scheduler_admission':True,'R07_observed_latency_never_modified':True})
shutil.copytree(OLD,NEW,ignore=shutil.ignore_patterns('__pycache__'))
for p in NEW.iterdir():
 if p.is_file() and p.suffix in ['.py','.sh']:p.write_text(p.read_text().replace('/revision_017/','/revision_018/'))
p=NEW/'run_capture.py';p.write_text(p.read_text().replace('runtime_capture_gate_010.json','runtime_capture_gate_011.json'))
helper='''"""R08-only scheduler admission replay of the recorded R07 per-rank order.

The original eight HTTP requests remain concurrent and byte-identical. This
holds the first measured admissions until all four requests for that rank
arrive, then invokes the unchanged scheduler add_request in observed R07 order.
No forward/model/kernel execution is added. Replay timing is never observed time.
"""
from pathlib import Path
import json,os,time,functools,hashlib
class AdmissionOrder:
    def __init__(self,orders,emit):
        self.orders={int(k):list(v) for k,v in orders.items()};self.byid={x:int(k) for k,v in orders.items() for x in v};self.emit=emit;self.buffer={};self.rank=None;self.released=False
        assert len(self.byid)==8 and set(self.orders)=={0,1} and all(len(v)==4 for v in self.orders.values())
    def stable_id(self,value):
        candidate=value[len('chatcmpl-'):] if value.startswith('chatcmpl-') else value
        for stable in self.byid:
            if candidate==stable:return stable
            if candidate.startswith(stable+'-'):
                suffix=candidate[len(stable)+1:]
                if len(suffix)==8 and all(c in '0123456789abcdef' for c in suffix):return stable
        return None
    def submit(self,request,original):
        stable=self.stable_id(request.request_id)
        if stable is None:return original(request)
        rank=self.byid[stable]
        if self.rank is None:self.rank=rank
        if rank!=self.rank or stable in self.buffer or self.released:raise RuntimeError('R08 measured scheduler admission identity/rank/repeat mismatch')
        self.buffer[stable]=request
        self.emit({'operation':'measured_request_buffered','rank':rank,'stable_request_id':stable,'arrival_ordinal':len(self.buffer),'pid':os.getpid(),'monotonic_ns':time.perf_counter_ns(),'realtime_ns':time.time_ns()})
        if len(self.buffer)<4:return None
        order=self.orders[rank]
        if set(self.buffer)!=set(order):raise RuntimeError('Incomplete exact four-request rank population')
        self.released=True
        for stable in order:original(self.buffer[stable])
        self.emit({'operation':'original_scheduler_admission_released','rank':rank,'request_order':order,'pid':os.getpid(),'monotonic_ns':time.perf_counter_ns(),'realtime_ns':time.time_ns(),'request_objects_modified':False,'extra_requests':0,'extra_model_executions':0})
        return None

def install():
    from r08_native import ROOT,sha,read
    from vllm.v1.core.sched.scheduler import Scheduler
    contract=ROOT/'raw/runtime_tools/replay_admission_order_001.json'
    if sha(contract)!='CONTRACT_SHA':raise RuntimeError('Immutable R07 admission replay contract hash')
    plan=read(contract);source=plan['source_R07_bound_sidecar']
    if sha(source['path'])!=source['sha256']:raise RuntimeError('R07 source order bytes changed')
    original=Scheduler.add_request
    if getattr(original,'_r08_observed_admission_order',False):return
    @functools.wraps(original)
    def add_request(scheduler,request):
        gate=getattr(scheduler,'_r08_admission_order_gate',None)
        if gate is None:
            counter=[0]
            def emit(event):
                counter[0]+=1;out=Path(os.environ['QWEN_DCU_R08_PASS_ROOT'])/'control/admission_order';out.mkdir(exist_ok=True)
                event.update(contract_path=str(contract),contract_sha256='CONTRACT_SHA',replay_diagnostic_only=True)
                path=out/(str(os.getpid())+'.'+str(counter[0]).zfill(3)+'.json')
                with path.open('x') as f:json.dump(event,f,indent=2);f.write('\\n')
            gate=AdmissionOrder(plan['orders_by_rank'],emit);scheduler._r08_admission_order_gate=gate
        return gate.submit(request,lambda value:original(scheduler,value))
    add_request._r08_observed_admission_order=True;Scheduler.add_request=add_request
'''.replace('CONTRACT_SHA',rec(contract)['sha256'])
p=NEW/'r08_admission_order.py';p.write_text(helper)
p=NEW/'sitecustomize.py';s=p.read_text().replace('    r08_pmc_gate.install(r01_runtime_patch)','    r08_pmc_gate.install(r01_runtime_patch)\n    import r08_admission_order\n    r08_admission_order.install()');p.write_text(s)
for p in NEW.glob('*.py'):compile(p.read_text(),str(p),'exec')
spec=importlib.util.spec_from_file_location('admission_CPU_gate',NEW/'r08_admission_order.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);tests=0
for rank in [0,1]:
 for order in itertools.permutations(orders[str(rank)]):
  calls=[];events=[];gate=m.AdmissionOrder(orders,events.append);warm=types.SimpleNamespace(request_id='r08-pmc-warmup-001-'+order[0],payload=object());gate.submit(warm,calls.append);assert calls==[warm];calls.clear();objects={x:types.SimpleNamespace(request_id='chatcmpl-'+x+'-1234abcd',payload=object()) for x in order}
  for i,x in enumerate(order):
   gate.submit(objects[x],calls.append)
   if i<3:assert not calls
  assert calls==[objects[x] for x in orders[str(rank)]] and events[-1]['request_order']==orders[str(rank)];assert all(gate.stable_id(x.request_id)==stable for stable,x in objects.items());tests+=1
# Negative duplicate and cross-rank admissions cannot reach the original scheduler.
for mode in ['duplicate','cross_rank']:
 calls=[];gate=m.AdmissionOrder(orders,lambda e:None);one=types.SimpleNamespace(request_id=orders['0'][0]);gate.submit(one,calls.append)
 try:gate.submit(one if mode=='duplicate' else types.SimpleNamespace(request_id=orders['1'][0]),calls.append)
 except RuntimeError:pass
 else:raise AssertionError('invalid admission accepted')
 assert not calls
# New analysis only adds SQLite read caching; mapping semantics stay byte-identical.
analysis=R/'tools/analysis_006';shutil.copytree(R/'tools/analysis_005',analysis,ignore=shutil.ignore_patterns('__pycache__'))
for p in analysis.glob('*.py'):
 s=p.read_text()
 if p.name=='normalize_capture.py':s=s.replace("conn.row_factory=sqlite3.Row", "conn.row_factory=sqlite3.Row;conn.execute('PRAGMA mmap_size=4294967296');conn.execute('PRAGMA cache_size=-1048576')")
 if p.name=='audit_capture.py':
  # The independent auditor's own connection stays independent.
  s=s.replace("conn.row_factory=sqlite3.Row", "conn.row_factory=sqlite3.Row;conn.execute('PRAGMA mmap_size=4294967296');conn.execute('PRAGMA cache_size=-1048576')")
 p.write_text(s);compile(s,str(p),'exec')
raw=R/'raw/captures/04_triton_red_fused__to_copy_add_mean_mul_pow_rsqrt_0_pmc/attempt_002';e=json.loads((raw/'execution_manifest.json').read_text());assert e['all_started_processes_terminated']
proof={'status':'complete','runtime_revision':'revision_018','previous_runtime_gate':rec(BASE/'runtime_capture_gate_010.json'),'admission_order_contract':rec(contract),'pinned_scheduler_source':rec(Path('/public/home/accl15ptg7/auto_trace/pra2026-bh408-gqa-page784-k5120-batch8/vllm/v1/core/sched/scheduler.py')),'production_buffer_CPU_cases':tests,'warmups_nonselected_requests_passthrough_unchanged':True,'all_request_objects_unchanged':True,'duplicate_and_cross_rank_negative_cases_rejected':True,'request_selection_HTTP_order_DP2_and_1024_tokens_unchanged':True,'no_device_queries_or_model_imports_in_CPU_gate':True,'frozen_tools':[rec(p) for p in sorted(NEW.iterdir()) if p.is_file()],'capture_plan_sha256':rec(R/'plans/r08_capture_plan.json')['sha256'],'prior_valid_raw_capture_not_promoted_due_to_non_equivalent_native_kernel_ownership':rec(BASE/'capture04_multiplicity_diagnostic_001.json'),'no_CPU_bug_or_missing_rows_waiver':True,'new_attempt_required_for_different_replay_scheduling_context':True};save(BASE/'runtime_capture_gate_011.json',proof)
save(R/'validation/NFS_mmap_analysis_CPU_gate_001.json',{'status':'complete','analysis_revision':'analysis_006','changes':'connection-local SQLite mmap and pager cache only; exact attribution and auditor arithmetic unchanged','native_real_DB_quick_check':rec(BASE/'NFS_SQLite_mmap_probe_001.json'),'prior_analysis_gate':rec(R/'validation/NFS_runtime_CPU_gate_001.json'),'frozen_tools':[rec(p) for p in sorted(analysis.iterdir()) if p.is_file()],'model_or_device_actions':0})
print('REPLAY_ADMISSION_CPU_GATE_COMPLETE',orders,tests,flush=True)
