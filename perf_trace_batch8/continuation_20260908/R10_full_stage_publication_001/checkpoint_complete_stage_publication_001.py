"""Checkpoint closed stage publication receipts and every expected server digest."""
from pathlib import Path
import datetime
import hashlib
import json
import sys

C = Path('/public/home/accl15ptg7/run_R08_R10')
P = Path('/public/home/accl15ptg7/auto_trace')
D = P / 'perf_trace_batch8/continuation_20260908'
stage = sys.argv[1]
assert stage in ['R08', 'R09', 'R10']
folder = C / 'publication' / ('complete_' + stage)

def read(path):
    return json.loads(path.read_text())

def record(path):
    data = path.read_bytes()
    return {'path': str(path), 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

receipt = read(folder / 'PUBLICATION_COMPLETE.json')
assert receipt['status'] == 'published' and receipt['runtime_goal'] == stage
assert receipt['all_server_asset_sha256_match']
assert record(Path(receipt['handoff']['path'])) == receipt['handoff']
handoff = read(Path(receipt['handoff']['path']))
assert handoff['status'] == 'complete' and handoff['all_started_processes_terminated']
manifest = read(folder / 'ASSET_MANIFEST.json')
assert manifest['status'] == 'verified_ready_for_release'
expected = {x['name']: (x['size'], 'sha256:' + x['sha256']) for x in manifest['assets']}
for name in ['ASSET_MANIFEST.json', 'SHA256SUMS']:
    entry = record(folder / name)
    expected[name] = (entry['size'], 'sha256:' + entry['sha256'])
server = {x['name']: (x['size'], x['digest']) for x in receipt['assets']}
assert expected == server
cleanup = read(folder / 'LOCAL_UPLOAD_CACHE_CLEANUP.json')
assert cleanup['status'] == 'complete' and cleanup['only_server_SHA256_verified_upload_copies_removed']
assert cleanup['all_original_stage_data_outputs_logs_retained_under_verified_storage_authorizations']
out = D / (stage + '_full_stage_publication_001')
out.mkdir(exist_ok=False)
sources = [folder / name for name in ['PUBLICATION_COMPLETE.json', 'FILE_MANIFEST.json',
           'ASSET_MANIFEST.json', 'SHA256SUMS', 'LOCAL_UPLOAD_CACHE_CLEANUP.json']] + [Path(__file__)]
for source in sources:
    assert source.stat().st_size < 5_000_000
    (out / source.name).write_bytes(source.read_bytes())
(out / 'SOURCE_RECORDS.json').write_text(json.dumps([record(path) for path in sources], indent=2) + '\n')
with (D / 'LIVE_PROGRESS.md').open('a') as stream:
    stream.write('\n- ' + datetime.datetime.now(datetime.timezone.utc).isoformat() + ': ' + stage +
                 ' complete stage Release published: ' + receipt['url'] + '. All ' + str(len(server)) +
                 ' exact expected asset sizes and server SHA256 digests match the verified package manifests. '
                 'Upload caches were removed after verification; original stage data and logs remain under their authorized storage paths.\n')
print(json.dumps({'stage': stage, 'release': receipt['url'], 'server_assets_verified': len(server),
                  'checkpoint_directory': str(out)}))
