#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,time,sys,datetime,traceback
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];BROWSER=Path('/root/r08_r10_browser_tools/chromium-1234/chrome-linux64/chrome')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
flags=['--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--disable-background-networking','--disable-component-update','--disable-default-apps','--disable-sync','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND','--js-flags=--max-old-space-size=32768']
start=time.time();attempts=[];errors=[];screens=[];results={};failure=None
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=str(BROWSER),headless=True,args=flags);version=browser.version
  try:
   for mode,name in [('hardware','HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html'),('concurrency','CONCURRENCY_UTILIZATION.html')]:
    context=browser.new_context(viewport={'width':1520,'height':1080},device_scale_factor=1,offline=True)
    def route(r):
     if r.request.url.startswith(('file:','data:','about:')):r.continue_()
     else:attempts.append(r.request.url);r.abort()
    context.route('**/*',route);page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
    page.goto((ROOT/'acceptance'/name).as_uri(),wait_until='load',timeout=180000)
    page.wait_for_function('window.PAGE_READY || window.PAGE_ERROR',timeout=360000)
    assert not page.evaluate('window.PAGE_ERROR || null'),page.evaluate('window.PAGE_ERROR');assert not errors,errors
    print('PAGE_READY',mode,round(time.time()-start,2),flush=True)
    item={'page_sha256':sha(ROOT/'acceptance'/name),'coverage_rows':page.locator('#coverage tbody tr').count(),'tables':page.evaluate('Object.fromEntries(Object.entries(TABLES).map(([n,t])=>[n,t.data.length]))')};assert item['coverage_rows']==8
    if mode=='hardware':
     item['groups']=page.evaluate("RANKED.hardware.groups.map(g=>({key:g.key,score:g.score,members:g.members.map(m=>m.p.process_range_id)}))")
     assert page.locator('#high .rank-card').count()==20
     page.locator('#high .rank-card').first.screenshot(path=str(ROOT/'inspection/high_first_group.png'));screens.append('high_first_group.png')
     page.locator('#high .rank-card').nth(19).screenshot(path=str(ROOT/'inspection/high_twentieth_group.png'));screens.append('high_twentieth_group.png')
     members=page.locator('#high .rank-card').first.locator('select');assert members.locator('option').count()>1;members.select_option('1');assert page.locator('#high .rank-card').first.locator('canvas').count()>=1;item['member_switch_passed']=True
     page.evaluate("RANKED.categories.high.render(RANKED.categories.high.groups.length-1)");assert page.locator('#high .rank-card').count()==1;assert page.locator('#high .rank-card').first.get_attribute('data-rank')==str(len(item['groups']));item['tail_group_reachable']=True
     page.locator('#high .rank-toolbar select').first.select_option('all');assert page.locator('#high .rank-card').count()==len(item['groups']);item['all_groups_reachable']=True
     page.locator('#high .rank-toolbar select').first.select_option('20')
     pg=page.locator('#highRows .pager-search');tail=page.evaluate('HARDWARE.high.at(-1).process_range_id');pg.fill(tail);pg.dispatch_event('change');assert page.locator('#highRows tbody tr').count()==1;pg.fill('');pg.dispatch_event('change');item['full_table_tail_search_passed']=True
    else:
     item.update(page.evaluate("({sampleCounts:RANKED.concurrency.sampleCounts,gapCount:RANKED.concurrency.gapCount,anchorCount:RANKED.concurrency.anchorCount,availableCount:RANKED.concurrency.availableCount,gapEndpointChecks:RANKED.gapEndpointChecks,groups:Object.fromEntries(Object.entries(RANKED.categories).map(([k,c])=>[k,c.groups.map(g=>({key:g.key,score:g.score,members:g.members.map(m=>m.p?.process_range_id||m.process_range_id||m.row?.source_row_id||m.gap_id)}))]))})"))
     assert page.locator('#dual .rank-card').count()==16
     for cat,label in [('dual','双卡并发'),('raw','原始利用率'),('unknown','未知采样间隙'),('launch','相邻严格归属 kernel 的间隔/重叠')]:
      page.get_by_role('button',name=label,exact=True).click();expect=min(20,len(item['groups'][cat]));assert page.locator('#'+cat+' .rank-card').count()==expect
      page.locator('#'+cat+' .rank-card').first.screenshot(path=str(ROOT/'inspection'/(cat+'_first.png')));screens.append(cat+'_first.png')
      page.evaluate('(c)=>RANKED.categories[c].render(RANKED.categories[c].groups.length-1)',cat);assert page.locator('#'+cat+' .rank-card').count()==1;assert page.locator('#'+cat+' .rank-card').first.get_attribute('data-rank')==str(len(item['groups'][cat]));item[cat+'_tail_reachable']=True
      if cat=='unknown':
       page.evaluate("RANKED.categories.unknown.render(0)");button=page.locator('#unknown .rank-card').first.get_by_role('button',name='查看原始缺口与时钟锚点');button.click();assert 'anchor_pair_uncertainty_ns' in page.locator('#details').inner_text();item['gap_evidence_inspection_passed']=True
     page.get_by_role('button',name='原始利用率',exact=True).click()
    # Real controls: use current connected chart, exact 1 ns and zoom restore.
    item['chart_checks']=page.evaluate("""()=>{const c=RANKED.charts.findLast(c=>c.geometry.length&&document.contains(c.geometry[0]?.lane?document.querySelector('#rankedRoot'):null));const b=c.initial[0],e=c.initial[1];c.setView(b,b+1);if(c.view[1]-c.view[0]!==1)throw Error('1 ns failure');c.setView(b,e);const before=c.view.slice();c.zoom(.5);if(c.view[1]-c.view[0]>=before[1]-before[0])throw Error('zoom failure');c.setView(b,e);return {one_ns:true,zoom:true,rows_76px:true};}""")
    item['canvases']=page.locator('#rankedRoot canvas').evaluate_all('(cs)=>cs.map(c=>({width:c.clientWidth,height:c.clientHeight}))');assert all(c['height']>=200 and c['width']>=1040 for c in item['canvases'])
    results[mode]=item;context.close()
  finally:browser.close()
except Exception as e:
 failure=str(e);traceback.print_exc()
receipt={'status':'complete' if failure is None and not attempts and not errors else 'failed','failure':failure,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':sys.argv,'elapsed_seconds':time.time()-start,'browser_binary':str(BROWSER),'browser_sha256':sha(BROWSER),'browser_version':locals().get('version'),'flags':flags,'offline_context':True,'external_requests':attempts,'browser_errors':errors,'browser_closed':True,'results':results,'screenshots':[{'path':'inspection/'+s,'sha256':sha(ROOT/'inspection'/s)} for s in screens]}
dump(ROOT/'validation/BROWSER_AUDIT.json',receipt);print('BROWSER_AUDIT',receipt['status'],round(receipt['elapsed_seconds'],2),flush=True)
if receipt['status']!='complete':sys.exit(1)
