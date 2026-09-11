#!/usr/bin/env python3
"""Inventory every observed overlap segment and classify stratified resource windows."""
from pathlib import Path
import argparse,json
from expand_process_and_concurrency_examples import read,dump

def main(root):
 out=root/'analysis_reports';inventory={}
 for key in ['single_batch','batch8']:
  d=read(root/'revised'/key/'CONCURRENCY_UTILIZATION.html');rows=[]
  refs=[] if key=='single_batch' else [json.loads(x) for x in (root/'batch8_bandwidth/DISPATCH_BANDWIDTH.jsonl').read_text().splitlines()]
  valid={r['r07_kernel_instance_id'] for r in refs if r['r07_projection_permitted']}
  for c in sorted((x for x in d['counts'] if x[3]=='kernel' and x[4]>1),key=lambda x:(x[0],x[2])):
   a,b,dev,_,peak=c;ks=[k for k in d['kernels'] if k[3]==dev and k[1]<b and k[2]>a]
   rows.append({'begin_ns':a,'end_ns':b,'device':dev,'peak':peak,'overlap_ns':b-a,'kernel_ids':[k[6] for k in ks],'kernel_names':sorted({k[5] for k in ks}),'process_ids':sorted({k[0] for k in ks}),'matched_resource_kernels':sum(k[6] in valid or bool(d['resources'][k[0]].get('l2_samples')) for k in ks)})
  assert sum(x['overlap_ns'] for x in rows)==sum(x[1]-x[0] for x in d['counts'] if x[3]=='kernel' and x[4]>1)
  inventory[key]={'origin_ns':d['origin_ns'],'segments':rows,'count':len(rows),'duration_ns':sum(x['overlap_ns'] for x in rows),'resource_matched_segments':sum(x['matched_resource_kernels']>0 for x in rows)}
 dump(out/'data/ALL_KERNEL_OVERLAPS.json',inventory)
 print('All overlap segments:',[(k,v['count'],v['resource_matched_segments']) for k,v in inventory.items()],flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();main(a.root.resolve())
