#!/usr/bin/env python3
"""Separate raw-table reconciliation and offline-browser acceptance for the explanatory report."""
import csv,json,hashlib,re,datetime,sys,subprocess,shutil
from pathlib import Path
from collections import Counter
from playwright.sync_api import sync_playwright
csv.field_size_limit(30_000_000)
O=Path(__file__).resolve().parent;D=O/'data';a=json.loads((D/'analysis.json').read_text());s=json.loads((D/'scheduling.json').read_text())
checks={}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rec(p):return {'path':str(p.relative_to(O)),'size':p.stat().st_size,'sha256':sha(p)}
source=next(Path(x['path']) for x in a['sources'] if x['path'].endswith('/kernel_timeline.csv'))
assert sha(source)==next(x['sha256'] for x in a['sources'] if x['path']==str(source))
raw={r['kernel_instance_id']:r for r in csv.DictReader(source.open())};k={r['kernel_instance_id']:r for r in csv.DictReader((D/'kernels.csv').open())};assert raw.keys()==k.keys() and len(k)==23660
for ident,r in raw.items():
 d=k[ident]
 for field in ['begin_ns','end_ns','duration_ns','request_id','rank','physical_device_id','phase','forward_id','layer_idx','owner_process_range_id','runtime_call_id','hip_runtime_index','native_kernel_name']:assert r[field]==d[field],(ident,field)
 assert int(d['end_ns'])-int(d['begin_ns'])==int(d['duration_ns'])
checks['all_unique_raw_kernel_identities_durations_and_owners_match']=True
assert sum(int(r['duration_ns']) for r in raw.values())==a['total_kernel_duration_ns']==3154602493
assert sum(v['duration_ns'] for v in a['categories'].values())==a['total_kernel_duration_ns']
checks['category_partition_and_integer_sum']=True
# Recompute the principal claims independently from raw symbols and preserved launches.
launch={r['kernel_instance_id']:r for r in csv.DictReader((D/'observed_launches.csv').open())};assert launch.keys()==raw.keys()
for ident,r in k.items():
 for name in ['gridDimX','gridDimY','gridDimZ','blockDimX','blockDimY','blockDimZ','sharedMemBytes']:
  v=re.search(r'\b'+name+r'=(\d+)',launch[ident]['api_arguments'])
  if v:assert int(v[1])==int(r[name])
  else:assert r[name]=='' # hipExtModuleLaunchKernel retains global/localWorkSize verbatim; no fabricated grid fields
gqa=[r for r in k.values() if r['native_kernel_name']=='_gqa6'];bm32=[r for r in gqa if int(r['gridDimZ']) in (3,4,5)];norm=[r for r in k.values() if r['native_kernel_name']=='_gdn_rmsnorm'];packed=[r for r in k.values() if r['native_kernel_name']=='fused_recurrent_gated_delta_rule_packed_decode_kernel']
assert (len(gqa),sum(int(r['duration_ns']) for r in gqa))==(224,901614133)
assert (len(bm32),sum(int(r['duration_ns']) for r in bm32))==(128,579995773)
assert (len(norm),sum(int(r['duration_ns']) for r in norm))==(672,22983517)
assert len(packed)==96 and all(int(r['gridDimY'])==192 and int(r['blockDimX'])==64 for r in packed)
assert all(int(r['gridDimX'])==1536 and int(r['blockDimX'])==256 for r in norm)
checks['all_observed_launch_fields_and_optimization_claims']=True
for u in a['units']:
 part=[r for r in raw.values() if r['request_id']==u['request_id'] and r['phase']==u['phase']];assert len(part)==u['kernel_count'] and sum(int(r['duration_ns']) for r in part)==u['kernel_duration_ns']
checks['all_16_request_phase_denominators_recomputed']=True
requests=list(csv.DictReader((D/'requests.csv').open()));assert Counter(r['rank'] for r in requests)=={'0':4,'1':4}
for rank,expected in [(0,{2,4,5,6}),(1,{1,3,7,8})]:assert {int(r['measured_request_ordinal']) for r in requests if int(r['rank'])==rank}==expected
assert len(s['launch_samples'])==16
for sample in s['launch_samples']:
 r=k[sample['kernel_instance_id']];assert int(r['rank'])==sample['rank'] and int(r['begin_ns'])==sample['launch_begin_ns'];assert sample['local_batch_sequences']==(int(r['gridDimZ']) if r['native_kernel_name']=='_gqa6' else int(r['gridDimY'])//48)
checks['eight_request_routing_and_discrete_batch_samples']=True
f=json.loads((O/'FIGURE_AUDIT.json').read_text())
for n in ['A','B','D']:assert abs(f['panels'][n]['measured_rectangle_height_points']-56.241)<.001
for panel in f['panels'].values():
 for rect in panel['rectangles']:
  lim=panel['ylim'] if rect['vertical'] else panel['xlim'];assert lim[0]<=rect['start']<=rect['display_end']<=lim[1]
for panel,phase in [('B','prefill'),('C','decode')]:
 for item in f['panels'][panel]['local_top5']:
  u=next(u for u in a['units'] if u['phase']==phase and u['request']==item['unit']);vals=u['category_duration_ns'];expected=sorted((c for c in vals if vals[c]>0),key=lambda c:(-vals[c],c))[:5];assert expected==item['categories']
checks['figure_bounds_physical_heights_and_per_unit_top5']=True
origin=min(int(r['begin_ns']) for r in requests)
ar=f['panels']['A']['rectangles'];assert len(ar)==24
for r in ar:
 if r['kind']=='client':
  raw_request=next(q for q in requests if int(q['measured_request_ordinal'])==r['request'])
  assert r['raw_begin_ns']==int(raw_request['begin_ns']) and r['raw_end_ns']==int(raw_request['end_ns'])
  assert r['folded'] and len(r['visible_blocks'])==2 and r['cap']==260
  assert abs(r['display_end']-r['start']-260)<1e-9
 else:
  u=next(u for u in a['units'] if u['request']==r['request'] and u['phase']==r['kind'])
  assert r['raw_begin_ns']==u['selected_marker_begin_ns'] and r['raw_end_ns']==u['selected_marker_end_ns']
  assert r['scale']==12 and not r['folded']
  assert abs(r['display_end']-r['start']-12*(r['raw_end_ns']-r['raw_begin_ns'])/1e9)<1e-9
 assert abs(r['start']-(r['raw_begin_ns']-origin)/1e9)<1e-9
sf=json.loads((O/'SCHEDULING_FIGURE_AUDIT.json').read_text());assert sf['sample_count']==16 and sf['information_card_fraction_of_axes']>.75
assert sf['information_card_fraction_of_full_figure']>.50
assert {q['kernel_instance_id'] for q in sf['samples']}=={q['kernel_instance_id'] for q in s['launch_samples']}
for rank in (0,1):
 cards=sorted((q for q in sf['samples'] if q['rank']==rank),key=lambda q:q['order'])
 expected=sorted((q for q in s['launch_samples'] if q['rank']==rank),key=lambda q:q['launch_begin_ns'])
 assert len(cards)==8
 for card,sample in zip(cards,expected):
  for key in ['request','phase','kernel_instance_id','launch_begin_ns','client_relative_s','local_batch_sequences','grid','threads_per_block','GQA_BLOCK_M']:assert card[key]==sample[key]
  assert card['all_text_inside_card'] and card['width_pt']>200 and card['height_pt']>200
  x0,y0,x1,y1=card['bounds'];assert 0<=x0<x1<=8 and 0<=y0<y1<=2
checks['eight_client_folds_and_16_enlarged_markers_keep_raw_times']=True
checks['16_large_scheduling_cards_match_actual_launch_order_and_values']=True
assert (O/'REPORT.html').read_text().count('<svg ')==5
browser_errors=[];network=[];B=O/'validation';B.mkdir(exist_ok=True)
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/root/r08_r10_browser_tools/chromium-1234/chrome-linux64/chrome',headless=True,args=['--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--disable-background-networking','--disable-component-update','--disable-default-apps','--disable-sync','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND'])
 context=browser.new_context(viewport={'width':1600,'height':1100},offline=True)
 def route(rt):
  if rt.request.url.startswith(('file:','data:','about:')):rt.continue_()
  else:network.append(rt.request.url);rt.abort()
 context.route('**/*',route);page=context.new_page();page.on('pageerror',lambda e:browser_errors.append(str(e)))
 page.goto((O/'REPORT.html').as_uri(),wait_until='load',timeout=60000);page.wait_for_function('window.REPORT_READY === true');page.evaluate('document.fonts.ready')
 assert page.locator('.svg-scroll svg').count()==5
 assert page.locator('[id^="scheduling_local_batch_sample-rank"]').count()==16
 assert page.evaluate("document.fonts.check('16px \"Noto Sans CJK SC\"','双卡调度')")
 seen=[]
 for num in range(1,9):
  page.select_option('#request-select',str(num));text=page.locator('#details').inner_text();matches=[x for x in s['launch_samples'] if x['request']==num]
  assert len(matches)==2
  for x in matches:assert x['kernel_instance_id'] in text and str(x['launch_begin_ns']) in text
  seen.append(num)
 page.select_option('#request-select','5');page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(B/'report_opening.png'))
 page.locator('figure').nth(0).scroll_into_view_if_needed();page.screenshot(path=str(B/'report_timeline.png'))
 page.locator('figure').nth(1).scroll_into_view_if_needed();page.screenshot(path=str(B/'report_scheduling.png'))
 page.locator('#request-select').scroll_into_view_if_needed();page.screenshot(path=str(B/'report_lookup.png'))
 # Declared SVG data rectangles are already numerically audited. Check actual browser dimensions and offline links.
 sizes=page.locator('.svg-scroll svg').evaluate_all('(els)=>els.map(e=>({width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}))');assert all(z['width']>=1000 and z['height']>100 for z in sizes)
 page.emulate_media(media='print');page.pdf(path=str(O/'Batch8_DP2_Scheduling_Report.pdf'),print_background=True,prefer_css_page_size=True)
 context.close();browser.close()
assert not browser_errors,browser_errors;assert not network,network
checks.update({'actual_offline_browser_opened':True,'all_eight_request_selectors_exact_ns_and_ids':seen,'five_embedded_figures_rendered':True,'Chinese_font_available':True,'page_errors':browser_errors,'external_network_attempts':network,'browser_closed':True,'pdf_generated':True})
result={'status':'complete','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'builder_imported':False,'original_R09_raw_table_reconciled':True,'checks':checks,'report_html':rec(O/'REPORT.html'),'report_markdown':rec(O/'REPORT.md'),'pdf':rec(O/'Batch8_DP2_Scheduling_Report.pdf'),'browser_screenshots':[rec(p) for p in sorted(B.glob('report_*.png'))],'figure_audit':rec(O/'FIGURE_AUDIT.json'),'interpreter':sys.executable}
(O/'REPORT_AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('REPORT_AUDIT_COMPLETE',json.dumps({'raw_kernel_count':len(raw),'request_controls':len(seen),'network_attempts':len(network),'pdf_bytes':(O/'Batch8_DP2_Scheduling_Report.pdf').stat().st_size}),flush=True)
print('PDF_UTILITIES',shutil.which('pdftoppm'),shutil.which('pdftotext'),shutil.which('pdfinfo'),flush=True)
