"""Issue the explicit recovered-prefix binding for the user-authorized continuation."""
from continuation_common import *
import shutil
import time

def main():
    area=RUN/'artifacts/R08/continuation_001'
    original=SNAPSHOT/'recovery_index/control/runtime_handoff_ledger.r01_r06_prefix.json'
    ledger=read(original)
    require(sha(original)=='86990e6156267c36334c31ae3ead733807d11286002d0fe00425b395d3397670','original ledger hash')
    require([e['source_goal'] for e in ledger['handoffs']]==[f'R{i:02d}' for i in range(1,7)],'prefix order')
    r07=RUN/'handoffs/R07.recovered.json';h=read(r07)
    require(sha(r07)==R07_HASH,'R07 bytes');validate_recovered_status(h)
    for e in ledger['handoffs']:
        p=SNAPSHOT/'recovery_index/handoffs'/(e['source_goal']+'.json')
        require(sha(p)==e['sha256'] and read(p)==e['payload'],'ledger original direct payload')
    ledger['handoffs'].append({'source_goal':'R07','status':h['status'],'path':str(r07),'sha256':R07_HASH,'payload':h,'admission':'explicit_complete_recovered_offline_adapter'})
    ledger['continuation']={'historical_prefix_path':str(original),'historical_prefix_sha256':sha(original),'historical_collector_termination_claimed':False,'original_handoffs_or_ledger_modified':False,'relocation_tool':str(Path(__file__).with_name('continuation_common.py')),'relocation_tool_sha256':sha(Path(__file__).with_name('continuation_common.py'))}
    ledgerpath=area/'contract/recovered_prefix_ledger.json';write_new(ledgerpath,ledger)
    bulk=Path('/root/r08_continuation_001_bulk')
    require(not bulk.exists(),'new bulk root')
    capacity=shutil.disk_usage('/root')
    authorization={'schema_version':1,'runtime_run_id':RUN_ID,'runtime_goal':'R08','runtime_attempt_id':RUN_ID+'-R08-continuation-001','ordinal':1,'artifact_root':str(area),'handoff_output':str(RUN/'handoffs/R08.continuation.json'),'ledger_path':str(ledgerpath),'ledger_sha256':sha(ledgerpath),'bulk_storage_root':str(bulk),'root_filesystem_device':os.stat('/root').st_dev,'capacity_bytes':capacity.total,'free_bytes_at_issuance':capacity.free,'issued_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'authority':'User requested execution through R10 on current machine within original eight-hour allocation; local continuation controller issues exact paths.','paths':{str(area/key):str(bulk/key) for key in ['raw','normalized','model']},'attempt_roots_immutable':True}
    authpath=area/'authorization/bulk_storage_authorization.json';write_new(authpath,authorization)
    bulk.mkdir()
    for lexical,resolved in authorization['paths'].items():
        lexical=Path(lexical);resolved=Path(resolved)
        require(not lexical.exists() and not lexical.is_symlink() and not resolved.exists(),'entrypoint collision')
        resolved.mkdir();lexical.symlink_to(resolved,target_is_directory=True)
        require(lexical.resolve()==resolved and resolved.stat().st_dev==authorization['root_filesystem_device'],'bulk binding')
    assignment={'status':'assigned_predevice_pending','runtime_run_id':RUN_ID,'runtime_goal':'R08','runtime_artifact_root':str(area),'runtime_handoff_output':authorization['handoff_output'],'bulk_storage_authorization_path':str(authpath),'bulk_storage_authorization_sha256':sha(authpath),'cumulative_runtime_ledger_path':str(ledgerpath),'cumulative_runtime_ledger_sha256':sha(ledgerpath),'original_R07_status_preserved':True,'deadline_utc':'2026-09-08T12:18:09Z','device_or_model_execution_authorized_by_this_assignment':False,'device_gate':'A subsequent complete CPU predevice report and separate fresh device capability checkpoint are required.'}
    write_new(area/'authorization/continuation_assignment.json',assignment)
    print('R08_ASSIGNED_WITH_EXPLICIT_RECOVERY_BINDING',flush=True)

if __name__=='__main__':main()
