"""Seal complete R08 replay evidence after every capture and resource audit exits."""
from cpu_stage_common import *
import csv

def main():
 assignment=read(ROOT/'authorization/closure_assignment_001.json');check(assignment['runtime_goal']=='R08' and assignment['predecessor_stages']==['R%02d'%i for i in range(1,8)],'complete assigned prefix');target=target_state();check(target==assignment['target'],'immutable source state')
 for x in assignment['predecessor_handoffs']:verify(x)
 restoration=read(ROOT/'raw/runtime_tools/release_restoration_001/COMPLETE.json');check(restoration['status']=='complete' and restoration['all_evicted_raw_files_original_SHA256_verified'],'all Release evictions restored')
 for raw_inventory in sorted((ROOT/'raw/captures').glob('*/*/raw_inventory_at_exit.json')):
  for source in read(raw_inventory)['files']:verify(source)
 indexpath=ROOT/'normalized/accepted_captures.json';index=read(indexpath);plan=read(ROOT/'plans/r08_capture_plan.json');check(index['status']=='complete' and len(index['captures'])==12,'all captures accepted');check([x['segment_id'] for x in index['captures']]==[x['segment_id'] for x in plan['physical_captures']],'ordered full physical plan')
 modelroot=ROOT/'model/resource_model_001';model=read(modelroot/'traffic_resource_model.json');audit=read(modelroot/'RESOURCE_MODEL_INDEPENDENT_AUDIT.json');check(audit['status']=='complete' and audit['model_manifest_sha256']==sha(modelroot/'traffic_resource_model.json'),'accepted resource model')
 captures=[];schemas={};attrs=0
 for item in index['captures']:
  for key in ['execution_manifest','normalization_manifest','independent_audit']:verify(item[key])
  execution=read(item['execution_manifest']['path']);normal=read(item['normalization_manifest']['path']);independent=read(item['independent_audit']['path']);check(execution['all_started_processes_terminated'] and normal['status']==independent['status']=='complete','closed accepted capture');check(not execution['replay_time_used_as_observed_latency'] and not normal['R07_observed_clock_modified'],'observed clock invariant')
  check(normal['current_process_markers']==12544 and normal['native_owned_kernel_count']==23660 and set(normal['rank_counts'])=={'0','1'},'full DP2 trace and counter attribution');attrs+=normal['accepted_rows']
  modeschemas=set()
  with Path(normal['dispatch_attributes']['path']).open() as f:
   for line in f:
    row=json.loads(line);modeschemas.add(tuple(sorted(row['counters'])));check(row['evidence_class']=='replay_projected' and not row['direct_R07_resource_measurement_claimed'],'replay semantic boundary')
  check(len(modeschemas)==1,'one observed native mode schema');schema=list(next(iter(modeschemas)));mode=normal['counter_mode'];check(mode not in schemas or schemas[mode]==schema,'counter schema stable across exact kernel filters');schemas[mode]=schema
  captures.append({**item,'raw_inventory':execution['raw_inventory'],'process_targets':normal['current_process_markers'],'strict_owned_kernels':normal['native_owned_kernel_count'],'accepted_dispatch_attributes':normal['accepted_rows'],'rank_counts':normal['rank_counts'],'runtime_shape_match_counts':normal['runtime_shape_match_counts']})
 check(attrs==model['attributable_physical_dispatch_rows']==6912,'full physical attributes');check(model['inventory_family_count']==89 and model['selected_family_count']==32 and model['selected_logical_target_count']==7936,'full logical denominator')
 probe=ROOT/'preflight/native_probe_003/CAPABILITY_PROBE_COMPLETE.json';p=read(probe);check(p['status']=='complete' and p['all_started_processes_terminated'] and p['collector_kernel_filter_empirically_effective'],'empirical native capability')
 capability={'schema_version':1,'status':'complete','runtime_run_id':RUN_ID,'runtime_goal':'R08','lineage_id':RUN_ID,'trace_profile_sha256':PROFILE,'architecture':'gfx936','rank_to_physical_device':{'0':0,'1':1},'native_probe':rec(probe),'actual_native_counter_schemas':schemas,'observed_native_capture_index':rec(indexpath),'achieved_occupancy':{'availability_state':'unavailable','reason':'bounded observed schemas have no proven active-wave/max-wave measurement; register and LDS properties do not substitute achieved occupancy'},'runtime_FLOPs':{'availability_state':'unavailable','reason':'no unsupported opaque-kernel FLOP total inferred'},'all_native_counter_attributes_are_replay_projected':True,'sealing_did_not_query_device':True}
 save(ROOT/'preflight/device_capabilities.json',capability)
 targeted={'schema_version':1,'status':'complete','runtime_goal':'R08','runtime_run_id':RUN_ID,'lineage_id':RUN_ID,'trace_profile_sha256':PROFILE,'capture_plan':rec(ROOT/'plans/r08_capture_plan.json'),'logical_plan':rec(ROOT/'plans/logical_plan.json'),'capture_count':12,'accepted_dispatch_attribute_count':attrs,'captures':captures,'inventory_families':89,'selected_families':32,'selected_logical_targets':7936,'all_planned_targets_have_terminal_states':True,'family_accounting':model['family_accounting'],'resource_model_audit':rec(modelroot/'RESOURCE_MODEL_INDEPENDENT_AUDIT.json'),'replay_timing_used_as_latency':False,'failed_attempts_retained_but_not_promoted':True}
 save(ROOT/'normalized/targeted_pmc_manifest.json',targeted)
 save(ROOT/'model/traffic_resource_model.json',{'schema_version':1,'status':'complete','runtime_goal':'R08','runtime_run_id':RUN_ID,'lineage_id':RUN_ID,'trace_profile_sha256':PROFILE,'audited_model':rec(modelroot/'traffic_resource_model.json'),'independent_audit':rec(modelroot/'RESOURCE_MODEL_INDEPENDENT_AUDIT.json'),'traffic_resource_attachment':model['traffic_resource_attachment'],'family_accounting':model['family_accounting'],'metric_rows':model['metric_rows'],'replay_timing_used_as_latency':False,'static_bytes_are_measured_traffic':False})
 _,storage=storage_mappings();lineage={'schema_version':1,'runtime_goal':'R08','runtime_branch':'workflow01-10-fresh-e2e','runtime_run_id':RUN_ID,'lineage_id':RUN_ID,'trace_profile_sha256':PROFILE,'target':target,'selected_request':assignment['selected_request'],'workload':assignment['workload'],'topology':assignment['topology'],'predecessor_stages':assignment['predecessor_stages'],'predecessor_handoffs':assignment['predecessor_handoffs'],'predecessor_transitive_validation':assignment['predecessor_transitive_validation'],'cumulative_runtime_ledger':assignment['cumulative_runtime_ledger'],'consumed_sources':assignment['consumed_sources'],'targeted_pmc_manifest':rec(ROOT/'normalized/targeted_pmc_manifest.json'),'device_capabilities':rec(ROOT/'preflight/device_capabilities.json'),'traffic_resource_model':rec(ROOT/'model/traffic_resource_model.json'),'observed_clock':'R07 non-replay only','replay_timing_used_as_latency':False,'runtime_shape_mismatch_blocks_direct_R07_resource_comparison':True,'original_R07_native_controller_terminal_claimed':False,'same_run_R07_recovery_exception_preserved':True,'same_byte_storage_authorizations':storage,'frozen_tool_history':assignment['frozen_tool_history'],'closure_assignment':rec(ROOT/'authorization/closure_assignment_001.json'),'sealer':rec(Path(__file__)),'phase_lifecycle':[rec(x) for x in sorted((ROOT/'validation/phase_lifecycle').glob('*.json'))],'sealing_utc':now()}
 lineage.update(prefix_hash_fields(assignment))
 save(ROOT/'lineage/R08_SOURCE_LINEAGE.json',lineage)
 # All closed raw attempts, normalized outputs, tools and diagnostics retained;
 # reproducible compiler caches are explicitly outside business evidence.
 paths=set(ROOT.rglob('*'))
 for sub in ['raw','normalized','model']:paths.update((ROOT/sub).rglob('*'))
 files=[]
 for p in sorted(paths):
  if not p.is_file() or '__pycache__' in p.parts or p.is_relative_to(ROOT/'raw/runtime_cache') or p.name in ['artifact_manifest.json','R08_COMPLETION_AUDIT.json']:continue
  if p.is_relative_to(ROOT/'logs'):continue
  files.append(rec(p))
 save(ROOT/'artifact_manifest.json',{'schema_version':1,'runtime_goal':'R08','runtime_run_id':RUN_ID,'lineage_id':RUN_ID,'files':files,'excludes':['this manifest','later R08_COMPLETION_AUDIT.json','outer handoff','outer live phase stdout/stderr logs','reproducible raw/runtime_cache and __pycache__'],'failed_and_rejected_capture_evidence_preserved':True})
 print('R08_PREAUDIT_SEALED',len(files),flush=True)
if __name__=='__main__':main()
