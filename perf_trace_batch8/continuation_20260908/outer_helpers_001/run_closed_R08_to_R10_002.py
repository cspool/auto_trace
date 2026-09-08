"""Outer serial CPU suffix. Execute only after complete R08 capture checkpoint."""
from pathlib import Path
import subprocess,time,json,sys,os,datetime
CONTROL=Path('/public/home/accl15ptg7/run_R08_R10');RUN=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003');DEADLINE=datetime.datetime.fromisoformat('2026-09-09T04:18:09+00:00').timestamp();PY=sys.executable

def run(argv):
 assert time.time()<DEADLINE-120,'machine time reserve';print('OUTER_CPU_SUFFIX_START',argv,flush=True);p=subprocess.run(argv,timeout=max(1,DEADLINE-120-time.time()));assert p.returncode==0,'preserve failed phase without promotion';print('OUTER_CPU_SUFFIX_EXIT',argv,flush=True)
def phase(root,name,tool,*extra):
 run([PY,'-B',str(CONTROL/'phase_runner_002.py'),'--stage-root',str(root),'--phase',name,'--timeout',str(int(max(1,DEADLINE-120-time.time()))),'--',PY,'-B',str(tool),*extra])
def main():
 r08=RUN/'artifacts/R08/continuation_001';index=r08/'normalized/accepted_captures.json';assert index.exists() and json.loads(index.read_text())['status']=='complete','all twelve captures must be accepted first'
 run([PY,'-B',str(CONTROL/'restore_all_R08_release_artifacts_002.py')])
 # R08 owns resource construction and closure; R09 is never assigned early.
 run([PY,'-B',str(CONTROL/'prepare_stage_assignments_003.py'),'assign','R08']);phase(r08,'resource_model',r08/'tools/analysis_006/build_resource_model.py');phase(r08,'resource_audit',r08/'tools/analysis_006/audit_resource_model.py');phase(r08,'seal',r08/'tools/closure_001/seal_r08.py');phase(r08,'completion_audit',r08/'tools/closure_001/audit_r08.py');run([PY,'-B',str(CONTROL/'prepare_stage_assignments_003.py'),'handoff','R08'])
 for stage,phases in [('R09',[('analysis','build_analysis.py'),('table_audit','audit_analysis.py'),('seal','seal_r09.py'),('completion_audit','audit_completion.py')]),('R10',[('render','build_report.py'),('browser','browser_acceptance.py'),('seal','seal_acceptance.py'),('completion_audit','audit_report.py')])]:
  run([PY,'-B',str(CONTROL/'prepare_stage_assignments_003.py'),'assign',stage]);root=RUN/'artifacts'/stage/'continuation_001'
  for name,tool in phases:phase(root,name,root/'tools/revision_001'/tool)
  run([PY,'-B',str(CONTROL/'prepare_stage_assignments_003.py'),'handoff',stage])
 print('R08_R09_R10_LOCAL_COMPLETE_REQUIRES_FINAL_PUBLICATION_VERIFICATION',flush=True)
if __name__=='__main__':main()
