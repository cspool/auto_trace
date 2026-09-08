from pathlib import Path
import shutil,json,hashlib
root=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');old=root/'tools/analysis_001';new=root/'tools/analysis_002';shutil.copytree(old,new)
p=new/'normalize_capture.py';s=p.read_text().replace("'fragment_id','q_len','kv_len'","'fragment_id'")
s=s.replace("'runtime_shape_match':True","'runtime_shape_match':current['q_len']==observed['q_len'] and current['kv_len']==observed['kv_len'],'observed_q_len':observed['q_len'],'observed_kv_len':observed['kv_len'],'replay_q_len':current['q_len'],'replay_kv_len':current['kv_len']")
s=s.replace("'counter_payload_availability':'complete'", "'observed_q_len':observed_bound[old['owner_canonical_target_id']]['q_len'],'observed_kv_len':observed_bound[old['owner_canonical_target_id']]['kv_len'],'replay_q_len':native['bound']['q_len'],'replay_kv_len':native['bound']['kv_len'],'runtime_shape_match':all(native['bound'][k]==observed_bound[old['owner_canonical_target_id']][k] for k in ['q_len','kv_len']),'projection_context':'same corrected R06 request/phase/occurrence target and exact native kernel subsequence; runtime scheduler shapes are separately recorded','direct_R07_resource_measurement_claimed':False,'counter_payload_availability':'complete'")
s=s.replace("'all_attributes_replay_projected':True,","'all_attributes_replay_projected':True,'runtime_shape_match_counts':dict(collections.Counter(str(r['runtime_shape_match']) for r in accepted)),")
p.write_text(s)
p=new/'audit_capture.py';s=p.read_text().replace("'fragment_id','q_len','kv_len'","'fragment_id'")
a="        q=(pid,device,pmc['queue-id']);";b="        check(a['observed_q_len']==ob['q_len'] and a['observed_kv_len']==ob['kv_len'] and a['replay_q_len']==cb['q_len'] and a['replay_kv_len']==cb['kv_len'],'lossless runtime shape context')\n        check(a['runtime_shape_match']==(cb['q_len']==ob['q_len'] and cb['kv_len']==ob['kv_len']) and a['direct_R07_resource_measurement_claimed'] is False,'honest replay shape projection boundary')\n"+a
assert a in s;s=s.replace(a,b);s=s.replace("'replay_timing_used_as_latency':False,","'replay_timing_used_as_latency':False,'runtime_shape_match_counts':dict(collections.Counter(str(a['runtime_shape_match']) for a in attrs)),")
p.write_text(s)
p=new/'build_resource_model.py';s=p.read_text().replace("'physical_attribute_id','counter_mode','metric_name'","'physical_attribute_id','counter_mode','observed_q_len','observed_kv_len','replay_q_len','replay_kv_len','runtime_shape_match','metric_name'")
s=s.replace("'physical_attribute_id','counter_mode']}","'physical_attribute_id','counter_mode','observed_q_len','observed_kv_len','replay_q_len','replay_kv_len','runtime_shape_match']}")
s=s.replace("'attributable_physical_dispatch_rows':len(attrs),","'attributable_physical_dispatch_rows':len(attrs),'runtime_shape_match_counts':dict(collections.Counter(str(a['runtime_shape_match']) for a in attrs)),'different_runtime_shapes_are_not_directly_comparable_R07_resource_measurements':True,")
p.write_text(s)
for p in new.glob('*.py'):compile(p.read_text(),str(p),'exec')
correction=root.parents[4]/'recovery/r06_request_phase_selection_fix_004/corrected_logical_target_contract.json'
# Resolve from explicit project root, without guessing predecessor basenames.
correction=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/recovery/r06_request_phase_selection_fix_004/corrected_logical_target_contract.json')
c=json.loads(correction.read_text());assert c['selection_policy']['key_fields']==['request_id','phase','phase_occurrence'];assert c['selection_policy']['runtime_bound_fields']==['q_len','kv_len','runtime_execution_id']
def rec(p):return {'path':str(p),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
proof={'status':'complete','CPU_only':True,'selection_contract':rec(correction),'selection_policy':c['selection_policy'],'change':'use corrected R06 logical key for same-request replay projection; keep both actual q_len/kv_len and exact equality flags; prohibit claiming replay counter as direct R07 counter measurement','preserved_checks':['exact per-replay marker','native HIP launch correlation','unique exact native hardware timestamp pair','literal equality','request/rank/device/layer/process/fragment identity','R07 kernel subsequence multiplicity','both ranks complete','all counters and exclusions preserved'],'native_chain_diagnostic':rec(root/'normalized/chain_diagnostics/01__gqa6_pmc/attempt_003/revision_001/NATIVE_CHAIN_DIAGNOSTIC.json'),'tools':[rec(p) for p in sorted(new.iterdir()) if p.is_file()],'quantitative_cross_clock_comparisons_require_runtime_shape_match':True,'old_normalizer_source_preserved':rec(old/'normalize_capture.py')}
with (root/'validation/runtime_context_projection_cpu_gate.json').open('x') as f:json.dump(proof,f,indent=2);f.write('\n')
print('R06_LOGICAL_CONTEXT_PROJECTION_RULE_FROZEN')
