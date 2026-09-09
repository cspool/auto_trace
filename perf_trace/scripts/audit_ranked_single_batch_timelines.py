#!/usr/bin/env python3
"""Independent retained-source and offline browser audit for the ranked replay."""
import argparse,collections,csv,hashlib,json,re,tarfile,time
from pathlib import Path

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def parse(raw):return json.loads(re.search(r'<script[^>]*id=["\x27]page-payload["\x27][^>]*>(.*?)</script>',raw,re.S)[1])
def read(t,n):return t.extractfile(next(x for x in t if x.name.endswith('/'+n))).read()
def main(site,output,browser):
 output.mkdir(parents=True,exist_ok=True);begin=time.time();checks={}
 manifest=json.loads((site/'BUILD_MANIFEST.json').read_text());ranks=json.loads((site/'RANKINGS.json').read_text())
 paths=[site/'original'/r['name'] for r in manifest['sources']]
 for p,r in zip(paths,manifest['sources']):assert sha(p)==r['sha256']
 with tarfile.open(paths[0]) as t:
  A=parse(read(t,'E2E_PROCESS_TIMELINE.html').decode());H=parse(read(t,'HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html').decode());C=parse(read(t,'CONCURRENCY_UTILIZATION.html').decode())
 with tarfile.open(paths[1]) as t:
  raw=read(t,'E2E_PROCESS_TIMELINE.full.perfetto.json');assert hashlib.sha256(raw).hexdigest()==sha(site/'E2E_PROCESS_TIMELINE.full.perfetto.json');del raw
 B=parse((site/'E2E_PROCESS_TIMELINE_LOSSLESS.html').read_text());origin=int(B['origin_ns'])
 assert len(A['rows'])==len(B['rows'])==507005
 for a,b in zip(A['rows'],B['rows']):assert (a['g'],a['b'],a['e'])==(b['g'],origin+b['b'],origin+b['e'])
 for name,key,source in [('HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html','high',H),('CONCURRENCY_UTILIZATION.html','concurrency',C)]:
  D=parse((site/name).read_text())
  def restore(v):
   if isinstance(v,dict):return {k:restore(x) for k,x in v.items()}
   if isinstance(v,list):return [restore(x) for x in v]
   if isinstance(v,str) and re.fullmatch(r'-?\d{16,}',v) and abs(int(v))>2**53-1:return int(v)
   return v
  # Original payload fields already containing string ns stay strings; compare a canonical string-safe tree instead.
  def canonical(v):
   if isinstance(v,dict):return {k:canonical(x) for k,x in v.items()}
   if isinstance(v,list):return [canonical(x) for x in v]
   if isinstance(v,int) and abs(v)>2**53-1:return str(v)
   return v
  assert D[key]==canonical(source)
 checks['source_payloads_and_full_trace_unchanged']=True
 processes={r['process']:r for r in A['rows'] if r['g']=='process'}
 for mode,rows in [('high',H['processes']),('raw',list(processes.values()))]:
  buckets=collections.defaultdict(list)
  for p in rows:buckets[p['phase']+' / '+p['stage']].append(p)
  expected=[]
  for key,ms in buckets.items():
   ms.sort(key=lambda p:(-(p['e']-p['b']),p['process']));score=sum(p['e']-p['b'] for p in ms) if mode=='high' else max(p['e']-p['b'] for p in ms)
   expected.append((key,str(score),[p['process'] for p in ms]))
  expected.sort(key=lambda g:(-int(g[1]),g[0]));assert expected==[(g['key'],g['score_ns'],g['members']) for g in ranks[mode]]
 checks['all_process_group_memberships_and_rankings']=True
 attachments=collections.defaultdict(set)
 for a in H['attachments']:attachments[a['process_range']].add(a['matched_kernel_family'])
 hardware_processes={p['process'] for p in processes.values() if any(h['event_id']==p['event'] and h['stage']==p['stage'] and h['matched_kernel_family'] in attachments[p['process']] for h in H['hardware'])}
 assert hardware_processes=={p for g in ranks['hardware'] for p in g['members']}
 checks['exact_hardware_process_associations']=True
 # Re-sweep kernel endpoints independently, including multiple kernels on one queue.
 edges=collections.defaultdict(list)
 for k in H['kernels']:edges[k['b']].append((k['queue'],1));edges[k['e']].append((k['queue'],-1))
 edges[A['begin']];edges[A['end']];times=sorted(edges);q=collections.Counter();sweep=[]
 for a,b in zip(times,times[1:]):
  for queue,delta in edges[a]:q[queue]+=delta
  sweep.append((a,b,sum(q.values()),sum(v>0 for v in q.values())))
 for key,col in [('kernel_concurrency',2),('queue_concurrency',3)]:
  assert [(r['b'],r['e'],r['n']) for r in C[key]]==[(r[0],r[1],r[col]) for r in sweep]
 for g in ranks['concurrency']:
  f=g['forward'];busy=sum(max(0,min(e,f['e'])-max(b,f['b'])) for b,e,n,q in sweep if n>0);overlap=sum(max(0,min(e,f['e'])-max(b,f['b'])) for b,e,n,q in sweep if n>1)
  assert busy==int(g['score_ns']) and overlap==int(g['overlap_ns'])
  assert set(g['members'])=={p['process'] for p in processes.values() if p['forward']==f['forward']}
 checks['independent_kernel_queue_sweep_and_forward_unions']=True
 ordered=sorted(enumerate(C['samples']),key=lambda x:x[1]['t']);expected={(a[0],b[0]):b[1]['t']-a[1]['t'] for a,b in zip(ordered,ordered[1:]) if b[1]['t']>a[1]['t']}
 assert len(ranks['unknown'])==len(expected)
 for g in ranks['unknown']:assert int(g['score_ns'])==expected[tuple(g['members'])]
 checks['sample_gap_endpoints_and_complete_denominator']=True
 maxend=max(r['e'] for r in A['rows'] if r['g']!='request');scope=manifest['scope'];assert int(scope['display_end_ns'])==maxend and int(scope['omitted_tail_ns'])==A['end']-maxend==6113817
 checks['request_tail_scope']=True
 for path in site.glob('*.html'):
  s=path.read_text();assert not re.search(r'<(?:script|img|link)[^>]*(?:src|href)=["\x27]https?://',s)
  for link in re.findall(r'href=["\x27]([^"\x27]+)',s):
   if not link.startswith(('http:','https:','#','mailto:')):assert (site/link.split('#')[0]).exists(),(path.name,link)
 checks['offline_links_and_no_network_assets']=True
 result=dict(status='source_checks_complete',checks=checks,stats=manifest['stats'],elapsed_seconds=time.time()-begin)
 (output/'SOURCE_AUDIT.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
 if browser:
  from playwright.sync_api import sync_playwright
  errors=[];results={};shots=output/'screenshots';shots.mkdir(exist_ok=True)
  with sync_playwright() as pw:
   chromium=pw.chromium.launch(executable_path=browser,headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
   context=chromium.new_context(viewport={'width':1560,'height':1160},device_scale_factor=1)
   context.route('http://**/*',lambda r:r.abort());context.route('https://**/*',lambda r:r.abort())
   page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
   for name,mode in [('HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html','high'),('CONCURRENCY_UTILIZATION.html','concurrency')]:
    page.goto((site/name).resolve().as_uri(),wait_until='load',timeout=180000);page.wait_for_function('window.RANKED?.ready',timeout=180000)
    cats=page.evaluate('Object.keys(RANKED.categories)');results[mode]={}
    for cat in cats:
     if mode=='concurrency':
      ids=['concurrency','raw','unknown','launch'];page.locator('.rank-tab').nth(ids.index(cat)).click(timeout=60000)
     page.wait_for_timeout(150)
     state=page.evaluate('''id=>{const c=RANKED.categories[id],b=RANKED.bands.find(b=>c.section.contains(b.element));let err=0;if(b)for(const p of b.entries)for(const t of [p.b,p.e])err=Math.max(err,Math.abs(b.inverse(b.project(t))-t));return {groups:c.groups.length,visible:c.visible.length,members:c.groups.reduce((s,g)=>s+g.members.length,0),fold_inverse_max_error_ns:err,band_rows:b?.entries.length};}''',cat)
     assert state['visible']==min(20,state['groups']) and state['fold_inverse_max_error_ns']<0.001,state
     page.locator(f'#{cat} .rank-card').first.locator('canvas').first.screenshot(path=str(shots/f'{cat}_group.png'))
     page.locator(f'#{cat} .rank-card').first.locator('.chart-host canvas').first.screenshot(path=str(shots/f'{cat}_detail.png'))
     # Exercise exact ns range, member selection, paired/single axes and fold reversal.
     exact=page.evaluate('''id=>{const c=RANKED.charts.find(c=>RANKED.categories[id].section.contains(c.element)),b=c.initial[0];c.setView(b,b+1);const v=c.view;c.setView(...c.initial);return v[1]-v[0];}''',cat);assert exact==1
     band=page.locator(f'#{cat} .group-band').first
     if band.count():
      band.get_by_role('button',name='切换为单轴',exact=True).click();band.get_by_role('button',name='取消时间折叠',exact=True).click();band.get_by_role('button',name='展开逐行（36 px / 实例）',exact=True).click()
      assert page.evaluate('id=>RANKED.bands.find(b=>RANKED.categories[id].section.contains(b.element)).rowHeight',cat)==36
      if state['band_rows']>300:
       band.get_by_role('button',name='下一批实例',exact=True).click();assert page.evaluate('id=>RANKED.bands.find(b=>RANKED.categories[id].section.contains(b.element)).element.querySelector("canvas").height',cat)<=11000
      page.evaluate('''id=>{const b=RANKED.bands.find(b=>RANKED.categories[id].section.contains(b.element));b.pick(b.entries.length-1);}''',cat)
     if state['groups']>20:
      jump=page.locator(f'#{cat} .rank-jump');jump.select_option(str(state['groups']-1));assert page.locator(f'#{cat} .rank-card').count()==1
      assert page.locator(f'#{cat} .rank-card').get_attribute('data-rank')==str(state['groups'])
     results[mode][cat]=state
    page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(shots/f'{mode}_page.png'))
   page.goto((site/'E2E_PROCESS_TIMELINE_LOSSLESS.html').resolve().as_uri(),wait_until='load',timeout=180000);page.wait_for_function('window.SINGLE_FULL?.hits.length>0',timeout=180000)
   full=page.evaluate('''()=>({count:SINGLE_FULL.rows.length,view:SINGLE_FULL.view,requests:SINGLE_FULL.rows.filter(r=>r.g==='request').map(r=>({source:r.e_abs,display:r.display_end_ns,end:r.e}))})''')
   assert full['count']==507005 and full['view'][1]==int(scope['display_span_ns'])
   b=int(scope['origin_ns'])+100000000;page.locator('#absolute-b').fill(str(b));page.locator('#absolute-e').fill(str(b+1));page.locator('#absolute-go').click();assert page.evaluate('SINGLE_FULL.view[1]-SINGLE_FULL.view[0]')==1
   page.locator('#reset').click();page.locator('#chart').screenshot(path=str(shots/'full_timeline.png'));results['full']=full
   assert not errors,errors;context.close();chromium.close()
  (output/'BROWSER_AUDIT.json').write_text(json.dumps(dict(status='complete',results=results,errors=errors,elapsed_seconds=time.time()-begin),indent=2)+'\n');print('BROWSER_AUDIT_COMPLETE',flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--site',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--browser');a=p.parse_args();main(a.site,a.output,a.browser)
