#!/usr/bin/env python3
"""Derive observed DP2 placement and launch-local batch samples; never interpolate scheduler state."""
from pathlib import Path
import json,csv,hashlib,shutil,subprocess
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
O=Path(__file__).resolve().parent;P=O.parents[2];T=P/'pra2026-bh408-gqa-page784-k5120-batch8';D=O/'data';F=O/'figures';F.mkdir(exist_ok=True)
a=json.loads((D/'analysis.json').read_text());ks=list(csv.DictReader((D/'kernels.csv').open()));origin=min(int(r['begin_ns']) for r in a['requests'])
raw=next(Path(x['path']) for x in a['sources'] if x['path'].endswith('/request_timeline.csv'))
assert hashlib.sha256(raw.read_bytes()).hexdigest()==next(x['sha256'] for x in a['sources'] if x['path']==str(raw))
rr=list(csv.DictReader(raw.open()));assert all(r['data_parallel_rank_requested']==r['rank'] for r in rr)
samples=[]
for u in a['units']:
 part=[k for k in ks if k['request_id']==u['request_id'] and k['phase']==u['phase'] and k['native_kernel_name'] in ['_gqa6','fused_recurrent_gated_delta_rule_packed_decode_kernel']]
 k=min(part,key=lambda k:int(k['begin_ns']));gqa=k['native_kernel_name']=='_gqa6';b=int(k['gridDimZ']) if gqa else int(k['gridDimY'])//48
 samples.append({'request':u['request'],'request_id':u['request_id'],'rank':u['rank'],'phase':u['phase'],'launch_begin_ns':int(k['begin_ns']),'client_relative_s':(int(k['begin_ns'])-origin)/1e9,'local_batch_sequences':b,'batch_inference_rule':'GQA gridDimZ = num_sequences' if gqa else 'packed gridDimY / HV48 = local batch','kernel_instance_id':k['kernel_instance_id'],'native_kernel_name':k['native_kernel_name'],'grid':[int(k[x]) for x in ['gridDimX','gridDimY','gridDimZ']],'threads_per_block':int(k['blockDimX']),'GQA_BLOCK_M':int(k['gqa_block_m_from_source_and_grid']) if gqa else None})
samples.sort(key=lambda x:(x['rank'],x['launch_begin_ns']))
ranks=[]
for rank in [0,1]:
 req=[r for r in a['requests'] if int(r['rank'])==rank]
 ranks.append({'rank':rank,'physical_device':rank,'requests':[int(r['measured_request_ordinal']) for r in req],'request_count':len(req),'prompt_tokens':sum(int(r['prompt_tokens']) for r in req),'output_tokens':sum(int(r['completion_tokens']) for r in req),'last_completion_client_relative_s':(max(int(r['end_ns']) for r in req)-origin)/1e9})
source_rel=['scripts/serve_cscc_dp2.sh','vllm/v1/engine/core_client.py','vllm/v1/core/sched/scheduler.py','vllm/platforms/rocm.py']
source=[]
for rel in source_rel:
 p=T/rel;data=p.read_bytes();assert subprocess.check_output(['git','-C',str(T),'show','HEAD:'+rel])==data
 q=O/'source_snapshot'/rel;q.parent.mkdir(exist_ok=True,parents=True);q.write_bytes(data);source.append({'path':str(p),'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)})
s={'status':'complete','focus':'global batch8 -> DP2 request placement -> per-rank dynamic batching and prefill token budget','topology':{'DP':2,'TP':1,'PP':1,'backend':'mp','replica_model':'full Qwen3.5-27B per device'},'source_records':source,'actual_routing':'explicit requested DP rank in this accepted trace; actual native owner rank agrees for all requests','default_serving_router':'when request.data_parallel_rank is absent: argmin(4*waiting + running), local waiting increment and coordinator updates','default_router_guarantees_exact_4_plus_4':False,'ranks':ranks,'client_all_eight_overlap_s':(min(int(r['end_ns']) for r in a['requests'])-max(int(r['begin_ns']) for r in a['requests']))/1e9,'prompt_token_imbalance_fraction_of_mean':abs(ranks[0]['prompt_tokens']-ranks[1]['prompt_tokens'])/((ranks[0]['prompt_tokens']+ranks[1]['prompt_tokens'])/2),'rank_last_completion_difference_s':abs(ranks[0]['last_completion_client_relative_s']-ranks[1]['last_completion_client_relative_s']),'launch_samples':samples,'sampling_for_figure':'one earliest matched GQA or packed launch per declared request/phase; 16 markers, no state interpolation','all_raw_kernels_preserved_in':'kernels.csv','prefill_budget_policy':{'max_prompt_tokens_gt_16384':512,'max_prompt_tokens_gt_8192':1024,'other_prefill':2048,'pure_decode':'does not enter prefill budget clamp'},'trace_prefill_q_labels':[u['q_len_request_label'] for u in a['units'] if u['phase']=='prefill'],'norm_physical_tensor_tokens':512,'baseline_DP1_comparison_performed':False}
(D/'scheduling.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':18,'svg.fonttype':'none','svg.hashsalt':'batch8-fixed-dp2-report-20260909'})
fig,axes=plt.subplots(2,1,figsize=(32,15),sharex=True);fig.subplots_adjust(left=.07,right=.97,top=.87,bottom=.20,hspace=.55)
for rank,ax in enumerate(axes):
 items=[x for x in samples if x['rank']==rank];ax.set_title('DCU '+str(rank)+' / DP rank '+str(rank)+'  |  requests '+', '.join('R%02d'%r for r in ranks[rank]['requests']),loc='left',fontsize=24,fontweight='bold',pad=22)
 ax.set_ylim(.55,4.95);ax.set_yticks([1,2,3,4]);ax.set_ylabel('Local sequence count B\n(at observed launches)',fontsize=20);ax.grid(alpha=.2);ax.spines[['top','right']].set_visible(False)
 for j,x in enumerate(items):
  t=x['client_relative_s'];b=x['local_batch_sequences'];pref=x['phase']=='prefill';ax.plot([t,t],[.65,b],color='#cbd5e1',lw=1.4);ax.scatter(t,b,s=220,marker='o' if pref else 's',color='#e49c13' if pref else '#1d80c0',zorder=3)
  dx=-10 if pref and j>0 else 10;dy=38 if pref else -60
  text=f'R{x["request"]:02d} {"P" if pref else "D"} | {t:.3f} s\nB={b} | '+('BM'+str(x['GQA_BLOCK_M']) if x['GQA_BLOCK_M'] else 'packed, 64 threads')
  ax.annotate(text,(t,b),xytext=(dx,dy),textcoords='offset points',ha='right' if dx<0 else 'left',fontsize=16,arrowprops={'arrowstyle':'-','lw':.7,'color':'#64748b'})
 ax.set_xlim(-8,220)
axes[-1].set_xlabel('Seconds since earliest client start; actual R07 launch timestamps, discrete samples only',fontsize=21,labelpad=18)
fig.suptitle('S  How global Batch8 becomes two independent per-device dynamic batches',x=.07,ha='left',fontsize=28,fontweight='bold')
fig.text(.07,.055,'P / D are request phase labels. The GQA grid identifies the total sequence count in the physical mixed batch.\nBoth ranks have observed local B=1,2,3,4 launches. No line interpolates unobserved scheduler states or asserts full-step coverage.\nThe R06/R07 B4 decode launches use the official packed path; the optimized B1-B3 packed path has no observed hit.',fontsize=20,linespacing=1.5,color='#35445a')
fig.savefig(F/'scheduling_local_batch.svg',metadata={'Date':None});fig.savefig(F/'scheduling_local_batch.png',dpi=160);plt.close(fig)
print(json.dumps({'ranks':ranks,'all_eight_overlap_s':s['client_all_eight_overlap_s'],'sample_count':len(samples)},ensure_ascii=False,indent=2),flush=True)
