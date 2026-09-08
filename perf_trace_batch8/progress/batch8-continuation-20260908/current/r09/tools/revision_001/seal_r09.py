"""Seal accepted twelve-table analysis after independent conservation audit exits."""
from cpu_stage_common import *

def main():
 assignment=read(ROOT/'authorization/assignment.json');check(assignment['runtime_goal']=='R09','assigned stage');target=target_state();check(target==assignment['target'],'unchanged immutable target');candidate=ROOT/'analysis/fresh_e2e_analysis.json';analysis=read(candidate);auditpath=ROOT/'validation/R09_TABLE_INDEPENDENT_AUDIT.json';audit=read(auditpath);check(audit['status']=='complete' and audit['analysis_manifest_sha256']==sha(candidate),'independent full table audit')
 for phase in ['analysis','table_audit']:
  x=read(ROOT/'validation/phase_lifecycle'/(phase+'.json'));check(x['status']=='complete' and x['all_started_processes_terminated'],'closed preceding CPU phases')
 for item in analysis['tables']:verify(item)
 accepted={**analysis,'status':'complete','candidate_analysis':rec(candidate),'independent_table_audit':rec(auditpath),'acceptance_sealer':rec(Path(__file__)),'accepted_utc':now()};acceptedpath=ROOT/'analysis/fresh_e2e_analysis.accepted.json';save(acceptedpath,accepted)
 boundaries={key:False for key in ['model_execution_performed','gpu_dcu_execution_performed','device_query_performed','profiler_execution_performed','trace_collection_performed','pmc_collection_performed','replay_performed','external_network_contacted','target_mutation_performed','predecessor_mutation_performed','successor_execution_performed','report_generation_performed']}
 lineage={'schema_version':1,'runtime_goal':'R09','runtime_branch':'workflow01-10-fresh-e2e','runtime_run_id':RUN_ID,'lineage_id':RUN_ID,'trace_profile_sha256':PROFILE,'target':target,'selected_request':assignment['selected_request'],'workload':assignment['workload'],'topology':assignment['topology'],'predecessor_stages':assignment['predecessor_stages'],'predecessor_handoffs':assignment['predecessor_handoffs'],'cumulative_runtime_ledger':assignment['cumulative_runtime_ledger'],'predecessor_transitive_validation':assignment['predecessor_transitive_validation'],'consumed_sources':assignment['consumed_sources'],'full_request_analysis':rec(acceptedpath),'tables':analysis['tables'],'independent_table_audit':rec(auditpath),'observed_clock':'R07 only','replay_attribute_source':'audited R08 exact instance attributes; runtime shape mismatch blocks direct comparison','replay_timing_used_as_latency':False,'execution_boundaries':boundaries,'source_revision_history':assignment['frozen_tool_history'],'phase_lifecycle':[rec(ROOT/'validation/phase_lifecycle'/(x+'.json')) for x in ['analysis','table_audit']],'assignment':rec(ROOT/'authorization/assignment.json'),'sealer':rec(Path(__file__)),'sealed_utc':now(),'same_run_R07_recovery_exception_preserved':True,'remote_publishing_owned_by_separate_outer_scheduler':True}
 lineage.update(prefix_hash_fields(assignment))
 save(ROOT/'R09_SOURCE_LINEAGE.json',lineage)
 paths=set(ROOT.rglob('*'))|set((ROOT/'tables').rglob('*'));files=[]
 for p in sorted(paths):
  if p.is_file() and '__pycache__' not in p.parts and p.name not in ['artifact_manifest.json','R09_COMPLETION_AUDIT.json'] and not p.is_relative_to(ROOT/'logs'):files.append(rec(p))
 save(ROOT/'artifact_manifest.json',{'schema_version':1,'runtime_goal':'R09','runtime_run_id':RUN_ID,'lineage_id':RUN_ID,'files':files,'excludes':['this manifest','later independent completion audit','outer handoff','live phase logs'],'full_twelve_tables_preserved':True});print('R09_PREAUDIT_SEAL_COMPLETE',len(files),flush=True)
if __name__=='__main__':main()
