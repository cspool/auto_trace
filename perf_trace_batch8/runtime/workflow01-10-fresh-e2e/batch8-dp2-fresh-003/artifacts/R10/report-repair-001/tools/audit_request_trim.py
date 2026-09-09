#!/usr/bin/env python3
from pathlib import Path
import csv,json,hashlib,time,sys
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];R09=ROOT.parent.parent/'R09/continuation_001';BROWSER='/root/r08_r10_browser_tools/chromium-1234/chrome-linux64/chrome';csv.field_size_limit(2**31-1)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def rows(n):
 with (R09/'tables'/(n+'.csv')).open() as f:return list(csv.DictReader(f))
start=time.time();scope=json.loads((ROOT/'REQUEST_VIEW_SCOPE.json').read_text());build=json.loads((ROOT/'validation/REQUEST_TRIM_BUILD.json').read_text())
for source in scope['sources']:assert sha(Path(source['path']))==source['sha256']
q=rows('request_timeline');p=rows('process_timeline');k=rows('kernel_timeline');ends={r['request_id']:[] for r in q}
for r in p:
 ends[r['request_id']].append(int(r['end_ns']))
 for rr in json.loads(r['layer_forward_context']).values():ends[r['request_id']].extend(int(x['end_ns']) for x in rr)
 schema=json.loads(r['hip_runtime_context_schema']);position=schema.index('end_ns');ends[r['request_id']].extend(int(x[position]) for x in json.loads(r['hip_runtime_context']))
for r in k:ends[r['request_id']].append(int(r['end_ns']))
for r in q:
 s=scope['request_ends'][r['request_id']];assert max(ends[r['request_id']])==int(s['display_end_ns']);assert int(s['omitted_tail_ns'])==int(r['end_ns'])-max(ends[r['request_id']]);assert s['source_end_ns']==r['end_ns']
assert int(scope['omitted_global_tail_ns'])==max(int(r['end_ns']) for r in q)-max(max(v) for v in ends.values())
source=ROOT/'original/acceptance/E2E_PROCESS_TIMELINE_LOSSLESS.html';output=ROOT/'acceptance/E2E_PROCESS_TIMELINE_LOSSLESS.html';extract=lambda p:p.read_text().split('<script>const PAYLOAD=',1)[1].split(';</script>',1)[0];assert extract(source)==extract(output);assert sha(output)==build['output_page_sha256']
errors=[];requests=[];result={}
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path=BROWSER,headless=True,args=['--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND','--js-flags=--max-old-space-size=32768'])
 try:
  context=browser.new_context(offline=True,viewport={'width':1520,'height':1100});context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(('file:','data:','about:')) else (requests.append(r.request.url),r.abort()));page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(output.as_uri(),wait_until='load',timeout=180000);page.wait_for_function('window.PAGE_READY || window.PAGE_ERROR',timeout=300000);assert not page.evaluate('window.PAGE_ERROR||null')
  result=page.evaluate("""()=>({eventCount:TIMELINE.events.length,contextCount:TIMELINE.contexts.length,view:TIMELINE.view,requests:TIMELINE.events.filter(e=>e.kind==='request').map(e=>({id:e.request_id,display_end_ns:e.end_ns,source_end_ns:e.original.end_ns,omitted_tail_ns:e.omitted_untraced_tail_ns})),allNonRequestIntervalsRetained:TIMELINE.all.filter(e=>e.kind!=='request').every(e=>e.begin_ns===e.original.begin_ns&&e.end_ns===e.original.end_ns),noEventBeyondCut:TIMELINE.all.every(e=>BigInt(e.end_ns)<=BigInt(REQUEST_VIEW_SCOPE.display_end_ns)),allRequestCutsContainTheirEvents:TIMELINE.all.every(e=>BigInt(e.end_ns)<=BigInt(REQUEST_VIEW_SCOPE.request_ends[e.request_id].display_end_ns))})""")
  assert result['eventCount']==8+12544+2*23660;assert result['allNonRequestIntervalsRetained'] and result['noEventBeyondCut'] and result['allRequestCutsContainTheirEvents'];assert int(result['view'][1])==int(scope['display_envelope_duration_ns']);assert len(result['requests'])==8
  for rr in result['requests']:
   s=scope['request_ends'][rr['id']];assert rr['display_end_ns']==s['display_end_ns'] and rr['source_end_ns']==s['source_end_ns'] and rr['omitted_tail_ns']==s['omitted_tail_ns']
  page.locator('#traceScope').screenshot(path=str(ROOT/'inspection/request_trim_scope.png'));page.locator('#plotScroll').screenshot(path=str(ROOT/'inspection/request_trim_timeline.png'))
  result['interactions']=page.evaluate("""()=>{const r=TIMELINE.events.find(e=>e.kind==='request');TIMELINE.locate(r.id);if(TIMELINE.view[1]!==String(BigInt(r.end_ns)-BigInt(PAYLOAD.origin_ns)))throw Error('locate bypassed cut');TIMELINE.setView(r.begin_ns,String(BigInt(r.begin_ns)+1n));if(BigInt(TIMELINE.view[1])-BigInt(TIMELINE.view[0])!==1n)throw Error('1ns');TIMELINE.reset();return {locate_clipped_request:true,source_original_retained:!!r.original.end_ns,one_ns_zoom:true};}""")
  page.goto((ROOT/'acceptance/REQUEST_COVERAGE.html').as_uri(),wait_until='load');assert page.locator('#traceScope tbody tr').count()==8;page.screenshot(path=str(ROOT/'inspection/request_coverage_trimmed.png'),full_page=True)
 finally:browser.close()
assert not errors and not requests
out={'status':'complete','argv':sys.argv,'script_sha256':sha(Path(__file__)),'elapsed_seconds':time.time()-start,'checks':{'independent_R09_context_endpoints_and_tail_durations':True,'all_eight_requests_retained':True,'only_request_presentation_endpoints_changed':True,'all_non_request_intervals_unchanged':True,'complete_original_payload_unchanged':True,'scope_and_omitted_durations_before_visualization':True,'network_denied_browser':True},'browser':result,'browser_errors':errors,'external_requests':requests,'scope_sha256':sha(ROOT/'REQUEST_VIEW_SCOPE.json'),'output_files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'size':p.stat().st_size} for p in [output,ROOT/'acceptance/REQUEST_COVERAGE.html',ROOT/'index.html',ROOT/'acceptance/index.html']]};(ROOT/'validation/REQUEST_TRIM_AUDIT.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print('REQUEST_TRIM_AUDIT_COMPLETE',round(out['elapsed_seconds'],2))
