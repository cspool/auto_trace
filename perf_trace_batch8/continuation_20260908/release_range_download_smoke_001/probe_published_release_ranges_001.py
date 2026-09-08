"""Read-only smoke check of the exact outer restorer's public asset/CDN routes."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import requests
import sys

C = Path('/public/home/accl15ptg7/run_R08_R10')
P = Path('/public/home/accl15ptg7/auto_trace')
R = P / 'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001'
receipt = R / 'raw/runtime_tools/remote_release_offloads_001/09_chunk_gated_delta_rule_fwd_kernel_h_blockdim64_pmc_write.complete.json'
out = C / 'RELEASE_RANGE_DOWNLOAD_SMOKE_001.json'
assert not out.exists()
result = {'status': 'running_read_only_range_probe',
          'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'weights_changed': False, 'restoration_started': False, 'ranges': []}
try:
    offload = json.loads(receipt.read_text())
    assert offload['status'] == 'complete'
    asset = next(x for x in offload['remote_verification']['assets'] if x['name'] == 'capture.tar.zst.part001')
    result.update(source_release_url=offload['remote_verification']['release_url'],
                  asset_name=asset['name'], asset_size=asset['size'], published_asset_digest=asset['digest'])
    origin = requests.Session()
    cdn = requests.Session()
    cdn.trust_env = False
    cdn.proxies = {'http': os.environ['ftp_proxy'], 'https': os.environ['ftp_proxy']}
    with origin.get(asset['url'], headers={'Range': 'bytes=0-0'}, stream=True, timeout=(30, 45)) as response:
        result['origin_HTTP_status'] = response.status_code
        assert response.status_code in (200, 206), 'public asset redirect unavailable'
        signed_url = response.url
    for begin in (0, 65536, asset['size'] - 65536):
        end = begin + 65535
        with cdn.get(signed_url, headers={'Range': 'bytes=%d-%d' % (begin, end)}, stream=True, timeout=(30, 45)) as response:
            item = {'requested_start': begin, 'requested_end': end,
                    'HTTP_status': response.status_code, 'content_range': response.headers.get('Content-Range'),
                    'content_length': response.headers.get('Content-Length')}
            result['ranges'].append(item)
            assert response.status_code == 206, 'CDN must honor a nonzero resume range'
            assert item['content_range'] == 'bytes %d-%d/%d' % (begin, end, asset['size']), 'exact requested byte range'
            body = response.raw.read(65537)
            assert len(body) == 65536, 'exact bounded response size'
            item['received_bytes'] = len(body)
            item['received_range_sha256'] = hashlib.sha256(body).hexdigest()
    result['status'] = 'complete_actual_remote_range_smoke'
    result['source_receipt_sha256'] = hashlib.sha256(receipt.read_bytes()).hexdigest()
    result['original_full_asset_SHA_verification_still_required_during_restore'] = True
except Exception as error:
    result['status'] = 'failed_read_only_range_probe'
    result['failure_type'] = type(error).__name__
    # Signed URLs and proxy configuration are deliberately excluded from reports.
finally:
    with out.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result), flush=True)
sys.exit(0 if result['status'] == 'complete_actual_remote_range_smoke' else 1)
