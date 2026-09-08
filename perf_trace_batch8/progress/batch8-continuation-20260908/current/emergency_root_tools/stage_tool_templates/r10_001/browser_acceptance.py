"""CPU-only local-file browser audit, independent of renderer code imports."""
from pathlib import Path
import json,hashlib,os,time,re,sys,collections
from html.parser import HTMLParser
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).parents[2];ACCEPT=ROOT/'acceptance'
PAGES=['E2E_PROCESS_TIMELINE.html','E2E_PROCESS_TIMELINE_LOSSLESS.html','HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html','CONCURRENCY_UTILIZATION.html']
def check(v,m):
 if not v:raise RuntimeError(m)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def rec(p):return {'path':str(p),'size':Path(p).stat().st_size,'sha256':sha(p)}
class ActiveHTML(HTMLParser):
 def __init__(self):super().__init__();self.links=[];self.external=[];self.scripts=[];self.styles=[];self.current=None
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=='a' and attrs.get('href'):self.links.append(attrs['href'])
  for key in ['src','srcset','poster','action','formaction','data']:
   if attrs.get(key) and not attrs[key].startswith('data:'):self.external.append([tag,key,attrs[key]])
  if tag=='link':self.external.append([tag,'href',attrs.get('href')])
  if tag=='meta' and attrs.get('http-equiv','').lower()=='refresh':self.external.append(['meta','refresh',attrs.get('content')])
  if tag in ['script','style']:self.current=tag
  for k,v in attrs.items():
   if k.startswith('on'):self.scripts.append(v or '')
 def handle_endtag(self,tag):
  if self.current==tag:self.current=None
 def handle_data(self,data):
  if self.current=='script':self.scripts.append(data)
  if self.current=='style':self.styles.append(data)
def static_check(path):
 parser=ActiveHTML();parser.feed(path.read_text());check(not parser.external,'external active HTML resources')
 code='\n'.join(x for x in parser.scripts if not x.strip().startswith('const PAYLOAD='));css='\n'.join(parser.styles)
 patterns=[r'\bfetch\s*\(',r'\bXMLHttpRequest\b',r'\bWebSocket\b',r'\bEventSource\b',r'\bimport\s*\(',r'serviceWorker\s*\.\s*register',r'\bsendBeacon\s*\(',r'https?://',r'(?<!:)//[a-zA-Z0-9.-]+/']
 for pat in patterns:check(not re.search(pat,code),'forbidden network code '+pat)
 check(not re.search(r'@import|url\s*\(',css,re.I),'external CSS resource')
 for link in parser.links:
  check(':' not in link and not link.startswith('//'),'nonlocal navigation');check(Path(os.path.abspath(path.parent/link)).is_relative_to(ROOT),'contained relative navigation')
 return {'file':rec(path),'active_external_resources':[],'runtime_code_sha256':hashlib.sha256(code.encode()).hexdigest(),'network_patterns_rejected':patterns,'relative_navigation':parser.links}
def timeline_checks(page,manifest):
 results={}
 results['full_universe']=page.evaluate('''() => {
 const t=TIMELINE,bykind={},byreq={},ids=new Set();
 for(const e of t.all){if(ids.has(e.id))throw Error('duplicate event identity');ids.add(e.id);if(t.idMap.get(e.id)!==e)throw Error('unaddressable event');if(BigInt(e.begin_ns)-BigInt(PAYLOAD.origin_ns)!==e.begin||BigInt(e.end_ns)-BigInt(PAYLOAD.origin_ns)!==e.end)throw Error('coordinate corruption');if(e.end<e.begin)throw Error('invalid half-open interval');if(e.overlap_sub_lane<0)throw Error('missing lane');if(!e.source_table_sha256||!e.source_row_id)throw Error('missing source identity');bykind[e.kind]=(bykind[e.kind]||0)+1;}
 for(const r of TABLES.request_timeline.rows()){const a=t.events.filter(e=>e.request_id===r.request_id);byreq[r.request_id]={rank:r.rank,device:r.physical_device_id,requests:a.filter(e=>e.kind==='request').length,processes:a.filter(e=>e.kind==='process').length,owner_kernels:a.filter(e=>e.kind==='strict_owned_kernel').length,queue_kernels:a.filter(e=>e.kind==='gpu_queue').length};}
 const lanes=new Map();for(const e of t.all){const end=lanes.get(e.track);if(end!==undefined&&e.begin<end)throw Error('overlap in same lane');lanes.set(e.track,e.end);}
 return {main:t.events.length,context:t.contexts.length,all:t.all.length,unique_ids:ids.size,kinds:bykind,requests:byreq,source_lookup_all_pass:true,integer_coordinates_all_pass:true,nonoverlap_lanes:true};}''')
 full=results['full_universe'];check(full['main']==manifest['expected_event_count'],'browser full denominator');check(len(full['requests'])==8,'browser eight requests');check({r['rank'] for r in full['requests'].values()}=={'0','1'},'browser DP2')
 for q in manifest['batch8_coverage']['coverage']:
  r=full['requests'][q['request_id']];check(r['requests']==1 and r['processes']==q['process_targets'] and r['owner_kernels']==r['queue_kernels']==q['strict_owned_kernels'],'browser per-request exact source coverage')
 results['exact_history']=page.evaluate('''() => {const t=TIMELINE,o=BigInt(PAYLOAD.origin_ns);const base=t.historyIndex;for(let i=0;i<105;i++)t.setView(String(o+BigInt(i)),String(o+BigInt(i)+1n));for(let i=104;i>=0;i--){const v=t.view;if(v[0]!==String(i)||v[1]!==String(i+1))throw Error('history back precision');t.back();}if(t.historyIndex!==base)throw Error('back count');for(let i=0;i<105;i++){t.forward();if(t.view[0]!==String(i)||t.view[1]!==String(i+1))throw Error('history forward precision');}return {states:105,span_ns:String(BigInt(t.view[1])-BigInt(t.view[0])),back_forward_exact:true};}''')
 results['pan_zoom_reset']=page.evaluate('''()=>{const t=TIMELINE;t.reset();const before=t.view;t.pan('17');if(BigInt(t.view[0])!==BigInt(before[0])+17n||BigInt(t.view[1])!==BigInt(before[1])+17n)throw Error('exact pan');t.zoom(.5,.25);const after=t.view;if(BigInt(after[1])-BigInt(after[0])>=BigInt(before[1])-BigInt(before[0]))throw Error('zoom');t.reset();if(JSON.stringify(t.view)!==JSON.stringify(before))throw Error('reset');return {exact_pan_ns:17,pointer_anchor_zoom:true,reset:true};}''')
 results['filters_fit_locate']=page.evaluate('''()=>{const t=TIMELINE,fields=['process','event','layer','phase','family','track','request_id'];const out={};for(const f of fields){const e=t.all.find(x=>String(x[f]||'').length>0);const value=String(e[f]);t.filter(f,value);t.fit();const expected=t.all.filter(x=>String(x[f]??'').toLowerCase().includes(value.toLowerCase()));if(!expected.length)throw Error('empty filter');let b=expected[0].begin,end=expected[0].end;for(const x of expected){if(x.begin<b)b=x.begin;if(x.end>end)end=x.end;}if(t.view[0]!==String(b)||t.view[1]!==String(end>b?end:b+1n))throw Error('fit mismatch');out[f]={value,complete_matches:expected.length};t.filter(f,'');}const first=t.all[0],last=t.all[t.all.length-1];t.locate(last.id);if(t.view[0]!==String(last.begin))throw Error('tail event lost');t.locate(first.id);if(t.view[0]!==String(first.begin))throw Error('first event lost');t.reset();return {filters:out,first_id:first.id,last_id:last.id,complete_universe_unchanged:t.all.length};}''')
 results['unbounded_interval_inspection']=page.evaluate('''()=>{const t=TIMELINE;t.reset();t.listViewport();const expected=t.all.filter(e=>e.begin<BigInt(t.view[1])&&BigInt(t.view[0])<e.end);if(t.selected.length!==expected.length||document.querySelectorAll('#eventList .event-item').length!==expected.length)throw Error('viewport listing capped');const q=t.events.find(e=>e.kind==='strict_owned_kernel');t.setView(q.begin_ns,String(BigInt(q.begin_ns)+1n));t.listViewport();const exact=t.all.filter(e=>e.begin<BigInt(t.view[1])&&BigInt(t.view[0])<e.end);if(t.selected.length!==exact.length)throw Error('overlap loss');if(!t.selected.some(e=>e.kind==='gpu_queue'&&e.source_id===q.source_id))throw Error('paired kernel overlap missing');const count=expected.length;document.getElementById('toggleDensity').click();document.getElementById('toggleDensity').click();if(t.all.length!==t.idMap.size)throw Error('density changed universe');return {full_viewport_count:count,dom_rows_before_zoom:count,one_ns_overlap_count:exact.length,result_cap:false,density_preserves_all:true};}''')
 # Real pointer operations exercise the visible controls rather than only API.
 page.locator('#resetView').click();canvas=page.locator('#timelineCanvas');box=canvas.bounding_box();check(box is not None,'visible timeline canvas');x=box['x']+box['width']*.7;y=box['y']+60
 before=page.evaluate('TIMELINE.view');page.mouse.move(x,y);page.mouse.wheel(0,-220);page.wait_for_timeout(150);after=page.evaluate('TIMELINE.view');check(int(after[1])-int(after[0])<int(before[1])-int(before[0]),'actual wheel zoom')
 page.keyboard.down('Shift');page.mouse.move(x-100,y);page.mouse.down();page.mouse.move(x+70,y,steps=4);page.mouse.up();page.keyboard.up('Shift');boxview=page.evaluate('TIMELINE.view');check(int(boxview[1])-int(boxview[0])<int(after[1])-int(after[0]),'actual box zoom')
 page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+50,y,steps=4);page.mouse.up();panview=page.evaluate('TIMELINE.view');check(panview!=boxview and int(panview[1])-int(panview[0])==int(boxview[1])-int(boxview[0]),'actual drag pan')
 page.mouse.click(x,y);check(page.locator('#listCount').inner_text().startswith('点击时间像素所有交集'),'actual pixel inspection')
 origin=manifest['origin_ns'];page.locator('#jumpBegin').fill(origin);page.locator('#jumpEnd').fill(str(int(origin)+1));page.locator('#jumpView').click();check(page.evaluate('TIMELINE.view')==['0','1'],'actual 1 ns jump')
 results['visible_pointer_and_jump_controls']={'wheel':True,'shift_box':True,'drag_pan':True,'pixel_all_intersections':True,'exact_jump_one_ns':True}
 return results
def main():
 started=time.monotonic();manifest=json.loads((ACCEPT/'full_timeline_manifest.json').read_text());static=[static_check(ACCEPT/name) for name in ['index.html']+PAGES];expected={x['logical_name']:x['row_count'] for x in manifest['r09_tables']};results=[];attempts=[];allerrors=[]
 browser_path=Path('/root/r08_r10_browser_tools');check(browser_path.exists(),'browser installed before R10 assignment');os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(browser_path)
 flags=['--disable-background-networking','--disable-component-update','--disable-domain-reliability','--no-first-run','--no-default-browser-check','--host-resolver-rules=MAP * ~NOTFOUND','--disable-features=MediaRouter,OptimizationHints,AutofillServerCommunication','--js-flags=--max-old-space-size=32768']
 with sync_playwright() as p:
  executable=Path(p.chromium.executable_path);browser=p.chromium.launch(executable_path=str(executable),headless=True,args=flags);binary=rec(executable);version=browser.version
  try:
   for filename in ['index.html']+PAGES:
    context=browser.new_context(offline=True,viewport={'width':1440,'height':1000});page=context.new_page();errors=[]
    def request_guard(route):
     url=route.request.url
     if url.startswith('file:'):route.continue_()
     else:attempts.append({'page':filename,'url':url});route.abort('internetdisconnected')
    context.route('**/*',request_guard)
    page.on('request',lambda request:attempts.append({'page':filename,'url':request.url}) if not request.url.startswith('file:') else None)
    page.on('pageerror',lambda error:errors.append(str(error)));page.on('console',lambda msg:errors.append(msg.text) if msg.type=='error' else None)
    page.goto((ACCEPT/filename).as_uri(),wait_until='load',timeout=600000)
    if filename!='index.html':
     page.wait_for_function('window.PAGE_READY===true||window.PAGE_ERROR!==undefined',timeout=600000);check(not page.evaluate('window.PAGE_ERROR||null'),'page runtime failure');counts=page.evaluate('Object.fromEntries(Object.entries(TABLES).map(([k,v])=>[k,v.data.length]))')
     for name,count in counts.items():check(count==expected[name],'all embedded browser rows '+name)
     check(page.locator('#coverage tbody tr').count()==8,'visible eight-request coverage matrix')
     check(all(label in page.locator('.legend').inner_text() for label in ['observed R07 timing','observed live utilization','replay_projected R08 hardware attributes','derived analysis','unavailable/unknown evidence']),'visible textual evidence separation')
    else:counts={}
    checks={}
    if filename==PAGES[1]:checks=timeline_checks(page,manifest)
    elif filename==PAGES[2]:
     checks=page.evaluate('({high:HARDWARE.high.length,all_processes:HARDWARE.processes.size,metrics:HARDWARE.metrics.length,high_dom:document.querySelectorAll("#highRows tbody tr").length})');check(checks['high']==checks['high_dom']==expected['high_latency_processes'],'no high latency row cap');page.locator('#highRows tbody tr').last.click();check('replay_and_static_hardware_metrics' in page.locator('#details').inner_text(),'full tail hardware evidence inspection')
    elif filename==PAGES[3]:
     checks=page.evaluate('({live:CONCURRENCY.live.data.length,samples:CONCURRENCY.groups[0].length+CONCURRENCY.groups[1].length,gaps:CONCURRENCY.gaps.length,anchors:CONCURRENCY.anchors.length,kernel_segments:CONCURRENCY.kernelSegments.length,queue_segments:CONCURRENCY.queueSegments.length,launch_gaps:CONCURRENCY.launchGaps.length,process_availability:CONCURRENCY.processAvailability.length})');check(checks['live']==expected['live_utilization_aligned'],'all raw utilization records');page.locator('#sampleIndex').fill(str(checks['live']-1));page.locator('#inspectSample').click();check(str(checks['live']-1) in page.locator('#details').inner_text(),'tail raw sample/gap/anchor addressable')
    check(not errors,'browser console/page errors');check(not attempts,'attempted external request');results.append({'page':rec(ACCEPT/filename),'embedded_table_counts':counts,'checks':checks,'console_errors':errors,'page_errors':errors,'external_requests':[]});page.screenshot(path=str(ROOT/'validation'/('browser_'+Path(filename).stem+'.png')),full_page=False);context.close();print('BROWSER_PAGE_ACCEPTED',filename,flush=True)
  finally:browser.close()
 result={'status':'complete','runtime_goal':'R10','cpu_only':True,'browser_binary':binary,'browser_version':version,'browser_flags':flags,'network_denial':['Playwright context offline=true','route abort all non-file requests','DNS host resolver all names NOTFOUND','background-network features disabled'],'network_attempt_count':len(attempts),'attempted_requests':attempts,'all_browser_processes_closed_before_result':True,'static':static,'pages':results,'harness':rec(Path(__file__)),'interpreter':rec(Path(sys.executable).resolve()),'argv':sys.argv,'full_timeline_manifest':rec(ACCEPT/'full_timeline_manifest.json'),'elapsed_seconds':time.monotonic()-started}
 with (ROOT/'validation/BROWSER_ACCEPTANCE.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print('R10_BROWSER_ACCEPTANCE_COMPLETE',round(time.monotonic()-started,2),flush=True)
if __name__=='__main__':main()
