from pathlib import Path
import runpy,sys,sqlite3,json,traceback,collections,time,hashlib
R=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');original=sqlite3.connect
# Pure connection-local read caching; input DB and native rows remain unchanged.
def connect(*args,**kwargs):
 c=original(*args,**kwargs);c.execute('PRAGMA mmap_size=4294967296');c.execute('PRAGMA cache_size=-1048576');return c
sqlite3.connect=connect
sys.argv=['normalize_capture.py','--segment','04_triton_red_fused__to_copy_add_mean_mul_pow_rsqrt_0_pmc','--attempt','attempt_002','--revision','diagnostic_001']
try:runpy.run_path(str(R/'tools/analysis_005/normalize_capture.py'),run_name='__main__')
except ValueError as error:
 tb=error.__traceback__;scope=None
 while tb:
  if tb.tb_frame.f_code.co_name=='main' and tb.tb_frame.f_code.co_filename.endswith('normalize_capture.py'):scope=tb.tb_frame.f_locals
  tb=tb.tb_next
 assert scope and 'kernels_by_source' in scope
 cases=[];good=0
 for source_id,selection in scope['pending'].items():
  target=selection['target'];current=scope['bound_by_source'][source_id];observed=scope['observed_bound'][target['r07_bound_target_id']];kernels=scope['kernels_by_source'][source_id];actual=[r for r in kernels if r['kernel_literal']==scope['literal']];expected=[scope['observed_kernels'][k] for k in target['exact_literal_kernel_ids']]
  if len(actual)==len(expected):good+=1;continue
  cases.append({'source_r06_target_id':source_id,'request_id':current['request_id'],'phase':current['phase'],'layer_idx':current['layer_idx'],'process_id':current['process_id'],'rank':current['dp_rank'],'R07_q_len':observed['q_len'],'R08_q_len':current['q_len'],'R07_kv_len':observed['kv_len'],'R08_kv_len':current['kv_len'],'expected_count':len(expected),'actual_exact_literal_count':len(actual),'all_owned_current_kernel_literals':[{'literal':k['kernel_literal'],'HIP_Index':k['kernel']['_Index'],'rowid':k['kernel']['native_rowid']} for k in kernels]})
 result={'status':'diagnostic_complete_not_accepted','error':str(error),'expected_literal':scope['literal'],'current_process_count':len(scope['events']),'current_owned_kernel_count':len(scope['all_owned']),'matching_owner_count':good,'mismatching_owner_count':len(cases),'cases':cases,'native_counter_records_not_reassigned':True,'original_source_unmodified':True,'diagnostic_normalization_output':str(scope['output'])};out=R/'raw/runtime_tools/capture04_multiplicity_diagnostic_001.json'
 with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps({k:v for k,v in result.items() if k!='cases'}),flush=True);print(json.dumps(cases[:10],indent=2),flush=True)
else:raise AssertionError('failure unexpectedly not reproduced')
