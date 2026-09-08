from pathlib import Path
import json,csv,collections
R=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003');old=R/'artifacts/R07/resume-042';new=R/'artifacts/R08/continuation_001/raw/captures/04_triton_red_fused__to_copy_add_mean_mul_pow_rsqrt_0_pmc/attempt_002';side=json.loads((old/'contract/r07_bound_target_sidecar.json').read_text())['records'];current=[]
for p in (new/'workload/runtime_bindings').glob('*.jsonl'):
 with p.open() as f:current.extend(json.loads(l) for l in f)
for label,records in [('R07',side),('R08',current)]:
 print(label)
 groups=collections.defaultdict(list)
 for x in records:
  if x['marker_kind']=='process' and x['phase']=='decode' and x['layer_idx']==0 and x['process_id']=='input_rmsnorm':groups[x['dp_rank']].append(x)
 for rank,xs in sorted(groups.items()):
  print('RANK',rank,[{k:x[k] for k in ['request_id','runtime_execution_id','q_len','kv_len','num_output_tokens_before_step']} for x in sorted(xs,key=lambda x:x['runtime_execution_id'])])
 if label=='R07':
  with (old/'trace/strict_owned_kernels.csv').open() as f:counts=collections.Counter(x['request_id'] for x in csv.DictReader(f))
  print('OWNED_KERNELS',counts)
# Snapshot all selected first-decode forward contexts, including all batched
# participants, without accepting or rewriting any native counters.
for p in (new/'workload/r01_events').glob('rank*/events.*.jsonl'):
 observed=set();contexts=[]
 with p.open() as f:
  for line in f:
   x=json.loads(line)
   if x.get('kind')=='observed_forward_range' and x.get('phase')=='decode':
    for participant in x.get('participants',[]):
     if participant['request_id'] not in observed and participant['phase']=='decode':
      observed.add(participant['request_id']);contexts.append({'first_decode_request':participant['request_id'],'execution_id':x.get('execution_id'),'total_q_len':x.get('q_len'),'participants':x['participants']})
    if len(observed)==4:break
 print(p.parent.name,'CURRENT_BATCH_CONTEXTS',json.dumps(contexts))
