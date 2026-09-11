#!/usr/bin/env python3
"""Compute report facts from immutable retained trace payloads, not rendered pixels."""
from pathlib import Path
import argparse,base64,collections,gzip,hashlib,json,math,re

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(gzip.decompress(base64.b64decode(re.search(r'<script id="packed"[^>]*>(.*?)</script>',p.read_text(),re.S)[1])))
def stats(values,additive=False):
 v=sorted(values);n=len(v)
 if not n:return {'n':0}
 return {'n':n,**({'sum':sum(v)} if additive else {}),'mean':sum(v)/n,'median':(v[(n-1)//2]+v[n//2])/2,'p95':v[math.ceil(.95*n)-1],'min':v[0],'max':v[-1]}
def sweep(kernels):
 events=collections.Counter()
 for k in kernels:events[k[1]]+=1;events[k[2]]-=1
 active=0;prev=None;busy=overlap=peak=0
 for t,d in sorted(events.items()):
  if prev is not None:
   if active>0:busy+=t-prev
   if active>1:overlap+=t-prev
  active+=d;assert active>=0;peak=max(peak,active);prev=t
 assert active==0
 return {'unique_kernels':len(kernels),'kernel_duration_sum_ns':sum(k[2]-k[1] for k in kernels),'busy_union_ns':busy,'overlap_union_ns':overlap,'peak':peak}
def main(root):
 out=root/'analysis_reports/data';out.mkdir(parents=True,exist_ok=True);allfacts={}
 for key in ['single_batch','batch8']:
  page=root/'revised'/key/'CONCURRENCY_UTILIZATION.html';d=read(page);ps=d['processes'];pmap={p['id']:p for p in ps};types=collections.defaultdict(list);ks=collections.defaultdict(list)
  for p in ps:types[p['name']].append(p)
  for k in d['kernels']:ks[k[0]].append(k)
  total=sum(p['d'] for p in ps);assert total==d['total_process_ns'];groupfacts=[];pilefacts=[]
  for g in d['groups']:
   ms=types[g['name']];assert sum(p['d'] for p in ms)==g['total_ns']
   groupfacts.append({'name':g['name'],'share_pct':g['share']*100,'duration_ns':stats([p['d'] for p in ms],True),'phase':{phase:stats([p['d'] for p in ms if p['phase']==phase],True) for phase in sorted({p['phase'] for p in ms})},'fragments':{f:stats([p['d'] for p in ms if p['fragment']==f],True) for f in sorted({p['fragment'] for p in ms})},'owned_kernel_count':sum(len(ks[p['id']]) for p in ms),'owned_kernel_duration_sum_ns':sum(k[2]-k[1] for p in ms for k in ks[p['id']]),'original_high_count':sum(p['high'] for p in ms)})
  for rank,ref in enumerate(d['pile_order'],1):
   g=next(g for g in d['groups'] if g['name']==ref['group']);c=next(c for c in g['piles'] if c['rank']==ref['pile_rank']);ms=[pmap[i] for i in c['members']]
   pilefacts.append({'rank':rank,'name':g['name'],'pile':c['rank'],'duration_ns':stats([p['d'] for p in ms],True),'total_share_pct':c['total_ns']/total*100,'type_share_pct':c['total_ns']/g['total_ns']*100,'phase_counts':dict(collections.Counter(p['phase'] for p in ms)),'device_counts':dict(collections.Counter(p['device'] for p in ms)),'representative':c['representative'],'member_ids':c['members']})
  selected=[p for p in ps if p['name'] in {g['name'] for g in d['groups']}];ids={p['id'] for p in selected};devices={dev:sweep([k for k in d['kernels'] if k[3]==dev]) for dev in sorted({k[3] for k in d['kernels']})}
  for dev,summary in devices.items():
   cs=[r for r in d['counts'] if r[2]==dev and r[3]=='kernel'];assert sum(r[1]-r[0] for r in cs if r[4]>0)==summary['busy_union_ns'];assert sum(r[1]-r[0] for r in cs if r[4]>1)==summary['overlap_union_ns']
  resources={};hardware_ids=set()
  for name in sorted({p['name'] for p in selected}):
   ms=[p for p in selected if p['name']==name];r=[d['resources'][p['id']] for p in ms];compute=[x['compute_pct'] for x in r if x['compute_pct'] is not None]
   item={'instances':len(ms),'compute_pct':stats(compute),'compute_zero_count':sum(v==0 for v in compute),'reasons':dict(collections.Counter(x.get('compute_state',x.get('compute_reason','unknown')) for x in r))}
   if key=='batch8':
    for direction in ['read','write']:
     valid=[x['bandwidth_profiles'][direction] for x in r if x.get('bandwidth_profiles',{}).get(direction,{}).get('reference_pct') is not None];item[direction+'_reference_pct']=stats([x['reference_pct'] for x in valid]);item[direction+'_GBps']=stats([x['bandwidth_GBps'] for x in valid])
    item['l2_hit_pct']=stats([x['l2_activity']['hit_rate_pct'] for x in r if (x.get('l2_activity') or {}).get('hit_rate_pct') is not None]);item['l2_Greqps']=stats([x['l2_activity']['requests_per_second']/1e9 for x in r if (x.get('l2_activity') or {}).get('requests_per_second') is not None])
    for p,x in zip(ms,r):
     if any(v.get('reference_pct') is not None for v in x.get('bandwidth_profiles',{}).values()) or (x.get('l2_activity') or {}).get('hit_rate_pct') is not None:hardware_ids.add(p['id'])
   else:
    samples=[s for x in r for s in x.get('l2_samples',[])];item['l2_projected_GBps']=stats([s['projected_L2_GBps'] for s in samples]);item['l2_sample_count']=len(samples);item['l2_instances']=sum(bool(x.get('l2_samples')) for x in r)
    hardware_ids.update(p['id'] for p,x in zip(ms,r) if x.get('l2_samples'))
   resources[name]=item
  examples={}
  if key=='batch8':
   candidates=[]
   for p in selected:
    r=d['resources'][p['id']];rd=r.get('bandwidth_profiles',{}).get('read',{});wr=r.get('bandwidth_profiles',{}).get('write',{});l=r.get('l2_activity') or {}
    if all(v is not None for v in [r['compute_pct'],rd.get('reference_pct'),wr.get('reference_pct'),l.get('hit_rate_pct')]):candidates.append(p)
   candidates.sort(key=lambda p:(p['b'],p['id']));paired=next((p for p in candidates if any(q['device']!=p['device'] and q['b']<p['e'] and q['e']>p['b'] for q in candidates)),None)
   examples['resource']=paired or (candidates[0] if candidates else next(p for p in selected if p['id'] in hardware_ids))
  else:examples['resource']=min((p for p in selected if p['id'] in hardware_ids and d['resources'][p['id']]['compute_pct'] is not None),key=lambda p:(p['b'],p['id']))
  examples['high']=pmap[pilefacts[0]['representative']]
  # Exact IDs and typed ownership give a reusable link back to raw Process/kernel evidence.
  for role,p in examples.items():p['owned_kernel_examples']=ks[p['id']][:8]
  facts={'trace':key,'origin_ns':d['origin_ns'],'source_page':str(page),'source_sha256':sha(page),'scope':d['scope'],'process_count':len(ps),'selected_count':len(selected),'selected_type_count':len(groupfacts),'total_process_duration_ns':total,'selected_type_share_pct':sum(g['share_pct'] for g in groupfacts),'raw_sample_value_counts':dict(collections.Counter(str(s[1]) for s in d['samples'])),'source_process_extent_ns':d['time_sections'][9][1]-d['time_sections'][0][0],'kernel_count':len(d['kernels']),'groups':groupfacts,'piles':pilefacts,'devices':devices,'resources':resources,'hardware_eligible_instances':len(hardware_ids),'resource_coverage':d.get('resource_coverage'),'time_sections':d['time_sections'],'examples':examples}
  if key=='batch8':
   rates=[json.loads(line) for line in (root/'batch8_bandwidth/DISPATCH_BANDWIDTH.jsonl').read_text().splitlines()];kmap={k[6]:k for k in d['kernels']};ratios={}
   for direction in ['read','write']:
    vals=[r['duration_ns']/(kmap[r['r07_kernel_instance_id']][2]-kmap[r['r07_kernel_instance_id']][1]) for r in rates if r['direction']==direction and r['r07_projection_permitted']]
    ratios[direction]=stats(vals)
   facts['replay_vs_observed_kernel_duration_ratio']=ratios
  segments=[]
  for index,(begin,end) in enumerate(d['time_sections'],1):
   intersect=[p for p in selected if p['b']<end and p['e']>begin];totals=collections.Counter()
   for p in intersect:totals[p['name']]+=min(end,p['e'])-max(begin,p['b'])
   per_device={}
   for dev in devices:
    source=[r for r in d['counts'] if r[2]==dev and r[3]=='kernel' and r[0]<end and r[1]>begin]
    per_device[dev]={'busy_ns':sum(min(end,r[1])-max(begin,r[0]) for r in source if r[4]>0),'overlap_ns':sum(min(end,r[1])-max(begin,r[0]) for r in source if r[4]>1),'peak':max([r[4] for r in source] or [0])}
   segments.append({'segment':index,'begin_ns':begin,'end_ns':end,'intersecting_selected_instances':len(intersect),'selected_duration_intersection_sum_ns':sum(totals.values()),'type_duration_intersections_ns':dict(totals),'dominant_type':max(totals,key=totals.get) if totals else None,'hardware_intersecting_instances':sum(p['id'] in hardware_ids for p in intersect),'per_device':per_device})
  assert sum(row['selected_duration_intersection_sum_ns'] for row in segments)==sum(p['d'] for p in selected)
  facts['time_segments']=segments
  facts['kernel_busy_outside_process_extent_ns']={dev:summary['busy_union_ns']-sum(r['per_device'][dev]['busy_ns'] for r in segments) for dev,summary in devices.items()}
  allfacts[key]=facts
  (out/(key+'.json')).write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n')
  print(key,'sum_ns',total,'selected share',facts['selected_type_share_pct'],'device',devices,'resource',resources,flush=True)
 import csv
 with (out/'SEGMENTS.csv').open('w',newline='') as f:
  writer=csv.writer(f);writer.writerow(['trace','segment','begin_ns','end_ns','intersecting_selected_instances','selected_duration_intersection_sum_ns','hardware_intersecting_instances','dominant_type','device_metrics_json'])
  for key,facts in allfacts.items():
   for row in facts['time_segments']:writer.writerow([key,row['segment'],row['begin_ns'],row['end_ns'],row['intersecting_selected_instances'],row['selected_duration_intersection_sum_ns'],row['hardware_intersecting_instances'],row['dominant_type'],json.dumps(row['per_device'])])
 (out/'SUMMARY.json').write_text(json.dumps(allfacts,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();main(a.root.resolve())
