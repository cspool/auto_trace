"""Diagnose a frozen CPU normalizer failure without modifying any native evidence."""
from pathlib import Path
import runpy,sys,json,collections,time
R=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');sys.argv=['normalize_capture.py','--segment','04_triton_red_fused__to_copy_add_mean_mul_pow_rsqrt_0_pmc','--attempt','attempt_003','--revision','diagnostic_002'];started=time.monotonic()
try:runpy.run_path(str(R/'tools/analysis_006/normalize_capture.py'),run_name='__main__')
except ValueError as error:
 tb=error.__traceback__;s=None
 while tb:
  if tb.tb_frame.f_code.co_name=='main' and tb.tb_frame.f_code.co_filename.endswith('normalize_capture.py'):s=tb.tb_frame.f_locals
  tb=tb.tb_next
 assert s is not None and 'eligible' in s
 conn=s['conn'];bad=[];hist=collections.Counter();eligible={(x['kernel']['pid'],x['kernel']['_Index']) for x in s['eligible'].values()}
 for pid in s['pid_ranks']:
  cfg=s['configs'][pid];ck=cfg['KEY'];ids=[x[0] for x in conn.execute('SELECT STR_ID FROM STR_TABLE WHERE CONFIG_KEY=? AND PID=? AND TYPE=6 AND STR_NAME=?',(ck,pid,s['literal']))]
  for op in conn.execute('SELECT rowid AS native_rowid,* FROM '+s['q']('HIPOPS_'+ck)+' WHERE Name IN ('+','.join('?' for _ in ids)+')',ids):
   hs=list(conn.execute('SELECT rowid AS native_rowid,* FROM '+s['q']('HIP_'+ck)+' WHERE _Index=?',(op['_Index'],)))
   if len(hs)!=1:bad.append({'pid':pid,'op':dict(op),'launch_count':len(hs),'required_selected_dispatch':(pid,op['_Index']) in eligible});continue
   h=dict(hs[0]);api=str(h['args']).split('(',1)[0];hist[api]+=1
   if api not in s['LAUNCH_APIS']:bad.append({'pid':pid,'op':dict(op),'HIP':h,'API':api,'native_ops_with_same_Index':conn.execute('SELECT COUNT(*) FROM '+s['q']('HIPOPS_'+ck)+' WHERE _Index=?',(op['_Index'],)).fetchone()[0],'required_selected_dispatch':(pid,op['_Index']) in eligible})
 result={'status':'CPU_diagnostic_complete_not_accepted','error':str(error),'current_process_markers':len(s['events']),'current_owned_kernels':len(s['all_owned']),'all_required_logical_owner_multiplicities_already_passed':len(s['owner_rows'])==len(s['pending']),'required_eligible_dispatches':len(eligible),'pending_logical_owners':len(s['pending']),'exact_literal_API_histogram':dict(hist),'non_direct_dispatches':bad,'original_raw_bytes_unmodified':True,'elapsed_seconds':time.monotonic()-started,'diagnostic_normalization_revision':str(s['output'])}
 out=R/'raw/runtime_tools/capture04_native_launch_diagnostic_001.json'
 with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps(result,indent=2),flush=True)
else:raise AssertionError('expected failure did not reproduce')
