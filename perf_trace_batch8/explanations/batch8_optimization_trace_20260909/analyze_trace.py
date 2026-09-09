#!/usr/bin/env python3
"""Read accepted R09/R10 evidence; derive optimization composition without a device call."""
import csv, json, hashlib, re, shutil, subprocess, datetime
from pathlib import Path
from collections import Counter, defaultdict
csv.field_size_limit(30_000_000)
OUT=Path(__file__).resolve().parent
PROJECT=OUT.parents[2]
RUN=PROJECT/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003'
R09=RUN/'artifacts/R09/continuation_001'; R10=RUN/'artifacts/R10/continuation_001'
TARGET=PROJECT/'pra2026-bh408-gqa-page784-k5120-batch8'
DATA=OUT/'data'; DATA.mkdir(exist_ok=True)
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def rec(p):return {'path':str(p),'size':p.stat().st_size,'sha256':sha(p)}
def writecsv(name,rows):
 with (DATA/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def union(rows):
 total=0;end=None
 for b,e in sorted(rows):
  if end is None or b>end:total+=e-b;end=e
  elif e>end:total+=e-end;end=e
 return total
sources=[]
for st in ['R09','R10']:
 p=RUN/'handoffs'/f'{st}.continuation.json';h=json.loads(p.read_text())
 assert h['status']==h['evidence_status']==h['execution_status']=='complete'
 assert h['coverage_target_met'] and not h['replay_timing_used_as_latency']
 sources.append(rec(p))
 for name in ['completion_audit','artifact_manifest','source_lineage']:
  q=Path(h[name]['path']);r=rec(q);assert r['sha256']==h[name]['sha256'];sources.append(r)
a=json.loads((R09/'analysis/fresh_e2e_analysis.accepted.json').read_text())
sources.append(rec(R09/'analysis/fresh_e2e_analysis.accepted.json'))
used=['request_timeline','process_timeline','kernel_timeline','high_latency_processes','opportunity_candidates','process_live_utilization','traffic_resource_attachment']
for item in a['tables']:
 if item['logical_name'] in used:
  r=rec(Path(item['path']));assert r['sha256']==item['sha256'];sources.append(r)
print('ACCEPTED_INPUT_HASHES_VERIFIED',len(sources),flush=True)
def rows(name):
 with (R09/'tables'/f'{name}.csv').open() as f:yield from csv.DictReader(f)
kraw=list(rows('kernel_timeline'));reqraw=list(rows('request_timeline'))
assert len(kraw)==23660 and len({k['kernel_instance_id'] for k in kraw})==23660
pfields='process_range_id request_id measured_request_ordinal rank physical_device_id phase forward_id layer_idx layer_type process_id fragment_id begin_ns end_ns duration_ns q_len kv_len owned_kernel_count explicit_no_kernel_target parent_process_range_id'.split()
kfields='kernel_instance_id owner_process_range_id request_id measured_request_ordinal rank physical_device_id phase forward_id layer_idx process_id fragment_id q_len kv_len native_kernel_name begin_ns end_ns duration_ns runtime_call_id hip_runtime_index queue_id stream_id'.split()
ks=[{f:k[f] for f in kfields} for k in kraw];byprocess=defaultdict(list)
for k in ks:byprocess[k['owner_process_range_id']].append(k)
ps=[];launches=[];allcontext=0;launch_missing=[]
for p in rows('process_timeline'):
 ps.append({f:p[f] for f in pfields})
 children=byprocess[p['process_range_id']]
 assert len(children)==int(p['owned_kernel_count'])
 context={c[0]:c for c in json.loads(p['hip_runtime_context'])};allcontext+=len(context)
 for k in children:
  assert (k['request_id'],k['rank'],k['phase'],k['forward_id'],k['layer_idx'])==(p['request_id'],p['rank'],p['phase'],p['forward_id'],p['layer_idx'])
  assert int(k['end_ns'])-int(k['begin_ns'])==int(k['duration_ns'])
  c=context[k['runtime_call_id']];assert c[3]==k['hip_runtime_index']
  assert int(p['begin_runtime_index'])<=int(c[3])<=int(p['end_runtime_index'])
  parsed=dict(re.findall(r'\b(gridDim[XYZ]|blockDim[XYZ]|sharedMemBytes)=(\d+)',c[5]))
  for field in ['gridDimX','gridDimY','gridDimZ','blockDimX','blockDimY','blockDimZ','sharedMemBytes']:k[field]=int(parsed[field]) if field in parsed else ''
  k['launch_metadata_present']=bool(parsed)
  if parsed:
   launches.append({'kernel_instance_id':k['kernel_instance_id'],'runtime_call_id':k['runtime_call_id'],'hip_runtime_index':k['hip_runtime_index'],'native_kernel_name':k['native_kernel_name'],'api_arguments':c[5]})
  else:launch_missing.append(k['kernel_instance_id'])
assert len(ps)==12544
reqfields='request_id measured_request_ordinal rank physical_device_id prompt_tokens completion_tokens http_status begin_ns end_ns duration_ns'.split()
requests=[{f:r[f] for f in reqfields} for r in reqraw]
requests.sort(key=lambda r:int(r['measured_request_ordinal']))
assert Counter(r['rank'] for r in requests)=={'0':4,'1':4}
assert all(r['http_status']=='200' and r['completion_tokens']=='1024' for r in requests)
category_order=['MMAC GEMM','GQA6','GDN chunk/state','GDN fused norm','Packed decode','Attention fallback','RMSNorm','MLP activation','Other']
def classify(k):
 n=k['native_kernel_name']
 if n.startswith('Cijk_'):return 'MMAC GEMM'
 if n=='_gqa6':return 'GQA6'
 if n=='_gdn_rmsnorm':return 'GDN fused norm'
 if n=='fused_recurrent_gated_delta_rule_packed_decode_kernel':return 'Packed decode'
 if n in ['kernel_unified_attention_3d','reduce_segments']:return 'Attention fallback'
 if n=='triton_red_fused__to_copy_add_mean_mul_pow_rsqrt_0':return 'RMSNorm'
 if n=='triton_poi_fused_mul_rocm_unquantized_gemm_silu_slice_0':return 'MLP activation'
 if n.startswith(('chunk_','recompute_w_u','merge_16x16','l2norm_','fused_gdn_gating','_causal_conv1d')):return 'GDN chunk/state'
 return 'Other'
for k in ks:
 k['category']=classify(k);k['gqa_block_m_from_source_and_grid']='';k['packed_path']='';k['tensor_tokens_from_norm_grid']=''
 if k['category']=='GQA6':
  assert k['gridDimY']==12 and k['gridDimZ'] in [1,2,3,4,5]
  bm=32 if 3<=k['gridDimZ']<=5 else (64 if k['gridDimZ']==1 and k['blockDimX']==256 else 16)
  k['gqa_block_m_from_source_and_grid']=bm
 if k['category']=='GDN fused norm':
  assert k['gridDimX']%3==0 and k['blockDimX']==256;k['tensor_tokens_from_norm_grid']=k['gridDimX']//3
 if k['category']=='Packed decode':
  assert k['gridDimX']==4 and k['gridDimY']%48==0
  k['packed_path']='optimized_B1_B3' if k['blockDimX']==256 and k['gridDimY']//48<=3 else 'official_fallback'
writecsv('kernels.csv',ks);writecsv('processes.csv',ps);writecsv('requests.csv',requests);writecsv('observed_launches.csv',launches)
pmap={p['process_range_id']:p for p in ps}
total=sum(int(k['duration_ns']) for k in ks)
def summary(items):
 return {'hits':len(items),'duration_ns':sum(int(k['duration_ns']) for k in items),'global_kernel_share':sum(int(k['duration_ns']) for k in items)/total,'requests':sorted({int(k['measured_request_ordinal']) for k in items}),'ranks':sorted({int(k['rank']) for k in items}),'units':sorted({(int(k['measured_request_ordinal']),k['phase']) for k in items}),'layers':sorted({int(k['layer_idx']) for k in items})}
units=[]
for r in requests:
 for phase in ['prefill','decode']:
  part=[k for k in ks if k['request_id']==r['request_id'] and k['phase']==phase];process=[p for p in ps if p['request_id']==r['request_id'] and p['phase']==phase]
  assert len(process)==784
  t=sum(int(k['duration_ns']) for k in part);cats={c:sum(int(k['duration_ns']) for k in part if k['category']==c) for c in category_order}
  units.append({'request':int(r['measured_request_ordinal']),'request_id':r['request_id'],'rank':int(r['rank']),'phase':phase,'q_len_request_label':process[0]['q_len'],'kv_len_request_label':process[0]['kv_len'],'process_count':len(process),'kernel_count':len(part),'kernel_duration_ns':t,'kernel_union_ns':union([(int(k['begin_ns']),int(k['end_ns'])) for k in part]),'selected_marker_begin_ns':min(int(p['begin_ns']) for p in process),'selected_marker_end_ns':max(int(p['end_ns']) for p in process),'category_duration_ns':cats,'category_share':{c:n/t for c,n in cats.items()},'gqa_launch_shapes':dict(Counter(str((k['gridDimX'],k['gridDimY'],k['gridDimZ'],k['blockDimX'],k['gqa_block_m_from_source_and_grid'])) for k in part if k['category']=='GQA6'))})
matchers={
 'page784_GQA6_all':lambda k:k['native_kernel_name']=='_gqa6' and k['process_id']=='kv_cache_attention',
 'page784_GQA6_BM32_local_B3_B5':lambda k:k['native_kernel_name']=='_gqa6' and 3<=k['gridDimZ']<=5,
 'strided_GDN_RMSNorm_SiLU':lambda k:k['native_kernel_name']=='_gdn_rmsnorm',
 'packed_GDN_optimized_B1_B3':lambda k:k['packed_path']=='optimized_B1_B3',
 'packed_GDN_official_B4':lambda k:k['packed_path']=='official_fallback',
 'GDN_chunk_h':lambda k:k['native_kernel_name']=='chunk_gated_delta_rule_fwd_kernel_h_blockdim64',
 'GDN_chunk_o':lambda k:k['native_kernel_name']=='chunk_fwd_kernel_o',
 'fixed_custom_GEMV':lambda k:bool(re.search('qwen35.*gemv|_qwen35_gemv|bf16_gemv.*qwen',k['native_kernel_name'],re.I)),
}
opt={name:summary([k for k in ks if fn(k)]) for name,fn in matchers.items()}
for name,fn in matchers.items():
 hits=[k for k in ks if fn(k)];parent_ids={k['owner_process_range_id'] for k in hits};den=sum(int(k['duration_ns']) for k in ks if k['owner_process_range_id'] in parent_ids)
 opt[name].update({'matched_owner_kernel_denominator_ns':den,'matched_owner_kernel_share':sum(int(k['duration_ns']) for k in hits)/den if den else None,'launch_configurations':dict(Counter(str(tuple(k[v] for v in ['gridDimX','gridDimY','gridDimZ','blockDimX','blockDimY','blockDimZ','sharedMemBytes'])) for k in hits))})
resource=Counter();metric_names=Counter();physical={};mismatch_process=set()
for r in rows('traffic_resource_attachment'):
 resource[(r['availability_state'],r['runtime_shape_match'])]+=1;metric_names[(r['metric_name'],r['availability_state'])]+=1
 if r['physical_attribute_id']:physical[r['physical_attribute_id']]=r['runtime_shape_match']
 if r['runtime_shape_match']=='False':mismatch_process.add(r['r07_process_range_id'])
live=Counter(r['availability_state'] for r in rows('process_live_utilization'))
opps=list(rows('opportunity_candidates'));cand=Counter(r['candidate_state'] for r in opps);candidate_process=Counter(pmap[r['process_range_id']]['process_id'] for r in opps if r['candidate_state']=='candidate')
high=list(rows('high_latency_processes'));highproc=Counter(r['process_id'] for r in high)
records={'status':'analysis_complete','generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'skill':'perf_trace/skills/build-optimization-trace-report/SKILL.md','run_id':'batch8-dp2-fresh-003','target_commit':a['target']['commit'],'evidence_scope':a['timeline_coverage_scope'],'observed_clock':a['observed_clock'],'r07_native_controller_history_exception_preserved':True,'optimized_only_trace':True,'baseline_comparison_performed':False,'speedup_claimed':False,'sources':sources,'total_kernels':len(ks),'total_processes':len(ps),'total_kernel_duration_ns':total,'kernel_launch_metadata_present':len(launches),'kernel_launch_metadata_missing':len(launch_missing),'category_order':category_order,'categories':{c:summary([k for k in ks if k['category']==c]) for c in category_order},'optimizations':opt,'units':units,'requests':requests,'source_derived_scope_summaries':a['derived_scope_summaries'],'cross_device_concurrency_state':a['cross_device_concurrency_state'],'live_process_availability':dict(live),'resource_row_availability_shape':{str(k):v for k,v in resource.items()},'resource_physical_shape_match':dict(Counter(physical.values())),'resource_metrics':{str(k):v for k,v in metric_names.items()},'opportunity_states':dict(cand),'candidate_processes':dict(candidate_process),'high_latency_processes':dict(highproc),'high_latency_rows':len(high),'global_p95_process_ns':a['global_p95_ns']}
# Preserve the original inventory and source, without importing target modules.
h2=json.loads((RUN/'handoffs/R02.json').read_text())
for name in ['process_inventory','source_and_ast_manifest']:
 p=Path(h2[name+'_path'].replace('/public/home/tangyu408/Qwen_DCU_Worker_0',str(PROJECT)));assert sha(p)==h2[name+'_sha256'];shutil.copy2(p,DATA/p.name);records['sources'].append(rec(p))
source_paths=['vllm/v1/attention/ops/rocm_aiter_unified_attention_gqa6.py','vllm/v1/attention/backends/rocm_aiter_unified_attn.py','vllm/model_executor/layers/fla/ops/gfx936.py','vllm/model_executor/layers/fla/ops/fused_recurrent.py','vllm/model_executor/layers/fla/ops/chunk_o.py','vllm/model_executor/models/qwen3_5.py','vllm/model_executor/models/qwen3_next.py','vllm/v1/core/sched/scheduler.py','vllm/platforms/rocm.py','docs/cscc/BATCH8_OFFICIAL_BASE_RECOMMENDATION.md']
assert subprocess.check_output(['git','-C',str(TARGET),'rev-parse','HEAD'],text=True).strip()==a['target']['commit']
for rel in source_paths:
 p=TARGET/rel;r=rec(p);assert subprocess.check_output(['git','-C',str(TARGET),'show','HEAD:'+rel])==p.read_bytes();records['sources'].append(r)
 q=OUT/'source_snapshot'/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
# Independently sealed R10 trace identity; report reuses tables to avoid counting paired display copies twice.
p=R10/'acceptance/E2E_PROCESS_TIMELINE.full.perfetto.json';r=rec(p);h10=json.loads((RUN/'handoffs/R10.continuation.json').read_text());assert r['sha256']==h10['full_perfetto_trace_sha256'];records['sources'].append(r)
dump(DATA/'analysis.json',records)
dump(DATA/'MATCHERS.json',{'ownership':'exact R09 owner_process_range_id + runtime_call_id + HIP runtime index, checked against owner HIP context; no GPU time-overlap attribution','categories':category_order,'matcher_implementation':'analyze_trace.py::classify and matchers','phase_semantics':'request label; physical launch may contain mixed prefill/decode participants','launch_source':'R07 HIP API arguments embedded losslessly in accepted R09 process_timeline.csv','duration':'integer end_ns - begin_ns; unique kernel IDs only','denominator':'sum of strict-owned observed kernel durations in the declared unit, not wall time or rectangle area'})
print(json.dumps({'total_kernel_ms':total/1e6,'optimizations':{k:{f:v[f] for f in ['hits','duration_ns','global_kernel_share']} for k,v in opt.items()},'category_percent':{c:records['categories'][c]['global_kernel_share']*100 for c in category_order},'launch_metadata':len(launches),'candidate_states':dict(cand),'physical_shape':dict(Counter(physical.values()))},ensure_ascii=False,indent=2),flush=True)
