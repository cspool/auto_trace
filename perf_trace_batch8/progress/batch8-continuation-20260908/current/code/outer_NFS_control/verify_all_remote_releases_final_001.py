"""Fresh read-only server digest review of every required continuation Release."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote
import datetime
import hashlib
import json
import os
import subprocess
import time
import requests

C = Path('/public/home/accl15ptg7/run_R08_R10')
P = Path('/public/home/accl15ptg7/auto_trace')
R = P / 'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001'

def read(path):
    return json.loads(path.read_text())

def rec(path):
    data = path.read_bytes()
    return {'path': str(path), 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

inputs = []
index = read(R / 'normalized/accepted_captures.json')
assert index['status'] == 'complete' and len(index['captures']) == 12
for capture in index['captures']:
    path = R / 'raw/runtime_tools/remote_release_offloads_001' / (capture['segment_id'] + '.complete.json')
    remote = read(path)['remote_verification']
    assert remote['status'] == 'complete'
    inputs.append({'label': capture['segment_id'], 'kind': 'accepted_capture',
                   'url': remote['release_url'], 'assets': remote['assets'], 'source': rec(path)})
for stage in ['R08', 'R09', 'R10']:
    path = C / 'publication' / ('complete_' + stage) / 'PUBLICATION_COMPLETE.json'
    remote = read(path)
    assert remote['status'] == 'published' and remote['all_server_asset_sha256_match']
    inputs.append({'label': stage, 'kind': 'complete_stage', 'url': remote['url'],
                   'assets': remote['assets'], 'source': rec(path)})
path = C / 'publication_emergency/r08_capture09_closed_prehealth_failures_001/PUBLICATION_COMPLETE.json'
remote = read(path)
assert remote['status'] == 'published' and remote['all_server_asset_sha256_match']
inputs.append({'label': 'capture09_preserved_failed_attempts', 'kind': 'supplemental_failed_capture_evidence',
               'url': remote['url'], 'assets': remote['assets'], 'source': rec(path)})
assert len(inputs) == 16 and len({x['url'] for x in inputs}) == 16
credential = subprocess.run(['git', 'credential', 'fill'],
                            input='protocol=https\nhost=github.com\n\n', text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
                            env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
assert credential.returncode == 0
token = dict(line.split('=', 1) for line in credential.stdout.splitlines() if '=' in line)['password']

def verify(item):
    expected = {x['name']: (x['size'], x.get('digest') or ('sha256:' + x['sha256'])) for x in item['assets']}
    assert all(digest.startswith('sha256:') and len(digest) == 71 for _, digest in expected.values())
    tag = item['url'].split('/releases/tag/', 1)[1]
    error_name = None
    for attempt in range(3):
        try:
            with requests.Session() as api:
                api.headers.update({'Authorization': 'Bearer ' + token,
                                    'Accept': 'application/vnd.github+json', 'Cache-Control': 'no-cache'})
                response = api.get('https://api.github.com/repos/cspool/auto_trace/releases/tags/' + quote(tag, safe=''),
                                   timeout=(15, 45))
                response.raise_for_status()
                release = response.json()
            actual = {x['name']: (x['size'], x.get('digest')) for x in release['assets']}
            assert actual == expected, 'exact expected remote asset inventory and digests'
            assert release['html_url'] == item['url'] and not release['draft']
            result = {'label': item['label'], 'kind': item['kind'], 'url': item['url'],
                      'source_receipt': item['source'], 'release_id': release['id'],
                      'verified_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      'expected_asset_count': len(expected), 'every_asset_size_and_server_SHA256_matches': True,
                      'assets': [{key: asset[key] for key in ['id', 'name', 'size', 'digest', 'browser_download_url']}
                                 for asset in release['assets']]}
            print('FINAL_REMOTE_RELEASE_REVERIFIED', item['label'], len(expected), flush=True)
            return result
        except Exception as error:
            error_name = type(error).__name__
            time.sleep(attempt + 1)
    raise RuntimeError('Remote review failed for ' + item['label'] + ': ' + str(error_name))

with ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(verify, inputs))
result = {'status': 'complete', 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'accepted_capture_releases': 12, 'complete_stage_releases': 3,
          'supplemental_failed_evidence_releases': 1, 'release_count': 16,
          'asset_count': sum(x['expected_asset_count'] for x in results),
          'all_expected_remote_assets_currently_present_with_exact_size_and_SHA256': True,
          'read_only_remote_review': True, 'releases': results, 'code': rec(Path(__file__))}
out = C / 'FINAL_REMOTE_RELEASE_VERIFICATION_001.json'
with out.open('x') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
    stream.flush()
    os.fsync(stream.fileno())
print('ALL_REQUIRED_REMOTE_RELEASES_REVERIFIED', result['release_count'], result['asset_count'], flush=True)
