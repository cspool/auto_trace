"""Independent outer advance gate. Reads sealed artifacts; imports no producer."""
from pathlib import Path
import json,hashlib
TABLES=['request_timeline','process_timeline','kernel_timeline','live_utilization_aligned','process_live_utilization','kernel_concurrency','queue_concurrency','launch_gaps','high_latency_processes','dependency_state','traffic_resource_attachment','opportunity_candidates']
OUTPUTS={'R08':['device_capabilities','targeted_pmc_manifest','traffic_resource_model','source_lineage'],'R09':[*TABLES,'full_request_analysis','source_lineage'],'R10':['offline_acceptance_manifest','full_timeline_manifest','full_perfetto_trace','e2e_process_timeline','e2e_process_timeline_lossless','high_latency_process_hardware_timeline','concurrency_utilization','index_html','source_lineage']}
BASE=['status','execution_status','evidence_status','coverage_target_met','next_authorization_required','runtime_branch','runtime_goal','runtime_run_id','lineage_id','trace_profile_sha256','cumulative_runtime_ledger_sha256','artifact_manifest_sha256','completion_audit_sha256']
def check(v,reason):
 if not v:raise RuntimeError('Independent scheduler handoff gate: '+reason)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def verify(x):
 p=Path(x['path']);check(p.is_absolute() and '..' not in p.parts,'absolute contained lexical source');check(p.is_file() and p.stat().st_size==x['size'] and sha(p)==x['sha256'],'referenced file bytes '+str(p));return p
def validate_shape(h):
 stage=h['runtime_goal'];check(stage in OUTPUTS,'supported terminal stage');prefix=['R%02d'%i for i in range(1,int(stage[1:]))]
 required=BASE+[x.lower()+'_handoff_sha256' for x in prefix]+[x+'_sha256' for x in OUTPUTS[stage]];check(set(required)<=h.keys(),'all required direct fields present')
 check(all(h[k]=='complete' for k in ['status','execution_status','evidence_status']) and h['coverage_target_met'] is True and h['next_authorization_required'] is False,'complete evidence and advance flags')
 check(h['runtime_branch']=='workflow01-10-fresh-e2e' and h['runtime_run_id']==h['lineage_id']=='batch8-dp2-fresh-003','same nonempty fresh run and lineage');check(h['trace_profile_sha256']=='3b4c952063f48ae662b48b5ce9d8fd76e0ac4d74e170bdb1839ae8b1aaa23cce','immutable profile')
 check(h['runtime_predecessors']==','.join(prefix) and len(h['predecessor_handoffs'])==len(prefix),'complete ordered prefix');check(h['all_started_processes_terminated'] is True and h['replay_timing_used_as_latency'] is False,'process closure and unique observed clock')
 check(h['topology']=={'dp':2,'tp':1,'rank_to_physical_device':{'0':0,'1':1}},'both original native devices');check(h['workload']=={'requests':8,'selection':'ordered first eight original records','warmups':2,'output_tokens_each':1024,'max_concurrency':8,'temperature':0,'ignore_eos':True,'dp':2,'tp':1},'full original eight concurrent requests')
 for key in ['model_execution_performed','gpu_dcu_execution_performed','device_query_performed','profiler_execution_performed','trace_collection_performed','pmc_collection_performed','replay_performed']:check(h[key] is (stage=='R08'),'explicit stage execution boundary '+key)
 check(h['report_generation_performed'] is (stage=='R10') and h['visualization_performed'] is (stage=='R10'),'terminal-only report generation')
 check(h['R07_original_native_controller_terminal_claimed'] is False and h['same_run_R07_recovery_exception_preserved'] is True,'preserve original R07 lifecycle uncertainty')
 for name in OUTPUTS[stage]:check(name in h['logical_outputs'] and h[name+'_sha256']==h['logical_outputs'][name]['sha256'],'direct logical output hash '+name)
 return stage,prefix,required

def validate(h):
 stage,prefix,required=validate_shape(h);refs=[h['artifact_manifest'],h['completion_audit'],h['source_lineage'],h['cumulative_runtime_ledger'],h['selected_request'],h['authorization'],h['predecessor_transitive_validation'],*h['predecessor_handoffs'],*h['logical_outputs'].values()];seen={}
 for item in refs:
  old=seen.get(item['path']);check(old is None or (old['size'],old['sha256'])==(item['size'],item['sha256']),'unambiguous referenced bytes')
  if old is None:verify(item);seen[item['path']]=item
 for name in ['artifact_manifest','completion_audit','source_lineage','cumulative_runtime_ledger']:check(h[name+'_sha256']==h[name]['sha256'],'direct provenance hash '+name)
 for expected,item in zip(prefix,h['predecessor_handoffs']):
  source=read(item['path']);check(source['runtime_goal']==expected and source['runtime_run_id']==h['runtime_run_id'] and source['trace_profile_sha256']==h['trace_profile_sha256'],'ordered same-run predecessor');check(item['sha256']==h[expected.lower()+'_handoff_sha256'],'direct predecessor hash')
  check(source['execution_status']==source['evidence_status']=='complete' and source['coverage_target_met'] is True and source['next_authorization_required'] is False,'advance eligible predecessor')
  if expected=='R07':check(source['status']=='complete_recovered_offline' and source['native_controller_lifecycle_completion_claimed'] is False and source['remote_original_hipprof_terminal'] is False,'exact recovered R07 exception')
  else:check(source['status']=='complete','complete predecessor')
 audit=read(h['completion_audit']['path']);check(audit['status']=='complete' and audit['evidence_status']=='complete' and audit['coverage_target_met'] is True and audit['next_authorization_required'] is False,'sealed independent completion audit');check(audit['runtime_goal']==stage and audit['runtime_run_id']==h['runtime_run_id'],'audit same stage and run')
 lineage=read(h['source_lineage']['path']);check(lineage['predecessor_handoffs']==h['predecessor_handoffs'] and lineage['cumulative_runtime_ledger']==h['cumulative_runtime_ledger'],'lineage exact accepted prefix')
 for key in ['cumulative_runtime_ledger_sha256',*[x.lower()+'_handoff_sha256' for x in prefix]]:check(lineage[key]==h[key] and audit[key]==h[key],'lineage and completion audit prefix conservation')
 if stage=='R08':
  check(audit['all_eight_requests_have_trace_and_selected_PMC_in_all_captures'] is True and audit['physical_capture_count']==12 and audit['physical_dispatch_attributes']==6912,'all twelve replay passes and every request')
  targeted=read(h['logical_outputs']['targeted_pmc_manifest']['path']);check(targeted['capture_count']==12 and targeted['accepted_dispatch_attribute_count']==6912 and targeted['all_planned_targets_have_terminal_states'] is True,'complete required PMC logical output')
  check(audit['artifact_manifest']==h['artifact_manifest'],'audit seals exact artifact manifest')
 elif stage=='R09':
  analysis=read(h['logical_outputs']['full_request_analysis']['path']);check(analysis['status']=='complete' and [x['logical_name'] for x in analysis['tables']]==TABLES,'all twelve accepted tables');check(analysis['complete_timeline'] is True and analysis['sampling_performed'] is False and analysis['replay_timing_used_as_latency'] is False,'lossless R07 clock');check(audit['all_eight_request_phase_process_kernel_coverage_verified'] is True,'all eight observed traces')
  for item in analysis['tables']:check(item==h['logical_outputs'][item['logical_name']],'direct table metadata conservation')
  check(audit['artifact_manifest']==h['artifact_manifest'],'audit seals exact artifact manifest')
 else:
  final=read(h['artifact_manifest']['path']);check(final['includes_all_ten_required_deliverables'] is True and final['finalized_after_independent_audit'] is True,'final manifest includes completion audit without hash cycle');check(final['completion_audit']==h['completion_audit'] and final['preaudit_manifest']['sha256']==audit['preaudit_artifact_manifest_sha256'],'final manifest exact preaudit and independent audit')
  entries={x['path']:x for x in final['files']}
  for item in [*h['logical_outputs'].values(),h['completion_audit']]:check(entries.get(item['path'])==item,'ten mandatory deliverables sealed')
  check(audit['all_eight_requests_have_exact_trace_coverage'] is True,'all eight final trace coverage');offline=read(h['logical_outputs']['offline_acceptance_manifest']['path']);timeline=read(h['logical_outputs']['full_timeline_manifest']['path']);check(offline['event_count']==timeline['expected_event_count']==audit['event_count']==59872 and offline['network_attempt_count']==0,'complete final event and offline denominators')
 payload={k:v for k,v in h.items() if k!='independent_scheduler_validation'};digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 if 'independent_scheduler_validation' in h:check(h['independent_scheduler_validation']['validated_payload_sha256']==digest,'handoff unchanged after validation')
 return {'status':'complete','runtime_goal':stage,'required_field_count':len(required),'unique_direct_artifacts_SHA256_verified':len(seen),'validated_payload_sha256':digest,'all_required_fields_and_prefix_conserved':True,'auditor':{'path':str(Path(__file__)),'size':Path(__file__).stat().st_size,'sha256':sha(Path(__file__))},'no_model_or_device_access':True}
