"""Complete twelve-table analysis of the admitted R07 clock; CPU only."""
from stage_common import *
import array,bisect,collections,math,time,sys
ALGORITHM='r09-exact-observed-1'
def allrows(p):return list(rows(p))
def p95(a):
 check(bool(a),'nonempty percentile denominator');return sorted(a)[math.ceil(.95*len(a))-1]
def sweep(kernels,scope_type,scope_id,request,rank,device):
 changes=collections.defaultdict(lambda:[set(),set()]);byid={r['kernel_instance_id']:r for r in kernels}
 for r in kernels:
  b=int(r['begin_ns']);e=int(r['end_ns']);check(b<e,'positive kernel interval');changes[b][1].add(r['kernel_instance_id']);changes[e][0].add(r['kernel_instance_id'])
 active=set();previous=None;result=[]
 for stamp,(ends,starts) in sorted(changes.items()):
  if previous is not None and previous<stamp and active:
   ids=sorted(active);queues=sorted({byid[k]['queue_id'] for k in ids});result.append({'segment_id':digest([scope_type,scope_id,previous,stamp,ids]),'scope_type':scope_type,'scope_id':scope_id,'request_id':request,'rank':rank,'physical_device_id':device,'begin_ns':previous,'end_ns':stamp,'duration_ns':stamp-previous,'active_kernel_count':len(ids),'active_kernel_ids':ids,'active_kernel_ids_sha256':digest(ids),'active_queue_count':len(queues),'active_queue_ids':queues,'aggregation_rule':'scope-local; device/rank/request views are non-additive','clock':'R07 native HIPOPS realtime nanoseconds'})
  check(ends<=active,'ending active kernels');active-=ends;active|=starts;previous=stamp
 check(not active,'sweep closed');return result

def main():
 started=time.monotonic();assignment,target=admission();check(not (ROOT/'analysis/fresh_e2e_analysis.json').exists(),'new immutable build')
 src={k:rec(R07/v) for k,v in {'process':'trace/process_ranges.csv','kernel':'trace/strict_owned_kernels.csv','runtime':'trace/hip_runtime_calls.csv','layer':'trace/layer_ranges.csv','forward':'trace/forward_ranges.csv','request_marker':'trace/request_ranges.csv','sample':'alignment/r07_live_utilization_aligned.csv','gap':'alignment/r07_live_utilization_gaps.csv','process_live':'alignment/r07_process_live_utilization.csv','dependency':'dependency/fresh_run_dependency_adapter.csv'}.items()}
 request_input=next(x for x in assignment['consumed_sources'] if x['path'].endswith('/capture/workload/request_results.json'));src['request']=request_input
 src['anchors']=rec(CONTROL/'r07_additional_inputs/clock_anchors.json');src['resource']=rec(R08/'model/resource_model_001/traffic_resource_attachment.csv')
 processes=allrows(src['process']['path']);kernels=allrows(src['kernel']['path']);runtime=allrows(src['runtime']['path']);layer=allrows(src['layer']['path']);forward=allrows(src['forward']['path']);reqmarkers=allrows(src['request_marker']['path'])
 process_byid={p['process_range_id']:p for p in processes};kernel_byid={k['kernel_instance_id']:k for k in kernels};check(len(process_byid)==len(processes) and len(kernel_byid)==len(kernels),'unique full observed universes')
 bound=read(R07/'contract/r07_bound_target_sidecar.json')['records'];bound_byid={b['canonical_target_id']:b for b in bound};check({p['canonical_target_id'] for p in processes}=={b['canonical_target_id'] for b in bound if 'source_r06_target_id' in b},'R06 full process target conservation')
 requests=[];ordinal={};intervals={};results=read(request_input['path'])['results']
 for result in sorted(results,key=lambda x:x['dispatch_ordinal']):
  q=result['request_id'];rank=result['data_parallel_rank_requested'];check(result['http_status']==200 and not result['error'] and result['completion_tokens']==1024,'successful measured request');ordinal[q]=int(result['dispatch_ordinal'])+1
  b=int(result['start_realtime_ns']);e=int(result['end_realtime_ns']);check(e>b and result['duration_ns']==result['end_monotonic_ns']-result['start_monotonic_ns'],'request clock arithmetic');intervals[q]=(b,e)
  markers=[r for r in reqmarkers if r['request_id']==q]
  requests.append({**common(src['request'],'R07_client_request_outcome',q,q,rank),**result,'measured_request_ordinal':ordinal[q],'begin_ns':b,'end_ns':e,'duration_ns':e-b,'client_monotonic_duration_ns':result['duration_ns'],'clock_drift_difference_ns':e-b-result['duration_ns'],'observed_phase_markers':markers,'warmup':False})
 check(len(requests)==8 and len(ordinal)==8 and {x['rank'] for x in requests}=={0,1},'eight successful measured requests and DP2')
 tables=[]
 def emit(name,values,sources,sortkey):
  check(name==TABLES[len(tables)],'exact table order');m=write_table(name,values,fields_of(values),sortkey,sources);tables.append(m);print('R09_TABLE',name,m['row_count'],flush=True)
 emit('request_timeline',requests,[src['request'],src['request_marker']],['measured_request_ordinal'])
 runtime_byproc=collections.defaultdict(list);launch={}
 for x in runtime:
  runtime_byproc[x['owner_process_range_id']].append(x)
  if x['is_kernel_launch']=='True':launch[x['hip_runtime_table'],x['hip_runtime_rowid']]=x
 context_fields=['runtime_call_id','hip_runtime_table','hip_runtime_rowid','hip_runtime_index','hip_runtime_api','hip_runtime_args','begin_ns','end_ns','duration_ns','is_kernel_launch','launch_correlation_state','tid']
 pvalues=[];process_name={p['range_name']:p['process_range_id'] for p in processes}
 for p in sorted(processes,key=lambda x:(int(x['begin_ns']),x['process_range_id'])):
  q=p['request_id'];b,e=intervals[q];check(b<=int(p['begin_ns'])<=int(p['end_ns'])<=e,'actual client request contains native process')
  binding=bound_byid[p['canonical_target_id']];parent=process_name.get(p['parent_range_name'],'');contexts={}
  for key,items in [('layer',layer),('forward',forward)]:contexts[key]=[x for x in items if x['request_id']==q and x['forward_id']==p['forward_id'] and int(x['begin_ns'])<=int(p['begin_ns']) and int(x['end_ns'])>=int(p['end_ns'])]
  pvalues.append({**p,**common(src['process'],'R07_process',p['process_range_id'],q,p['dp_rank']),'source_evidence_class':p['evidence_class'],'measured_request_ordinal':ordinal[q],'parent_process_range_id':parent,'source_r06_target_id':binding['source_r06_target_id'],'runtime_bound_target':binding,'layer_forward_context':contexts,'hip_runtime_context_schema':context_fields,'hip_runtime_context':[[x[k] for k in context_fields] for x in runtime_byproc[p['process_range_id']]],'context_source_records':[src['runtime'],src['layer'],src['forward']],'coverage_scope':'complete declared R06 target universe: selected first prefill/decode occurrences; other generated-token execution is not traced here'})
 emit('process_timeline',pvalues,[src[k] for k in ['process','runtime','layer','forward']],['begin_ns','process_range_id'])
 resources=allrows(src['resource']['path']);bykernel=collections.defaultdict(set);byprocessmetric=collections.defaultdict(list)
 for x in resources:
  check(x['r07_process_range_id'] in process_byid,'resource exact process membership');byprocessmetric[x['r07_process_range_id']].append(x)
  if x['r07_kernel_instance_id']:check(x['r07_kernel_instance_id'] in kernel_byid,'resource exact kernel membership');bykernel[x['r07_kernel_instance_id']].add(x['physical_attribute_id'])
 kvalues=[]
 for k in sorted(kernels,key=lambda x:(int(x['begin_ns']),x['kernel_instance_id'])):
  owner=process_byid[k['owner_process_range_id']];h=launch[k['hip_runtime_table'],k['hip_runtime_rowid']];check(h['hip_runtime_index']==k['hip_runtime_index'] and h['owner_process_range_id']==k['owner_process_range_id'],'exact observed runtime/kernel correlation')
  kvalues.append({**k,**common(src['kernel'],'R07_strict_owned_kernel',k['kernel_instance_id'],k['request_id'],k['dp_rank']),'source_evidence_class':k['evidence_class'],'measured_request_ordinal':ordinal[k['request_id']],'phase':owner['phase'],'layer_type':owner['layer_type'],'q_len':owner['q_len'],'kv_len':owner['kv_len'],'runtime_call_id':h['runtime_call_id'],'launch_begin_ns':h['begin_ns'],'launch_end_ns':h['end_ns'],'launch_duration_ns':h['duration_ns'],'launch_tid':h['tid'],'r08_physical_attribute_ids':sorted(bykernel[k['kernel_instance_id']]),'resource_join_rule':'exact R07 kernel_instance_id; 1:N metric observations; each physical attribute referenced once','runtime_source_record':src['runtime']})
 emit('kernel_timeline',kvalues,[src['kernel'],src['runtime'],src['resource']],['begin_ns','kernel_instance_id'])
 # Stream the complete 2.49M sample population; packed arrays support exact
 # per-process membership without a multi-gigabyte Python dictionary cache.
 samples={d:{'time':array.array('q'),'value':array.array('q'),'eligible':array.array('q')} for d in [0,1]};gaps=allrows(src['gap']['path']);anchors=read(src['anchors']['path'])
 sample_fields=list(next(rows(src['sample']['path'])));gap_fields=list(gaps[0]);anchor_fields=['anchor_name','anchor_monotonic_before_ns','anchor_monotonic_after_ns','anchor_monotonic_midpoint_ns','anchor_realtime_ns','anchor_pair_uncertainty_ns','anchor_metadata']
 base_fields=list(common(src['sample'],'sample',''));fields=list(dict.fromkeys(base_fields+['record_kind']+sample_fields+gap_fields+anchor_fields))
 def live_values():
  for x in rows(src['sample']['path']):
   d=int(x['native_device']);s=samples[d];t=int(x['sample_midpoint_monotonic_ns']);check(not s['time'] or t>=s['time'][-1],'sample source order');s['time'].append(t);s['value'].append(int(x['se_active_cu_pct']));s['eligible'].append(x['timing_eligible']=='True')
   yield {**common(src['sample'],'sample',str(d)+':'+x['sequence'],'',str(d),'observed_r07_live_utilization'),**x,'record_kind':'sample'}
  for x in gaps:yield {**common(src['gap'],'gap',x['native_device']+':'+x['previous_sequence']+':'+x['next_sequence'],'',x['native_device'],'observed_r07_live_utilization'),**x,'record_kind':'gap'}
  for key in ['start','end']:
   x=anchors[key];yield {**common(src['anchors'],'anchor',key,evidence='observed_r07_clock_anchor'),'record_kind':'anchor','anchor_name':key,**{'anchor_'+k:v for k,v in x.items()},'anchor_metadata':{k:v for k,v in anchors.items() if k not in ['start','end']}}
 m=write_table('live_utilization_aligned',live_values(),fields,['record_kind_source_order','native_device','sequence'],[src[k] for k in ['sample','gap','anchors']]);tables.append(m);print('R09_TABLE',m['logical_name'],m['row_count'],flush=True)
 # Prefix sums preserve exact integer sample membership and reproduce R07's
 # arithmetic mean only when all three availability conditions hold.
 gapby=collections.defaultdict(list)
 for g in gaps:gapby[int(g['native_device'])].append(g)
 for d,s in samples.items():
  s['prefix_count']=array.array('q',[0]);s['prefix_sum']=array.array('q',[0])
  for v,ok in zip(s['value'],s['eligible']):s['prefix_count'].append(s['prefix_count'][-1]+ok);s['prefix_sum'].append(s['prefix_sum'][-1]+(v if ok else 0))
 live_original={x['process_range_id']:x for x in rows(src['process_live']['path'])};plvalues=[];live_byid={}
 for p in sorted(processes,key=lambda x:(int(x['begin_ns']),x['process_range_id'])):
  d=int(p['native_device']);s=samples[d];b=int(p['sidecar_start_monotonic_ns']);e=int(p['sidecar_end_monotonic_ns']);left=bisect.bisect_left(s['time'],b);right=bisect.bisect_left(s['time'],e)
  check(right==len(s['time']) or s['time'][right]!=e,'R07 inclusive-end convention has no boundary sample; half-open equivalence')
  count=right-left;eligible=s['prefix_count'][right]-s['prefix_count'][left];errors=count-eligible;gs=[g for g in gapby[d] if int(g['gap_begin_monotonic_ns'])<e and b<int(g['gap_end_monotonic_ns'])]
  if int(p['sidecar_alignment_uncertainty_ns'])>1000000:state='unavailable_alignment_error'
  elif gs:state='unavailable_sampling_gap'
  elif eligible>=3:state='available'
  elif errors:state='unavailable_alignment_error'
  else:state='unavailable_intrinsic_short_window'
  value=f"{(s['prefix_sum'][right]-s['prefix_sum'][left])/eligible:.9f}" if state=='available' else ''
  original=live_original[p['process_range_id']]
  for key,v in {'real_sample_count_inside':count,'timing_eligible_sample_count':eligible,'alignment_error_sample_count':errors,'intersecting_gap_count':len(gs),'availability_state':state,'se_active_cu_pct_mean':value}.items():check(str(v)==original[key],'independent R07 live aggregation reproduction: '+key)
  x={**original,**common(src['process_live'],'R07_process_live',p['process_range_id'],p['request_id'],p['dp_rank'],'derived_from_observed_r07' if state=='available' else 'unavailable'),'availability_state':state,'availability_reason':'' if state=='available' else state,'sample_membership_rule':'R07 declared midpoint membership; no endpoint coincidences; half-open equivalent','sample_left_index_per_device':left,'sample_right_exclusive_index_per_device':right,'eligible_value_sum':s['prefix_sum'][right]-s['prefix_sum'][left],'intersecting_gap_source_ids':[g['native_device']+':'+g['previous_sequence']+':'+g['next_sequence'] for g in gs],'source_process_record':src['process'],'source_sample_record':src['sample']};plvalues.append(x);live_byid[p['process_range_id']]=x
 emit('process_live_utilization',plvalues,[src[k] for k in ['process_live','process','sample','gap','anchors']],['process_begin_realtime_ns','process_range_id'])
 segments=[]
 for kind in ['device','rank']:
  for d in [0,1]:segments.extend(sweep([k for k in kernels if int(k['native_device'])==d],kind,str(d),'',str(d),str(d)))
 for request in requests:
  rid=request['request_id'];d=str(request['rank']);segments.extend(sweep([k for k in kernels if k['request_id']==rid],'request_rank_device',rid,rid,d,d))
 segments.sort(key=lambda x:(x['scope_type'],x['scope_id'],x['begin_ns'],x['segment_id']))
 kc=[{**common(src['kernel'],'derived_kernel_concurrency',x['segment_id'],x['request_id'],x['rank'],'derived_from_observed_r07'),**x,'algorithm_version':'half-open-exact-sweep-1'} for x in segments]
 emit('kernel_concurrency',kc,[src['kernel']],['scope_type','scope_id','begin_ns','segment_id'])
 qc=[{**x,'source_record_kind':'derived_queue_concurrency','kernel_concurrency_segment_id':x['segment_id'],'segment_id':digest(['queue',x['segment_id']])} for x in kc]
 emit('queue_concurrency',qc,[src['kernel']],['scope_type','scope_id','begin_ns','kernel_concurrency_segment_id'])
 groups=collections.defaultdict(list)
 for k in kvalues:groups[(k['request_id'],k['dp_rank'],k['native_device'],k['queue_id'],k['stream_id'])].append(k)
 gapvalues=[];gaps_byproc=collections.defaultdict(list)
 for scope,items in sorted(groups.items()):
  items.sort(key=lambda x:(int(x['hip_runtime_index']),x['kernel_instance_id']))
  for previous,nxt in zip(items,items[1:]):
   pe=int(previous['end_ns']);nb=int(nxt['begin_ns']);gap=max(0,nb-pe);overlap=max(0,pe-nb);sid=digest(['launch_gap',previous['kernel_instance_id'],nxt['kernel_instance_id']])
   x={**common(src['kernel'],'observed_adjacent_native_launch_kernel_pair',sid,nxt['request_id'],nxt['dp_rank'],'derived_from_observed_r07'),'gap_id':sid,'queue_id':scope[3],'stream_id':scope[4],'previous_kernel_instance_id':previous['kernel_instance_id'],'next_kernel_instance_id':nxt['kernel_instance_id'],'previous_runtime_call_id':previous['runtime_call_id'],'next_runtime_call_id':nxt['runtime_call_id'],'previous_hip_runtime_index':previous['hip_runtime_index'],'next_hip_runtime_index':nxt['hip_runtime_index'],'previous_end_ns':pe,'next_begin_ns':nb,'gap_ns':gap,'overlap_ns':overlap,'gap_begin_ns':pe,'gap_end_ns':max(pe,nb),'next_owner_process_range_id':nxt['owner_process_range_id'],'sequence_rule':'same request/rank/device/queue/stream, ascending native HIP runtime index','interpretation':'gap between selected strict-owned kernels; may contain unselected work; not evidence of device idleness'};gapvalues.append(x);gaps_byproc[nxt['owner_process_range_id']].append(x)
 emit('launch_gaps',gapvalues,[src['kernel'],src['runtime']],['request_id','rank','physical_device_id','queue_id','next_hip_runtime_index'])
 peers=collections.defaultdict(list)
 def peer(p):return (p['phase'],p['layer_type'],p['process_id'],p['fragment_id'])
 for p in processes:peers[peer(p)].append(int(p['duration_ns']))
 global_p95=p95([int(p['duration_ns']) for p in processes]);peer_threshold={key:p95(a) for key,a in peers.items()};high=[];high_ids=set()
 for p in sorted(processes,key=lambda x:x['process_range_id']):
  key=peer(p);duration=int(p['duration_ns']);global_flag=duration>=global_p95;peer_flag=duration>=peer_threshold[key]
  if global_flag or peer_flag:
   high_ids.add(p['process_range_id']);high.append({**common(src['process'],'observed_duration_classification',p['process_range_id'],p['request_id'],p['dp_rank'],'derived_from_observed_r07'),'process_range_id':p['process_range_id'],'duration_ns':duration,'phase':p['phase'],'layer_type':p['layer_type'],'process_id':p['process_id'],'fragment_id':p['fragment_id'],'peer_group_key':list(key),'global_denominator':len(processes),'global_p95_ns':global_p95,'peer_denominator':len(peers[key]),'peer_p95_ns':peer_threshold[key],'meets_global_p95':global_flag,'meets_peer_p95':peer_flag,'percentile_rule':'nearest-rank ceil(0.95*N), complete positive-duration universe, all ties','classification_rule_version':'observed-duration-p95-1'})
 emit('high_latency_processes',high,[src['process']],['process_range_id'])
 deps=allrows(src['dependency']['path']);nodes={};edges=[];deps_byproc=collections.defaultdict(list)
 for dep in deps:
  pid=dep['process_range_id'];check(pid in process_byid,'dependency exact process');q=dep['request_id'];rank=dep['dp_rank'];node_refs=[('process',pid)]
  for kind,field in [('runtime','hip_runtime_call_id'),('kernel','kernel_instance_id')]:
   if dep[field]:node_refs.append((kind,dep[field]))
  for kind,sid in node_refs:
   nodekey=kind+':'+sid
   if nodekey not in nodes:nodes[nodekey]={**common(src['dependency'],'adapter_endpoint_node',nodekey,q,rank),'record_kind':'node','node_id':nodekey,'node_type':kind,'native_source_id':sid,'process_range_id':pid,'dependency_state':dep['dependency_state'],'availability_state':dep['dependency_state'],'availability_reason':'endpoint explicitly present in R07 adapter; no inferred temporal edge','supporting_adapter_edge_ids':[]}
   nodes[nodekey]['supporting_adapter_edge_ids'].append(dep['dependency_edge_id'])
  x={**dep,**common(src['dependency'],'adapter_edge',dep['dependency_edge_id'],q,rank),'record_kind':'edge','edge_id':dep['dependency_edge_id'],'from_node_id':'runtime:'+dep['hip_runtime_call_id'] if dep['hip_runtime_call_id'] else 'process:'+pid,'to_node_id':'kernel:'+dep['kernel_instance_id'] if dep['kernel_instance_id'] else '', 'owner_node_id':'process:'+pid,'availability_state':dep['dependency_state'],'availability_reason':'' if dep['kernel_instance_id'] else dep['dependency_relation'],'direction':'runtime_to_kernel' if dep['kernel_instance_id'] else 'explicit_no_direct_kernel_state','derived_waiting_or_ready_state':'unavailable_not_proven_by_adapter'};edges.append(x);deps_byproc[pid].append(dep['dependency_edge_id'])
 depvalues=sorted(nodes.values(),key=lambda x:x['node_id'])+sorted(edges,key=lambda x:x['edge_id']);emit('dependency_state',depvalues,[src['dependency']],['record_kind_nodes_then_edges','stable_node_or_edge_id'])
 traffic=[]
 for x in sorted(resources,key=lambda x:x['metric_id']):
  p=process_byid[x['r07_process_range_id']];check(x['request_id']==p['request_id'] and x['dp_rank']==p['dp_rank'] and x['native_device']==p['native_device'],'exact resource owner topology')
  traffic.append({**x,'rank':x['dp_rank'],'physical_device_id':x['native_device'],'source_record_kind':'R08_resource_metric','source_row_id':x['metric_id'],'r08_original_source_row_id':x['source_row_id'],'r08_metric_source_path':src['resource']['path'],'r08_metric_source_sha256':src['resource']['sha256'],'observed_process_source_sha256':src['process']['sha256'],'observed_kernel_source_sha256':src['kernel']['sha256'] if x['r07_kernel_instance_id'] else '', 'join_left_id':p['process_range_id'],'join_right_id':x['metric_id'],'join_cardinality':'one exact observed owner to many distinct metric observations; unique metric_id','join_state':'matched','join_rule_version':'exact-instance-resource-1','runtime_shape_comparison_permitted':x['runtime_shape_match'] in ['True','true'] if x['record_kind']=='native_dispatch_metric' else False})
 emit('traffic_resource_attachment',traffic,[src['resource'],src['process'],src['kernel']],['metric_id'])
 candidates=[]
 owned_byproc=collections.defaultdict(list)
 for k in kernels:owned_byproc[k['owner_process_range_id']].append(k)
 device_segments={str(d):sorted([x for x in segments if x['scope_type']=='device' and str(x['physical_device_id'])==str(d)],key=lambda x:x['begin_ns']) for d in [0,1]}
 device_segment_ends={d:[x['end_ns'] for x in xs] for d,xs in device_segments.items()}
 for p in sorted(processes,key=lambda x:x['process_range_id']):
  pid=p['process_range_id'];live=live_byid[pid];metrics=byprocessmetric[pid];native=[x for x in metrics if x['record_kind']=='native_dispatch_metric'];matching=[x for x in native if x['runtime_shape_match'] in ['True','true']];blocking=[]
  if live['availability_state']!='available':blocking.append(live['availability_state'])
  if not native:blocking.append('no_attributable_R08_native_metric_for_process')
  if native and len(matching)!=len(native):blocking.append('replay_runtime_shape_differs_from_observed_R07')
  if any(x['metric_name']=='GPUBusy_pct' and x['availability_state']!='available' for x in native):blocking.append('required_GPUBusy_unavailable')
  ishigh=pid in high_ids;low=live['availability_state']=='available' and float(live['se_active_cu_pct_mean'])<50
  ownkernels=owned_byproc[pid];ownset={k['kernel_instance_id'] for k in ownkernels};ds=device_segments[p['native_device']];start_index=bisect.bisect_right(device_segment_ends[p['native_device']],int(p['begin_ns']));overlap_segments=[]
  for x in ds[start_index:]:
   if x['begin_ns']>=int(p['end_ns']):break
   overlap_segments.append(x)
  max_concurrency=max([x['active_kernel_count'] for x in overlap_segments],default=0);maxgap=max([x['gap_ns'] for x in gaps_byproc[pid]],default=0)
  if not ishigh:state='non_candidate';reason='below global and comparable-peer p95'
  elif blocking:state='blocked_by_unavailable';reason=';'.join(blocking)
  elif low:state='candidate';reason='high observed duration and available live CU activity below50%; inspect exact native metrics and selected-kernel serialization'
  else:state='non_candidate';reason='high duration without low live-activity criterion'
  candidates.append({**common(src['process'],'opportunity_rule_evaluation',pid,p['request_id'],p['dp_rank'],'derived_from_observed_and_replay_projected'),'process_range_id':pid,'candidate_state':state,'availability_state':'available_rule_evaluation','hypothesis':reason,'duration_ns':p['duration_ns'],'meets_high_latency_rule':ishigh,'live_availability_state':live['availability_state'],'live_mean_pct':live['se_active_cu_pct_mean'],'live_threshold_pct':50,'max_selected_kernel_concurrency_in_process_interval':max_concurrency,'max_adjacent_selected_kernel_gap_ns':maxgap,'owned_kernel_ids':sorted(ownset),'dependency_edge_ids':deps_byproc[pid],'metric_ids':[x['metric_id'] for x in metrics],'replay_runtime_shape_match_metric_count':len(matching),'native_metric_count':len(native),'blocking_reasons':blocking,'contradicting_evidence':[] if low else ['low_live_activity_criterion_not_established'],'opportunity_rule_version':'duration-live-resource-hypothesis-1','quantitative_cross_clock_comparison_performed':False,'measured_or_predicted_speedup_claimed':False,'root_cause_claimed_proven':False,'target_change_authorized':False})
 emit('opportunity_candidates',candidates,[src['process'],src['process_live'],src['dependency'],src['resource'],src['kernel']],['process_range_id'])
 check([x['logical_name'] for x in tables]==TABLES,'complete exactly twelve tables')
 coverage=read(R08/'validation/batch8_observed_coverage_gate_001.json');check(coverage['request_count']==8 and coverage['exact_R06_bound_target_set_equality_per_request_phase'],'full eight-request observed coverage')
 summary_groups=collections.defaultdict(list)
 for segment in segments:summary_groups[segment['scope_type'],segment['scope_id']].append(segment)
 manifest={'schema_version':1,'status':'candidate_complete_pending_independent_audit','algorithm_version':ALGORITHM,'runtime_run_id':RUN_ID,'runtime_goal':'R09','lineage_id':RUN_ID,'trace_profile_sha256':PROFILE,'target':target,'assignment':rec(ROOT/'authorization/assignment.json'),'tables':tables,'source_records':list(src.values()),'row_universes':{'requests':len(requests),'processes':len(processes),'strict_owned_kernels':len(kernels),'runtime_context_rows':len(runtime),'live_samples':sum(len(x['time']) for x in samples.values()),'live_gaps':len(gaps),'live_anchors':2,'dependency_nodes':len(nodes),'dependency_edges':len(edges)},'batch8_coverage':coverage,'derived_scope_summaries':[{'scope_type':kind,'scope_id':scope,'rank':xs[0]['rank'],'physical_device_id':xs[0]['physical_device_id'],'selected_kernel_union_duration_ns':sum(x['duration_ns'] for x in xs),'peak_selected_kernel_concurrency':max(x['active_kernel_count'] for x in xs),'evidence_scope':'derived R07 strict-owned selected kernel busy union; not all device activity'} for (kind,scope),xs in sorted(summary_groups.items())],'observed_clock':'R07 native non-replay only; actual R07 client outcomes supply request intervals','complete_timeline':True,'timeline_coverage_scope':coverage['coverage_scope'],'sampling_performed':False,'top_n_performed':False,'event_budget_applied':False,'interpolation_or_imputation':False,'replay_timing_used_as_latency':False,'cross_device_concurrency_state':'unavailable_no_separate_cross_device_clock_error_bound_promoted','resource_clock_boundary':'separate replay metrics, no replay durations; runtime shape mismatch blocks comparison','global_p95_ns':global_p95,'peer_thresholds':[{'key':list(k),'denominator':len(peers[k]),'p95_ns':v} for k,v in sorted(peer_threshold.items())],'builder':rec(Path(__file__)),'common_tool':rec(Path(__file__).with_name('stage_common.py')),'interpreter':rec(Path(sys.executable).resolve()),'argv':sys.argv,'cpu_only':True,'model_or_device_or_profiler_execution_performed':False,'report_or_visualization_generated':False,'elapsed_seconds':time.monotonic()-started}
 save(ROOT/'analysis/fresh_e2e_analysis.json',manifest);print('R09_CANDIDATE_TABLES_COMPLETE',round(time.monotonic()-started,2),flush=True)
if __name__=='__main__':main()
