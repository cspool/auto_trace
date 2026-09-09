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
fig,axes=plt.subplots(2,1,figsize=(32,18),sharex=True)
fig.subplots_adjust(left=.075,right=.985,top=.87,bottom=.12,hspace=.27)
geometry={'status':'complete','layout':'two time plots, one per DP rank; enlarged information rectangles anchored at actual launch times','x_axis':'actual seconds since earliest client start','y_axis':'actual launch-local B at the dot','rectangle_display_width_s':43,'rectangle_display_height_B':1.15,'rectangle_width_is_measured_duration':False,'samples':[],'panels':[]}
for rank,ax in enumerate(axes):
 items=[x for x in samples if x['rank']==rank]
 ax.set_xlim(-4,239);ax.set_ylim(.65,5.35);ax.set_yticks([1,2,3,4]);ax.set_xticks(list(range(0,226,25)));ax.tick_params(labelsize=20,labelbottom=True)
 ax.set_ylabel('Local batch B\n(at each dot)',fontsize=22);ax.grid(alpha=.23);ax.spines[['top','right']].set_visible(False)
 ax.set_title('DCU '+str(rank)+' / rank '+str(rank)+'  |  '+'  '.join('R%02d'%r for r in ranks[rank]['requests']),loc='left',fontsize=25,fontweight='bold',pad=16)
 boxes=[]
 for j,x in enumerate(items):
  left=x['client_relative_s'];b=x['local_batch_sequences'];pref=x['phase']=='prefill';bottom=b+.10 if pref else b-1.25
  color='#ffedbf' if pref else '#d7eafc';edge='#c88700' if pref else '#1975b6'
  patch=Rectangle((left,bottom),43,1.15,facecolor=color,edgecolor=edge,lw=1.8,zorder=3);patch.set_gid(f'sample-rank{rank}-order{j+1}');ax.add_patch(patch)
  ax.plot([left,left],[b,bottom if pref else bottom+1.15],color=edge,lw=2,zorder=4)
  ax.scatter([left],[b],s=105,color=edge,edgecolor='white',linewidth=.7,zorder=5)
  center=left+21.5
  texts=[ax.text(center,bottom+.88,f'R{x["request"]:02d} {"PREFILL" if pref else "DECODE"}  |  B{b}',ha='center',va='center',fontsize=25,fontweight='bold',color='#624600' if pref else '#145985',zorder=6),
   ax.text(center,bottom+.57,f'{left:.3f} s',ha='center',va='center',fontsize=25,color='#23374c',zorder=6),
   ax.text(center,bottom+.25,('GQA BM'+str(x['GQA_BLOCK_M']) if x['GQA_BLOCK_M'] else 'Packed B4')+f' | {x["threads_per_block"]} threads',ha='center',va='center',fontsize=22,color='#23374c',zorder=6)]
  fig.canvas.draw();renderer=fig.canvas.get_renderer();box=patch.get_window_extent(renderer)
  for text in texts:
   tb=text.get_window_extent(renderer);assert box.x0<=tb.x0 and tb.x1<=box.x1 and box.y0<=tb.y0 and tb.y1<=box.y1,('rectangle text outside',rank,j,text.get_text())
  bounds=[left,bottom,left+43,bottom+1.15]
  for previous in boxes:assert not (max(bounds[0],previous[0])<min(bounds[2],previous[2]) and max(bounds[1],previous[1])<min(bounds[3],previous[3])),('overlapping rectangles',rank,j)
  boxes.append(bounds)
  geometry['samples'].append({'rank':rank,'order':j+1,'request':x['request'],'phase':x['phase'],'kernel_instance_id':x['kernel_instance_id'],'launch_begin_ns':x['launch_begin_ns'],'client_relative_s':left,'local_batch_sequences':b,'grid':x['grid'],'threads_per_block':x['threads_per_block'],'GQA_BLOCK_M':x['GQA_BLOCK_M'],'bounds':bounds,'anchor':[left,b],'width_pt':box.width/fig.dpi*72,'height_pt':box.height/fig.dpi*72,'all_text_inside_rectangle':True})
 geometry['panels'].append({'rank':rank,'xlim':list(ax.get_xlim()),'ylim':list(ax.get_ylim()),'xticks':[float(v) for v in ax.get_xticks()],'rectangles_do_not_overlap':True})
axes[-1].set_xlabel('Actual seconds since earliest client start; every dot and rectangle LEFT edge uses the recorded launch time',fontsize=22,labelpad=16)
fig.suptitle('S  How global Batch8 becomes two independent per-device dynamic batches',x=.075,y=.965,ha='left',fontsize=28,fontweight='bold')
fig.text(.075,.924,'Actual time on X; launch-local B at each dot. Large rectangles retain request, phase, time and kernel configuration.',fontsize=23,color='#35445a')
fig.text(.075,.025,'PREFILL labels sit above their dots; DECODE labels sit below. Rectangle width = 43 display seconds (annotation size, not execution duration).\nThe dot is the measured (time, B) sample. Rectangle right edges are display boundaries. No scheduler state is interpolated between samples.',fontsize=20,linespacing=1.5,color='#35445a')
fig.savefig(F/'scheduling_local_batch.svg',metadata={'Date':None});fig.savefig(F/'scheduling_local_batch.png',dpi=160);plt.close(fig)
geometry['sample_count']=len(geometry['samples']);assert geometry['sample_count']==16
(O/'SCHEDULING_FIGURE_AUDIT.json').write_text(json.dumps(geometry,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'ranks':ranks,'all_eight_overlap_s':s['client_all_eight_overlap_s'],'sample_count':len(samples)},ensure_ascii=False,indent=2),flush=True)
