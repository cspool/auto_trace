"""Lossless R02 FX template characterization attached to exact R07 identities."""
from pathlib import Path
import sys
ROOT=Path(__file__).parents[2]
sys.path.insert(0,str(ROOT/'raw/runtime_tools/revision_016'))
from r08_native import *
import collections,csv,math,time
WIDTHS={'torch.bfloat16':2,'torch.float16':2,'torch.float32':4,'torch.float64':8,'torch.int64':8,'torch.int32':4,'torch.int16':2,'torch.int8':1,'torch.uint8':1,'torch.bool':1}
def main():
    out=output_path(ROOT/'model/fx_templates_001');require(not out.exists(),'immutable FX model');out.mkdir()
    inventory=read(R02_INVENTORY);templates={};graphs={};sources=[source_record(R02_INVENTORY)]
    for p in sorted((R02/'fx/deep').glob('*/*/metadata.json')):
        meta=read(p);nodesfile=p.with_name('nodes.json');require(sha(nodesfile)==meta['nodes_sha256'],'sealed FX node hash')
        graph=read(nodesfile);key=(meta['dp_rank'],meta['phase'],meta['layer_type']);require(key not in graphs,'unique FX template')
        graphs[key]={'metadata':meta,'nodes':{n['name']:n for n in graph['nodes']},'path':nodesfile,'sha256':sha(nodesfile)};sources += [source_record(p),source_record(nodesfile)]
    for i,row in enumerate(inventory['rows']):
        key=(row['dp_rank'],row['phase'],row['layer_type'],row['process_id'],row['fragment_id']);require(key not in templates,'unique R02 process template')
        g=graphs[key[:3]];names=json.loads(row['fx_nodes']);selected=set(names);nodes=g['nodes'];missing=[n for n in names if n not in nodes]
        require(not missing,'R02 inventory node absent from exact graph')
        # Edges are inherited from sealed FX users; no text or timing heuristics.
        incoming={name for name,n in nodes.items() if name not in selected and set(n.get('users',[]))&selected}
        placeholders={name for name in selected if nodes[name]['op']=='placeholder'}
        parameter={name for name in incoming|placeholders if 'parameters_' in nodes[name]['name'] or 'parameters_' in str(nodes[name]['target'])}
        inputs=(incoming|placeholders)-parameter
        outputs={name for name in selected if any(u not in selected for u in nodes[name].get('users',[])) or nodes[name]['op']=='output'}
        intermediates={name for name in selected if nodes[name]['op'] not in ['placeholder','output'] and name not in outputs}
        groups={'input':inputs,'parameter':parameter,'output':outputs,'intermediate':intermediates}
        counts={};details=[]
        for role,identities in groups.items():
            known_bytes=0;known_elements=0;unknown=[]
            for name in sorted(identities):
                n=nodes[name];shape=n.get('shape');dtype=n.get('dtype');width=WIDTHS.get(dtype)
                concrete=isinstance(shape,list) and all(str(d).isdigit() for d in shape) and width is not None
                elements=math.prod(int(d) for d in shape) if concrete else None
                size=elements*width if concrete else None
                if concrete:known_elements+=elements;known_bytes+=size
                else:unknown.append(name)
                details.append({'node_id':name,'role':role,'shape':shape,'dtype':dtype,'dtype_width_bytes':width,'elements':elements,'bytes':size,'availability_state':'available_static_tensor_metadata' if concrete else 'unavailable_opaque_or_symbolic_tensor_metadata','fx_nodes_path':str(g['path']),'fx_nodes_sha256':g['sha256']})
            counts[role]={'bytes':known_bytes if not unknown else None,'elements':known_elements if not unknown else None,'known_tensor_bytes_lower_bound':known_bytes,'known_tensor_elements_lower_bound':known_elements,'unknown_node_ids':unknown,'node_ids':sorted(identities)}
        template={'template_id':hashlib.sha256(json.dumps(key).encode()).hexdigest(),'key':key,'r02_inventory_row':i,'r02_exact_marker':row['nvtx_range_name'],'fx_metadata_shape':{'q_len':g['metadata']['q_len'],'kv_len':g['metadata']['kv_len'],'example_inputs':g['metadata']['example_inputs']},'fx_nodes':names,'tensor_metadata':details,'role_totals':counts,'evidence_class':'derived_static','measurement_claim':'FX template visible tensor size only; no DRAM measurement or alias-deduplicated allocation claim','formula':'product(concrete tensor dimensions)*declared dtype width; each unique FX node counted once per role','aggregation_rule':'template characterization is non-additive across requests/layers and nested process templates; runtime batch tensor multiplicity is not inferred','flops':None,'flops_availability_reason':'opaque/custom-op and fused graph semantics do not support a complete exact FLOP total'}
        templates[key]=template
    with (out/'fx_template_characterization.jsonl').open('x') as f:
        for key,t in sorted(templates.items()):f.write(json.dumps(t,sort_keys=True,separators=(',',':'))+'\n')
    r07=RUN/'artifacts/R07/resume-042';processfile=r07/'trace/process_ranges.csv';processhash=sha(processfile)
    rows=[]
    with processfile.open() as f:
        for process in csv.DictReader(f):
            key=(int(process['dp_rank']),process['phase'],process['layer_type'],process['process_id'],process['fragment_id']);template=templates.get(key)
            require(template is not None,'R07 process missing exact R02 semantic template '+str(key))
            rows.append({'r07_process_range_id':process['process_range_id'],'r07_bound_target_id':process['canonical_target_id'],'request_id':process['request_id'],'dp_rank':int(process['dp_rank']),'native_device':int(process['native_device']),'layer_idx':int(process['layer_idx']),'phase':process['phase'],'process_id':process['process_id'],'fragment_id':process['fragment_id'],'template_id':template['template_id'],'r02_inventory_row':template['r02_inventory_row'],'join_rule':'exact rank/phase/layer_type/process_id/fragment_id; R02 representative template only','r07_q_len':int(process['q_len']),'r07_kv_len':int(process['kv_len']),'r02_q_len':template['fx_metadata_shape']['q_len'],'r02_kv_len':template['fx_metadata_shape']['kv_len'],'runtime_shape_equivalence_claimed':False,'r07_process_sha256':processhash,'r02_inventory_sha256':sha(R02_INVENTORY) if not rows else rows[0]['r02_inventory_sha256'],'evidence_class':'derived_static','template_totals_are_current_measured_traffic':False,'direct_kernel_state':process['ownership_state'],'owned_kernel_count':int(process['owned_kernel_count'])})
    require(len(rows)==12544,'complete exact process membership')
    with (out/'process_fx_template_links.jsonl').open('x') as f:
        for row in rows:f.write(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n')
    save(out/'FX_MODEL_COMPLETE.json',{'status':'complete','template_count':len(templates),'R07_process_count':len(rows),'rank_counts':dict(collections.Counter(x['dp_rank'] for x in rows)),'sources':sources+[source_record(processfile)],'tools':[source_record(Path(__file__))],'outputs':[source_record(out/'fx_template_characterization.jsonl'),source_record(out/'process_fx_template_links.jsonl')],'all_template_fields_static':True,'observed_or_replay_latency_used':False,'unavailable_opaque_values_preserved':True})
    print('FX_MODEL_COMPLETE',len(templates),len(rows),flush=True)
if __name__=='__main__':main()
