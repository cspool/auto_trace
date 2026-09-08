"""Resolve the sealed R06 family universe onto the recovered R07 exact owners."""
import csv
from collections import Counter, defaultdict
from continuation_common import *

def main():
    require(read(Path(__file__).parent/'RECOVERED_R07_ADMISSION.json')['status']=='admitted_recovered_r07','R07 admission')
    require(read(Path(__file__).parent/'predecessor_validations/R06.json')['status']=='complete','R06 admission')
    r06=RUN/'artifacts/R06';r07=RUN/'artifacts/R07/resume-042'
    h=read(RUN/'handoffs/R06.json')
    plan_record=h['hardware_family_planning']['plan_json'];verify_record(plan_record,owner=r06)
    inventory_record=h['hardware_family_planning']['inventory_csv'];verify_record(inventory_record,owner=r06)
    plan=read(resolve_source(plan_record['path']))
    with resolve_source(inventory_record['path']).open() as f:inventory=list(csv.DictReader(f))
    require(len(inventory)==89 and len(plan['selected_families'])==32,'complete R06 family inventory')
    sidecar=read(r07/'contract/r07_bound_target_sidecar.json')
    bound_by_source={r['source_r06_target_id']:r for r in sidecar['records'] if 'source_r06_target_id' in r}
    with (r07/'trace/process_ranges.csv').open() as f:processes={r['canonical_target_id']:r for r in csv.DictReader(f)}
    kernels=defaultdict(list)
    with (r07/'trace/strict_owned_kernels.csv').open() as f:
        for row in csv.DictReader(f):kernels[row['owner_canonical_target_id']].append(row)
    families=[];grouped=defaultdict(list);states=Counter()
    for family in plan['selected_families']:
        literal=family['kernel_name_filter_literal']
        require(hashlib.sha256(literal.encode()).hexdigest()==family['kernel_name_filter_literal_sha256'],'R06 literal hash')
        targets=[]
        for source_id in family['represented_target_ids']:
            require(source_id in bound_by_source,'missing logical-to-bound target '+source_id)
            bound=bound_by_source[source_id];key=bound['canonical_target_id'];p=processes[key]
            exact=[k for k in kernels[key] if k['native_kernel_name']==literal]
            if not kernels[key]:
                require(int(p['owned_kernel_count'])==0,'no-kernel conservation')
                state='explicit_no_direct_kernel_in_observed_r07'
            elif exact:
                state='requires_fresh_r08_pmc'
            else:
                raise ValueError('R06 selected literal differs from observed nonempty owner: '+source_id)
            targets.append({'source_r06_target_id':source_id,'source_r06_target_sha256':bound['source_r06_target_sha256'],'r07_bound_target_id':key,'r07_process_range_id':p['process_range_id'],'request_id':p['request_id'],'phase':p['phase'],'dp_rank':int(p['dp_rank']),'native_device':int(p['native_device']),'state':state,'observed_owned_kernel_count':len(kernels[key]),'exact_literal_kernel_ids':[k['kernel_instance_id'] for k in exact]})
        require(len(targets)==family['represented_target_count'],'represented targets')
        pending=[x for x in targets if x['state']=='requires_fresh_r08_pmc']
        state='requires_fresh_r08_pmc' if pending else 'explicit_no_direct_kernel_in_observed_r07'
        if pending:grouped[literal].append(family['plan_id'])
        families.append({'r06_plan':family,'current_state':state,'targets':targets,'pending_target_count':len(pending),'explicit_no_direct_kernel_target_count':len(targets)-len(pending)})
        states[state]+=1
    output=RUN/'artifacts/R08/continuation_001/plans'
    record={'schema_version':1,'status':'logical_plan_resolved_pending_predevice_and_capability_gates','runtime_run_id':RUN_ID,'runtime_goal':'R08','lineage_id':RUN_ID,'r07_recovery_status':'complete_recovered_offline','r06_plan_sha256':plan_record['sha256'],'r06_inventory_sha256':inventory_record['sha256'],'r07_bound_sidecar_sha256':sha(r07/'contract/r07_bound_target_sidecar.json'),'r07_process_ranges_sha256':sha(r07/'trace/process_ranges.csv'),'r07_strict_kernels_sha256':sha(r07/'trace/strict_owned_kernels.csv'),'r06_inventory':inventory,'selected_families':families,'selected_family_state_counts':dict(states),'physical_literal_groups':[{'literal':k,'logical_family_ids':v,'counter_modes_pending_current_capability':['pmc','pmc_read','pmc_write']} for k,v in grouped.items()],'selected_family_count':32,'inventory_count':89,'no_kernel_evidence_basis':'zero strictly owned native kernels for every explicitly recorded exact R07 bound process; no replay metric manufactured','observed_r07_time_changed':False,'model_or_device_access_performed':False,'capture_authorized':False,'tool_sha256':sha(__file__)}
    write_new(output/'logical_plan.json',record)
    print('R08_LOGICAL_PLAN',dict(states),'physical_literals',len(grouped),flush=True)

if __name__=='__main__':main()
