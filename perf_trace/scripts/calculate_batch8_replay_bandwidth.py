#!/usr/bin/env python3
"""Calculate per-native-dispatch directional replay bandwidth from restored R08.
No R07 elapsed times enter the rate denominator. No cross-pass read/write sum.
"""
from pathlib import Path
from decimal import Decimal,localcontext
import argparse,base64,collections,csv,gzip,hashlib,json,re

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def dump(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def counter_sum(c,prefix):
 values=[v for k,v in c.items() if re.fullmatch(re.escape(prefix)+r'\[\d+\]',k)]
 if not values or any(v is None or not isinstance(v,int) or v<0 for v in values):return None
 return sum(values)
def sum_channels(c,prefixes):
 values=[counter_sum(c,p) for p in prefixes]
 return None if any(v is None for v in values) else sum(values)
def byte_count(a):
 c=a['counters'];direction='read' if a['counter_mode']=='pmc_read' else 'write';tag='RD' if direction=='read' else 'WR'
 requests=sum_channels(c,[f'TCC_EA_{tag}REQ',f'TCC_EA1_{tag}REQ']);kind='32B' if direction=='read' else '64B'
 sized=sum_channels(c,[f'TCC_EA_{tag}REQ_{kind}',f'TCC_EA1_{tag}REQ_{kind}'])
 if requests is None or sized is None or sized>requests:return None,'missing_null_or_inconsistent_native_counters'
 return (32*sized+64*(requests-sized) if direction=='read' else 32*(requests-sized)+64*sized),''
def original_metrics(root):
 p=root/'batch8/site/acceptance/HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html';s=p.read_text();d=json.loads(s.split('<script>const PAYLOAD=',1)[1].split(';</script>',1)[0]);pack=d['tables']['traffic_resource_attachment'];out={}
 for b in pack['blocks']:
  for cells in json.loads(gzip.decompress(base64.b64decode(b))):
   r=dict(pack['constants'],**dict(zip(pack['fields'],cells)))
   if r['metric_name'] not in ['native_DRAM_read_bytes','native_DRAM_write_bytes']:continue
   k=(r['physical_attribute_id'],r['metric_name']);assert k not in out
   out[k]=r
 return out,dict(path=str(p),sha256=sha(p))
def main(root):
 out=root/'batch8_bandwidth';manifest=json.loads((out/'RESTORE_MANIFEST.json').read_text());reference=json.loads((root/'hardware_docs/HARDWARE_REFERENCE.json').read_text());B=Decimal(str(reference['bandwidth_reference']['value']));assert reference['bandwidth_reference']['unit']=='GB/s' and B.is_finite() and B>0
 expected,original=original_metrics(root);all_rows=[];seen=set();comparison=0;attrs_total=0
 for f in manifest['restored']:
  if not f['path'].endswith('/dispatch_attributes.jsonl'):continue
  p=Path(f['local_path']);assert sha(p)==f['sha256']
  with p.open() as handle:
   for line_no,line in enumerate(handle,1):
    a=json.loads(line);attrs_total+=1
    if a['counter_mode'] not in ['pmc_read','pmc_write']:continue
    ident=a['physical_attribute_id'];assert ident not in seen;seen.add(ident)
    direction='read' if a['counter_mode']=='pmc_read' else 'write';total,reason=byte_count(a)
    begin=int(a['native_signature_begin_monotonic_ns']);end=int(a['native_signature_end_monotonic_ns']);dt=end-begin
    if dt<=0:reason='nonpositive_native_gpu_duration'
    metric=expected[(ident,'native_DRAM_'+direction+'_bytes')];comparison+=1
    assert metric['r07_process_range_id']==a['r07_process_range_id'] and metric['r07_kernel_instance_id']==a['r07_kernel_instance_id']
    assert (metric['value']=='' if total is None else Decimal(metric['value'])==total),(ident,total,metric['value'])
    valid=total is not None and dt>0
    with localcontext() as ctx:
     ctx.prec=40;gbps=Decimal(total)/Decimal(dt) if valid else None;percent=gbps/B*100 if valid else None
    shape=a['runtime_shape_match'] is True
    r=dict(physical_attribute_id=ident,r07_process_range_id=a['r07_process_range_id'],r07_kernel_instance_id=a['r07_kernel_instance_id'],segment_id=a['segment_id'],capture_attempt=a['capture_attempt'],direction=direction,device=a['native_device'],request_id=a['request_id'],kernel_name=a['kernel_name_filter_literal'],begin_monotonic_ns=str(begin),end_monotonic_ns=str(end),duration_ns=dt,bytes=total,bandwidth_GBps=str(gbps) if valid else None,reference_pct=str(percent) if valid else None,above_reference=bool(valid and percent>100),runtime_shape_match=shape,observed_q_len=a['observed_q_len'],observed_kv_len=a['observed_kv_len'],replay_q_len=a['replay_q_len'],replay_kv_len=a['replay_kv_len'],calculation_state='calculated' if valid else 'unavailable',reason=reason,r07_projection_permitted=bool(valid and shape),evidence_class='replay_directional_bandwidth_normalized_to_document_reference',counter_mode=a['counter_mode'],source_dispatch_path=f['path'],source_dispatch_sha256=f['sha256'],source_line=line_no,raw_csv_path=a['raw_csv_path'],raw_csv_sha256=a['raw_csv_sha256'],raw_database_sha256=a['raw_database_sha256'],gpu_timestamp_pair_matches_hipops=a.get('GPU_timestamp_pair_equal_after_CONFIG_conversion'),reference_GBps=str(B))
    all_rows.append(r)
 assert len(expected)==comparison,'Unmatched source metrics'
 all_rows.sort(key=lambda r:(r['segment_id'],r['physical_attribute_id']))
 with (out/'DISPATCH_BANDWIDTH.jsonl').open('w') as f:
  for r in all_rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
 with (out/'DISPATCH_BANDWIDTH.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(all_rows[0]));w.writeheader();w.writerows(all_rows)
 groups=collections.defaultdict(list)
 for r in all_rows:groups[(r['r07_process_range_id'],r['direction'])].append(r)
 processes={}
 for (ident,direction),rs in groups.items():
  accepted=[r for r in rs if r['r07_projection_permitted']];same_shape=all(r['runtime_shape_match'] for r in rs);complete=len(accepted)==len(rs)
  # Do not average mixed shapes or silently omit unavailable counters.
  value=None;rate=None
  if complete:
   with localcontext() as ctx:
    ctx.prec=40;rate=Decimal(sum(r['bytes'] for r in rs))/Decimal(sum(r['duration_ns'] for r in rs));value=rate/B*100
  processes.setdefault(ident,{})[direction]=dict(reference_pct=float(value) if value is not None else None,bandwidth_GBps=float(rate) if rate is not None else None,bytes=sum(r['bytes'] for r in rs) if complete else None,replay_duration_sum_ns=sum(r['duration_ns'] for r in rs) if complete else None,dispatch_count=len(rs),valid_dispatch_count=len(accepted),runtime_shape_match=same_shape,state='available_replay_reference' if complete else 'unavailable_shape_mismatch' if not same_shape else 'unavailable_counters_or_duration',physical_attribute_ids=[r['physical_attribute_id'] for r in rs],selected_kernel_scope_only=True,aggregation='sum unique same-direction dispatch bytes / sum their own replay durations; not R07 Process bandwidth and not whole-device live bandwidth',above_reference=bool(value is not None and value>100))
 summary={}
 for direction in ['read','write']:
  rs=[r for r in all_rows if r['direction']==direction];valid=[r for r in rs if r['calculation_state']=='calculated'];ps=[r for r in rs if r['r07_projection_permitted']];values=sorted(float(r['reference_pct']) for r in valid)
  summary[direction]=dict(dispatches=len(rs),calculated=len(valid),unavailable=len(rs)-len(valid),shape_matched_projectable=len(ps),above_reference=sum(r['above_reference'] for r in valid),min_reference_pct=values[0] if values else None,median_reference_pct=values[len(values)//2] if values else None,max_reference_pct=values[-1] if values else None,nonpositive_durations=sum(r['duration_ns']<=0 for r in rs),gpu_timestamp_mismatches=sum(r['gpu_timestamp_pair_matches_hipops'] is False for r in rs))
 dump(out/'PROCESS_BANDWIDTH.json',dict(schema_version=1,reference=reference,processes=processes,source_dispatch_table_sha256=sha(out/'DISPATCH_BANDWIDTH.jsonl'),original_R10_source=original))
 dump(out/'CALCULATION_AUDIT.json',dict(status='complete',fresh_acquisition=False,restored_attributes=attrs_total,exact_counter_byte_and_identity_checks=comparison,source_reference=reference,summary=summary,processes_with_evidence=len(processes),method=f'bytes / (same PMC row EndNs-BeginNs) / {B} * 100; bytes/ns = decimal GB/s',R07_duration_used=False,cross_pass_read_write_summed=False,raw_results_clipped_at_100=False,restoration_manifest_sha256=sha(out/'RESTORE_MANIFEST.json'),script_sha256=sha(Path(__file__)),outputs={n:sha(out/n) for n in ['DISPATCH_BANDWIDTH.csv','DISPATCH_BANDWIDTH.jsonl','PROCESS_BANDWIDTH.json']}))
 print(json.dumps(summary,indent=2),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);a=p.parse_args();main(a.root.resolve())
