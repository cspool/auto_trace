#!/usr/bin/env python3
"""Independently verify restored timestamp/byte/rate associations and projections."""
from pathlib import Path
from fractions import Fraction
import argparse,collections,hashlib,json

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def main(root):
 out=root/'batch8_bandwidth';source=json.loads((out/'RESTORE_MANIFEST.json').read_text());raw={}
 for entry in source['restored']:
  if not entry['path'].endswith('dispatch_attributes.jsonl'):continue
  p=Path(entry['local_path']);assert sha(p)==entry['sha256']
  for line in p.read_text().splitlines():
   a=json.loads(line)
   if a['counter_mode'] in ['pmc_read','pmc_write']:raw[a['physical_attribute_id']]=a
 profiles=json.loads((out/'PROCESS_BANDWIDTH.json').read_text());reference=Fraction(str(profiles['reference']['bandwidth_reference']['value']));assert reference>0 and profiles['reference']['bandwidth_reference']['unit']=='GB/s'
 rs=[json.loads(line) for line in (out/'DISPATCH_BANDWIDTH.jsonl').read_text().splitlines()];seen=set();accepted=collections.defaultdict(list)
 for r in rs:
  assert r['physical_attribute_id'] not in seen;seen.add(r['physical_attribute_id']);a=raw[r['physical_attribute_id']]
  assert int(r['begin_monotonic_ns'])==a['native_signature_begin_monotonic_ns'] and int(r['end_monotonic_ns'])==a['native_signature_end_monotonic_ns']
  dt=a['native_signature_end_monotonic_ns']-a['native_signature_begin_monotonic_ns'];assert dt==r['duration_ns']
  c=a['counters'];tag='RD' if r['direction']=='read' else 'WR';size='32B' if tag=='RD' else '64B'
  requests=[v for k,v in c.items() if k.startswith((f'TCC_EA_{tag}REQ[',f'TCC_EA1_{tag}REQ['))]
  special=[v for k,v in c.items() if k.startswith((f'TCC_EA_{tag}REQ_{size}[',f'TCC_EA1_{tag}REQ_{size}['))]
  total=None
  if requests and special and all(isinstance(v,int) and v>=0 for v in requests+special) and sum(special)<=sum(requests):
   total=64*sum(requests)-32*sum(special) if tag=='RD' else 32*sum(requests)+32*sum(special)
  assert total==r['bytes']
  valid=total is not None and dt>0
  assert (r['calculation_state']=='calculated')==valid
  assert Fraction(r['reference_GBps'])==reference
  if valid:
   rate=Fraction(total,dt);pct=rate*100/Fraction(r['reference_GBps'])
   assert abs(Fraction(r['bandwidth_GBps'])-rate)<Fraction(1,10**20)*max(abs(rate),1)
   assert abs(Fraction(r['reference_pct'])-pct)<Fraction(1,10**20)*max(abs(pct),1)
   assert r['above_reference']==(pct>100)
  assert r['r07_projection_permitted']==(valid and a['runtime_shape_match'] is True)
  accepted[(r['r07_process_range_id'],r['direction'])].append(r)
 assert seen==set(raw)
 for (p,d),rows in accepted.items():
  profile=profiles['processes'][p][d];allowed=all(r['r07_projection_permitted'] for r in rows)
  assert (profile['reference_pct'] is not None)==allowed
  assert set(profile['physical_attribute_ids'])=={r['physical_attribute_id'] for r in rows}
  if allowed:
   assert profile['bytes']==sum(r['bytes'] for r in rows)
   assert profile['replay_duration_sum_ns']==sum(r['duration_ns'] for r in rows)
   expected=profile['bytes']/profile['replay_duration_sum_ns']/float(reference)*100
   assert abs(profile['reference_pct']-expected)<1e-10*max(abs(expected),1)
 report=dict(status='PASS',dispatches_checked=len(rs),process_direction_profiles_checked=len(accepted),source_counter_formulas_independently_recomputed=True,same_row_timestamps=True,no_R07_latency_denominator=True,read_write_kept_separate=True,shape_gate_verified=True,over_100_values_preserved=True,outputs={n:sha(out/n) for n in ['DISPATCH_BANDWIDTH.csv','DISPATCH_BANDWIDTH.jsonl','PROCESS_BANDWIDTH.json']})
 (out/'INDEPENDENT_AUDIT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();main(a.root.resolve())
