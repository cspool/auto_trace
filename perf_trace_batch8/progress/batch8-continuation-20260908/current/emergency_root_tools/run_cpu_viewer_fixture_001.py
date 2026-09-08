from pathlib import Path
import importlib.util,json,os,time,traceback
BASE=Path('/root/r08_emergency_tools');OUT=BASE/'cpu_viewer_fixture_001';spec=importlib.util.spec_from_file_location('browser_check',BASE/'stage_tool_templates/r10_001/browser_acceptance.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.ROOT=OUT
os.environ['PLAYWRIGHT_BROWSERS_PATH']='/root/r08_r10_browser_tools'
start=time.monotonic();errors=[];requests=[];static=m.static_check(OUT/'fixture.html');manifest=json.loads((OUT/'FIXTURE_MANIFEST.json').read_text())
with m.sync_playwright() as p:
 binary=Path(p.chromium.executable_path);browser=p.chromium.launch(executable_path=str(binary),headless=True,args=['--disable-background-networking','--host-resolver-rules=MAP * ~NOTFOUND','--disable-gpu'])
 try:
  context=browser.new_context(offline=True,viewport={'width':1440,'height':1000});page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)));page.on('request',lambda request:requests.append(request.url) if not request.url.startswith('file:') else None);page.goto((OUT/'fixture.html').as_uri(),wait_until='load');page.wait_for_function('window.PAGE_READY===true||window.PAGE_ERROR!==undefined',timeout=60000);assert not page.evaluate('window.PAGE_ERROR||null'),errors
  checks=m.timeline_checks(page,manifest);assert not errors and not requests;page.screenshot(path=str(OUT/'fixture.png'));context.close()
 finally:browser.close()
result={'status':'complete','fixture_only':True,'R10_actual_stage_execution':False,'checks':checks,'static':static,'browser':m.rec(binary),'errors':errors,'network_requests':requests,'elapsed_seconds':time.monotonic()-start};(OUT/'CPU_BROWSER_FIXTURE_AUDIT.json').write_text(json.dumps(result,indent=2)+'\n');print('CPU_BROWSER_FIXTURE_COMPLETE',result['elapsed_seconds'])
