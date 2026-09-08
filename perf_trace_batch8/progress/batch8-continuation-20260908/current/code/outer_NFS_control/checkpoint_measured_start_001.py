"""Checkpoint both-device native health and original measured admission records."""
from pathlib import Path
import json,hashlib,sys,datetime
C=Path('/public/home/accl15ptg7/run_R08_R10');P=Path('/public/home/accl15ptg7/auto_trace');R=P/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001';D=P/'perf_trace_batch8/continuation_20260908';seg,attempt=sys.argv[1:3];assert '/' not in seg and '/' not in attempt;A=R/'raw/captures'/seg/attempt
read=lambda p:json.loads(p.read_text())
def rec(p):return {'path':str(p),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
health=A/'control/PRE_MEASURED_NATIVE_PMC_HEALTH.json';h=read(health);assert h['status']=='complete' and {x['rank'] for x in h['workers']}=={0,1};assert all(x['observed_native_bytes']>0 for x in h['workers'])
releases=[p for p in sorted((A/'control/admission_order').glob('*.json')) if read(p)['operation']=='original_scheduler_admission_released'];assert len(releases)==2 and {read(p)['rank'] for p in releases}=={0,1};orders=read(R/'raw/runtime_tools/replay_admission_order_001.json')['orders_by_rank']
for p in releases:assert read(p)['request_order']==orders[str(read(p)['rank'])]
warmups=sorted((A/'control/pmc_gate_events').glob('warmup_start.*.json'));assert len(warmups)==2
reset=[]
for p in warmups:
 w=read(p);assert w['profiler_transition']['status']==0
 if w.get('native_off_to_on_reset_before_original_warmup'):
  assert w['profiler_reset_stop_transition']['status']==0;reset.append(w['dp_rank'])
out=D/('capture'+seg[:2]+'_'+attempt+'_measured_start_001');out.mkdir(exist_ok=False);sources=[health,A/'control/capture_contract.json',*releases,*warmups]
for p in sources:(out/p.name).write_bytes(p.read_bytes())
(out/'SOURCE_RECORDS.json').write_text(json.dumps([rec(p) for p in sources],indent=2)+'\n');(D/'outer_helpers_001'/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
with (D/'LIVE_PROGRESS.md').open('a') as f:f.write('\n- '+datetime.datetime.now(datetime.timezone.utc).isoformat()+': '+seg+' '+attempt+' passed both-device native prehealth and released the original four requests per rank in exact observed R07 admission order. Warmup native reset recorded on ranks '+json.dumps(sorted(reset))+'. Complete live marker and closed native attribution audits are still required.\n')
print(json.dumps({'checkpoint_directory':str(out),'native_health':'complete','warmup_reset_ranks':sorted(reset),'closed_capture_accepted':False}))
