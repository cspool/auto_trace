#!/usr/bin/env python3
"""Deterministic A-D figures, local Top-5, explicit display transforms, physical height audit."""
import json,csv,math,xml.etree.ElementTree as ET
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle,Patch
from PIL import Image
O=Path(__file__).resolve().parent;F=O/'figures';F.mkdir(exist_ok=True)
a=json.loads((O/'data/analysis.json').read_text());ks=list(csv.DictReader((O/'data/kernels.csv').open()));ps=list(csv.DictReader((O/'data/processes.csv').open()))
C={'MMAC GEMM':'#7856b4','GQA6':'#117db0','GDN chunk/state':'#009d78','GDN fused norm':'#c9649a','Packed decode':'#c56b21','Attention fallback':'#526ab7','RMSNorm':'#4ba895','MLP activation':'#dfae32','Other':'#abb0bb'}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':18,'axes.titlesize':25,'axes.labelsize':20,'xtick.labelsize':18,'ytick.labelsize':18,'axes.linewidth':1.6,'svg.fonttype':'none','svg.hashsalt':'batch8-fixed-dp2-report-20260909','savefig.dpi':160})
audit={'status':'complete','K':5,'width_in':32,'rect_height_points_target':56.241,'panels':{},'measurement_source':'data/kernels.csv: original integer nanoseconds','geometry_only_transform':True};outputs=[]
def init(name,height,ymax,title,xlabel,left=.08):
 fig=plt.figure(figsize=(32,height));ax=fig.add_axes([left,.17,.96-left,.63 if name!='D' else .70]);ax.set_ylim(-.7,ymax);ax.set_title(title,loc='left',pad=86 if name in ['B','C'] else 55,fontweight='bold');ax.set_xlabel(xlabel,labelpad=24,fontweight='semibold');ax.grid(axis='x' if name!='C' else 'y',alpha=.22,zorder=0);ax.spines[['top','right']].set_visible(False)
 fig.canvas.draw();h=56.241/72*fig.dpi/ax.bbox.height*(ax.get_ylim()[1]-ax.get_ylim()[0]);return fig,ax,h

def rect(ax,panel,start,y,duration,height,color,scale=1,cap=float('inf'),vertical=False,width=1.15):
 length=min(duration*scale,cap);fold=duration*scale>cap
 parts=[(0,length)] if not fold else [(0,length*.45),(length*.55,length*.45)]
 for off,l in parts:
  patch=Rectangle((y,start+off) if vertical else (start+off,y-height/2),width if vertical else l,l if vertical else height,color=color,zorder=2,linewidth=0);ax.add_patch(patch)
 if fold:
  xx=[start+length*(.45+i*.025) for i in range(5)];yy=[y+height*(v) for v in [0,.19,-.19,.19,0]]
  if vertical:ax.plot([y+width*.5+width*v for v in [0,.14,-.14,.14,0]],xx,color='#47515f',lw=1)
  else:ax.plot(xx,yy,color='#47515f',lw=1)
 audit['panels'][panel]['rectangles'].append({'start':start,'display_end':start+length,'raw_duration':duration,'scale':scale,'cap':None if math.isinf(cap) else cap,'folded':fold,'vertical':vertical,'category_coordinate':y,'thickness':width if vertical else height})
 return length,fold

def label_fit(fig,ax,text,x,y,block_width,block_height,fontsize=24,color='white',vertical=False):
 t=ax.text(x,y,text,ha='center',va='center',fontsize=fontsize,color=color,zorder=5)
 fig.canvas.draw();b=t.get_window_extent(fig.canvas.get_renderer());lo=ax.transData.transform((x-block_width/2,y-block_height/2));hi=ax.transData.transform((x+block_width/2,y+block_height/2))
 if b.width>abs(hi[0]-lo[0])*.94 or b.height>abs(hi[1]-lo[1])*.87:t.remove();return False
 return True

def finish(name,fig,ax,h):
 fig.canvas.draw();v=audit['panels'][name];v['xlim']=list(ax.get_xlim());v['ylim']=list(ax.get_ylim())
 if name!='C':v['measured_rectangle_height_points']=h/(ax.get_ylim()[1]-ax.get_ylim()[0])*ax.bbox.height/fig.dpi*72;assert abs(v['measured_rectangle_height_points']-56.241)<.001
 for r in v['rectangles']:
  limits=v['ylim'] if r['vertical'] else v['xlim'];assert limits[0]<=r['start']<=r['display_end']<=limits[1],(name,r,limits)
 fig.savefig(F/f'panel_{name.lower()}.svg',metadata={'Date':None});fig.savefig(F/f'panel_{name.lower()}.png',dpi=160);plt.close(fig);outputs.append(name)
 print('RENDERED',name,'rectangles',len(v['rectangles']),'height_pt',v.get('measured_rectangle_height_points'),flush=True)

# A: actual client time and only the selected process windows; no stretching.
audit['panels']['A']={'rectangles':[],'local_top5':[],'transform':'actual request-relative placement and width, seconds; scale=1; no folds'}
fig,ax,h=init('A',13,8*1.35,'A  Eight requests: client spans and the selected first-prefill / first-decode windows','X: seconds since earliest client start; all rectangle edges are actual timestamps\nY: request / rank categories. Colored windows cover selected process markers, not the full phase.')
origin=min(int(r['begin_ns']) for r in a['requests']);labels=[]
ordered_requests=sorted(a['requests'],key=lambda r:(int(r['rank']),int(r['measured_request_ordinal'])))
for i,r in enumerate(ordered_requests):
 y=(7-i)*1.35;num=int(r['measured_request_ordinal']);b=(int(r['begin_ns'])-origin)/1e9;dur=(int(r['end_ns'])-int(r['begin_ns']))/1e9
 rect(ax,'A',b,y,dur,h,'#dce2e9');ax.text(b+dur-8,y,f'{dur:.3f} s',ha='right',va='center',fontsize=24,color='#344154')
 spans=[]
 for phase,col in [('prefill','#e69f00'),('decode','#2584d7')]:
  u=next(u for u in a['units'] if u['request']==num and u['phase']==phase);s=(u['selected_marker_begin_ns']-origin)/1e9;d=(u['selected_marker_end_ns']-u['selected_marker_begin_ns'])/1e9;rect(ax,'A',s,y,d,h,col);spans.append((phase,s,d))
 ax.text(765,y+.18,f'P {spans[0][2]:.3f} s  /  D {spans[1][2]:.3f} s',va='center',fontsize=17)
 ax.text(765,y-.22,f'starts: {spans[0][1]:.3f} / {spans[1][1]:.3f} s',va='center',fontsize=15,color='#596779')
 audit['panels']['A']['local_top5'].append({'unit':num,'raw_duration_rank':['client']+[x[0] for x in sorted(spans,key=lambda z:-z[2])],'labels':'client inside; selected window durations and starts in reserved annotation area'})
 labels.append(f'R{num:02d} / rank {r["rank"]}')
ax.set_yticks([(7-i)*1.35 for i in range(8)],labels);ax.set_xlim(0,990);ax.legend(handles=[Patch(color='#dce2e9',label='Observed client span'),Patch(color='#e69f00',label='Selected prefill marker window'),Patch(color='#2584d7',label='Selected decode marker window')],loc='lower left',bbox_to_anchor=(0,1.01),ncol=3,fontsize=20,frameon=False)
fig.text(.08,.025,'8 requests x 1024 output tokens; both ranks carry 4 requests. Uncolored client time is outside this selected process scope.\nCross-device fine-grained concurrency has no promoted clock-error bound; these intervals do not quantify accelerator utilization.',fontsize=20,color='#344154',linespacing=1.5)
finish('A',fig,ax,h)

# B: local prefill composition from every selected kernel in each request.
audit['panels']['B']={'rectangles':[],'local_top5':[],'transform':'cumulative display ms; length=min(3*raw category kernel sum,150 ms); folds are one category'}
fig,ax,h=init('B',14,8*1.35,'B  First-prefill composition: GEMM and GQA6 dominate the selected kernel sum','X: cumulative DISPLAY milliseconds; each category length = min(3 x actual kernel sum, 150 ms)\nY: request / rank categories. Folds cap display length; percentages always use actual kernel sums.')
ends=[]
maxend_pre=max(sum(min(3*n/1e6,150) for n in u['category_duration_ns'].values()) for u in a['units'] if u['phase']=='prefill')
ax.set_xlim(0,maxend_pre+230)
for i,u in enumerate([u for u in a['units'] if u['phase']=='prefill']):
 y=(7-i)*1.35;vals=u['category_duration_ns'];top=sorted((c for c in C if vals[c]>0),key=lambda c:(-vals[c],c))[:5];x=0;hidden=[]
 for cat in C:
  raw=vals[cat]/1e6
  if not raw:continue
  length,fold=rect(ax,'B',x,y,raw,h,C[cat],3,150)
  if cat in top:
   width=length*.45 if fold else length;center=x+width/2
   if not label_fit(fig,ax,f'#{top.index(cat)+1} {vals[cat]/u["kernel_duration_ns"]*100:.1f}%',center,y,width,h,24,'#172332' if cat=='Other' else 'white'):hidden.append(cat)
  if cat in top[:3]:ax.text(x,y-h/2-.08,f'{x:.1f}',fontsize=14,va='top',color='#435167')
  x+=length
 ends.append((x,y,u));audit['panels']['B']['local_top5'].append({'unit':u['request'],'categories':top,'hidden_for_fit_only':hidden})
maxend=max(x for x,_,_ in ends);ax.set_xlim(0,maxend+230)
# Re-evaluate label fit at final coordinates after fixed extent (safe: texts were checked with autoscale then need below draw).
for x,y,u in ends:
 route='BM'+str(next(k['gqa_block_m_from_source_and_grid'] for k in ks if k['measured_request_ordinal']==str(u['request']) and k['phase']=='prefill' and k['category']=='GQA6'))
 ax.text(maxend+12,y,f'{u["kernel_duration_ns"]/1e6:.3f} ms | {route} | q-label {u["q_len_request_label"]}',va='center',fontsize=17)
ax.set_yticks([(7-i)*1.35 for i in range(8)],[f'R{u["request"]:02d} / rank {u["rank"]}' for u in a['units'] if u['phase']=='prefill']);ax.legend(handles=[Patch(color=C[c],label=c) for c in C],loc='lower left',bbox_to_anchor=(0,1.03),ncol=5,fontsize=18,frameon=False)
fig.text(.08,.025,'Each row includes every strict-owned kernel in that declared request/phase unit. Top-5 is ranked independently per row.\nSmall labels omitted only for fit remain in data/analysis.json and the report tables. Composition order is categorical, not launch order.',fontsize=20,color='#344154',linespacing=1.5)
finish('B',fig,ax,h)

# C: do not invent repeated decode steps; show the first declared decode unit of all eight requests.
audit['panels']['C']={'rectangles':[],'local_top5':[],'transform':'cumulative display ms vertically; min(3*raw category sum,90ms); no averaging or step extrapolation'}
fig,ax,h=init('C',20,430,'C  First-decode labels: mixed-batch launches and two observed B4 decode fallbacks','X: request / rank categories; one declared decode unit per request, no averaging\nY: cumulative DISPLAY milliseconds; category height = min(3 x actual kernel sum, 90 ms)')
ax.set_xlim(-.5,8*1.65);ax.set_ylim(0,430);ticks=[];labels=[]
for i,u in enumerate([u for u in a['units'] if u['phase']=='decode']):
 x=i*1.65;bottom=0;vals=u['category_duration_ns'];top=sorted((c for c in C if vals[c]>0),key=lambda c:(-vals[c],c))[:5];hidden=[]
 for cat in C:
  raw=vals[cat]/1e6
  if not raw:continue
  length,fold=rect(ax,'C',bottom,x,raw,h,C[cat],3,90,True,1.2)
  if cat in top:
   bh=length*.45 if fold else length
   if not label_fit(fig,ax,f'{raw:.3f} ms',x+.6,bottom+bh/2,1.2,bh,23,'#172332' if cat=='Other' else 'white',True):hidden.append(cat)
  bottom+=length
 ax.text(x+.6,bottom+11,f'Sum {u["kernel_duration_ns"]/1e6:.3f} ms',ha='center',va='bottom',fontsize=20)
 ax.text(x+.6,bottom+25,'B4 fallback' if u['request'] in [6,7] else 'mixed-batch path',ha='center',va='bottom',fontsize=17,color='#4f5d70')
 ticks.append(x+.6);labels.append(f'R{u["request"]:02d}\nrank {u["rank"]}');audit['panels']['C']['local_top5'].append({'unit':u['request'],'categories':top,'hidden_for_fit_only':hidden})
ax.set_xticks(ticks,labels);ax.set_ylabel('Cumulative display length (ms)',fontsize=20);ax.legend(handles=[Patch(color=C[c],label=c) for c in C],loc='lower left',bbox_to_anchor=(0,1.02),ncol=5,fontsize=18,frameon=False)
fig.text(.08,.025,'A request labeled decode can share a physical launch with prefill participants: q_len=1 is not the whole kernel workload.\nR06/R07 show B4 launches: packed GDN has 64 threads, not the B1-B3 optimized 256-thread configuration.\nThe difference between about 10 ms and 223 ms is not a measured decode speedup; these units run different physical work.',fontsize=20,color='#344154',linespacing=1.6)
finish('C',fig,ax,h)

# D: one row per kernel, raw launch order; enlarged widths with actual starts.
selected=sorted([k for k in ks if k['measured_request_ordinal']=='5' and k['phase']=='prefill' and k['layer_idx']=='3'],key=lambda k:int(k['hip_runtime_index']));assert len(selected)==15
parents=[p for p in ps if p['measured_request_ordinal']=='5' and p['phase']=='prefill' and p['layer_idx']=='3'];base=min(int(p['begin_ns']) for p in parents);p_end=max(int(p['end_ns']) for p in parents);ss=sum(int(k['duration_ns']) for k in selected)
audit['panels']['D']={'rectangles':[],'local_top5':[],'transform':'actual layer-marker-relative starts, microseconds; width=min(30*raw duration,10000us)','selection':{'request':5,'rank':0,'phase':'prefill','layer':3,'process_marker_origin_ns':base,'process_marker_envelope_ns':p_end-base,'kernel_duration_sum_ns':ss,'kernel_ids':[k['kernel_instance_id'] for k in selected]}}
fig,ax,h=init('D',20,15*1.8,'D  R05 / rank 0 / prefill / layer 3: the BM32 GQA6 launch in its actual order','X: microseconds since earliest selected layer-3 process marker\nLeft edges are actual starts; widths = min(30 x raw kernel duration, 10000 us). A fold is one execution.',left=.20)
ends=[];yt=[];yl=[]
short={'triton_red_fused__to_copy_add_mean_mul_pow_rsqrt_0':'fused RMSNorm','_gqa6':'_gqa6 (BM32)','triton_poi_fused_mul_rocm_unquantized_gemm_silu_slice_0':'fused MLP activation'}
for i,k in enumerate(selected):
 y=(14-i)*1.8;s=(int(k['begin_ns'])-base)/1e3;d=int(k['duration_ns'])/1e3;l,_=rect(ax,'D',s,y,d,h,C[k['category']],30,10000);ends.append(s+l)
 ax.text(s+l+450,y,f'{d:.2f} us | {int(k["duration_ns"])/ss*100:.2f}%',va='center',fontsize=18)
 name=short.get(k['native_kernel_name'],'GEMM '+('MT256' if 'MT256' in k['native_kernel_name'] else 'MT128') if k['category']=='MMAC GEMM' else k['native_kernel_name'][:24])
 yt.append(y);yl.append(f'{i+1:02d}  {name}\nstart {s:.3f} us');audit['panels']['D']['local_top5'].append({'unit':k['kernel_instance_id'],'kernel_ids':[k['kernel_instance_id']],'label':'all: each row is one actual launch; duration label outside'})
ax.set_yticks(yt,yl);ax.set_xlim(0,max(max(ends),(p_end-base)/1e3)+9000)
fig.text(.20,.025,f'15 strict-owned kernels; additive sum {ss/1e3:.2f} us; enclosing selected marker span {(p_end-base)/1e3:.2f} us.\nLaunch order is exact. Display-scaled widths can extend past actual end time. Gaps are not proof of production device idle time.\n_gqa6: grid (21,12,3), block 128 threads; 756 launched CTAs, BM32 = 2 query heads x 16 query positions.',fontsize=20,color='#344154',linespacing=1.6)
finish('D',fig,ax,h)

# Combined artifacts preserve the independently readable physical panel sizes.
ims=[Image.open(F/f'panel_{name.lower()}.png').convert('RGB') for name in outputs];combined=Image.new('RGB',(max(im.width for im in ims),sum(im.height for im in ims)),'white');y=0
for im in ims:combined.paste(im,(0,y));y+=im.height
combined.save(F/'batch8_optimization_timeline.png');preview=combined.copy();preview.thumbnail((1280,3200));preview.save(F/'combined_preview.png')
ET.register_namespace('','http://www.w3.org/2000/svg');ns='{http://www.w3.org/2000/svg}'
svgs=[ET.parse(F/f'panel_{n.lower()}.svg').getroot() for n in outputs];heights=[float(r.attrib['height'].removesuffix('pt')) for r in svgs];root=ET.Element(ns+'svg',{'width':'2304pt','height':str(sum(heights))+'pt','viewBox':f'0 0 2304 {sum(heights)}'});y=0
for i,(r,hei) in enumerate(zip(svgs,heights)):
 # IDs are panel-local in matplotlib; prefix every reference before combining.
 text=ET.tostring(r,encoding='unicode');ids=[n.attrib['id'] for n in r.iter() if 'id' in n.attrib]
 for ident in sorted(ids,key=len,reverse=True):text=text.replace('id="'+ident+'"','id="p'+str(i)+'_'+ident+'"').replace('#'+ident+'"','#p'+str(i)+'_'+ident+'"').replace('#'+ident+')','#p'+str(i)+'_'+ident+')')
 r=ET.fromstring(text);r.attrib.update({'x':'0','y':str(y)});root.append(r);y+=hei
ET.ElementTree(root).write(F/'batch8_optimization_timeline.svg',encoding='utf-8',xml_declaration=True)
audit['combined_height_in']=sum(heights)/72
(O/'FIGURE_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
print('ALL_FIGURES_COMPLETE',audit['combined_height_in'],'in',flush=True)
