"""Independent resource arithmetic, FX metadata, membership and sharing audit."""
from pathlib import Path
import csv,json,hashlib,collections,re,math,time
from decimal import Decimal,localcontext
ROOT=Path(__file__).parents[2];RUN=ROOT.parents[2]
def check(x,m):
 if not x:raise RuntimeError(m)
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def jl(p):
 with Path(p).open() as f:
  for l in f:
   if l.strip():yield json.loads(l)
def csvs(p):
 with Path(p).open() as f:yield from csv.DictReader(f)
def q(n,d,m=100):
 if n is None or d in (None,0):return None
 with localcontext() as ctx:ctx.prec=40;return Decimal(n)*m/Decimal(d)
def metric_values(a):
 c=a['counters'];v={}
 def group(prefix):
  keys=[k for k in c if re.fullmatch(re.escape(prefix)+r'\[\d+\]',k)]
  return sum(c[k] for k in keys) if keys and all(c[k] is not None for k in keys) else None
 def groups(*keys):
  values=[group(k) for k in keys]
  return sum(values) if all(x is not None for x in values) else None
 g=c.get('GRBM_GUI_ACTIVE')
 if a['counter_mode']=='pmc':
  v.update(GPUBusy_pct=q(g,c.get('GRBM_COUNT')),VALUBusy_pct=q(c.get('SQ_ACTIVE_INST_VALU'),None if g is None else g*320,400),LDSBankConflict_pct=q(c.get('SQ_LDS_BANK_CONFLICT'),None if g is None else g*80))
  h=group('TCC_HIT');m=group('TCC_MISS');v.update(L2_hit_count=h,L2_miss_count=m,L2CacheHit_pct=q(h,None if h is None or m is None else h+m))
  for k in ['SQ_INSTS_VALU','SQ_INSTS_VMEM_RD','SQ_INSTS_VMEM_WR','SQ_INSTS_LDS','SQ_WAIT_INST_LDS']:v[k]=c.get(k)
  for k in ['grd','wgr','lds','scr','arch_vgpr','accum_vgpr','sgpr','wave_size']:v['dispatch_'+k]=int(a['native_'+k])
  v['achieved_occupancy_pct']=None
 elif a['counter_mode']=='pmc_read':
  r=groups('TCC_EA_RDREQ','TCC_EA1_RDREQ');s=groups('TCC_EA_RDREQ_32B','TCC_EA1_RDREQ_32B');v.update(read_requests=r,read_requests_32B=s,native_DRAM_read_bytes=(64*r-32*s if r is not None and s is not None and 0<=s<=r else None),flat_read_wavefronts=group('TA_FLAT_READ_WAVEFRONTS'))
 else:
  r=groups('TCC_EA_WRREQ','TCC_EA1_WRREQ');s=groups('TCC_EA_WRREQ_64B','TCC_EA1_WRREQ_64B');v.update(write_requests=r,write_requests_64B=s,native_DRAM_write_bytes=(32*r+32*s if r is not None and s is not None and 0<=s<=r else None),flat_write_wavefronts=group('TA_FLAT_WRITE_WAVEFRONTS'))
 return v
def main():
 start=time.monotonic();out=ROOT/'model/resource_model_001';m=read(out/'traffic_resource_model.json');check(m['status']=='complete_pending_independent_audit','model checkpoint')
 for r in [*m['source_records'],m['family_accounting'],m['traffic_resource_attachment']]:check(sha(r['path'])==r['sha256'],'sealed input hash '+r['path'])
 index=read(ROOT/'normalized/accepted_captures.json');attributes={}
 for cap in index['captures']:
  n=read(cap['normalization_manifest']['path']);a=read(Path(cap['normalization_manifest']['path']).parent/'INDEPENDENT_AUDIT.json');check(a['status']=='complete','independent native-chain audit')
  for row in jl(n['dispatch_attributes']['path']):check(row['physical_attribute_id'] not in attributes,'physical duplicate');attributes[row['physical_attribute_id']]=row
 values={i:metric_values(a) for i,a in attributes.items()};expected_native={(i,name) for i,vs in values.items() for name in vs};seen_native=set();seen_static=set();seen_ids=set();counts=collections.Counter();classes=collections.Counter()
 fxroot=ROOT/'model/fx_templates_001';templates={t['template_id']:t for t in jl(fxroot/'fx_template_characterization.jsonl')};links={t['r07_process_range_id']:t for t in jl(fxroot/'process_fx_template_links.jsonl')};r02=RUN/'artifacts/R02';inventory=read(r02/'instrumentation/process_range_inventory.json')['rows'];widths={'torch.bfloat16':2,'torch.float16':2,'torch.float32':4,'torch.float64':8,'torch.int64':8,'torch.int32':4,'torch.int16':2,'torch.int8':1,'torch.uint8':1,'torch.bool':1}
 for t in templates.values():
  inv=inventory[t['r02_inventory_row']];check(json.loads(inv['fx_nodes'])==t['fx_nodes'],'exact template node membership')
  graph_path=next((r02/'fx/deep').glob('rank_'+str(inv['dp_rank'])+'_device_'+str(inv['dp_rank'])+'/'+inv['phase']+'_*_'+inv['layer_type']+'/nodes.json'));nodes={n['name']:n for n in read(graph_path)['nodes']};chosen=set(t['fx_nodes']);incoming={name for name,n in nodes.items() if name not in chosen and set(n.get('users',[]))&chosen};placeholders={name for name in chosen if nodes[name]['op']=='placeholder'};parameters={name for name in incoming|placeholders if 'parameters_' in nodes[name]['name'] or 'parameters_' in str(nodes[name]['target'])};outputs={name for name in chosen if any(u not in chosen for u in nodes[name].get('users',[])) or nodes[name]['op']=='output'};groups={'parameter':parameters,'input':(incoming|placeholders)-parameters,'output':outputs,'intermediate':{name for name in chosen if nodes[name]['op'] not in ['placeholder','output'] and name not in outputs}}
  for role,group in groups.items():
   check(set(t['role_totals'][role]['node_ids'])==group,'FX boundary role conservation');known=0;unknown=[]
   for name in group:
    n=nodes[name];shape=n.get('shape');width=widths.get(n.get('dtype'));concrete=isinstance(shape,list) and all(str(x).isdigit() for x in shape) and width is not None
    if concrete:known+=math.prod(int(x) for x in shape)*width
    else:unknown.append(name)
   totals=t['role_totals'][role];check(totals['known_tensor_bytes_lower_bound']==known and totals['bytes']==(known if not unknown else None) and set(totals['unknown_node_ids'])==set(unknown),'FX bytes/null arithmetic')
 for row in csvs(out/'traffic_resource_attachment.csv'):
  check(row['metric_id'] not in seen_ids,'duplicate metric row');seen_ids.add(row['metric_id']);counts[row['availability_state']]+=1;classes[row['evidence_class']]+=1
  check(row['runtime_run_id']==row['lineage_id']=='batch8-dp2-fresh-003' and row['dp_rank']==row['native_device'] in ['0','1'],'lineage/rank mapping')
  if row['record_kind']=='native_dispatch_metric':
   aid=row['physical_attribute_id'];check(aid in attributes,'unknown native attribute');a=attributes[aid];key=(aid,row['metric_name']);check(key in expected_native and key not in seen_native,'native metric universe');seen_native.add(key);value=values[aid][row['metric_name']]
   check((row['value']=='' if value is None else Decimal(row['value'])==Decimal(value)),'independent native metric arithmetic '+row['metric_name'])
   check(row['evidence_class']=='replay_projected' and bool(row['formula']) and bool(row['unit']),'metric evidence/unit/formula')
   for field in ['r07_process_range_id','r07_bound_target_id','r07_kernel_instance_id','request_id','dp_rank','native_device','counter_mode','observed_q_len','observed_kv_len','replay_q_len','replay_kv_len','runtime_shape_match']:check(row[field]==str(a[field]),'native attachment identity '+field)
   check(json.loads(row['logical_family_ids'])==a['logical_family_ids'],'shared logical family references')
   check(row['source_path']==a['raw_csv_path'] and row['source_sha256']==a['raw_csv_sha256'],'native byte provenance')
  else:
   check(row['record_kind']=='FX_template_characterization' and row['r07_process_range_id'] in links,'static process universe');link=links[row['r07_process_range_id']];t=templates[link['template_id']];name=row['metric_name'];key=(row['r07_process_range_id'],name);check(key not in seen_static,'static duplicate');seen_static.add(key)
   if name=='exact_runtime_FLOPs':check(row['value']=='' and row['availability_state']=='unavailable','unsupported FLOPs preserved')
   else:
    role,kind=name.removeprefix('fx_template_').split('_',1);total=t['role_totals'][role];expected=total['bytes'] if kind=='bytes' else total['known_tensor_bytes_lower_bound'];check(row['value']==('' if expected is None else str(expected)),'FX static attachment value');check(row['evidence_class']=='derived_static','static/replay distinction')
   check(row['r07_bound_target_id']==link['r07_bound_target_id'] and row['request_id']==link['request_id'],'static exact logical attachment')
 check(seen_native==expected_native,'complete native metrics');check(len(seen_static)==len(links)*9,'complete static/unavailable process rows');check(len(seen_ids)==m['metric_rows'] and dict(counts)==m['availability_counts'] and dict(classes)==m['evidence_class_counts'],'metric manifest conservation')
 accounting=read(out/'family_accounting.json');logical=read(ROOT/'plans/logical_plan.json');check(len(accounting['families'])==len(logical['r06_inventory'])==89,'complete family inventory');check(len(accounting['selected_logical_targets'])==sum(len(f['targets']) for f in logical['selected_families']),'selected logical target universe')
 by_source={(f['r06_plan']['stable_family_id'],t['source_r06_target_id']):t for f in logical['selected_families'] for t in f['targets']}
 for t in accounting['selected_logical_targets']:
  old=by_source[(t['stable_family_id'],t['source_r06_target_id'])];check(t['r07_bound_target_id']==old['r07_bound_target_id'],'family target identity')
  if old['state']=='requires_fresh_r08_pmc':
   matched=[attributes[x] for x in t['physical_attribute_ids']];check({x['counter_mode'] for x in matched}=={'pmc','pmc_read','pmc_write'} and len(matched)==3*len(old['exact_literal_kernel_ids']),'complete required target modes')
  else:check(not t['physical_attribute_ids'] and t['terminal_state']=='explicit_no_direct_kernel','explicit no-kernel target')
 check(not m['replay_timing_used_as_latency'] and not m['static_bytes_are_measured_traffic'],'unique clock and traffic semantics')
 report={'status':'complete','independent_audit':True,'model_manifest_sha256':sha(out/'traffic_resource_model.json'),'auditor_sha256':sha(Path(__file__)),'metric_rows':len(seen_ids),'native_metric_rows':len(seen_native),'static_or_unavailable_metric_rows':len(seen_static),'physical_attribute_rows':len(attributes),'FX_templates_independently_recomputed':len(templates),'R07_process_links':len(links),'families':89,'selected_families':32,'selected_logical_targets':len(by_source),'runtime_shape_match_counts':dict(collections.Counter(str(a['runtime_shape_match']) for a in attributes.values())),'unit_formula_value_and_null_checks':True,'physical_sharing_conserved':True,'replay_time_used_as_latency':False,'elapsed_seconds':time.monotonic()-start}
 with (out/'RESOURCE_MODEL_INDEPENDENT_AUDIT.json').open('x') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
 print('R08_RESOURCE_INDEPENDENT_AUDIT_COMPLETE',len(seen_ids),round(time.monotonic()-start,2),flush=True)
if __name__=='__main__':main()
