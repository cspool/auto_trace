#!/usr/bin/env python3
"""Read-only checks for shared view docs, skill links and active scheduler pins.
Does not load a target model, query devices, start a scheduler or run a stage.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,sys

STAGES=['evidence-planning','full-request-process-trace','targeted-hardware-gap-analysis','utilization-concurrency-analysis','trace-visualization-reporting']
def main(repo):
 docs=[];skills=[]
 for package in ['perf_trace','perf_trace_batch8']:
  for suffix in STAGES:
   skill=repo/package/'skills'/('qwen-dcu-workflow05-'+suffix);skills.append(skill/'SKILL.md');docs.extend(skill.rglob('*.md'))
  docs.extend((repo/package/'workflows').glob('05*.md'));docs.extend((repo/package/'workflows/references').glob('*.md'))
 docs.extend((repo/'perf_trace/skills/build-optimization-trace-report').rglob('*.md'))
 for p in docs:
  text=re.sub(r'(?ms)^(```|~~~).*?^\1[^\n]*\n?', '',p.read_text())
  for target in re.findall(r'\]\(([^)]+)\)',text):
   target=target.split('#',1)[0].strip('<>')
   if target and '://' not in target and not target.startswith('/') and '<' not in target:
    assert (p.parent/target).exists(),(p,target)
 for p in skills:
  text=p.read_text();front=re.match(r'^---\n(.*?)\n---',text,re.S);assert front,p
  assert re.search(r'^name: '+re.escape(p.parent.name)+r'$',front[1],re.M),p
  assert re.search(r'^description: .+',front[1],re.M),p
 a=repo/'perf_trace/skills/qwen-dcu-workflow05-trace-visualization-reporting/references/process-resource-contract.md';b=repo/'perf_trace_batch8/skills/qwen-dcu-workflow05-trace-visualization-reporting/references/process-resource-contract.md';assert a.read_bytes()==b.read_bytes()
 manifest=json.loads((repo/'perf_trace_batch8/manifests/workflow01_10_fresh_e2e_pipeline.json').read_text());profile=json.loads((repo/'perf_trace_batch8/configs/trace_targets/batch8_dual_dcu_dp2.json').read_text())
 spec=importlib.util.spec_from_file_location('_view_contract_scheduler',repo/'perf_trace_batch8/scripts/run_perf_trace_01_10.py');module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
 for goal,binding in manifest['bindings'].items():
  p=repo/binding['skill_path'];text=p.read_text();assert hashlib.sha256(p.read_bytes()).hexdigest()==binding['skill_file_sha256'],goal
  tree,files=module.skill_tree_sha256(p.parent);assert tree==binding['skill_tree_sha256'] and files==binding['skill_tree_files'],goal
  assert all(x in text for x in profile['required_skill_literals']),goal
  assert not any(x in text for x in profile['forbidden_skill_literals']),goal
  parsed=module.parse_serial_contract(text,binding['skill']);assert parsed['runtime_goal']==goal and parsed['runtime_predecessors']==(','.join(binding['predecessors']) or 'none'),goal
 print(json.dumps({'status':'PASS','markdown_files_checked':len(docs),'skill_entrypoints_checked':len(skills),'shared_contracts_identical':True,'active_scheduler_bindings_checked':len(manifest['bindings']),'serial_parser_checked':True,'runtime_stage_executed':False},indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2]);args=p.parse_args();main(args.repo.resolve())
