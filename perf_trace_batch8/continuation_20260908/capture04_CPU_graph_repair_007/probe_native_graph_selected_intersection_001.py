from pathlib import Path
import json,sqlite3,collections,bisect,time,hashlib
R=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');raw=R/'raw/captures/04_triton_red_fused__to_copy_add_mean_mul_pow_rsqrt_0_pmc/attempt_003';start=time.monotonic();d=json.loads((R/'raw/runtime_tools/capture04_native_launch_diagnostic_001.json').read_text());logical=json.loads((R/'plans/logical_plan.json').read_text());execution=json.loads((raw/'execution_manifest.json').read_text());selected={x['source_r06_target_id'] for f in logical['selected_families'] if f['r06_plan']['plan_id'] in execution['segment']['logical_family_ids'] for x in f['targets'] if x['state']=='requires_fresh_r08_pmc'};bound={}
for p in (raw/'workload/runtime_bindings').glob('rank*.jsonl'):
 with p.open() as f:
  for line in f:
   x=json.loads(line)
   if x.get('source_r06_target_id') in selected:bound[x['canonical_target_id']]=x['source_r06_target_id']
markers={}
for p in (raw/'workload/overlay_events').glob('rank*/*.jsonl'):
 with p.open() as f:
  for line in f:
   x=json.loads(line)
   if x['canonical_target_id'] in bound:markers[x['range_name']]=bound[x['canonical_target_id']]
conn=sqlite3.connect('file:'+str(raw/'capture.db')+'?mode=ro&immutable=1',uri=True);conn.row_factory=sqlite3.Row;conn.execute('PRAGMA mmap_size=4294967296');conn.execute('PRAGMA cache_size=-1048576');cfg={r['PID']:dict(r) for r in conn.execute('SELECT * FROM CONFIG')};intervals=collections.defaultdict(list)
for pid in {r['pid'] for r in d['non_direct_dispatches']}:
 ck=cfg[pid]['KEY'];assert ck.replace('_','').isalnum()
 for x in conn.execute('SELECT * FROM "HIPTX_'+ck+'"'):
  if x['message'] in markers:intervals[pid,x['tid']].append((x['begin_Index'],x['end_Index'],x['BeginNs'],x['EndNs'],markers[x['message']]))
for scope,items in intervals.items():items.sort()
begins={k:[x[0] for x in v] for k,v in intervals.items()};seen=set();hits=[];cross=collections.Counter();groups=collections.Counter()
for x in d['non_direct_dispatches']:
 h=x['HIP'];scope=x['pid'],h['tid'];key=x['pid'],h['_Index'];groups[x['pid'],x['API']]+=1
 if key in seen:continue
 seen.add(key)
 for row in intervals.get(scope,[]):
  if row[0]<=h['_Index']<=row[1]:
   cross['index_intersection']+=1
   if row[2]<=h['BeginNs']<=h['EndNs']<=row[3]:hits.append({'pid':x['pid'],'HIP_Index':h['_Index'],'API':x['API'],'selected_source_r06_target_id':row[4],'HIP':h})
result={'status':'diagnostic_complete','selected_R06_owner_count':len(selected),'selected_native_marker_rows':sum(len(v) for v in intervals.values()),'background_native_dispatch_count':len(d['non_direct_dispatches']),'distinct_graph_launch_count':len(seen),'counter':dict(cross),'selected_process_containing_graph_launch_count':len(hits),'all_outside_selected_processes':not hits,'exact_intersections':hits,'elapsed_seconds':time.monotonic()-start}
p=R/'raw/runtime_tools/native_graph_selected_intersection_001.json'
with p.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in result.items() if k!='exact_intersections'},indent=2));print('HIT_EXAMPLES',json.dumps(hits[:5],indent=2),flush=True)
