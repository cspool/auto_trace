#!/usr/bin/env python3
"""Complete per-type distributions and evidence-classified concurrency examples."""
from pathlib import Path
import argparse,base64,bisect,collections,gzip,hashlib,json,re
from playwright.sync_api import sync_playwright
from capture_diagnostic_report_figures import high_svg,svg_start,txt

def read(p):return json.loads(gzip.decompress(base64.b64decode(re.search(r'<script id="packed"[^>]*>(.*?)</script>',p.read_text(),re.S)[1])))
def dump(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def kernel_svg(case,label):
 w=1500;left=350;right=40;top=160;rowh=100;h=top+len(case['kernels'])*rowh+160;lo,hi=case['view'];span=hi-lo;px=lambda t:left+(t-lo)/span*(w-left-right);out=[svg_start(w,h,label+'：同设备 kernel 重叠证据'),txt(28,75,f"DCU{case['device']} · 峰值 {case['peak']} · 窗口内重叠 {case['overlap_ns']/1e3:.3f} µs；没有匹配硬件资源，不能补成0%。",19)]
 out.append(txt(left,112,'窗口内真实时间 / µs（线性）',19))
 for i in range(6):
  x=left+i/5*(w-left-right);t=txt(x,142,f'{span/1e3*i/5:.3f}',18)
  if i==5:t=t.replace('<text ','<text text-anchor="end" ',1)
  out.extend([f'<path d="M{x} 150 V{h-110}" stroke="#dce4ed"/>',t])
 for j,k in enumerate(case['kernels']):
  y=top+j*rowh;a=px(max(lo,k[1]));b=px(min(hi,k[2]));out.append(txt(25,y+23,f'kernel {j+1}',18,weight='bold'));out.append(txt(25,y+45,k[5][:28]+('…' if len(k[5])>28 else ''),14));out.append(txt(25,y+68,f'原始时长 {(k[2]-k[1])/1e3:.3f} µs',16));out.append(f'<rect x="{a}" y="{y+15}" width="{b-a}" height="24" fill="{["#5994cd","#d99a60"][j%2]}"/>');out.append(txt(left,y+67,k[5][:100],14,color='#50677f'))
 out.append(txt(28,h-66,f"原点 {case['origin_ns']} ns；相对窗口 [{lo}, {hi}) ns；条形仅按本窗裁切。",16));out.append(txt(28,h-30,'这是已归属 kernel 的重叠；不推断整卡占用，也不把缺失资源参考填入。',18));out.append('</svg>');return ''.join(out)
def main(root):
 folder=root/'analysis_reports/figures';facts=json.loads((root/'analysis_reports/data/SUMMARY.json').read_text());fm=json.loads((folder/'FIGURE_MANIFEST.json').read_text());items=[];cases={};records=[]
 for key,label in [('single_batch','单 batch'),('batch8','Batch8')]:
  source=root/'revised'/key/'CONCURRENCY_UTILIZATION.html';d=read(source);pm={p['id']:p for p in d['processes']};selected={i for g in d['groups'] for c in g['piles'] for i in c['members']};dur=sorted(pm[i]['d'] for i in selected);cap=dur[len(dur)//2]*2;extent=[d['time_sections'][0][0],d['time_sections'][-1][1]];ends=sorted({*extent,*[v for i in selected for v in [pm[i]['b'],pm[i]['e']]]});prefix=[0]
  for a,b in zip(ends,ends[1:]):prefix.append(prefix[-1]+min(b-a,cap))
  def project(t):
   i=max(0,min(len(ends)-2,bisect.bisect_right(ends,t)-1));return prefix[i]+(t-ends[i])/(ends[i+1]-ends[i])*min(ends[i+1]-ends[i],cap)
  def inverse(u):
   i=max(0,min(len(ends)-2,bisect.bisect_right(prefix,u)-1));return ends[i]+(u-prefix[i])/(prefix[i+1]-prefix[i])*(ends[i+1]-ends[i])
  ranks={(r['group'],r['pile_rank']):i+1 for i,r in enumerate(d['pile_order'])}
  def distribution(g,view,piles,subtitle):
   lo,hi=view;a=project(lo);b=project(hi);tracks=[]
   for c in sorted(piles,key=lambda c:ranks[(g['name'],c['rank'])]):
    ps=sorted((pm[i] for i in c['members'] if pm[i]['b']<hi and pm[i]['e']>lo),key=lambda p:(p['b'],p['e'],p['id']))
    tracks.append(dict(rank=ranks[(g['name'],c['rank'])],name=g['name'],pile=c['rank'],total_ms=c['total_ns']/1e6,min_ms=c['min_ns']/1e6,max_ms=c['max_ns']/1e6,member_count=len(c['members']),lines=[dict(id=p['id'],xf=(project(max(lo,p['b']))-a)/(b-a),xef=(project(min(hi,p['e']))-a)/(b-a),device=p['device'],high=p['high'],duration_ms=p['d']/1e6,duration_ns=p['d'],begin_ns=str(int(d['origin_ns'])+p['b']),end_ns=str(int(d['origin_ns'])+p['e']),layer=p['layer']) for p in ps]))
   breaks=[]
   for x,y in zip(ends,ends[1:]):
    if y-x>cap and x<hi and y>lo:
     f=(project((max(lo,x)+min(hi,y))/2)-a)/(b-a)
     if not breaks or f-breaks[-1]>.035:breaks.append(f)
   return dict(trace=key,type=g['name'],view=view,origin_ns=d['origin_ns'],folded=True,subtitle=subtitle,ticks=[{'fraction':i/5,'ns':inverse(a+(b-a)*i/5)} for i in range(6)],breaks=breaks,tracks=tracks)
  for g in d['groups']:
   full=distribution(g,extent,g['piles'],'该Process的五堆全部成员；每条线是一个真实实例，未删除或抽样。')
   full['envelope']='rectangle';full['subtitle']='五堆矩形总览：左边界为最早开始，右边界为最晚结束；每堆只绘制一个矩形。'
   largest=max(g['piles'],key=lambda c:c['total_ns']);ordered=sorted((pm[i] for i in largest['members']),key=lambda p:(p['b'],p['e'],p['id']));focus=max(ordered,key=lambda p:(p['d'],-p['b'],p['id']));center=ordered.index(focus);start=max(0,min(center-2,len(ordered)-5));neighbors=[focus];lo=min(p['b'] for p in neighbors);hi=max(p['e'] for p in neighbors);pad=max(1,(hi-lo)//20);view=[max(extent[0],lo-pad),min(extent[1],hi+pad)]
   detail=distribution(g,view,[largest],'累计延迟最高堆：只用一个矩形表示最长实例的开始与结束。');detail.update(envelope='rectangle',row_height=205,folded=False,breaks=[],focus_id=focus['id'],axis_label='窗口内真实时间 / ms · 线性放大（不折叠）',ticks=[{'fraction':i/5,'ns':view[0]+(view[1]-view[0])*i/5} for i in range(6)])
   for track in detail['tracks']:
    track['lines']=[line for line in track['lines'] if line['id']==focus['id']]
    for line in track['lines']:
     p=pm[line['id']];line['xf']=(max(view[0],p['b'])-view[0])/(view[1]-view[0]);line['xef']=(min(view[1],p['e'])-view[0])/(view[1]-view[0])
   stem=f"{key}_type_{g['name']}";item={'trace':key,'type':g['name'],'share':g['share'],'instance_count':g['count'],'full':stem+'_full','detail':stem+'_detail','focus_id':focus['id'],'focus_duration_ns':focus['d'],'focus_begin_ns':focus['b'],'focus_end_ns':focus['e'],'selected_pile':largest['rank'],'detail_selection':'Pile with largest summed duration; longest member by raw duration; only the longest member, 5% padding, linear time axis.'};items.append(item)
   for suffix,data in [('full',full),('detail',detail)]:
    name=stem+'_'+suffix;svg=high_svg(data,label+' · '+g['name']+('：五堆完整分布' if suffix=='full' else '：最长过程区间放大'));(folder/(name+'.svg')).write_text(svg);dump(folder/(name+'.json'),data);records.append({'name':name,'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'geometry':name+'.json','SVG_sha256':hashlib.sha256(svg.encode()).hexdigest(),'kind':'process_'+suffix})
  # True concurrency is classified only from per-device native kernel segments.
  segments=[c for c in d['counts'] if c[3]=='kernel'];overlap=sorted((c for c in segments if c[4]>1),key=lambda c:(-(c[1]-c[0]),c[0]));best=overlap[0];delta=best[1]-best[0];view=[best[0]-delta,best[1]+delta];ks=[k for k in d['kernels'] if k[3]==best[2] and k[1]<view[1] and k[2]>view[0]];refs=[]
  if key=='batch8':refs=[json.loads(x) for x in (root/'batch8_bandwidth/DISPATCH_BANDWIDTH.jsonl').read_text().splitlines()]
  valid_ids={r['r07_kernel_instance_id'] for r in refs if r['r07_projection_permitted']};matched=sum(k[6] in valid_ids or bool(d['resources'][k[0]].get('l2_samples')) for k in ks)
  case={'case':'with_kernel_overlap','device':best[2],'origin_ns':d['origin_ns'],'view':view,'peak':max(c[4] for c in segments if c[2]==best[2] and c[0]<view[1] and c[1]>view[0]),'overlap_ns':sum(min(view[1],c[1])-max(view[0],c[0]) for c in segments if c[2]==best[2] and c[4]>1 and c[0]<view[1] and c[1]>view[0]),'kernels':ks,'resource_matched_kernels':matched,'resource_state':'unavailable' if not matched else 'partial_or_available'};assert matched==0
  name=key+'_kernel_overlap';svg=kernel_svg(case,label);(folder/(name+'.svg')).write_text(svg);dump(folder/(name+'.json'),case);records.append({'name':name,'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'geometry':name+'.json','SVG_sha256':hashlib.sha256(svg.encode()).hexdigest(),'kind':'kernel_overlap'})
  old=json.loads((folder/(key+'_resource.json')).read_text());non=[]
  for r in old['instances']:
   dev=r['device'];cs=[c for c in segments if c[2]==dev and c[0]<old['view'][1] and c[1]>old['view'][0]];peak=max([c[4] for c in cs] or [0]);ol=sum(min(c[1],old['view'][1])-max(c[0],old['view'][0]) for c in cs if c[4]>1);assert peak<=1 and ol==0;non.append({'process_id':r['id'],'device':dev,'peak':peak,'overlap_ns':ol})
  cases[key]={'definition':'same-device observed strict-owned kernel overlap, not nested Process ranges or cross-device alignment','with_overlap':case,'without_overlap':{'view':old['view'],'origin_ns':old['origin_ns'],'per_instance_device_check':non,'figure_prefix':key,'resource_values_available':True}}
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':1500,'height':1100})
  for r in records:
   page.goto((folder/(r['name']+'.svg')).resolve().as_uri());page.locator('svg').screenshot(path=str(folder/(r['name']+'.png')));r['PNG_sha256']=hashlib.sha256((folder/(r['name']+'.png')).read_bytes()).hexdigest()
  browser.close()
 fm['figures']=[r for r in fm['figures'] if r['name'] not in {x['name'] for x in records}]+records;fm['status']='generated_pending_visual_review';dump(folder/'FIGURE_MANIFEST.json',fm);dump(folder/'PROCESS_DISTRIBUTIONS.json',items);dump(folder/'CONCURRENCY_CASES.json',cases);print('Complete per-type distributions:',[(x['trace'],x['type'],x['instance_count']) for x in items],flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();main(a.root.resolve())
