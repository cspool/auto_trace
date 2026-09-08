"""Outer wait only; successor assignments remain impossible before full capture gate."""
from pathlib import Path
import datetime,time,json,subprocess,sys,os
C=Path('/public/home/accl15ptg7/run_R08_R10');R=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');deadline=datetime.datetime.fromisoformat('2026-09-08T20:18:09+00:00').timestamp();index=R/'normalized/accepted_captures.json'
while time.time()<deadline-1800:
 if index.exists():
  try:x=json.loads(index.read_text())
  except json.JSONDecodeError:time.sleep(2);continue
  assert x['status']=='complete' and len(x['captures'])==12
  print('ALL_CAPTURE_INDEX_OBSERVED_STARTING_OUTER_RESTORATION_THEN_CPU',flush=True)
  result=subprocess.run([sys.executable,'-u','-B',str(C/'run_closed_R08_to_R10_001.py')]);print('OUTER_CPU_SUFFIX_EXIT',result.returncode,flush=True);raise SystemExit(result.returncode)
 if (C/'STOP_CPU_SUFFIX_WAITER').exists():raise SystemExit(0)
 time.sleep(20)
raise RuntimeError('machine deadline leaves insufficient CPU suffix reserve')
