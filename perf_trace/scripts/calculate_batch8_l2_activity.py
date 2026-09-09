#!/usr/bin/env python3
"""L2 hit/miss activity from restored PMC counters, without invented byte sizes."""
from pathlib import Path
from decimal import Decimal,localcontext
import argparse,collections,csv,json,hashlib,re

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(root):
 out=root/'batch8_bandwidth';restore=json.loads((out/'RESTORE_MANIFEST.json').read_text());rs=[];seen=set();key_inventory=collections.defaultdict(set)
 for item in restore['restored']:
  if not item['path'].endswith('dispatch_attributes.jsonl'):continue
  p=Path(item['local_path']);assert sha(p)==item['sha256']
  for n,line in enumerate(p.read_text().splitlines(),1):
   a=json.loads(line);c=a['counters'];key_inventory[a['counter_mode']].update(re.sub(r'\[\d+\]$','',k) for k in c)
   if a['counter_mode']!='pmc':continue
   ident=a['physical_attribute_id'];assert ident not in seen;seen.add(ident)
   hits={k:v for k,v in c.items() if re.fullmatch(r'TCC_HIT\[\d+\]',k)};misses={k:v for k,v in c.items() if re.fullmatch(r'TCC_MISS\[\d+\]',k)}
   complete=bool(hits) and {k[7:] for k in hits}=={k[8:] for k in misses} and all(isinstance(v,int) and v>=0 for v in [*hits.values(),*misses.values()])
   hit=sum(hits.values()) if complete else None;miss=sum(misses.values()) if complete else None;total=hit+miss if complete else None;dt=int(a['native_signature_end_monotonic_ns'])-int(a['native_signature_begin_monotonic_ns'])
   valid=complete and total>0 and dt>0
   with localcontext() as ctx:
    ctx.prec=40;pct=str(Decimal(hit)*100/total) if valid else None;rate=str(Decimal(total)*10**9/dt) if valid else None
   rs.append(dict(physical_attribute_id=ident,r07_process_range_id=a['r07_process_range_id'],r07_kernel_instance_id=a['r07_kernel_instance_id'],segment_id=a['segment_id'],device=a['native_device'],hit_count=hit,miss_count=miss,request_count=total,duration_ns=dt,hit_rate_pct=pct,requests_per_second=rate,runtime_shape_match=a['runtime_shape_match'],projection_permitted=bool(valid and a['runtime_shape_match'] is True),state='calculated' if valid else 'unavailable',bandwidth_utilization_pct=None,bandwidth_GBps=None,source_path=item['path'],source_sha256=item['sha256'],source_line=n))
 profiles={}
 grouped=collections.defaultdict(list)
 for r in rs:grouped[r['r07_process_range_id']].append(r)
 for ident,members in grouped.items():
  ok=all(r['projection_permitted'] for r in members)
  hits=sum(r['hit_count'] for r in members) if ok else None;miss=sum(r['miss_count'] for r in members) if ok else None;dt=sum(r['duration_ns'] for r in members) if ok else None
  profiles[ident]=dict(hit_rate_pct=hits/(hits+miss)*100 if ok else None,requests_per_second=(hits+miss)/dt*1e9 if ok else None,hit_count=hits,miss_count=miss,replay_duration_sum_ns=dt,dispatch_count=len(members),state='available_replay_hit_rate' if ok else 'unavailable_shape_or_counter',physical_attribute_ids=[r['physical_attribute_id'] for r in members],aggregation='sum hits / sum hits+misses across unique same-shape selected PMC dispatches; request rate uses sum of their replay durations',bandwidth_utilization_pct=None)
 # Cross-check the existing independently accepted R10 metrics.
 import gzip,base64
 p=root/'batch8/site/acceptance/HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html';d=json.loads(p.read_text().split('<script>const PAYLOAD=',1)[1].split(';</script>',1)[0]);pack=d['tables']['traffic_resource_attachment'];indexed={r['physical_attribute_id']:r for r in rs};checks=0
 for block in pack['blocks']:
  for cells in json.loads(gzip.decompress(base64.b64decode(block))):
   m=dict(pack['constants'],**dict(zip(pack['fields'],cells)))
   key={'L2_hit_count':'hit_count','L2_miss_count':'miss_count','L2CacheHit_pct':'hit_rate_pct'}.get(m['metric_name'])
   if key:
    r=indexed[m['physical_attribute_id']];v=r[key];assert r['r07_process_range_id']==m['r07_process_range_id']
    assert (m['value']=='' if v is None else abs(Decimal(str(v))-Decimal(m['value']))<Decimal('1e-20'))
    checks+=1
 assert checks==len(rs)*3
 with (out/'L2_ACTIVITY_DISPATCH.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
 data=dict(status='verified',profiles=profiles,summary=dict(dispatches=len(rs),valid=sum(r['state']=='calculated' for r in rs),projectable=sum(r['projection_permitted'] for r in rs),processes=len(profiles),available_processes=sum(r['hit_rate_pct'] is not None for r in profiles.values()),original_R10_metric_comparisons=checks),metric='L2 cache hit rate, not bandwidth utilization',L2_peak_reference_GBps=None,request_bytes_assumed=False,counters_by_mode={m:sorted(keys) for m,keys in key_inventory.items()},source_manifest_sha256=sha(out/'RESTORE_MANIFEST.json'),csv_sha256=sha(out/'L2_ACTIVITY_DISPATCH.csv'))
 (out/'L2_ACTIVITY.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');print(json.dumps(data['summary'],indent=2),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();main(a.root.resolve())
