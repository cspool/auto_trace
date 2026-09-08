"""Check every direct predecessor business-manifest entry using production relocation."""
import argparse
from continuation_common import *

def main():
    ap=argparse.ArgumentParser();ap.add_argument('stages',nargs='+');args=ap.parse_args()
    for stage in args.stages:
        require(stage in [f'R{i:02d}' for i in range(1,7)],'stage')
        hpath=RUN/'handoffs'/f'{stage}.json'
        snapshot_h=SNAPSHOT/f'recovery_index/handoffs/{stage}.json'
        require(sha(hpath)==sha(snapshot_h),'original handoff bytes '+stage)
        h=read(hpath)
        require(h['status']=='complete' and h['execution_status']=='complete' and h['evidence_status']=='complete','predecessor completion '+stage)
        require(h['coverage_target_met'] is True and h['next_authorization_required'] is False,'predecessor advance gate '+stage)
        require(h['runtime_run_id']==RUN_ID and h['runtime_branch']==BRANCH and h['runtime_goal']==stage,'predecessor identity '+stage)
        require(h['trace_profile_sha256']==PROFILE_HASH,'profile '+stage)
        owner=RUN/'artifacts'/stage
        manifest_path=owner/'manifests/artifact_manifest.json'
        expected=h['artifact_manifest_sha256']
        require(sha(manifest_path)==expected,'manifest hash '+stage)
        manifest=read(manifest_path)
        entries=[];total=0
        for i,record in enumerate(manifest['entries']):
            # All hashed business entries are mandatory, including retained failed attempts.
            if record.get('kind') not in (None,'file'):
                raise ValueError('unsupported business entry kind: '+str(record))
            item=verify_record(record,owner=owner);entries.append(item);total+=item['size']
            if i and i%10000==0:print(stage,'VERIFIED',i,total,flush=True)
        result={'schema_version':1,'status':'complete','runtime_run_id':RUN_ID,'stage':stage,'original_handoff_sha256':sha(hpath),'artifact_manifest_sha256':expected,'entry_count':len(entries),'logical_bytes':total,'entries':entries,'predecessor_bytes_modified':False,'device_or_model_access_performed':False,'tool_sha256':sha(__file__),'resolver_sha256':sha(Path(__file__).with_name('continuation_common.py'))}
        write_new(Path(__file__).parent/'predecessor_validations'/f'{stage}.json',result)
        print('PREDECESSOR_VERIFIED',stage,len(entries),total,flush=True)

if __name__=='__main__':main()
