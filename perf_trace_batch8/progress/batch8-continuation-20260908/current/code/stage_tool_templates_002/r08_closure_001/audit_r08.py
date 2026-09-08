"""Independent terminal closure checks; no replay, renderer, or builder imports."""
from cpu_stage_common import *
import csv

def main():
 start=now();a=read(ROOT/'authorization/closure_assignment_001.json');target=target_state();check(target==a['target'],'immutable target');manifest=read(ROOT/'artifact_manifest.json')
 for x in manifest['files']:verify(x)
 raw_inventory_checks=[]
 for raw_inventory in sorted((ROOT/'raw/captures').glob('*/*/raw_inventory_at_exit.json')):
  original=read(raw_inventory)
  for source in original['files']:verify(source)
  raw_inventory_checks.append({'inventory':rec(raw_inventory),'original_file_count':len(original['files']),'all_original_raw_files_present_and_SHA256_verified':True})
 check(bool(raw_inventory_checks),'raw capture inventories required')
 lineage=read(ROOT/'lineage/R08_SOURCE_LINEAGE.json');check(lineage['predecessor_stages']==['R%02d'%i for i in range(1,8)] and not lineage['original_R07_native_controller_terminal_claimed'],'ordered immutable recovery exception');check(not lineage['replay_timing_used_as_latency'],'observed timing boundary')
 index=read(ROOT/'normalized/accepted_captures.json');plan=read(ROOT/'plans/r08_capture_plan.json');logical=read(ROOT/'plans/logical_plan.json');check([x['segment_id'] for x in index['captures']]==[x['segment_id'] for x in plan['physical_captures']],'all planned captures exactly once');check(len(index['captures'])==12,'twelve capture coverage')
 observed=read(ROOT/'validation/batch8_observed_coverage_gate_001.json');check(observed['request_count']==8 and observed['exact_R06_bound_target_set_equality_per_request_phase'],'R07 eight-request full target gate');expected_ids={x['request_id'] for x in observed['coverage']};summaries=[];totalattrs=0
 for item in index['captures']:
  execution=read(item['execution_manifest']['path']);normal=read(item['normalization_manifest']['path']);audit=read(item['independent_audit']['path']);raw=Path(item['execution_manifest']['path']).parent;driver=read(raw/'workload/driver.json');check(execution['all_started_processes_terminated'] and execution['workload']['status']=='complete','closed full workload');check(driver['completed']==8 and driver['failed']==0 and driver['total_completion_tokens']==8192 and driver['warmup_count']==2,'exact original workload')
  check(set(driver['request_ids'])==expected_ids and len(driver['results'])==8,'exact stable request identity');rank_requests=collections.defaultdict(set)
  for r in driver['results']:
   check(r['http_status']==200 and r['completion_tokens']==1024 and not r['error'],'all measured request success');rank_requests[str(r['data_parallel_rank_requested'])].add(r['request_id'])
  check(set(rank_requests)=={'0','1'} and all(len(x)==4 for x in rank_requests.values()),'both ranks four requests');check(audit['status']=='complete' and audit['normalization_manifest_sha256']==sha(item['normalization_manifest']['path']),'independent exact attribution audit')
  check(normal['current_process_markers']==12544 and normal['native_owned_kernel_count']==23660 and set(normal['rank_counts'])=={'0','1'} and normal['missing_selected_counter_cells']==0,'complete native universe and both-rank counters');attrids=set();attrrequests=set()
  with Path(normal['dispatch_attributes']['path']).open() as f:
   for line in f:
    r=json.loads(line);check(r['physical_attribute_id'] not in attrids,'unique native attribute');attrids.add(r['physical_attribute_id']);attrrequests.add(r['request_id']);check(r['evidence_class']=='replay_projected' and not r['direct_R07_resource_measurement_claimed'] and not r['replay_duration_used_as_observed_latency'],'native evidence class')
  check(len(attrids)==normal['accepted_rows'] and attrrequests==expected_ids,'selected PMC covers every request');totalattrs+=len(attrids);summaries.append({'segment_id':item['segment_id'],'requests':8,'rank_requests':{k:sorted(v) for k,v in rank_requests.items()},'native_attributes':len(attrids),'rank_native_counts':normal['rank_counts']})
 model=read(ROOT/'model/resource_model_001/traffic_resource_model.json');audit=read(ROOT/'model/resource_model_001/RESOURCE_MODEL_INDEPENDENT_AUDIT.json');check(audit['status']=='complete' and audit['model_manifest_sha256']==sha(ROOT/'model/resource_model_001/traffic_resource_model.json'),'resource audit exact bytes');check(totalattrs==model['attributable_physical_dispatch_rows']==6912,'attribute denominator')
 check(model['inventory_family_count']==89 and model['selected_family_count']==32 and model['selected_logical_target_count']==7936 and model['R07_process_rows']==12544,'full family and process universe')
 result={'schema_version':1,'status':'complete','execution_status':'complete','evidence_status':'complete','runtime_goal':'R08','runtime_run_id':RUN_ID,'lineage_id':RUN_ID,'trace_profile_sha256':PROFILE,'coverage_target_met':True,'next_authorization_required':False,'independent_audit':True,'builder_imported':False,'target':target,'artifact_manifest':rec(ROOT/'artifact_manifest.json'),'source_lineage':rec(ROOT/'lineage/R08_SOURCE_LINEAGE.json'),'all_eight_requests_have_trace_and_selected_PMC_in_all_captures':True,'capture_checks':summaries,'all_original_raw_capture_inventories_verified':raw_inventory_checks,'physical_capture_count':12,'physical_dispatch_attributes':totalattrs,'resource_model_audit':rec(ROOT/'model/resource_model_001/RESOURCE_MODEL_INDEPENDENT_AUDIT.json'),'replay_timing_used_as_latency':False,'R07_original_native_controller_terminal_claimed':False,'cpu_only':True,'started_utc':start,'finished_utc':now(),'auditor':rec(Path(__file__))}
 save(ROOT/'R08_COMPLETION_AUDIT.json',result);print('R08_COMPLETION_AUDIT_COMPLETE',totalattrs,flush=True)
if __name__=='__main__':main()
