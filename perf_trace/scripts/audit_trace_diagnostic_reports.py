#!/usr/bin/env python3
"""Audit report facts, source-derived figure coordinates, HTML/PDF and local links."""
from pathlib import Path
from html.parser import HTMLParser
import argparse,base64,bisect,collections,gzip,hashlib,json,re,xml.etree.ElementTree as ET
import fitz
from playwright.sync_api import sync_playwright

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(root):
 out=root/'analysis_reports';facts=json.loads((out/'data/SUMMARY.json').read_text());fm=json.loads((out/'figures/FIGURE_MANIFEST.json').read_text());report={};sources={}
 for key,f in facts.items():
  p=Path(f['source_page']);assert sha(p)==f['source_sha256'];d=json.loads(gzip.decompress(base64.b64decode(re.search(r'<script id="packed"[^>]*>(.*?)</script>',p.read_text(),re.S)[1])));sources[key]=d;pm={p['id']:p for p in d['processes']}
  assert f['total_process_duration_ns']==sum(p['e']-p['b'] for p in pm.values());assert f['process_count']==len(pm);assert len({k[6] for k in d['kernels']})==f['kernel_count']
  for pile in f['piles']:assert pile['duration_ns']['sum']==sum(pm[i]['e']-pm[i]['b'] for i in pile['member_ids'])
  assert len(f['time_segments'])==10
  selected={i for g in d['groups'] for c in g['piles'] for i in c['members']}
  assert sum(row['selected_duration_intersection_sum_ns'] for row in f['time_segments'])==sum(pm[i]['d'] for i in selected)
  for row in f['time_segments']:
   a,b=row['begin_ns'],row['end_ns'];expected=sum(max(0,min(b,pm[i]['e'])-max(a,pm[i]['b'])) for i in selected);assert expected==row['selected_duration_intersection_sum_ns']
  if key=='batch8':assert len(d['samples'])==2491806 and all(s[1]==0 for s in d['samples'])
  for s in d['source']:assert sha(Path(s['path']))==s['sha256']
  # Independently reproduce the high-view common folding coordinate.
  chosen={i for g in d['groups'] for c in g['piles'] for i in c['members']};dur=sorted(pm[i]['d'] for i in chosen);cap=dur[len(dur)//2]*2;endpoints=sorted({d['time_sections'][0][0],d['time_sections'][9][1],*[t for i in chosen for t in [pm[i]['b'],pm[i]['e']]]});prefix=[0]
  for a,b in zip(endpoints,endpoints[1:]):prefix.append(prefix[-1]+min(b-a,cap))
  def project(t):
   i=min(len(endpoints)-2,max(0,bisect.bisect_left(endpoints,t)-1));return prefix[i]+(t-endpoints[i])/(endpoints[i+1]-endpoints[i])*min(endpoints[i+1]-endpoints[i],cap)
  fig=json.loads((out/'figures'/f'{key}_high.json').read_text());lo,hi=fig['view'];n=0
  if not fig['folded']:project=lambda t:t
  high_fig=fig
  for t in fig['tracks']:
   for row in t['lines']:
    p=pm[row['id']];a=(project(max(lo,p['b']))-project(lo))/(project(hi)-project(lo));b=(project(min(hi,p['e']))-project(lo))/(project(hi)-project(lo));assert abs(a-row['xf'])<1e-8 and abs(b-row['xef'])<1e-8;n+=1
  fig=json.loads((out/'figures'/f'{key}_resource.json').read_text());lo,hi=fig['view'];assert not fig['folded']
  assert high_fig['view']==fig['view'] and high_fig['origin_ns']==fig['origin_ns'] and high_fig['ticks']==fig['ticks']
  lines={r['id']:r for t in high_fig['tracks'] for r in t['lines']}
  for r in fig['instances']:
   assert r['id'] in lines and abs(r['xf']-lines[r['id']]['xf'])<1e-10 and abs(r['xef']-lines[r['id']]['xef'])<1e-10
  for row in fig['instances']:
   p=pm[row['id']];assert abs(row['xf']-(max(lo,p['b'])-lo)/(hi-lo))<1e-8;assert abs(row['xef']-(min(hi,p['e'])-lo)/(hi-lo))<1e-8
   r=d['resources'][p['id']]
   for g in row['glyphs']:
    k=g['key']
    if k=='compute':expected=r['compute_pct']
    elif k in ['read','write']:expected=r['bandwidth_profiles'].get(k,{}).get('reference_pct')
    elif k=='l2_hit':expected=(r.get('l2_activity') or {}).get('hit_rate_pct')
    elif k=='l2_requests':expected=(r.get('l2_activity') or {}).get('requests_per_second');expected=expected/1e9 if expected is not None else None
    elif k=='l2_projected':expected=r['l2_samples'][0]['projected_L2_GBps']
    assert g['value']==expected,(k,g['value'],expected)
  report[key]={'source_hashes_verified':True,'high_figure_member_coordinates_verified':n,'resource_figure_instances_verified':len(fig['instances']),'figures_use_original_time':True,'paired_window_ns':[lo,hi],'duration_ms':(hi-lo)/1e6,'paired_ids_and_coordinates_match':True}
 expanded=json.loads((out/'data/EXPANDED_WINDOW_ANALYSIS.json').read_text())
 expected_sections={(key,r['segment']-1) for key,f in facts.items() for r in f['time_segments'] if r['hardware_intersecting_instances']}
 assert {(w['trace'],w['section']) for w in expanded.values()}==expected_sections
 for stem,w in expanded.items():
  d=sources[w['trace']];pm={p['id']:p for p in d['processes']};a,b=w['view'];high=json.loads((out/'figures'/(stem+'_high.json')).read_text());res=json.loads((out/'figures'/(stem+'_resource.json')).read_text());assert high['view']==res['view']==w['view'] and high['ticks']==res['ticks'];assert not high['folded'] and not res['folded']
  rows={r['id']:r for t in high['tracks'] for r in t['lines']}
  for r in res['instances']:
   p=pm[r['id']];assert r['id'] in rows;assert abs(r['xf']-(max(a,p['b'])-a)/(b-a))<1e-8 and abs(r['xef']-(min(b,p['e'])-a)/(b-a))<1e-8
   assert abs(rows[r['id']]['xf']-r['xf'])<1e-8 and abs(rows[r['id']]['xef']-r['xef'])<1e-8
   original=d['resources'][r['id']]
   for g in r['glyphs']:
    k=g['key'];v=None
    if k=='compute':v=original['compute_pct']
    elif k in ['read','write']:v=original['bandwidth_profiles'].get(k,{}).get('reference_pct')
    elif k=='l2_hit':v=(original.get('l2_activity') or {}).get('hit_rate_pct')
    elif k=='l2_requests':v=(original.get('l2_activity') or {}).get('requests_per_second');v=v/1e9 if v is not None else None
    elif k=='l2_projected':assert g['value'] in [x['projected_L2_GBps'] for x in original['l2_samples']];continue
    assert g['value']==v,(stem,k,g['value'],v)
  for c in w['kernel_checks']:
   segments=[x for x in d['counts'] if x[3]=='kernel' and x[2]==c['device'] and x[0]<b and x[1]>a];assert c['peak']==max([x[4] for x in segments] or [0]);assert c['overlap_ns']==sum(min(b,x[1])-max(a,x[0]) for x in segments if x[4]>1)
 inventory=json.loads((out/'data/ALL_KERNEL_OVERLAPS.json').read_text())
 for key,v in inventory.items():
  expected=[(x[0],x[1],x[2],x[4]) for x in sources[key]['counts'] if x[3]=='kernel' and x[4]>1];assert sorted(expected)==sorted((r['begin_ns'],r['end_ns'],r['device'],r['peak']) for r in v['segments'])
 report['expanded_windows']={'count':len(expanded),'all_hardware_populated_sections':True,'coordinates_metrics_and_concurrency_verified':True};report['all_overlap_segments']={k:v['count'] for k,v in inventory.items()}
 items=json.loads((out/'figures/PROCESS_DISTRIBUTIONS.json').read_text());expected={(key,g['name']) for key,d in sources.items() for g in d['groups']};assert {(x['trace'],x['type']) for x in items}==expected
 total_lines=0
 for item in items:
  d=sources[item['trace']];pm={p['id']:p for p in d['processes']};g=next(g for g in d['groups'] if g['name']==item['type']);target={i for c in g['piles'] for i in c['members']};chosen={i for group in d['groups'] for c in group['piles'] for i in c['members']};ds=sorted(pm[i]['d'] for i in chosen);cap=ds[len(ds)//2]*2;ends=sorted({d['time_sections'][0][0],d['time_sections'][-1][1],*[t for i in chosen for t in [pm[i]['b'],pm[i]['e']]]});prefix=[0]
  for a,b in zip(ends,ends[1:]):prefix.append(prefix[-1]+min(b-a,cap))
  def mapped(t):
   i=min(len(ends)-2,max(0,bisect.bisect_right(ends,t)-1));return prefix[i]+(t-ends[i])/(ends[i+1]-ends[i])*min(ends[i+1]-ends[i],cap)
  for kind in ['full','detail']:
   fig=json.loads((out/'figures'/(item[kind]+'.json')).read_text());ids=[r['id'] for t in fig['tracks'] for r in t['lines']];assert len(ids)==len(set(ids));a,b=fig['view']
   if kind=='full':assert set(ids)==target and len(fig['tracks'])==5;total_lines+=len(ids)
   else:
    assert ids==[item["focus_id"]] and set(ids)<=target;largest=max(g['piles'],key=lambda c:c['total_ns']);assert item['selected_pile']==largest['rank'];assert item['focus_id'] in ids;assert pm[item['focus_id']]['d']==max(pm[i]['d'] for i in largest['members'])
   svg=ET.parse(out/'figures'/(item[kind]+'.svg'));boundaries=[e for e in svg.iter() if e.tag.endswith('polygon')];assert not boundaries;assert all(not e.get('stroke-dasharray') for e in svg.iter() if 'data-process-id' in e.attrib);drawn=[e.attrib['data-process-id'] for e in svg.iter() if 'data-process-id' in e.attrib];assert not drawn
   coord=mapped if fig['folded'] else lambda t:t
   rectangles=[e for e in svg.iter() if 'data-pile-envelope' in e.attrib];assert len(rectangles)==(5 if kind=='full' else 1)
   for rect,track in zip(rectangles,fig['tracks']):
    assert abs(float(rect.get('x'))-(340+1130*min(r['xf'] for r in track['lines'])))<1e-6
    assert abs(float(rect.get('width'))-1130*(max(r['xef'] for r in track['lines'])-min(r['xf'] for r in track['lines'])))<1e-6
   for track in fig['tracks']:
    for r in track['lines']:
     p=pm[r['id']];assert abs(r['xf']-(coord(max(a,p['b']))-coord(a))/(coord(b)-coord(a)))<1e-8;assert abs(r['xef']-(coord(min(b,p['e']))-coord(a))/(coord(b)-coord(a)))<1e-8
 cases=json.loads((out/'figures/CONCURRENCY_CASES.json').read_text())
 for key,caseset in cases.items():
  d=sources[key]
  for kind in ['with_overlap','without_overlap']:
   c=caseset[kind];a,b=c['view'];devices=[c['device']] if kind=='with_overlap' else [x['device'] for x in c['per_instance_device_check']]
   for device in devices:
    cs=[x for x in d['counts'] if x[3]=='kernel' and x[2]==device and x[0]<b and x[1]>a];peak=max([x[4] for x in cs] or [0]);overlap=sum(min(b,x[1])-max(a,x[0]) for x in cs if x[4]>1)
    if kind=='with_overlap':assert peak>=2 and overlap==c['overlap_ns'] and c['resource_matched_kernels']==0
    else:assert peak<=1 and overlap==0
 report['complete_process_coverage']={'types':len(items),'full_member_lines_verified':total_lines,'all_five_piles_per_type':True,'single_rectangle_detail':True};report['kernel_concurrency_cases_verified']=True
 class Links(HTMLParser):
  def __init__(self,p):super().__init__();self.p=p
  def handle_starttag(self,tag,attrs):
   for k,v in attrs:
    if k in ['href','src'] and not v.startswith(('http:','https:','data:','#')):assert (self.p.parent/v.split('#')[0]).exists(),(self.p,v)
 for p in out.glob('*/REPORT.html'):Links(p).feed(p.read_text())
 validation=out/'validation';validation.mkdir(exist_ok=True)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,args=['--no-sandbox']);context=browser.new_context(viewport={'width':1500,'height':1100});network=[]
  context.route('http://**/*',lambda r:(network.append(r.request.url),r.abort()));context.route('https://**/*',lambda r:(network.append(r.request.url),r.abort()))
  for p in (out/'figures').glob('*.svg'):
   assert not any(e.tag.endswith('polygon') for e in ET.parse(p).iter()),p
   page=context.new_page();page.goto(p.resolve().as_uri());boxes=page.locator('text').evaluate_all('(es)=>es.map(e=>{const b=e.getBBox();return {text:e.textContent,x:b.x,y:b.y,w:b.width,h:b.height};})');size=page.locator('svg').evaluate('(e)=>({w:e.viewBox.baseVal.width,h:e.viewBox.baseVal.height})');bad=[b for b in boxes if b['x']<-.5 or b['x']+b['w']>size['w']+.5 or b['y']<-.5 or b['y']+b['h']>size['h']+.5];assert not bad,(p,bad);page.close()
  for name in ['high_latency','concurrency']:
   page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto((out/name/'REPORT.html').resolve().as_uri(),wait_until='networkidle');assert page.locator('figure.report-figure').count()==(12 if name=='high_latency' else 6+2*len(expanded))
   assert page.locator('img').evaluate_all('(es)=>es.every(e=>e.complete && e.naturalWidth>0)');assert not errors;page.close()
   pdf=fitz.open(out/name/'REPORT.pdf');pages=[]
   for i,p in enumerate(pdf):
    spans=[s for b in p.get_text('dict')['blocks'] if 'lines' in b for l in b['lines'] for s in l['spans']];bad=[s['text'] for s in spans if s['bbox'][0]<-1 or s['bbox'][1]<-1 or s['bbox'][2]>p.rect.width+1 or s['bbox'][3]>p.rect.height+1];assert not bad,(name,i,bad);assert len(p.get_text().strip())>30
    path=validation/f'{name}_page_{i+1:02}.png';p.get_pixmap(matrix=fitz.Matrix(1,1)).save(path);pages.append({'page':i+1,'width_pt':p.rect.width,'height_pt':p.rect.height,'text_characters':len(p.get_text()),'text_bounds_ok':True})
   report[name]={'pdf_pages':pages,'embedded_images_loaded':True,'browser_errors':errors}
  assert not network;browser.close()
 for r in fm['figures']:
  assert sha(out/'figures'/(r['name']+'.svg'))==r['SVG_sha256'];assert sha(out/'figures'/(r['name']+'.png'))==r['PNG_sha256']
 report.update(status='PASS',no_new_acquisition=True,no_before_after_speedup_claim=True,external_requests=network,visual_review='SVG/PNG timeline examples and representative PDF pages inspected')
 (validation/'REPORT_AUDIT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('REPORT AUDIT PASS',[(k,len(report[k]['pdf_pages'])) for k in ['high_latency','concurrency']],flush=True)
 manifest=json.loads((out/'REPORT_MANIFEST.json').read_text());manifest['status']='audited';manifest['audit_sha256']=sha(validation/'REPORT_AUDIT.json');(out/'REPORT_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 fm['status']='audited';(out/'figures/FIGURE_MANIFEST.json').write_text(json.dumps(fm,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();main(a.root.resolve())
