"""Metadata-only capacity forecast for the accepted independent-session layout."""
from pathlib import Path
import datetime
import hashlib
import json
import os

C = Path('/public/home/accl15ptg7/run_R08_R10')
P = Path('/public/home/accl15ptg7/auto_trace')
R = P / 'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001'
seg = '09_chunk_gated_delta_rule_fwd_kernel_h_blockdim64_pmc_write'
publication = C / 'publication_emergency' / ('r08_' + seg)
file_manifest = publication / 'FILE_MANIFEST.json'
manifest = json.loads(file_manifest.read_text())
assert manifest['status'] == 'closed_accepted_capture'
assert manifest['segment_id'] == seg and manifest['capture_attempt'] == 'attempt_006'
raw_prefix = str(Path(manifest['accepted_item']['execution_manifest']['path']).parent.relative_to(P)) + '/'
raw_files = [x for x in manifest['files'] if x['path'].startswith(raw_prefix)]
large_files = [x for x in raw_files if x['size'] >= 200_000_000]
prior = [json.loads(p.read_text()) for p in (R / 'raw/runtime_tools/remote_release_offloads_001').glob('*.complete.json')
         if p.name[:2].isdigit() and int(p.name[:2]) < 9]
assert len(prior) == 8 and all(x['status'] == 'complete' for x in prior)
prior_bytes = sum(x['evicted_bytes'] for x in prior)
new_large_bytes = sum(x['size'] for x in large_files)
weights = list(Path('/root/Qwen3.5-27B-verified-root-backing-20260908').glob('*.safetensors'))
assert len(weights) == 11 and all(not p.is_symlink() and p.is_file() for p in weights)
weight_bytes = sum(p.stat().st_size for p in weights)
assert weight_bytes == 55_563_022_432

def available(path):
    fs = os.statvfs(path)
    return fs.f_bavail * fs.f_frsize

root_free = available('/root')
projected = prior_bytes + 4 * new_large_bytes
larger_future = prior_bytes + new_large_bytes + 3 * ((new_large_bytes * 3 + 1) // 2)
result = {
    'status': 'metadata_only_capacity_estimate_not_restore_authorization',
    'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'accepted_capture_count_at_forecast': 9,
    'remaining_capture_count': 3,
    'original_native_session_layout': 'both_original_DBs_plus_lossless_derived_DB_retained',
    'capture09_raw_bytes': sum(x['size'] for x in raw_files),
    'capture09_all_published_member_bytes': sum(x['size'] for x in manifest['files']),
    'capture09_large_raw_files_to_restore': large_files,
    'capture09_large_raw_bytes': new_large_bytes,
    'prior_eight_evicted_bytes': prior_bytes,
    'projected_total_restore_bytes_at_capture09_size': projected,
    'projected_total_restore_bytes_if_last_three_each_grow_50_percent': larger_future,
    'root_available_bytes_now': root_free,
    'NFS_available_bytes_now': available(C),
    'physical_root_weight_bytes_still_retained': weight_bytes,
    'root_only_projected_free_after_weights_and_full_restore': root_free + weight_bytes - projected,
    'root_only_projected_free_with_last_three_50_percent_larger': root_free + weight_bytes - larger_future,
    'actual_restorer_minimum_aggregate_reserve_bytes': 20 * (1 << 30),
    'actual_restorer_rechecks_all_12_releases_and_original_sizes': True,
    'assumptions': 'Restoration projection uses the accepted capture09 large-file set for captures10-12. Future retries and CPU stage output growth are excluded. All new CPU outputs remain on NFS; transient next-capture/package space is checked separately. No NFS free bytes are added to the root-only reserve estimate.',
    'weights_removed': False,
    'raw_files_removed_by_forecast': False,
    'source_file_manifest': {'path': str(file_manifest), 'size': file_manifest.stat().st_size,
                             'sha256': hashlib.sha256(file_manifest.read_bytes()).hexdigest()},
}
assert result['root_only_projected_free_with_last_three_50_percent_larger'] > 20 * (1 << 30)
out = C / 'STORAGE_FORECAST_AFTER_CAPTURE09_001.json'
with out.open('x') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
D = P / 'perf_trace_batch8/continuation_20260908'
(D / out.name).write_bytes(out.read_bytes())
(D / 'outer_helpers_001' / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
print(json.dumps({k: v for k, v in result.items() if isinstance(v, (int, str, bool))}))
