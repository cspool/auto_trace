"""Build complete family accounting and attributable replay/static resource model."""
from pathlib import Path
import sys
ROOT=Path(__file__).parents[2]
sys.path[:0]=[str(ROOT/'tools/revision_011'),str(Path(__file__).parent)]
from r08_native import *
from metric_rules import derive,RULE_VERSION
import csv,collections,time
PROFILE='3b4c952063f48ae662b48b5ce9d8fd76e0ac4d74e170bdb1839ae8b1aaa23cce'
def jsonlines(p):
    with Path(p).open() as f:
        for l in f:
            if l.strip():yield json.loads(l)
def main():
    indexpath=ROOT/'normalized/accepted_captures.json';index=read(indexpath);plan=read(ROOT/'plans/r08_capture_plan.json');logical=read(ROOT/'plans/logical_plan.json')
    require(index['status']=='complete' and len(index['captures'])==len(plan['physical_captures']),'all physical captures accepted')
    require({x['segment_id'] for x in index['captures']}=={x['segment_id'] for x in plan['physical_captures']},'capture plan conservation')
    out=output_path(ROOT/'model/resource_model_001');require(not out.exists(),'immutable model');out.mkdir()
    attrs=[];source_records=[source_record(indexpath),source_record(ROOT/'plans/logical_plan.json'),source_record(ROOT/'plans/r08_capture_plan.json')]
    for item in index['captures']:
        p=Path(item['normalization_manifest']['path']);require(sha(p)==item['normalization_manifest']['sha256'],'normalization index hash');m=read(p);a=read(p.parent/'INDEPENDENT_AUDIT.json');require(a['status']=='complete' and a['normalization_manifest_sha256']==sha(p),'independent capture audit')
        source_records += [source_record(p),source_record(p.parent/'INDEPENDENT_AUDIT.json'),m['dispatch_attributes']]
        require(sha(m['dispatch_attributes']['path'])==m['dispatch_attributes']['sha256'],'attributable dispatch bytes');attrs.extend(jsonlines(m['dispatch_attributes']['path']))
    require(len({x['physical_attribute_id'] for x in attrs})==len(attrs),'unique physical attributes')
    attr_by_family_target=collections.defaultdict(list)
    for a in attrs:
        for fid in a['logical_family_ids']:attr_by_family_target[(fid,a['source_r06_target_id'])].append(a)
    families=[];logical_targets=[];selected={f['r06_plan']['stable_family_id']:f for f in logical['selected_families']}
    for inv in logical['r06_inventory']:
        sid=inv['stable_family_id'];f=selected.get(sid)
        state='excluded_by_original_bounded_plan';counts=collections.Counter()
        if f:
            fid=f['r06_plan']['plan_id']
            for target in f['targets']:
                rows=attr_by_family_target[(fid,target['source_r06_target_id'])]
                if target['state']=='requires_fresh_r08_pmc':
                    require({a['counter_mode'] for a in rows}=={'pmc','pmc_read','pmc_write'},'required target counter modes')
                    expected=set(target['exact_literal_kernel_ids']);require(len(rows)==3*len(expected),'logical/physical multiplicity')
                    for mode in ['pmc','pmc_read','pmc_write']:require({a['r07_kernel_instance_id'] for a in rows if a['counter_mode']==mode}==expected,'exact target kernel set per mode')
                    state_target='complete_replay_projected'
                else:
                    require(target['state']=='explicit_no_direct_kernel_in_observed_r07' and not rows,'explicit no-kernel state');state_target='explicit_no_direct_kernel'
                counts[state_target]+=1
                logical_targets.append({**target,'stable_family_id':sid,'logical_family_id':fid,'terminal_state':state_target,'physical_attribute_ids':sorted(a['physical_attribute_id'] for a in rows),'physical_sharing_rule':'attributes referenced by stable ID; no multiplication across family aliases'})
            state='complete_replay_projected_with_explicit_no_kernel_states' if counts['complete_replay_projected'] else 'explicit_no_direct_kernel'
        elif inv['family_state'] in ['explicit_no_kernel','metadata_only_context_parent']:state=inv['family_state']
        families.append({**inv,'r08_terminal_state':state,'selected_target_terminal_counts':dict(counts),'r08_unavailable_reason':inv['exclusion_reason'] if not f else '', 'same_R06_selection_preserved':True})
    require(len(families)==89 and len(selected)==32,'full bounded family accounting')
    save(out/'family_accounting.json',{'inventory_count':89,'selected_count':32,'families':families,'selected_logical_targets':logical_targets})
    fxroot=ROOT/'model/fx_templates_001';fxmanifest=read(fxroot/'FX_MODEL_COMPLETE.json');require(fxmanifest['status']=='complete','FX model checkpoint')
    for rec in fxmanifest['outputs']:require(sha(rec['path'])==rec['sha256'],'FX model bytes')
    templates={x['template_id']:x for x in jsonlines(fxroot/'fx_template_characterization.jsonl')};links=list(jsonlines(fxroot/'process_fx_template_links.jsonl'))
    source_records += [source_record(fxroot/'FX_MODEL_COMPLETE.json'),*fxmanifest['outputs']]
    capability=ROOT/'preflight/native_probe_003/CAPABILITY_PROBE_COMPLETE.json';capsha=sha(capability)
    catalogs=[Path('/opt/dtk-26.04-DCC2602-0317/rocprofiler/lib/rocprofiler')/x for x in ['metrics.xml','gfx_metrics.xml']]
    for p in catalogs:source_records.append(source_record(p))
    source_records.append(source_record(capability))
    fields=['schema_version','runtime_run_id','lineage_id','trace_profile_sha256','metric_id','record_kind','r07_process_range_id','r07_bound_target_id','r07_kernel_instance_id','request_id','dp_rank','native_device','logical_family_ids','physical_attribute_id','counter_mode','observed_q_len','observed_kv_len','replay_q_len','replay_kv_len','runtime_shape_match','metric_name','value','unit','formula','assumptions','aggregation_rule','rule_version','evidence_class','availability_state','availability_reason','source_path','source_sha256','source_row_id','capability_path','capability_sha256']
    count=0;availability=collections.Counter();classes=collections.Counter();metricids=set()
    path=out/'traffic_resource_attachment.csv'
    with path.open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');writer.writeheader()
        def emit(base,metric):
            nonlocal count
            identity=base['source_row_id']+':'+metric['metric_name'];mid=hashlib.sha256(identity.encode()).hexdigest();require(mid not in metricids,'metric ID duplicate');metricids.add(mid)
            row={k:'' for k in fields};row.update(schema_version=1,runtime_run_id='batch8-dp2-fresh-003',lineage_id='batch8-dp2-fresh-003',trace_profile_sha256=PROFILE,metric_id=mid,capability_path=str(capability),capability_sha256=capsha);row.update(base);row.update(metric);writer.writerow(row);count+=1;availability[row['availability_state']]+=1;classes[row['evidence_class']]+=1
        for a in sorted(attrs,key=lambda a:(a['r07_kernel_instance_id'],a['counter_mode'])):
            base={k:a[k] for k in ['r07_process_range_id','r07_bound_target_id','r07_kernel_instance_id','request_id','dp_rank','native_device','physical_attribute_id','counter_mode','observed_q_len','observed_kv_len','replay_q_len','replay_kv_len','runtime_shape_match']};base.update(record_kind='native_dispatch_metric',logical_family_ids=json.dumps(a['logical_family_ids'],separators=(',',':')),source_path=a['raw_csv_path'],source_sha256=a['raw_csv_sha256'],source_row_id=a['physical_attribute_id'])
            for metric in derive(a):emit(base,metric)
        fxsource=fxroot/'process_fx_template_links.jsonl';fxsha=sha(fxsource)
        for link in links:
            template=templates[link['template_id']];base={k:link[k] for k in ['r07_process_range_id','r07_bound_target_id','request_id','dp_rank','native_device']};base.update(record_kind='FX_template_characterization',source_path=str(fxsource),source_sha256=fxsha,source_row_id=link['r07_process_range_id']+':'+link['template_id'])
            for role,total in template['role_totals'].items():
                for label,value in [('bytes',total['bytes']),('known_bytes_lower_bound',total['known_tensor_bytes_lower_bound'])]:
                    emit(base,{'metric_name':'fx_template_'+role+'_'+label,'value':value,'unit':'bytes','formula':template['formula'],'assumptions':template['measurement_claim']+'; template_id='+link['template_id']+'; runtime tensor shape equivalence not claimed','aggregation_rule':template['aggregation_rule'],'rule_version':'fx-template-1','evidence_class':'derived_static','availability_state':'available_static_template' if value is not None else 'unavailable','availability_reason':'' if value is not None else 'opaque_or_symbolic_tensor_metadata'})
            emit(base,{'metric_name':'exact_runtime_FLOPs','value':None,'unit':'FLOPs','formula':'unavailable','assumptions':'no unsupported FLOP total inferred','aggregation_rule':'not aggregatable','rule_version':'fx-template-1','evidence_class':'unavailable','availability_state':'unavailable','availability_reason':template['flops_availability_reason']})
    source_records += [source_record(Path(__file__)),source_record(Path(__file__).with_name('metric_rules.py'))]
    save(out/'traffic_resource_model.json',{'schema_version':1,'status':'complete_pending_independent_audit','runtime_run_id':'batch8-dp2-fresh-003','lineage_id':'batch8-dp2-fresh-003','trace_profile_sha256':PROFILE,'inventory_family_count':len(families),'selected_family_count':len(selected),'selected_logical_target_count':len(logical_targets),'attributable_physical_dispatch_rows':len(attrs),'runtime_shape_match_counts':dict(collections.Counter(str(a['runtime_shape_match']) for a in attrs)),'different_runtime_shapes_are_not_directly_comparable_R07_resource_measurements':True,'R07_process_rows':len(links),'metric_rows':count,'metric_schema':fields,'availability_counts':dict(availability),'evidence_class_counts':dict(classes),'native_counter_source':'lossless independently audited per-dispatch attributes referenced through accepted capture index','counter_modes_are_separate_replays':True,'replay_timing_used_as_latency':False,'static_bytes_are_measured_traffic':False,'shared_physical_attributes_counted_once':True,'observed_clock':'R07 attempt043 only','source_records':source_records,'family_accounting':source_record(out/'family_accounting.json'),'traffic_resource_attachment':source_record(path),'capability':source_record(capability),'rule_version':RULE_VERSION,'formula_file_sha256':sha(Path(__file__).with_name('metric_rules.py'))})
    print('R08_RESOURCE_MODEL_COMPLETE_PENDING_AUDIT',count,len(attrs),flush=True)
if __name__=='__main__':main()
