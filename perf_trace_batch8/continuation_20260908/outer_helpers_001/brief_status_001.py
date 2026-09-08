"""Read only the latest durable outer observations; never probe GPU or source DBs."""
from pathlib import Path
import json
C=Path('/public/home/accl15ptg7/run_R08_R10')
s=json.loads((C/'RECOVERY_STATE_NFS.json').read_text());h=s['latest_health_observation'];t=h['measured_request_token_progress'];coverage=h['live_eight_request_target_coverage'];p=json.loads((C/'REMOTE_PROGRESS_LAST_PUSH_NFS.json').read_text())
r={'utc':h['utc'],'accepted':h['accepted_R08'],'capture':h['current_capture'],'phase':h['current_phase'],'workers':[{'rank':x['rank'],'pid':x['worker_pid'],'alive':x['worker_alive'],'PMC_MB':round(x['PMC_bytes']/1e6,1)} for x in h['native_workers']],'prehealth':h['pre_measured_health'],'live_coverage':coverage['status'] if coverage else None,'orders_match_R07':coverage.get('all_first_phase_orders_match_R07') if coverage else None,'NFS_GiB':h['NFS_available_GiB'],'raw_evicted_GB':round(h['temporarily_evicted_bytes']/1e9,3),'remaining_hours':h['remaining_machine_hours'],'completed_stages':h['completed_stages'],'last_remote_progress':p['utc']}
if h['current_phase']=='measured_batch' and t:r['active_requests']=len(t);r['token_range']=[min(t.values()),max(t.values())]
print(json.dumps(r,separators=(',',':')))
