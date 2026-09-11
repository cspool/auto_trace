#!/usr/bin/env python3
"""Capture auditable figure geometry from existing offline viewers; export SVG/PNG."""
from pathlib import Path
import argparse,json,html,hashlib
from playwright.sync_api import sync_playwright

def esc(s):return html.escape(str(s))
def txt(x,y,s,size=19,color='#243852',weight='normal'):
 return f'<text x="{x:.3f}" y="{y:.3f}" font-size="{size}" fill="{color}" font-weight="{weight}">{esc(s)}</text>'
def svg_start(w,h,title):return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><style>text{{font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif}}</style><rect width="100%" height="100%" fill="#fff"/>'+txt(28,38,title,25,weight='bold')
def axis(parts,data,w,left,right,y,bottom):
 lo,hi=data['view']; origin=int(data['origin_ns']);
 for t in data['ticks']:
  x=left+t['fraction']*(w-left-right);parts.append(f'<path d="M{x} {y} V{bottom}" stroke="#dce4ed" stroke-width="1"/>');label=txt(x if t['fraction']>.9 else x-12,y-10,f"{t['ns']/1e9:.6f}" if data['folded'] else f"{(t['ns']-lo)/1e6:.3f}",17);parts.append(label.replace('<text ','<text text-anchor="end" ',1) if t['fraction']>.9 else label)
 parts.append(txt(left,y-38,'真实时间 / s（相对trace原点）· 公共折叠轴' if data['folded'] else data.get('axis_label','窗口内时间 / ms · 两图共用起点和线性比例尺'),18))
 parts.append(txt(28,bottom+36,f"原点 {origin} ns；视窗 [{lo}, {hi}) ns（相对原点）",15,color='#50677f'))
def high_svg(data,title):
 w=1500;left=340;right=30;top=146;rowh=data.get('row_height',205);h=top+rowh*len(data['tracks'])+108;parts=[svg_start(w,h,title),txt(28,75,data.get('subtitle','每堆一个矩形，表示本窗内的起止范围；原始全局堆排名保留。'),19)]
 axis(parts,data,w,left,right,top,top+rowh*len(data['tracks']))
 for row,t in enumerate(data['tracks']):
  y=top+row*rowh;parts.append(txt(25,y+30,f"#{t['rank']} {t['name']}",20,weight='bold'));parts.append(txt(25,y+57,f"堆{t['pile']} · 全堆 {t['total_ms']:.3f} ms",18));parts.append(txt(25,y+83,f"全堆{t['member_count']}实例；本窗{len(t['lines'])}实例",17));parts.append(txt(25,y+109,f"单次 {t['min_ms']:.3f}–{t['max_ms']:.3f} ms",17));parts.append(f'<path d="M0 {y+rowh-2} H{w}" stroke="#c9d6e4"/>')
  lines=t['lines'];n=len(lines)
  if not n:parts.append(txt(left+30,y+80,'本时间区间没有该堆实例',19,color='#728197'));continue
  px=lambda f:left+f*(w-left-right);py=lambda i:y+23+((rowh-75)*(i/(n-1)) if n>1 else (rowh-75)/2)
  bs=[px(l['xf']) for l in lines];es=[px(l['xef']) for l in lines]
  clip=f'clip{row}';parts.append(f'<defs><clipPath id="{clip}"><rect x="{left}" y="{y}" width="{w-left-right}" height="{rowh}"/></clipPath></defs><g clip-path="url(#{clip})">')
  parts.append(f'<rect data-pile-envelope="{t["pile"]}" x="{min(bs)}" y="{y+25}" width="{max(es)-min(bs)}" height="70" fill="#dbe9f6" stroke="#849bb5" stroke-width="1.2"/>')
  parts.append('</g>')
  if all('begin_ns' in l and 'end_ns' in l for l in lines):
   first=min(int(l['begin_ns']) for l in lines)-int(data['origin_ns']);last=max(int(l['end_ns']) for l in lines)-int(data['origin_ns'])
   parts.append(txt(left,y+rowh-14,f'起点 {first/1e9:.9f} s → 终点 {last/1e9:.9f} s；跨度 {(last-first)/1e6:.3f} ms'+('（过程执行时长）' if data.get('focus_id') else '（范围可能包含间隙）'),15))
 for f in data['breaks']:
  parts.append(txt(left+f*(w-left-right)-5,top-4,'//',15,color='#8654a5'))
 parts.append(txt(28,h-45,'矩形左右边界=图中成员区间的最早开始/最晚结束（按视窗裁切）；矩形内不展开成员。',15,color='#50677f'))
 parts.append(txt(28,h-21,'短于像素的区间是存在标记；放大后可读精确时长。统计结论使用全体记录，不只使用图中样例。',16,color='#50677f'));parts.append('</svg>');return ''.join(parts)
def resource_svg(data,title):
 w=1500;left=340;right=30;top=150;nmetrics=max(len(r['glyphs']) for r in data['instances']);rowh=nmetrics*47+86;h=top+rowh*len(data['instances'])+135;parts=[svg_start(w,h,title),txt(28,75,'实例原始时间对齐；条高与数值成比例。* 为重放/投影属性，不是同次 R07 观测。',19)]
 axis(parts,data,w,left,right,top,top+rowh*len(data['instances']))
 for row,r in enumerate(data['instances']):
  y=top+row*rowh;x=left+r['xf']*(w-left-right);xe=left+r['xef']*(w-left-right);parts.append(txt(25,y+27,f"#{r['rank']} {r['name']}",20,weight='bold'));parts.append(txt(25,y+54,f"堆{r['pile']} · DCU{r['device']} · {r['phase']}",18));parts.append(txt(25,y+81,f"L{r['layer']} · {r['duration_ms']:.3f} ms",18));parts.append(txt(25,y+108,r['request_short'],16,color='#50677f'))
  for j,g in enumerate(r['glyphs']):
   base=y+47+j*47;value=g['value'];height=0 if value is None else 30*value/g['cap'];parts.append(f'<path d="M{left} {base} H{w-right}" stroke="#e3eaf1"/>')
   if value is None:parts.append(txt(min(x+3,w-right-240),base-8,g['label']+'：不可用（未补零）',17,color='#6c7e90'));continue
   label=f"{g['label']} {value:.2f} {g['unit']}";parts.append(txt(min(x+3,w-right-240),base-max(height,0)-6,label,18,color='#263e57'))
   if value==0:parts.append(f'<path d="M{x} {base} H{xe}" stroke="{g["color"]}" stroke-width="1.5"/>')
   else:parts.append(f'<rect x="{x}" y="{base-height}" width="{xe-x}" height="{height}" fill="{g["color"]}"/>')
   if g.get('replay'):parts.append(f'<path d="M{x} {base} H{xe}" stroke="#765899" stroke-dasharray="5 3"/>')
  parts.append(txt(left,y+rowh-24,f"原始 Process ID: {r['id'][:77]}"+('…' if len(r['id'])>77 else ''),14,color='#667d92'));parts.append(f'<path d="M0 {y+rowh-5} H{w}" stroke="#c6d5e4"/>')
 units='；'.join(f"{g['label']} {g['cap']:.1f} {g['unit']}" for g in data['instances'][0]['glyphs']);parts.append(txt(28,h-50,'每30px高度对应：'+units,15,color='#50677f'));parts.append(txt(28,h-22,'不同测量来源不构成同一时刻的资源竞争证明；原始采样、计数和关联范围见报告。',16,color='#50677f'));parts.append('</svg>');return ''.join(parts)
def main(root,segmented=False):
 dest=root/'analysis_reports/figures';dest.mkdir(parents=True,exist_ok=True);facts=json.loads((root/'analysis_reports/data/SUMMARY.json').read_text());records=[];pairs={}
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,args=['--no-sandbox']);context=browser.new_context(viewport={'width':1500,'height':1100},device_scale_factor=1);network=[];context.route('http://**/*',lambda r:(network.append(r.request.url),r.abort()));context.route('https://**/*',lambda r:(network.append(r.request.url),r.abort()))
  tasks=[(key,label,row['segment']-1) for key,label in [('single_batch','单 batch'),('batch8','Batch8 DP2')] for row in facts[key]['time_segments'] if row['hardware_intersecting_instances']] if segmented else [(key,label,None) for key,label in [('single_batch','单 batch'),('batch8','Batch8 DP2')]]
  for key,label,section in tasks:
   stem=key if section is None else f'{key}_segment_{section+1:02}';label+=(' · 原始第'+str(section+1)+'段') if section is not None else ''
   errors=[];source=root/'revised'/key/'CONCURRENCY_UTILIZATION.html';page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(source.resolve().as_uri(),wait_until='load');page.wait_for_function('window.PAGE_READY || window.PAGE_ERROR',timeout=120000);assert not page.evaluate('window.PAGE_ERROR')
   page.evaluate('(id)=>PILES.focus(PILES.data.processes.find(p=>p.id===id))',facts[key]['examples']['resource']['id'])
   if page.evaluate('PILES.skipUncovered'):page.click('#skipUncovered')
   if page.evaluate('PILES.folded'):page.click('#foldToggle')
   if section is not None:page.evaluate('(s)=>PILES.chooseSection(s)',section)
   selection=page.evaluate("""()=>{const v=PILES,bounds=v.data.time_sections[v.sectionIndex];const candidates=v.geometry.filter(g=>g.p.b>=bounds[0]&&g.p.e<=bounds[1]).sort((a,b)=>a.p.b-b.p.b||a.p.e-b.p.e);const middle=Math.max(0,Math.floor((candidates.length-2)/2));candidates.splice(0,middle);candidates.splice(2);if(!candidates.length)throw Error('No bounded resource examples');const b=Math.min(...candidates.map(g=>g.p.b)),e=Math.max(...candidates.map(g=>g.p.e)),pad=Math.max(1,Math.floor((e-b)*.05));return {view:[Math.max(bounds[0],b-pad),Math.min(bounds[1],e+pad)],section:v.sectionIndex,ids:candidates.map(g=>g.id)};}""")
   page.evaluate('(v)=>PILES.setView(...v)',selection['view'])
   data=page.evaluate("""(ids)=>{const v=PILES,a=v.project(v.view[0]),b=v.project(v.view[1]),f=x=>(x-a)/(b-a);const candidates=v.geometry.filter(g=>ids.includes(g.id)).sort((a,b)=>a.track.rank-b.track.rank||a.p.b-b.p.b);return {view:v.view,origin_ns:v.data.origin_ns,section:v.sectionIndex,folded:v.folded,ticks:Array.from({length:6},(_,i)=>({fraction:i/5,ns:v.view[0]+(v.view[1]-v.view[0])*i/5})),instances:candidates.map(g=>({id:g.id,rank:g.track.rank,name:g.p.name,pile:g.track.pile.rank,device:g.p.device,phase:g.p.phase,layer:g.p.layer,request_short:g.p.request.replace('batch8-dual-dcu-dp2-','').slice(0,30),duration_ms:g.p.d/1e6,xf:f(g.x),xef:f(g.x+g.w),glyphs:v.glyphs(g.p)}))};}""",selection['ids'])
   data['selection_rule']='Temporal middle two fully bounded hardware-eligible instances within the original section; union of exact R07 intervals plus 5% padding per side. Shared unchanged with Process figure.'
   pairs[stem]={'trace':key,'view':data['view'],'origin_ns':data['origin_ns'],'section':data['section'],'duration_ns':data['view'][1]-data['view'][0],'absolute_begin_ns':str(int(data['origin_ns'])+data['view'][0]),'absolute_end_ns':str(int(data['origin_ns'])+data['view'][1]),'resource_ids':selection['ids'],'linear_axis':True,'same_plot_x_geometry':{'width':1500,'left':340,'right':30}}
   outputs=[('resource',data,resource_svg(data,label+' · B：同一窄窗口的资源指标'),source)]
   assert not errors;page.close()
   source=root/'revised'/key/'HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html';page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(source.resolve().as_uri(),wait_until='load');page.wait_for_function('window.PAGE_READY || window.PAGE_ERROR',timeout=120000);assert not page.evaluate('window.PAGE_ERROR')
   if page.evaluate('PILES.folded'):page.click('#foldToggle')
   page.evaluate('(s)=>{PILES.chooseSection(s.section);PILES.setView(...s.view);}',selection)
   high=page.evaluate("""()=>{const v=PILES,a=v.project(v.view[0]),b=v.project(v.view[1]),f=x=>(x-a)/(b-a);const visible=new Set(v.geometry.map(g=>g.track.rank));return {view:v.view,origin_ns:v.data.origin_ns,section:v.sectionIndex,folded:v.folded,ticks:Array.from({length:6},(_,i)=>({fraction:i/5,ns:v.view[0]+(v.view[1]-v.view[0])*i/5})),breaks:[],tracks:v.tracks.filter(t=>visible.has(t.rank)).map(t=>({rank:t.rank,name:t.g.name,pile:t.pile.rank,total_ms:t.pile.total_ns/1e6,min_ms:t.pile.min_ns/1e6,max_ms:t.pile.max_ns/1e6,member_count:t.members.length,lines:v.geometry.filter(g=>g.track.rank===t.rank).map(g=>({id:g.id,xf:f(g.x),xef:f(g.x+g.w),device:g.p.device,high:g.p.high}))}))};}""")
   assert high['view']==data['view'] and high['origin_ns']==data['origin_ns'] and high['ticks']==data['ticks'];high['selection_rule']='All visible selected Process piles in the exact resource-example window; no independent window selection.';assert set(selection['ids'])<={line['id'] for t in high['tracks'] for line in t['lines']};outputs.append(('high',high,high_svg(high,label+' · A：同一窄窗口的 Process 时间分布'),source));assert not errors;page.close()
   for mode,data,svg,source in outputs:
    name=f'{stem}_{mode}';(dest/(name+'.svg')).write_text(svg);(dest/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');p=context.new_page();p.goto((dest/(name+'.svg')).resolve().as_uri());p.locator('svg').screenshot(path=str(dest/(name+'.png')));p.close();records.append({'name':name,'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'geometry':name+'.json','SVG_sha256':hashlib.sha256(svg.encode()).hexdigest(),'PNG_sha256':hashlib.sha256((dest/(name+'.png')).read_bytes()).hexdigest(),'browser_errors':errors})
  assert not network;browser.close()
 pairfile='SEGMENT_PAIRED_WINDOWS.json' if segmented else 'PAIRED_WINDOWS.json'
 (dest/pairfile).write_text(json.dumps(pairs,ensure_ascii=False,indent=2)+'\n')
 manifest_path=dest/'FIGURE_MANIFEST.json';manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {'figures':[]}
 manifest.update(status='generated_pending_visual_review',external_requests=network)
 manifest['segmented_windows' if segmented else 'paired_windows']=pairs
 names={r['name'] for r in records};manifest['figures']=[r for r in manifest['figures'] if r['name'] not in names]+records
 manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');print('Paired narrow windows:',{k:v['duration_ns']/1e6 for k,v in pairs.items()},flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--segments',action='store_true');a=p.parse_args();main(a.root.resolve(),a.segments)
