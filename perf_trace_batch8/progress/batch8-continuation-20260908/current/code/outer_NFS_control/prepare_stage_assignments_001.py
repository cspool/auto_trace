"""Outer assignments and immutable handoffs; actual successor only after closure."""
from pathlib import Path
import os,json,hashlib,shutil,sys,subprocess,datetime,importlib.util
CONTROL=Path('/public/home/accl15ptg7/run_R08_R10');PROJECT=Path('/public/home/accl15ptg7/auto_trace');RUN=PROJECT/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003';RUN_ID='batch8-dp2-fresh-003';TEMPLATES=CONTROL/'stage_tool_templates_002';DEADLINE='2026-09-08T20:18:09Z'
spec=importlib.util.spec_from_file_location('outer_cpu_common',TEMPLATES/'shared_001/cpu_stage_common.py');common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
def sha(p):return common.sha(p)
def rec(p):return common.rec(Path(p))
def read(p):return common.read(p)
def now():return common.now()
def save(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(x,f,indent=2,ensure_ascii=False);f.write('\n');f.flush();os.fsync(f.fileno())
def handoff_path(stage):return RUN/'handoffs'/(stage+('.recovered.json' if stage=='R07' else '.continuation.json' if stage in ['R08','R09','R10'] else '.json'))
def prefix(stage):
 result=[]
 for i in range(1,int(stage[1:])):
  s='R%02d'%i;p=handoff_path(s);h=read(p);assert h['runtime_goal']==s and h['runtime_run_id']==RUN_ID and h['trace_profile_sha256']==common.PROFILE
  assert h['execution_status']==h['evidence_status']=='complete' and h['coverage_target_met'] and not h['next_authorization_required']
  if s=='R07':assert h['status']=='complete_recovered_offline' and not h['native_controller_lifecycle_completion_claimed'] and not h['remote_original_hipprof_terminal']
  else:
   assert h['status']=='complete'
   if i>=8:assert h['all_started_processes_terminated']
  result.append(rec(p))
 return result

def verify_transitive(stage,out):
 # Revalidate all mandatory R01-R06 manifest bytes, including failed attempts.
 # Listed storage moves preserve exact source bytes; no arbitrary symlinks.
 records=[];count=0;total=0
 original=PROJECT/'perf_trace_batch8/continuation_20260908';index=read(original/'predecessor_validation_index.json')
 for item in sorted(index['stages'],key=lambda x:x['stage']):
  assert sha(item['path'])==item['sha256'];validation=read(item['path']);assert validation['status']=='complete'
  for x in validation['entries']:
   p=common.validate_path(x['local_path']);assert p.stat().st_size==x['size'] and sha(p)==x['sha256'];count+=1;total+=x['size']
  records.append({'stage':item['stage'],'prior_full_manifest_validation':rec(item['path']),'current_handoff':rec(handoff_path(item['stage'])),'rehash_entry_count':validation['entry_count'],'logical_bytes':validation['logical_bytes']});print('PREFIX_FULL_MANIFEST_REHASHED',stage,item['stage'],validation['entry_count'],flush=True)
 admissionpath=original/'RECOVERED_R07_ADMISSION.json';admission=read(admissionpath)
 for x in admission['verified_sources']:
  p=Path(x['local_path']);assert p.exists() and sha(p)==x['sha256'];count+=1;total+=p.stat().st_size
 records.append({'stage':'R07','admission':rec(admissionpath),'recovered_handoff':rec(handoff_path('R07')),'verified_source_count':len(admission['verified_sources']),'original_native_controller_terminal_claimed':False})
 for i in range(8,int(stage[1:])):
  s='R%02d'%i;h=read(handoff_path(s));m=read(h['artifact_manifest']['path'])
  for x in m['files']:common.verify(x);count+=1;total+=x['size']
  common.verify(h['completion_audit']);records.append({'stage':s,'artifact_manifest':h['artifact_manifest'],'completion_audit':h['completion_audit'],'rehash_entry_count':len(m['files'])})
 result={'status':'complete','successor_stage':stage,'runtime_run_id':RUN_ID,'all_ordered_predecessor_business_files_rehashed':True,'file_records_verified':count,'logical_bytes_rehashed':total,'stages':records,'same_run_R07_recovery_exception_preserved':True,'source_byte_mutation_performed':False,'storage_authorizations':[rec(CONTROL/'storage_policy_correction_001/COMPLETE.json')],'verified_utc':now()};save(out,result);return rec(out)

def freeze(stage,root):
 source=TEMPLATES/({'R08':'r08_closure_001','R09':'r09_001','R10':'r10_001'}[stage]);tools=root/'tools'/('closure_001' if stage=='R08' else 'revision_001');assert not tools.exists();shutil.copytree(source,tools);shutil.copyfile(TEMPLATES/'shared_001/cpu_stage_common.py',tools/'cpu_stage_common.py')
 for p in tools.glob('*.py'):compile(p.read_text(),str(p),'exec')
 records=[rec(p) for p in sorted(tools.iterdir()) if p.is_file()];gate=root/'validation/frozen_CPU_tools_001.json';save(gate,{'status':'complete','runtime_goal':stage,'tools':records,'syntax_validated':True,'device_and_model_imports_performed':False,'outer_preparation':rec(Path(__file__)),'synthetic_browser_fixture':rec(CONTROL/'emergency_tools/cpu_viewer_fixture_001/CPU_BROWSER_FIXTURE_AUDIT.json') if stage=='R10' else None,'runtime_validation_still_required':True});return tools,[rec(gate),*records]

def assign(stage):
 assert stage in ['R08','R09','R10'];hs=prefix(stage);root=RUN/'artifacts'/stage/'continuation_001';root.mkdir(parents=True,exist_ok=True);output=root/'authorization'/('closure_assignment_001.json' if stage=='R08' else 'assignment.json');assert not output.exists()
 if stage=='R08':assert read(root/'normalized/accepted_captures.json')['status']=='complete'
 # The outer runner is excluded from the read-only source-root process scan.
 common.closed_process_proof([str(RUN/'artifacts'/('R%02d'%(int(stage[1:])-1)))],exclude=[os.getppid()])
 tools,history=freeze(stage,root);transitive=verify_transitive(stage,root/'validation/PREDECESSOR_TRANSITIVE_VALIDATION.json');ledger=read(RUN/'artifacts/R08/continuation_001/contract/recovered_prefix_ledger.json')
 for i in range(8,int(stage[1:])):
  name='R%02d'%i;p=handoff_path(name);ledger['handoffs'].append({'source_goal':name,'status':'complete','path':str(p),'sha256':sha(p),'payload':read(p)})
 ledgerpath=root/'contract/accepted_prefix_ledger.json';save(ledgerpath,ledger)
 workload={'requests':8,'selection':'ordered first eight original records','warmups':2,'output_tokens_each':1024,'max_concurrency':8,'temperature':0,'ignore_eos':True,'dp':2,'tp':1};selection=rec(RUN/'artifacts/R01/contract/request_selection.json');topology={'dp':2,'tp':1,'rank_to_physical_device':{'0':0,'1':1}}
 consumed=[];r07=RUN/'artifacts/R07/resume-042';r08=RUN/'artifacts/R08/continuation_001'
 for rel in ['trace/process_ranges.csv','trace/strict_owned_kernels.csv','trace/hip_runtime_calls.csv','trace/layer_ranges.csv','trace/forward_ranges.csv','trace/request_ranges.csv','alignment/r07_live_utilization_aligned.csv','alignment/r07_live_utilization_gaps.csv','alignment/r07_process_live_utilization.csv','dependency/fresh_run_dependency_adapter.csv','contract/r07_bound_target_sidecar.json']:consumed.append(rec(r07/rel))
 for p in [CONTROL/'r07_additional_inputs/clock_anchors.json',*list((CONTROL/'r07_additional_inputs').rglob('capture/workload/request_results.json')),r08/'validation/batch8_observed_coverage_gate_001.json']:consumed.append(rec(p))
 if stage in ['R09','R10']:
  for p in [r08/'model/resource_model_001/traffic_resource_attachment.csv',r08/'model/traffic_resource_model.json',r08/'R08_COMPLETION_AUDIT.json',r08/'lineage/R08_SOURCE_LINEAGE.json']:consumed.append(rec(p))
 nfspolicy=CONTROL/'USER_STORAGE_POLICY_20260908.json';assignment={'schema_version':1,'status':'assigned','runtime_goal':stage,'runtime_run_id':RUN_ID,'trace_profile_sha256':common.PROFILE,'target':common.target_state(),'artifact_root':str(root),'handoff_output':str(handoff_path(stage)),'predecessor_stages':['R%02d'%i for i in range(1,int(stage[1:]))],'predecessor_handoffs':hs,'predecessor_transitive_validation':transitive,'cumulative_runtime_ledger':rec(ledgerpath),'selected_request':selection,'workload':workload,'topology':topology,'consumed_sources':consumed,'frozen_tool_history':history,'deadline_utc':DEADLINE,'deadline_extension_authorization':rec(CONTROL/'MACHINE_TIME_EXTENSION_001.json'),'storage_policy':rec(nfspolicy),'NFS_filesystem_device':os.stat(CONTROL).st_dev,'all_stage_artifacts_and_logs_physical_NFS_required':True,'weights_physical_root_required':True,'assigned_utc':now()}
 if stage=='R10':
  r09=RUN/'artifacts/R09/continuation_001';analysispath=r09/'analysis/fresh_e2e_analysis.accepted.json';assignment.update(r09_handoff=rec(handoff_path('R09')),r09_analysis=rec(analysispath));assignment['consumed_sources'] += [rec(analysispath),*read(analysispath)['tables']];dest=CONTROL/'R10_acceptance_payload_001';assert not dest.exists() and not (root/'acceptance').exists();dest.mkdir();(root/'acceptance').symlink_to(dest,target_is_directory=True);assignment['bulk_storage_paths']={str(root/'acceptance'):str(dest)};save(root/'authorization/bulk_storage_authorization.json',{'runtime_goal':'R10','runtime_run_id':RUN_ID,'paths':assignment['bulk_storage_paths'],'NFS_filesystem_device':os.stat(CONTROL).st_dev,'user_storage_policy':rec(nfspolicy)})
 save(output,assignment);print('OUTER_STAGE_ASSIGNED',stage,flush=True);return root,tools

def seal_handoff(stage):
 root=RUN/'artifacts'/stage/'continuation_001';a=read(root/'authorization'/('closure_assignment_001.json' if stage=='R08' else 'assignment.json'));auditpath=root/(stage+'_COMPLETION_AUDIT.json');audit=read(auditpath);assert audit['status']=='complete';life=[read(p) for p in sorted((root/'validation/phase_lifecycle').glob('*.json'))];assert life and all(x['status']=='complete' and x['all_started_processes_terminated'] for x in life);common.closed_process_proof([root],exclude=[os.getppid()]);assert common.target_state()==a['target']
 refs={'R08':{'device_capabilities':root/'preflight/device_capabilities.json','traffic_resource_model':root/'model/traffic_resource_model.json','source_lineage':root/'lineage/R08_SOURCE_LINEAGE.json'},'R09':{'full_request_analysis':root/'analysis/fresh_e2e_analysis.accepted.json','source_lineage':root/'R09_SOURCE_LINEAGE.json'},'R10':{'offline_acceptance_manifest':root/'acceptance/offline_acceptance_manifest.json','source_lineage':root/'R10_SOURCE_LINEAGE.json'}}[stage]
 evidence={'schema_version':1,'status':'complete','lineage_id':RUN_ID,**{k:rec(v) for k,v in refs.items()}};h={'schema_version':1,'status':'complete','execution_status':'complete','evidence_status':'complete','coverage_target_met':True,'next_authorization_required':False,'runtime_goal':stage,'runtime_branch':'workflow01-10-fresh-e2e','runtime_run_id':RUN_ID,'lineage_id':RUN_ID,'trace_profile_sha256':common.PROFILE,'fresh_e2e_evidence':evidence,'artifact_manifest':rec(root/'artifact_manifest.json'),'completion_audit':rec(auditpath),'source_lineage':evidence['source_lineage'],'target':a['target'],'predecessor_handoffs':a['predecessor_handoffs'],'cumulative_runtime_ledger':a['cumulative_runtime_ledger'],'all_started_processes_terminated':True,'phase_lifecycle':[rec(p) for p in sorted((root/'validation/phase_lifecycle').glob('*.json'))],'closed_logs':[rec(p) for p in sorted((root/'logs').glob('*.log'))],'R07_original_native_controller_terminal_claimed':False,'same_run_R07_recovery_exception_preserved':True,'replay_timing_used_as_latency':False,'storage_policy':a['storage_policy'],'sealed_utc':now(),'outer_sealer':rec(Path(__file__))};save(handoff_path(stage),h);print('OUTER_HANDOFF_SEALED',stage,sha(handoff_path(stage)),flush=True)
if __name__=='__main__':
 assert len(sys.argv)==3
 (assign if sys.argv[1]=='assign' else seal_handoff)(sys.argv[2])
