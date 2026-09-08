from pathlib import Path
import shutil,hashlib,json
C=Path('/public/home/accl15ptg7/run_R08_R10');P=Path('/public/home/accl15ptg7/auto_trace');T=C/'stage_tool_templates_003';assert not T.exists();shutil.copytree(C/'stage_tool_templates_002',T,ignore=shutil.ignore_patterns('__pycache__'))
# Final R10 manifest follows the audit, avoiding a manifest/audit hash cycle.
p=T/'r10_001/seal_acceptance.py';s=p.read_text().replace("ROOT/'artifact_manifest.json'","ROOT/'artifact_manifest.preaudit.json'");s=s.replace("p.name not in ['artifact_manifest.json','R10_COMPLETION_AUDIT.json']", "p.name not in ['artifact_manifest.json','artifact_manifest.preaudit.json','R10_COMPLETION_AUDIT.json']");p.write_text(s)
p=T/'r10_001/audit_report.py';s=p.read_text().replace("ROOT/'artifact_manifest.json'","ROOT/'artifact_manifest.preaudit.json'").replace("'artifact_manifest_sha256':sha(ROOT/'artifact_manifest.preaudit.json')","'preaudit_artifact_manifest_sha256':sha(ROOT/'artifact_manifest.preaudit.json')");p.write_text(s)
# Expose exact direct prefix hashes in lineage and its completion audit.
p=T/'shared_001/cpu_stage_common.py';s=p.read_text();s+='''\ndef prefix_hash_fields(assignment):
 result={'cumulative_runtime_ledger_sha256':assignment['cumulative_runtime_ledger']['sha256']}
 for stage,item in zip(assignment['predecessor_stages'],assignment['predecessor_handoffs']):result[stage.lower()+'_handoff_sha256']=item['sha256']
 return result
''';p.write_text(s)
for directory,name,line in [('r08_closure_001','seal_r08.py'," save(ROOT/'lineage/R08_SOURCE_LINEAGE.json',lineage)"),('r09_001','seal_r09.py'," save(ROOT/'R09_SOURCE_LINEAGE.json',lineage)"),('r10_001','seal_acceptance.py'," save(ROOT/'R10_SOURCE_LINEAGE.json',lineage)")]:
 p=T/directory/name;s=p.read_text();assert line in s;s=s.replace(line," lineage.update(prefix_hash_fields(assignment))\n"+line);p.write_text(s)
for directory,name in [('r08_closure_001','audit_r08.py'),('r09_001','audit_completion.py')]:
 p=T/directory/name;s=p.read_text()
 if name=='audit_r08.py':s=s.replace(" save(ROOT/'R08_COMPLETION_AUDIT.json',result)"," result.update(prefix_hash_fields(a))\n save(ROOT/'R08_COMPLETION_AUDIT.json',result)")
 else:s=s.replace("save(ROOT/'R09_COMPLETION_AUDIT.json',{'schema_version':1", "save(ROOT/'R09_COMPLETION_AUDIT.json',{**prefix_hash_fields(assignment),'schema_version':1")
 p.write_text(s)
p=T/'r10_001/audit_report.py';s=p.read_text();s=s.replace(" with (ROOT/'R10_COMPLETION_AUDIT.json').open('x')", " result['cumulative_runtime_ledger_sha256']=assignment['cumulative_runtime_ledger']['sha256']\n for stage,item in zip(expected_stages,assignment['predecessor_handoffs']):result[stage.lower()+'_handoff_sha256']=item['sha256']\n with (ROOT/'R10_COMPLETION_AUDIT.json').open('x')");p.write_text(s)
for p in T.rglob('*.py'):compile(p.read_text(),str(p),'exec')
# Outer scheduler changes remain preparation; no R09/R10 business execution.
p=C/'prepare_stage_assignments_002.py';s=(C/'prepare_stage_assignments_001.py').read_text().replace('stage_tool_templates_002','stage_tool_templates_003');s=s.replace("   if i>=8:assert h['all_started_processes_terminated']", "   if i>=8:\n    assert h['all_started_processes_terminated']\n    handoff_auditor.validate(h)")
s=s.replace("def handoff_path(stage):", "spec2=importlib.util.spec_from_file_location('independent_outer_handoff_auditor',CONTROL/'audit_runtime_handoff_001.py');handoff_auditor=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(handoff_auditor)\n\ndef handoff_path(stage):")
s=s.replace("'traffic_resource_model':root/'model/traffic_resource_model.json'", "'targeted_pmc_manifest':root/'normalized/targeted_pmc_manifest.json','traffic_resource_model':root/'model/traffic_resource_model.json'")
needle=" refs={'R08':"
assert needle in s
s=s.replace(needle,""" if stage=='R10':
  prepath=root/'artifact_manifest.preaudit.json';pre=read(prepath);assert audit['preaudit_artifact_manifest_sha256']==sha(prepath)
  records={x['path']:x for x in pre['files']}
  for q in [prepath,auditpath,*sorted((root/'validation/phase_lifecycle').glob('*.json')),*sorted((root/'logs').glob('*.log'))]:records[str(q)]=rec(q)
  save(root/'artifact_manifest.json',{'schema_version':1,'runtime_goal':stage,'runtime_run_id':RUN_ID,'lineage_id':RUN_ID,'files':[records[k] for k in sorted(records)],'preaudit_manifest':rec(prepath),'completion_audit':rec(auditpath),'includes_all_ten_required_deliverables':True,'excludes':['this manifest','outer scheduler handoff'],'finalized_after_independent_audit':True})
"""+needle)
needle=";save(handoff_path(stage),h);print('OUTER_HANDOFF_SEALED'"
assert needle in s
s=s.replace(needle,"\n h.update(complete_handoff_fields(stage,root,a,h,evidence))\n h['independent_scheduler_validation']=handoff_auditor.validate(h)\n save(handoff_path(stage),h);print('OUTER_HANDOFF_SEALED'")
position=s.index("def seal_handoff(stage):")
helper='''def complete_handoff_fields(stage,root,a,h,evidence):
 fields=common.prefix_hash_fields(a)
 fields.update(runtime_predecessors=','.join(a['predecessor_stages']),runtime_attempt='continuation_001',formal_goal_scope='user-authorized same-run continuation through R10',selected_request=a['selected_request'],workload=a['workload'],topology=a['topology'],consumed_sources=a['consumed_sources'],predecessor_transitive_validation=a['predecessor_transitive_validation'],authorization=rec(root/'authorization'/('closure_assignment_001.json' if stage=='R08' else 'assignment.json')),artifact_manifest_sha256=h['artifact_manifest']['sha256'],completion_audit_sha256=h['completion_audit']['sha256'],source_lineage_sha256=h['source_lineage']['sha256'])
 outputs={k:v for k,v in evidence.items() if isinstance(v,dict) and 'sha256' in v}
 for key in ['model_execution_performed','gpu_dcu_execution_performed','device_query_performed','profiler_execution_performed','trace_collection_performed','pmc_collection_performed','replay_performed']:fields[key]=stage=='R08'
 fields.update(observed_timing_collection_performed=False,target_mutation_performed=False,predecessor_mutation_performed=False,successor_execution_performed=False,external_runtime_evidence_accepted=False,report_generation_performed=stage=='R10',visualization_performed=stage=='R10')
 if stage=='R08':fields.update(traffic_resource_model_built=True,accepted_capture_index=rec(root/'normalized/accepted_captures.json'),capture_plan=rec(root/'plans/r08_capture_plan.json'),replay_clock_excluded_from_observed_latency=True)
 if stage=='R09':
  fields.update(cpu_analysis_performed=True,twelve_table_analysis_performed=True,external_network_contacted=False)
  tables=read(outputs['full_request_analysis']['path'])['tables'];fields['tables']=tables
  for item in tables:outputs[item['logical_name']]=item
 if stage=='R10':
  fields.update(cpu_report_generation_performed=True,offline_browser_acceptance_performed=True,external_network_contacted=False,sampling_performed=False,complete_timeline=True,formal_r09_r10_regeneration=True,terminal_branch_complete=True,successor_authorized=False)
  for key,name in {'full_timeline_manifest':'full_timeline_manifest.json','full_perfetto_trace':'E2E_PROCESS_TIMELINE.full.perfetto.json','e2e_process_timeline':'E2E_PROCESS_TIMELINE.html','e2e_process_timeline_lossless':'E2E_PROCESS_TIMELINE_LOSSLESS.html','high_latency_process_hardware_timeline':'HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html','concurrency_utilization':'CONCURRENCY_UTILIZATION.html','index_html':'index.html'}.items():outputs[key]=rec(root/'acceptance'/name)
 fields['logical_outputs']=outputs
 for key,item in outputs.items():fields[key+'_sha256']=item['sha256']
 return fields

'''
s=s[:position]+helper+s[position:];compile(s,str(p),'exec');p.write_text(s)
p=C/'run_closed_R08_to_R10_001.py';s=p.read_text().replace('prepare_stage_assignments_001.py','prepare_stage_assignments_002.py');compile(s,str(p),'exec');p.write_text(s)
print('TERMINAL_TOOLS_003_PREPARED_NOT_EXECUTED')
