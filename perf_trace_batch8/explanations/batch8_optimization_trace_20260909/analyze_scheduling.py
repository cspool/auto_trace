#!/usr/bin/env python3
"""Derive observed DP2 placement and launch-local batch samples; never interpolate scheduler state."""
from pathlib import Path
import json,csv,hashlib,shutil,subprocess
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
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
fig,ax=plt.subplots(figsize=(32,10.5));fig.subplots_adjust(left=.075,right=.985,top=.84,bottom=.10)
ax.set_xlim(0,8);ax.set_ylim(0,2);ax.axis('off')
geometry={'status':'complete','layout':'two rank rows; eight equally sized cards per row in actual launch order','x_axis':'categorical launch ordinal within rank, not elapsed time','y_axis':'categorical DP rank / device','card_width':.94,'card_height':.82,'information_card_fraction_of_axes':.94*.82,'information_card_fraction_of_full_figure':.94*.82*(.985-.075)*(.84-.10),'samples':[]}
for rank in [0,1]:
 items=[x for x in samples if x['rank']==rank]
 y=1-rank+.02
 ax.text(-.02,y+.88,'DCU '+str(rank)+' / rank '+str(rank)+'  |  '+'  '.join('R%02d'%r for r in ranks[rank]['requests']),fontsize=24,fontweight='bold',va='bottom')
 for j,x in enumerate(items):
  left=j+.03;pref=x['phase']=='prefill';color='#fff0d0' if pref else '#dcecfb';edge='#cf8a06' if pref else '#257db7'
  patch=Rectangle((left,y),.94,.82,facecolor=color,edgecolor=edge,lw=1.6);patch.set_gid(f'sample-rank{rank}-order{j+1}');ax.add_patch(patch)
  center=left+.47
  texts=[ax.text(center,y+.715,f'{j+1:02d}  /  R{x["request"]:02d}  {"PREFILL" if pref else "DECODE"}',ha='center',va='center',fontsize=24,color='#2b4055'),
   ax.text(center,y+.49,f'B{x["local_batch_sequences"]}',ha='center',va='center',fontsize=58,fontweight='bold',color='#7b5100' if pref else '#125c92'),
   ax.text(center,y+.29,'GQA / BM'+str(x['GQA_BLOCK_M']) if x['GQA_BLOCK_M'] else 'Packed / B4',ha='center',va='center',fontsize=26,color='#23374c'),
   ax.text(center,y+.17,f'{x["threads_per_block"]} threads',ha='center',va='center',fontsize=23,color='#43576b'),
   ax.text(center,y+.055,f'{x["client_relative_s"]:.3f} s',ha='center',va='center',fontsize=24,color='#23374c')]
  fig.canvas.draw();renderer=fig.canvas.get_renderer();box=patch.get_window_extent(renderer)
  for text in texts:
   tb=text.get_window_extent(renderer);assert box.x0<=tb.x0 and tb.x1<=box.x1 and box.y0<=tb.y0 and tb.y1<=box.y1,('card text outside',rank,j,text.get_text())
  geometry['samples'].append({'rank':rank,'order':j+1,'request':x['request'],'phase':x['phase'],'kernel_instance_id':x['kernel_instance_id'],'launch_begin_ns':x['launch_begin_ns'],'client_relative_s':x['client_relative_s'],'local_batch_sequences':x['local_batch_sequences'],'grid':x['grid'],'threads_per_block':x['threads_per_block'],'GQA_BLOCK_M':x['GQA_BLOCK_M'],'bounds':[left,y,left+.94,y+.82],'width_pt':box.width/fig.dpi*72,'height_pt':box.height/fig.dpi*72,'all_text_inside_card':True})
fig.suptitle('S  How global Batch8 becomes two independent per-device dynamic batches',x=.075,y=.96,ha='left',fontsize=28,fontweight='bold')
fig.text(.075,.89,'16 observed launches  |  two rank rows  |  read each row left to right: B1 -> B2 -> B3 -> B4',fontsize=24,color='#35445a')
fig.text(.075,.025,'X: categorical launch order within each rank; Y: categorical DCU / rank. Card width is constant and does not encode duration.\nEach card gives the actual client-relative timestamp (seconds), request phase and launch-local B. No scheduler state is interpolated.',fontsize=20,linespacing=1.5,color='#35445a')
fig.savefig(F/'scheduling_local_batch.svg',metadata={'Date':None});fig.savefig(F/'scheduling_local_batch.png',dpi=160);plt.close(fig)
geometry['sample_count']=len(geometry['samples']);assert geometry['sample_count']==16
(O/'SCHEDULING_FIGURE_AUDIT.json').write_text(json.dumps(geometry,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'ranks':ranks,'all_eight_overlap_s':s['client_all_eight_overlap_s'],'sample_count':len(samples)},ensure_ascii=False,indent=2),flush=True)
