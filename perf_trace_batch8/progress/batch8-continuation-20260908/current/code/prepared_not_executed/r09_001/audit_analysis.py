"""Independent CPU audit. No import of the analysis builder or its rules."""
from pathlib import Path
import csv,json,hashlib,collections,math,bisect,array,time,sys
ROOT=Path(__file__).parents[2]
NAMES=['request_timeline','process_timeline','kernel_timeline','live_utilization_aligned','process_live_utilization','kernel_concurrency','queue_concurrency','launch_gaps','high_latency_processes','dependency_state','traffic_resource_attachment','opportunity_candidates']
def check(x,m):
 if not x:raise RuntimeError(m)
def read(p):return json.loads(Path(p).read_text())
def rows(p):
 with Path(p).open(newline='') as f:yield from csv.DictReader(f)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def main():
 start=time.monotonic();manifest=read(ROOT/'analysis/fresh_e2e_analysis.json');check(manifest['status']=='candidate_complete_pending_independent_audit','candidate manifest');check([x['logical_name'] for x in manifest['tables']]==NAMES,'exact twelve ordered tables')
 a=read(ROOT/'authorization/assignment.json');check(sha(ROOT/'authorization/assignment.json')==manifest['assignment']['sha256'],'assignment bytes')
 for x in a['predecessor_handoffs']+a['consumed_sources']+manifest['source_records']:check(sha(x['path'])==x['sha256'],'sealed source '+x['path'])
 check(manifest['complete_timeline'] and not manifest['sampling_performed'] and not manifest['replay_timing_used_as_latency'],'full observed evidence boundary')
 table={};metadata={};checks={}
 for m in manifest['tables']:
  p=Path(m['path']);check(p.is_relative_to(ROOT/'tables') and p.resolve().is_relative_to(ROOT.resolve()),'table containment');check(p.stat().st_size==m['size'] and sha(p)==m['sha256'],'table bytes')
  with p.open() as f:r=csv.DictReader(f);check(r.fieldnames==m['schema'] and digest(r.fieldnames)==m['schema_sha256'],'ordered schema')
  metadata[m['logical_name']]=m
  if m['logical_name']!='live_utilization_aligned':
   data=list(rows(p));check(len(data)==m['row_count'],'table row count');table[m['logical_name']]=data
 request_src=next(x['path'] for x in a['consumed_sources'] if x['path'].endswith('/capture/workload/request_results.json'));oldrequests=read(request_src)['results'];requests={r['request_id']:r for r in table['request_timeline']}
 check(len(requests)==len(table['request_timeline'])==8 and set(requests)=={r['request_id'] for r in oldrequests},'all eight unique source request identities')
 for x in oldrequests:
  r=requests[x['request_id']];check(int(r['begin_ns'])==x['start_realtime_ns'] and int(r['end_ns'])==x['end_realtime_ns'] and int(r['duration_ns'])==x['end_realtime_ns']-x['start_realtime_ns'],'request observed client times');check(int(r['rank'])==x['data_parallel_rank_requested']==int(r['physical_device_id']),'request native topology');check(int(r['completion_tokens'])==1024 and int(r['http_status'])==200,'request success')
 check(max(int(r['begin_ns']) for r in requests.values())<min(int(r['end_ns']) for r in requests.values()),'all eight requests concurrently in flight')
 r07=Path(next(x['path'] for x in manifest['source_records'] if x['path'].endswith('/trace/process_ranges.csv'))).parents[1]
 oldprocess={r['process_range_id']:r for r in rows(r07/'trace/process_ranges.csv')};oldkernel={r['kernel_instance_id']:r for r in rows(r07/'trace/strict_owned_kernels.csv')};oldruntime={r['runtime_call_id']:r for r in rows(r07/'trace/hip_runtime_calls.csv')}
 processes={r['process_range_id']:r for r in table['process_timeline']};kernels={r['kernel_instance_id']:r for r in table['kernel_timeline']}
 check(set(processes)==set(oldprocess) and len(processes)==len(table['process_timeline']),'complete unique source process universe');check(set(kernels)==set(oldkernel) and len(kernels)==len(table['kernel_timeline']),'complete unique source kernel universe')
 bound=read(r07/'contract/r07_bound_target_sidecar.json')['records'];expected={r['canonical_target_id']:r for r in bound if 'source_r06_target_id' in r};check({p['canonical_target_id'] for p in processes.values()}==set(expected),'exact R06 target membership')
 byreq=collections.defaultdict(lambda:collections.Counter());context_seen=set()
 for pid,r in processes.items():
  old=oldprocess[pid]
  for key,value in old.items():
   if key=='evidence_class':check(r['source_evidence_class']==value,'source evidence label preserved')
   else:check(r[key]==value,'lossless process field '+key)
  q=requests[r['request_id']];check(int(q['begin_ns'])<=int(r['begin_ns'])<=int(r['end_ns'])<=int(q['end_ns']),'process inside actual request')
  byreq[r['request_id']][r['phase']]+=1
  cs=json.loads(r['hip_runtime_context_schema'])
  for values in json.loads(r['hip_runtime_context']):
   x=dict(zip(cs,values));oid=x['runtime_call_id'];check(oid not in context_seen and oid in oldruntime,'unique runtime context');context_seen.add(oid);check(all(oldruntime[oid][k]==v for k,v in x.items()),'lossless HIP runtime context');check(oldruntime[oid]['owner_process_range_id']==pid,'runtime context deepest owner')
  if r['parent_process_range_id']:
   parent=processes[r['parent_process_range_id']];check(parent['range_name']==r['parent_range_name'] and int(parent['begin_ns'])<=int(r['begin_ns'])<=int(r['end_ns'])<=int(parent['end_ns']),'process nesting chain')
 check(context_seen==set(oldruntime),'all native runtime context rows conserved')
 for q in requests:
  for phase in ['prefill','decode']:
   e={x['canonical_target_id'] for x in expected.values() if x['request_id']==q and x['phase']==phase};o={x['canonical_target_id'] for x in processes.values() if x['request_id']==q and x['phase']==phase};check(e==o and len(o)>0,'per-request phase exact coverage')
 for kid,r in kernels.items():
  old=oldkernel[kid]
  for key,value in old.items():check(r['source_evidence_class' if key=='evidence_class' else key]==value,'lossless kernel field '+key)
  p=processes[r['owner_process_range_id']];h=oldruntime[r['runtime_call_id']];check(h['owner_process_range_id']==p['process_range_id'] and h['hip_runtime_index']==r['hip_runtime_index']==r['native_device_index'],'strict runtime/native kernel chain');check(r['request_id']==p['request_id'] and r['dp_rank']==p['dp_rank']==r['native_device'],'kernel topology and request')
  check(r['launch_begin_ns']==h['begin_ns'] and r['launch_end_ns']==h['end_ns'],'observed launch timestamps')
 checks['eight_request_process_kernel_runtime_conservation']={'requests':len(requests),'processes':len(processes),'kernels':len(kernels),'runtime_context_rows':len(context_seen),'per_request_phase_counts':{k:dict(v) for k,v in byreq.items()}}
 # Stream-check every live source field and independently collect packed
 # midpoint arrays, preserving invalid calls and all explicit gap intervals.
 live_meta=metadata['live_utilization_aligned'];iterator=iter(rows(live_meta['path']));sample_data={d:[] for d in [0,1]};count=0
 for old in rows(r07/'alignment/r07_live_utilization_aligned.csv'):
  r=next(iterator);count+=1;check(r['record_kind']=='sample' and all(r[k]==v for k,v in old.items()),'lossless sample value');d=int(old['native_device']);sample_data[d].append((int(old['sample_midpoint_monotonic_ns']),int(old['se_active_cu_pct']),old['timing_eligible']=='True'))
 gaps=list(rows(r07/'alignment/r07_live_utilization_gaps.csv'))
 for old in gaps:
  r=next(iterator);count+=1;check(r['record_kind']=='gap' and all(r[k]==v for k,v in old.items()),'lossless gap')
 anchor_path=next(x['path'] for x in manifest['source_records'] if x['path'].endswith('/clock_anchors.json'));anchors=read(anchor_path)
 for label in ['start','end']:
  r=next(iterator);count+=1;check(r['record_kind']=='anchor' and r['anchor_name']==label,'anchor identity');check(all(str(v)==r['anchor_'+k] for k,v in anchors[label].items()),'exact anchor value')
 check(next(iterator,None) is None and count==live_meta['row_count'],'complete live row count')
 times={d:[x[0] for x in values] for d,values in sample_data.items()};live={r['process_range_id']:r for r in table['process_live_utilization']};check(set(live)==set(processes),'all process live states')
 for pid,p in oldprocess.items():
  d=int(p['native_device']);b=int(p['sidecar_start_monotonic_ns']);e=int(p['sidecar_end_monotonic_ns']);left=bisect.bisect_left(times[d],b);right=bisect.bisect_right(times[d],e);inside=sample_data[d][left:right];eligible=[x[1] for x in inside if x[2]];invalid=len(inside)-len(eligible);gs=[g for g in gaps if int(g['native_device'])==d and int(g['gap_begin_monotonic_ns'])<e and b<int(g['gap_end_monotonic_ns'])]
  if int(p['sidecar_alignment_uncertainty_ns'])>1000000:state='unavailable_alignment_error'
  elif gs:state='unavailable_sampling_gap'
  elif len(eligible)>=3:state='available'
  elif invalid:state='unavailable_alignment_error'
  else:state='unavailable_intrinsic_short_window'
  value=f'{sum(eligible)/len(eligible):.9f}' if state=='available' else '';r=live[pid]
  for k,v in {'real_sample_count_inside':len(inside),'timing_eligible_sample_count':len(eligible),'alignment_error_sample_count':invalid,'intersecting_gap_count':len(gs),'availability_state':state,'se_active_cu_pct_mean':value}.items():check(r[k]==str(v),'independent live membership/availability '+k)
 checks['live_conservation']={'samples':sum(len(x) for x in sample_data.values()),'gaps':len(gaps),'anchors':2,'process_states':dict(collections.Counter(r['availability_state'] for r in live.values()))}
 del sample_data,times
 output_scopes=collections.defaultdict(list)
 for r in table['kernel_concurrency']:output_scopes[r['scope_type'],r['scope_id']].append(r)
 expected_scopes={('device',str(d)):[x for x in oldkernel.values() if int(x['native_device'])==d] for d in [0,1]};expected_scopes.update({('rank',str(d)):[x for x in oldkernel.values() if int(x['dp_rank'])==d] for d in [0,1]});expected_scopes.update({('request_rank_device',q):[x for x in oldkernel.values() if x['request_id']==q] for q in requests});check(set(output_scopes)==set(expected_scopes),'all device/rank/request concurrency scopes')
 kc_byid={r['segment_id']:r for r in table['kernel_concurrency']};union={}
 for scope,members in expected_scopes.items():
  events=[]
  for x in members:events.extend([(int(x['begin_ns']),1,x['kernel_instance_id']),(int(x['end_ns']),0,x['kernel_instance_id'])])
  events.sort();active=set();last=None;expected_rows=[];pos=0
  while pos<len(events):
   stamp=events[pos][0]
   if last is not None and stamp>last and active:expected_rows.append((last,stamp,sorted(active)))
   while pos<len(events) and events[pos][0]==stamp:
    _,kind,kid=events[pos]
    if kind:check(kid not in active,'one start');active.add(kid)
    else:check(kid in active,'end before start in half-open sweep');active.remove(kid)
    pos+=1
   last=stamp
  actual=sorted(output_scopes[scope],key=lambda x:int(x['begin_ns']));check(len(actual)==len(expected_rows),'exact sweep segment denominator')
  for r,(b,e,ids) in zip(actual,expected_rows):
   check(int(r['begin_ns'])==b and int(r['end_ns'])==e and json.loads(r['active_kernel_ids'])==ids,'exact concurrency intervals and full membership');check(int(r['active_kernel_count'])==len(ids) and r['active_kernel_ids_sha256']==digest(ids),'active set count/hash');queues=sorted({oldkernel[k]['queue_id'] for k in ids});check(json.loads(r['active_queue_ids'])==queues and int(r['active_queue_count'])==len(queues),'queue uniqueness')
  check(sum((e-b)*len(ids) for b,e,ids in expected_rows)==sum(int(x['duration_ns']) for x in members),'duration weighted active count conservation');union['/'.join(scope)]=sum(e-b for b,e,ids in expected_rows)
 check(len(manifest['derived_scope_summaries'])==len(expected_scopes),'all busy union summaries')
 for summary in manifest['derived_scope_summaries']:
  scope=(summary['scope_type'],summary['scope_id']);check(summary['selected_kernel_union_duration_ns']==union['/'.join(scope)],'independent selected-kernel busy union');check(summary['peak_selected_kernel_concurrency']==max(int(x['active_kernel_count']) for x in output_scopes[scope]),'peak selected kernel count')
 device_segments={d:sorted(output_scopes['device',d],key=lambda x:int(x['begin_ns'])) for d in ['0','1']};device_ends={d:[int(x['end_ns']) for x in xs] for d,xs in device_segments.items()}
 owned_byproc=collections.defaultdict(set)
 for kid,k in oldkernel.items():owned_byproc[k['owner_process_range_id']].add(kid)
 check(len(table['queue_concurrency'])==len(kc_byid),'queue segmentation denominator')
 for r in table['queue_concurrency']:
  k=kc_byid[r['kernel_concurrency_segment_id']]
  for f in ['begin_ns','end_ns','active_kernel_count','active_queue_count','active_queue_ids','active_kernel_ids_sha256','scope_type','scope_id']:check(r[f]==k[f],'kernel/queue sweep reconciliation')
 groups=collections.defaultdict(list)
 for k in oldkernel.values():groups[(k['request_id'],k['dp_rank'],k['native_device'],k['queue_id'],k['stream_id'])].append(k)
 expected_pairs={}
 for scope,items in groups.items():
  items.sort(key=lambda x:int(x['hip_runtime_index']))
  for x,y in zip(items,items[1:]):expected_pairs[x['kernel_instance_id'],y['kernel_instance_id']]=(x,y)
 got=set();gaps_byproc=collections.defaultdict(list)
 for r in table['launch_gaps']:
  key=(r['previous_kernel_instance_id'],r['next_kernel_instance_id']);check(key in expected_pairs and key not in got,'unique exact adjacent native launch pair');got.add(key);x,y=expected_pairs[key];delta=int(y['begin_ns'])-int(x['end_ns']);check(int(r['gap_ns'])==max(0,delta) and int(r['overlap_ns'])==max(0,-delta),'gap/overlap arithmetic');check(r['previous_hip_runtime_index']==x['hip_runtime_index'] and r['next_hip_runtime_index']==y['hip_runtime_index'],'native launch sequence');gaps_byproc[y['owner_process_range_id']].append(r)
 check(got==set(expected_pairs),'all launch gaps retained');checks['concurrency_and_gap_conservation']={'scopes':len(expected_scopes),'kernel_segments':len(kc_byid),'queue_segments':len(table['queue_concurrency']),'union_duration_ns_by_scope':union,'launch_pairs':len(got)}
 durations=sorted(int(x['duration_ns']) for x in oldprocess.values());global_threshold=durations[(95*len(durations)+99)//100-1];peers=collections.defaultdict(list)
 for p in oldprocess.values():peers[(p['phase'],p['layer_type'],p['process_id'],p['fragment_id'])].append(int(p['duration_ns']))
 peer_threshold={k:sorted(v)[(95*len(v)+99)//100-1] for k,v in peers.items()};expected_high=set()
 for pid,p in oldprocess.items():
  key=(p['phase'],p['layer_type'],p['process_id'],p['fragment_id'])
  if int(p['duration_ns'])>=global_threshold or int(p['duration_ns'])>=peer_threshold[key]:expected_high.add(pid)
 high={r['process_range_id']:r for r in table['high_latency_processes']};check(set(high)==expected_high and len(high)==len(table['high_latency_processes']),'full high-latency population and all p95 ties')
 for pid,r in high.items():
  p=oldprocess[pid];key=(p['phase'],p['layer_type'],p['process_id'],p['fragment_id']);check(int(r['global_denominator'])==len(durations) and int(r['global_p95_ns'])==global_threshold and int(r['peer_denominator'])==len(peers[key]) and int(r['peer_p95_ns'])==peer_threshold[key],'independent p95 thresholds')
 dep_source={r['dependency_edge_id']:r for r in rows(r07/'dependency/fresh_run_dependency_adapter.csv')};dep_edges={r['edge_id']:r for r in table['dependency_state'] if r['record_kind']=='edge'};dep_nodes={r['node_id']:r for r in table['dependency_state'] if r['record_kind']=='node'};expected_nodes=collections.defaultdict(set);dep_byproc=collections.defaultdict(set)
 check(set(dep_edges)==set(dep_source),'all adapter edges/states')
 for eid,old in dep_source.items():
  r=dep_edges[eid]
  for k,v in old.items():check(r[k]==v,'lossless dependency field '+k)
  dep_byproc[old['process_range_id']].add(eid)
  for kind,key in [('process','process_range_id'),('runtime','hip_runtime_call_id'),('kernel','kernel_instance_id')]:
   if old[key]:expected_nodes[kind+':'+old[key]].add(eid)
 check(set(dep_nodes)==set(expected_nodes),'adapter endpoint node conservation')
 for key,edges in expected_nodes.items():check(set(json.loads(dep_nodes[key]['supporting_adapter_edge_ids']))==edges,'node support exact adapter rows')
 resource_source=next(x['path'] for x in manifest['source_records'] if x['path'].endswith('/resource_model_001/traffic_resource_attachment.csv'));resources={r['metric_id']:r for r in rows(resource_source)};traffic={r['metric_id']:r for r in table['traffic_resource_attachment']};check(set(traffic)==set(resources) and len(traffic)==len(table['traffic_resource_attachment']),'complete unique resource metrics')
 metrics_byproc=collections.defaultdict(list)
 for mid,old in resources.items():
  r=traffic[mid]
  for k,v in old.items():
   if k!='source_row_id':check(r[k]==v,'lossless resource field '+k)
  p=oldprocess[r['r07_process_range_id']];check(r['join_left_id']==p['process_range_id'] and r['join_right_id']==mid and r['request_id']==p['request_id'] and r['rank']==p['dp_rank']==r['physical_device_id'],'exact resource owner and topology');metrics_byproc[p['process_range_id']].append(old)
  allowed=old['record_kind']=='native_dispatch_metric' and old['runtime_shape_match'] in ['True','true'];check(r['runtime_shape_comparison_permitted']==str(allowed),'runtime shape comparison guard')
 candidates={r['process_range_id']:r for r in table['opportunity_candidates']};check(set(candidates)==set(processes) and len(candidates)==len(table['opportunity_candidates']),'every process evaluated by opportunity rules')
 for pid,r in candidates.items():
  lv=live[pid];metrics=metrics_byproc[pid];native=[x for x in metrics if x['record_kind']=='native_dispatch_metric'];matching=[x for x in native if x['runtime_shape_match'] in ['True','true']];blocking=[]
  if lv['availability_state']!='available':blocking.append(lv['availability_state'])
  if not native:blocking.append('no_attributable_R08_native_metric_for_process')
  if native and len(matching)!=len(native):blocking.append('replay_runtime_shape_differs_from_observed_R07')
  if any(x['metric_name']=='GPUBusy_pct' and x['availability_state']!='available' for x in native):blocking.append('required_GPUBusy_unavailable')
  low=lv['availability_state']=='available' and float(lv['se_active_cu_pct_mean'])<50
  state='non_candidate' if pid not in expected_high else ('blocked_by_unavailable' if blocking else ('candidate' if low else 'non_candidate'))
  p=oldprocess[pid];overlap=[];d=p['native_device'];begin=int(p['begin_ns']);end=int(p['end_ns']);position=bisect.bisect_right(device_ends[d],begin)
  for segment in device_segments[d][position:]:
   if int(segment['begin_ns'])>=end:break
   overlap.append(int(segment['active_kernel_count']))
  check(int(r['max_selected_kernel_concurrency_in_process_interval'])==max(overlap,default=0),'opportunity concurrency support');check(int(r['max_adjacent_selected_kernel_gap_ns'])==max((int(x['gap_ns']) for x in gaps_byproc[pid]),default=0),'opportunity exact gap support');check(set(json.loads(r['owned_kernel_ids']))==owned_byproc[pid],'complete opportunity kernel membership');check(int(r['native_metric_count'])==len(native) and int(r['replay_runtime_shape_match_metric_count'])==len(matching),'opportunity exact resource denominators')
  check(r['candidate_state']==state and json.loads(r['blocking_reasons'])==blocking,'independent opportunity rule');check(set(json.loads(r['metric_ids']))=={x['metric_id'] for x in metrics},'all metric support');check(set(json.loads(r['dependency_edge_ids']))==dep_byproc[pid],'dependency opportunity support');check(r['measured_or_predicted_speedup_claimed']=='False' and r['root_cause_claimed_proven']=='False','hypothesis boundary')
 checks['classification_dependency_resource_opportunity']={'high_latency_processes':len(high),'global_p95_ns':global_threshold,'peer_groups':len(peers),'dependency_nodes':len(dep_nodes),'dependency_edges':len(dep_edges),'metrics':len(resources),'process_opportunity_states':dict(collections.Counter(r['candidate_state'] for r in candidates.values()))}
 # Independently enforce user's eight-request gate on every request-specific
 # source universe, rather than inferring coverage from a grand total.
 check(set(byreq)==set(requests),'all eight have process trace');check({k['request_id'] for k in kernels.values()}==set(requests),'all eight have strict kernel trace');check({p['rank'] for p in processes.values()}=={'0','1'},'both worker ranks represented')
 result={'status':'complete','independent_audit':True,'builder_imported':False,'runtime_goal':'R09','runtime_run_id':manifest['runtime_run_id'],'lineage_id':manifest['lineage_id'],'trace_profile_sha256':manifest['trace_profile_sha256'],'analysis_manifest_sha256':sha(ROOT/'analysis/fresh_e2e_analysis.json'),'auditor_sha256':sha(Path(__file__)),'checks':checks,'all_eight_requests_have_exact_phase_process_and_kernel_coverage':True,'replay_timing_used_as_latency':False,'all_tables_complete':True,'cpu_only':True,'elapsed_seconds':time.monotonic()-start}
 path=ROOT/'validation/R09_TABLE_INDEPENDENT_AUDIT.json';path.parent.mkdir(exist_ok=True)
 with path.open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
 print('R09_INDEPENDENT_TABLE_AUDIT_COMPLETE',round(time.monotonic()-start,2),flush=True)
if __name__=='__main__':main()
