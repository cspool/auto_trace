"""Synthetic CPU browser fixture only. No runtime-stage evidence or measured data."""
from pathlib import Path
import json,csv,hashlib,runpy
BASE=Path('/root/r08_emergency_tools');TOOLS=BASE/'stage_tool_templates/r10_001';OUT=BASE/'cpu_viewer_fixture_001';OUT.mkdir();renderer=runpy.run_path(str(TOOLS/'build_report.py'));origin=1788855000000000123;requests=[];processes=[];kernels=[];coverage=[];runtime_index=0
for q in range(8):
 rid='synthetic-request-'+str(q);rank=str(q%2);b=origin+q*7;e=b+1000000
 requests.append({'request_id':rid,'rank':rank,'physical_device_id':rank,'completion_tokens':'1024','begin_ns':str(b),'end_ns':str(e),'duration_ns':str(e-b),'fixture_only':'True'})
 for phase,index in [('prefill',0),('decode',1)]:
  pid=rid+'-'+phase;begin=b+100+index*20000;end=begin+10000;fields=['runtime_call_id','pid','tid','begin_ns','end_ns'];calls=[]
  for k in range(64):
   kid=pid+'-k'+str(k);kb=begin+100+k*3;ke=kb+1000;runtime_index+=1
   kernels.append({'request_id':rid,'rank':rank,'physical_device_id':rank,'kernel_instance_id':kid,'owner_process_range_id':pid,'begin_ns':str(kb),'end_ns':str(ke),'duration_ns':str(ke-kb),'native_kernel_name':'synthetic_shared_kernel','queue_id':'0','stream_id':'1','process_id':'synthetic_'+phase,'fragment_id':'fragment','phase':phase,'layer_idx':str(index),'fixture_only':'True'})
   calls.append([str(runtime_index),str(100+q),str(100+q),str(kb-1),str(kb+1)])
  ctx={kind:[{'request_id':rid,'rank':rank,'physical_device_id':rank,'range_id':pid+'-'+kind,'forward_id':pid,'layer_idx':str(index),'phase':phase,'begin_ns':str(begin),'end_ns':str(end)}] for kind in ['forward','layer']}
  processes.append({'request_id':rid,'rank':rank,'physical_device_id':rank,'process_range_id':pid,'begin_ns':str(begin),'end_ns':str(end),'duration_ns':str(end-begin),'process_id':'synthetic_'+phase,'fragment_id':'fragment','phase':phase,'layer_idx':str(index),'layer_forward_context':json.dumps(ctx),'hip_runtime_context_schema':json.dumps(fields),'hip_runtime_context':json.dumps(calls),'fixture_only':'True'})
 coverage.append({'request_id':rid,'process_targets':2,'strict_owned_kernels':128,'phases':[{'phase':'prefill','observed_process_targets':1},{'phase':'decode','observed_process_targets':1}]})
metas=[];packs={}
for name,data in [('request_timeline',requests),('process_timeline',processes),('kernel_timeline',kernels)]:
 path=OUT/(name+'.csv');fields=list(data[0])
 with path.open('x',newline='') as f:w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(data)
 meta={'logical_name':name,'path':str(path),'size':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'schema':fields,'row_count':len(data)};metas.append(meta);packs[name]=renderer['pack_table'](meta)
expected=len(requests)+len(processes)+2*len(kernels);payload={'mode':'timeline','origin_ns':str(origin),'expected_event_count':expected,'coverage':coverage,'source_tables':metas,'tables':packs,'lineage_id':'CPU_SYNTHETIC_FIXTURE_NEVER_RUNTIME_EVIDENCE'}
html='<!doctype html><html><meta charset="utf-8"><title>CPU synthetic fixture only</title><style>'+ (TOOLS/'viewer.css').read_text()+'</style><header><h1>CPU synthetic fixture only — not a runtime report</h1>'+renderer['LEGEND']+'</header><main><p id="loading"></p><div id="coverage"></div>'+renderer['TIMELINE_BODY']+'<pre id="details"></pre></main><script>const PAYLOAD='+json.dumps(payload,separators=(',',':'))+';</script><script>'+(TOOLS/'viewer.js').read_text()+'</script></html>'
(OUT/'fixture.html').write_text(html);manifest={'fixture_only':True,'origin_ns':str(origin),'expected_event_count':expected,'batch8_coverage':{'coverage':coverage},'source_tables':metas,'model_device_runtime_evidence_consumed':False};(OUT/'FIXTURE_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n');print('SYNTHETIC_BROWSER_FIXTURE_PREPARED',expected)
