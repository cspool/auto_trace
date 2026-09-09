#!/usr/bin/env python3
"""Independent source membership/ranking checks and offline browser interaction audit."""
from pathlib import Path
import argparse,base64,collections,gzip,hashlib,json,re
from playwright.sync_api import sync_playwright

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def audit_sources(root,key):
 folder=root/'revised'/key;g=json.loads((folder/'GROUPS.json').read_text());source=Path(g['source'][0]['path'])
 for r in g['source']:assert sha(Path(r['path']))==r['sha256']
 raw=source.read_text()
 if key=='single_batch':
  d=json.loads(re.search(r'<script[^>]*id="page-payload"[^>]*>(.*?)</script>',raw,re.S)[1]);ps=[(p['process'],p['stage'],int(p['e'])-int(p['b'])) for p in d['processes']]
 else:
  d=json.loads(raw.split('<script>const PAYLOAD=',1)[1].split(';</script>',1)[0]);pack=d['tables']['process_timeline'];ps=[]
  for block in pack['blocks']:
   for a in json.loads(gzip.decompress(base64.b64decode(block))):
    p=dict(pack['constants'],**dict(zip(pack['fields'],a)));ps.append((p['process_range_id'],p['process_id'],int(p['end_ns'])-int(p['begin_ns'])))
 by=collections.defaultdict(dict)
 for ident,name,duration in ps:by[name][ident]=duration
 total=sum(p[2] for p in ps);ranking=sorted((n for n in by if sum(by[n].values())*10>total),key=lambda n:(-sum(by[n].values()),n))
 assert [x['name'] for x in g['groups']]==ranking
 for group in g['groups']:
  expected=by[group['name']];members=[i for c in group['piles'] for i in c['members']]
  assert len(members)==len(set(members)) and set(members)==set(expected)
  assert len(group['piles'])==5 and all(c['members'] for c in group['piles'])
  assert abs(group['share']-sum(expected.values())/total)<1e-14
  for c in group['piles']:
   ds=[expected[i] for i in c['members']];assert c['min_ns']==min(ds) and c['max_ns']==max(ds);assert c['representative'] in c['members']
  assert all(a['max_ns']<=b['min_ns'] for a,b in zip(group['piles'],group['piles'][1:]))
 expected_order=sorted((dict(group=x['name'],pile_rank=c['rank'],total_ns=sum(by[x['name']][i] for i in c['members'])) for x in g['groups'] for c in x['piles']),key=lambda c:(-c['total_ns'],c['group'],c['pile_rank']))
 assert g['pile_order']==expected_order
 sections=g['time_sections'];assert len(sections)==10 and all(a[1]==b[0] for a,b in zip(sections,sections[1:])) and max(b-a for a,b in sections)-min(b-a for a,b in sections)<=1
 return dict(source_processes=len(ps),groups=len(ranking),piles=5*len(ranking),source_hashes_unchanged=True)

def main(root,trace='both'):
 result={key:audit_sources(root,key) for key in (['single_batch','batch8'] if trace=='both' else [trace])};print('SOURCE AUDIT',result,flush=True)
 validation=root/'revised'/'validation';validation.mkdir(exist_ok=True)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
  for key in result:
   result[key]['pages']={}
   for name in ['HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html','CONCURRENCY_UTILIZATION.html']:
    errors=[];network=[];context=browser.new_context(viewport={'width':1500,'height':1100},device_scale_factor=1)
    def block(route):
     if route.request.url.startswith(('http:','https:')):network.append(route.request.url);route.abort()
     else:route.continue_()
    context.route('**/*',block);page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto((root/'revised'/key/name).resolve().as_uri(),wait_until='load',timeout=120000);page.wait_for_function('window.PAGE_READY === true || window.PAGE_ERROR',timeout=120000)
    assert not page.evaluate('window.PAGE_ERROR'),page.evaluate('window.PAGE_ERROR')
    state=page.evaluate("""()=>{const v=PILES;if(MODE==='high'&&v.tracks.length!==v.data.groups.length*5||MODE==='concurrency'&&v.tracks.length>v.data.groups.length*5)throw Error('pile count');if(document.querySelector('#groupCriterion'))throw Error('old top10 selector');if(document.querySelectorAll('canvas').length!==2)throw Error('extra timelines');if(v.tracks.some((t,i)=>i&&v.tracks[i-1].pile.total_ns<t.pile.total_ns))throw Error('pile order');for(const g of v.data.groups)if(g.share<=.1)throw Error('threshold');for(const [x,want] of [[0,1],[25,1],[25.1,2],[50,2],[50.1,3],[75,3],[75.1,4],[100,4],[null,null],[-1,null],[101,null]])if(v.utilLevel(x)!==want)throw Error('util bin');return {tracks:v.tracks.length,order:v.tracks.map(t=>t.g.name+'/'+t.pile.rank),compute_known:v.data.processes.filter(p=>v.data.groups.some(g=>g.name===p.name)&&v.data.resources[p.id].compute_pct!==null).length,bandwidth_known:Object.values(v.data.resources).filter(r=>r.bandwidth_pct!==null).length};}""")
    if name.startswith('CONCURRENCY'):
     state['default_resource_windows']=page.evaluate("""()=>{const v=PILES;if(v.resourceFilter!=='hardware'||!v.skipUncovered)throw Error('wrong default');const eligible=v.data.processes.filter(p=>v.data.groups.some(g=>g.piles.some(c=>c.members.includes(p.id)))&&v.glyphs(p).some(g=>g.key!=='compute'&&g.value!==null));for(const g of v.geometry){if(!v.glyphs(g.p).some(g=>g.key!=='compute'&&g.value!==null))throw Error('unmatched instance shown');for(const x of g.glyphs)if(x.value===null&&!x.epsilon)throw Error('missing glyph rendered');}const skipped=v.segments.filter(s=>s.skipped);for(const s of skipped){if(s.weight!==0||v.project(s.b)!==v.project(s.e))throw Error('uncovered duration still has width');if(eligible.some(p=>p.b<s.e&&p.e>s.b))throw Error('covered time incorrectly omitted');}return {eligible_instances:eligible.length,visible_piles:v.tracks.length,skipped_intervals:skipped.length,skipped_duration_ns:skipped.reduce((n,s)=>n+s.e-s.b,0)};}""")
     page.click('#skipUncovered');assert page.evaluate('PILES.segments.some(s=>s.skipped)') is False
     page.click('#skipUncovered')
    page.screenshot(path=str(validation/(key+'_'+name.split('.')[0]+'_overview.png')))
    for section in range(10):
     page.select_option('#timeSection',str(section))
     page.evaluate("""()=>{const v=PILES,b=v.data.time_sections[v.sectionIndex];if(v.view[0]!==b[0]||v.view[1]!==b[1])throw Error('wrong section');for(const g of v.geometry)if(g.p.e<=b[0]||g.p.b>=b[1])throw Error('outside section');v.zoom(2);if(v.view[0]<b[0]||v.view[1]>b[1])throw Error('zoom escaped section');}""")
    page.select_option('#timeSection','0');page.click('#foldToggle')
    page.evaluate("""()=>{const v=PILES;if(v.folded)throw Error('toggle');const ratios=v.geometry.map(g=>g.actualWidth/g.p.d);if(ratios.length&&Math.max(...ratios)-Math.min(...ratios)>1e-7)throw Error('linear scale');}""")
    page.click('#foldToggle')
    page.evaluate("""()=>{const v=PILES,t=v.tracks[0],p=t.members.find(p=>MODE==='high'?v.data.resources[p.id].compute_pct!==null:v.glyphs(p).some(g=>g.key!=='compute'&&g.value!==null))||t.members[0];v.focus(p);if(!v.geometry.length)throw Error('focus');}""")
    page.screenshot(path=str(validation/(key+'_'+name.split('.')[0]+'_zoom.png')))
    resource_state=page.evaluate("""()=>({resource_rectangles:PILES.geometry.filter(g=>g.resource!==null).length,heights:[...new Set(PILES.geometry.map(g=>g.h))]})""")
    if name.startswith('CONCURRENCY'):assert resource_state['resource_rectangles']>0 and resource_state['heights']==([204] if key=='batch8' else [84])
    else:assert resource_state['resource_rectangles']==0 and resource_state['heights']==[2]
    page.evaluate("""()=>{PILES.inspect([PILES.geometry[0]]);}""");assert page.locator('#details').is_visible();page.click('#closeDetail')
    page.evaluate("""()=>{const p=PILES.tracks[0].members[0];PILES.focus(p);PILES.setView(p.b,p.b+1);if(PILES.view[1]-PILES.view[0]!==1)throw Error('1ns');if(PILES.geometry.some(g=>!Number.isFinite(g.x)||!Number.isFinite(g.w)))throw Error('nonfinite');}""")
    if key=='single_batch' and name.startswith('CONCURRENCY') and page.evaluate('!!PILES.data.l2_reference'):
     state['l2']=page.evaluate("""()=>{const v=PILES;if(v.l2Peak!==null)throw Error('invented L2 peak');let rows=0;for(const p of v.data.processes){for(const s of v.data.resources[p.id].l2_samples||[]){if(s.projected_L2_GBps!==Number(s.original_row.projected_L2_throughput_GBps_on_R07_latency_axis))throw Error('source L2 value changed');rows++;}const r=v.displayResource(p);if(r.bandwidth_pct!==null)throw Error('invented L2 utilization');}const candidates=v.tracks.flatMap(t=>t.members).filter(p=>v.displayResource(p).l2_GBps!==null);v.focus(candidates[0]);return {source_rows:rows,displayed_instances:candidates.length,default_peak:null};}""")
     page.screenshot(path=str(validation/'single_batch_L2_GBps.png'))
     options=page.locator('#l2Sample option').evaluate_all('(es)=>es.slice(1).map(e=>e.value)')
     for value in options:
      page.select_option('#l2Sample',value)
      page.evaluate("""()=>{const value=document.getElementById('l2Sample').value;const s=Object.values(PILES.data.resources).flatMap(r=>r.l2_samples||[]).find(s=>s.sample_id===value),p=PILES.data.processes.find(p=>p.id===s.process_range);if(PILES.displayResource(p).l2_sample.sample_id!==value)throw Error('sample selection');}""")
     page.fill('#l2Peak','1000');page.click('#applyL2Peak')
     page.evaluate("""()=>{for(const p of PILES.data.processes){const r=PILES.displayResource(p);if(r.l2_GBps!==null&&Math.abs(r.bandwidth_pct-r.l2_GBps/10)>1e-9)throw Error('user reference math');}}""")
     page.fill('#l2Peak','-1');page.click('#applyL2Peak');assert page.evaluate('PILES.l2Peak')==1000
     page.fill('#l2Peak','');page.click('#applyL2Peak');assert page.evaluate('PILES.l2Peak') is None
     state['l2'].update(all_visible_samples_selectable=len(options),user_reference_formula_checked=True,no_default_utilization=True)
    if key=='batch8' and name.startswith('CONCURRENCY') and page.evaluate('!!PILES.data.bandwidth_replay') and page.locator('#bandwidthDirection').count():
     state['directional_bandwidth']={}
     for direction in ['read','write']:
      page.select_option('#bandwidthDirection',direction)
      stats=page.evaluate("""()=>{const v=PILES;for(const p of v.data.processes){const profile=v.data.resources[p.id].bandwidth_profiles?.[v.bandwidthDirection],r=v.displayResource(p);if(r.bandwidth_pct!==(profile?.reference_pct??null))throw Error('directional value');if(profile?.runtime_shape_match===false&&r.bandwidth_pct!==null)throw Error('shape gate');}const candidates=v.tracks.flatMap(t=>t.members).filter(p=>v.displayResource(p).bandwidth_pct!==null);if(candidates.length){v.focus(candidates[0]);if(!v.geometry.some(g=>g.resource?.bandwidth_pct!==null))throw Error('numeric bandwidth missing');}return {eligible_displayed_instances:candidates.length,all_profiles:Object.values(v.data.resources).filter(r=>r.bandwidth_profiles?.[v.bandwidthDirection]?.reference_pct!=null).length};}""")
      state['directional_bandwidth'][direction]=stats
      page.screenshot(path=str(validation/(key+'_bandwidth_'+direction+'.png')))
    if key=='batch8' and name.startswith('CONCURRENCY') and page.evaluate('!!PILES.data.batch8_l2') and page.locator('#bandwidthDirection').count():
     state['batch8_l2']={}
     for option in ['l2_hit','l2_requests']:
      page.select_option('#bandwidthDirection',option)
      summary=page.evaluate("""()=>{const v=PILES;let n=0;for(const p of v.data.processes){const r=v.displayResource(p),a=v.data.resources[p.id].l2_activity,expected=v.bandwidthDirection==='l2_hit'?(a?.hit_rate_pct??null):(a?.requests_per_second!=null?a.requests_per_second/1e9:null);if(r.lower_metric_value!==expected||r.bandwidth_pct!==null)throw Error('L2 mislabeled or mismatched');if(expected!==null)n++;}const eligible=v.tracks.flatMap(t=>t.members).filter(p=>v.displayResource(p).lower_metric_value!==null);v.focus(eligible[0]);if(!v.geometry.some(g=>g.resource?.bandwidth_is_l2_activity&&g.resource.lower_metric_value!==null))throw Error('missing L2 geometry');return {all_available:n,selected_available:eligible.length,unit:v.displayResource(eligible[0]).lower_metric_unit};}""")
      state['batch8_l2'][option]=summary
      page.screenshot(path=str(validation/('batch8_'+option+'.png')))
    if name.startswith('CONCURRENCY') and page.locator('#resourceFilter').count():
     assert page.locator('#coverageSummary').inner_text()
     state['coverage_diagnostics']=page.evaluate("""()=>{const v=PILES,report=v.data.resource_coverage,total=v.data.groups.reduce((n,g)=>n+g.piles.reduce((s,c)=>s+c.members.length,0),0);if(total!==report.selected_instances)throw Error('coverage denominator');for(const [name,states] of Object.entries(report.metrics))if(Object.values(states).reduce((a,b)=>a+b,0)!==total)throw Error('coverage partition');if(v.data.trace==='single_batch'&&v.data.processes.some(p=>v.data.resources[p.id].compute_pct===null&&v.data.resources[p.id].compute_reason==='candidate'))throw Error('candidate mislabeled as sample reason');return report.metrics;}""")
     track_count=page.evaluate('PILES.tracks.length')
     for value in ['any','both','all']:
      page.select_option('#resourceFilter',value)
      page.evaluate("""()=>{const v=PILES;for(const g of v.geometry){const gs=v.glyphs(g.p),n=gs.filter(x=>x.value!==null).length;if(v.resourceFilter==='any'&&n===0||v.resourceFilter==='both'&&n!==gs.length)throw Error('invalid filtered instance');}}""")
      assert page.evaluate('PILES.tracks.length')<=page.evaluate('PILES.data.pile_order.length')
     page.select_option('#timeSection','0')
     page.screenshot(path=str(validation/(key+'_coverage.png')))
    if name.startswith('CONCURRENCY'):
     state['proportional_glyphs']=page.evaluate("""()=>{const v=PILES;let epsilon=0;for(const p of v.tracks.flatMap(t=>t.members)){const gs=v.glyphs(p),keys=gs.map(g=>g.key);if(v.data.trace==='batch8'&&keys.join(',')!=='compute,read,write,l2_hit,l2_requests')throw Error('missing simultaneous metric');for(const g of gs){const h=v.scaleHeight(g);if(g.value===null){if(h!==null)throw Error('invented height');if(g.epsilon){epsilon++;if(v.data.resources[p.id].compute_pct!==null)throw Error('epsilon overwrote data');}}else if(Math.abs(h-24*g.value/g.cap)>1e-10)throw Error('nonproportional height');}}return {metric_count:v.glyphs(v.tracks[0].members[0]).length,epsilon_markers:epsilon,values_kept_unknown:true};}""")
     page.evaluate("""()=>{const v=PILES,p=v.tracks.flatMap(t=>t.members).find(p=>v.glyphs(p).some(g=>g.epsilon));if(p)v.focus(p);}""")
     page.screenshot(path=str(validation/(key+'_epsilon_resources.png')))
     page.evaluate("""()=>{const v=PILES,p=v.tracks.flatMap(t=>t.members).find(p=>v.glyphs(p).filter(g=>g.value!==null).length>1);if(p)v.focus(p);}""")
     page.screenshot(path=str(validation/(key+'_simultaneous_resources.png')))
    else:
     page.select_option('#timeSection','0')
     state['trapezoids']=page.evaluate("""()=>{const v=PILES;let lines=0;for(const e of v.envelopes){const pts=e.points;if(pts.length!==4||pts[0][1]!==pts[1][1]||pts[2][1]!==pts[3][1])throw Error('not trapezoid');for(const g of v.geometry.filter(g=>g.track.rank===e.rank)){const f=(g.y+1-pts[0][1])/(pts[3][1]-pts[0][1]),left=pts[0][0]+f*(pts[3][0]-pts[0][0]),right=pts[1][0]+f*(pts[2][0]-pts[1][0]);if(g.x<left-0.01||g.x+g.w>right+0.01)throw Error('line outside envelope');lines++;}}if(lines!==v.geometry.length)throw Error('missing grouped lines');return {envelopes:v.envelopes.length,contained_lines:lines};}""")
    assert not errors,errors;assert not network,network
    state.update(browser_errors=errors,external_requests=network,ten_sections=True,linear_scale=True,exact_1ns=True,member_details=True,rendering=resource_state)
    result[key]['pages'][name]=state;print('BROWSER PASS',key,name,state,flush=True);context.close()
   pages=list(result[key]['pages'].values());assert [r for r in pages[0]['order'] if r in pages[1]['order']]==pages[1]['order']
  browser.close()
 (validation/('AUDIT.json' if trace=='both' else 'AUDIT_'+trace+'.json')).write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--trace',choices=['single_batch','batch8','both'],default='both');a=p.parse_args();main(a.root.resolve(),a.trace)
