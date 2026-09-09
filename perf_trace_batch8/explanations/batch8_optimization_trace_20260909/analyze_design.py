#!/usr/bin/env python3
"""Record implemented scheduling policy, historical OOM evidence and illustrative dispatch."""
from pathlib import Path
import csv, hashlib, json, subprocess

O = Path(__file__).resolve().parent
T = O.parents[2] / 'pra2026-bh408-gqa-page784-k5120-batch8'
a = json.loads((O / 'data/analysis.json').read_text())
sources = []
for rel in ['scripts/serve_cscc_dp2.sh', 'vllm/v1/engine/core_client.py',
            'vllm/v1/core/sched/scheduler.py', 'vllm/platforms/rocm.py',
            'vllm/model_executor/layers/fla/ops/chunk_o.py',
            'docs/cscc/BATCH8_OFFICIAL_BASE_RECOMMENDATION.md']:
    data = (T / rel).read_bytes()
    assert data == subprocess.check_output(['git', '-C', str(T), 'show', a['target_commit'] + ':' + rel])
    out = O / 'source_snapshot' / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    sources.append({'path': str(out.relative_to(O)), 'sha256': hashlib.sha256(data).hexdigest()})
original = next(x for x in a['sources'] if x['path'].endswith('/request_timeline.csv'))
raw = Path(original['path'])
assert hashlib.sha256(raw.read_bytes()).hexdigest() == original['sha256']
rows = sorted(csv.DictReader(raw.open()), key=lambda r: int(r['dispatch_ordinal']))
origin = min(int(r['begin_ns']) for r in rows)
dispatch = []
for r in rows:
    assert r['data_parallel_rank_requested'] == r['rank']
    assert r['http_status'] == '200' and r['completion_tokens'] == '1024' and not r['error']
    dispatch.append({'request': int(r['measured_request_ordinal']), 'dispatch_ordinal': int(r['dispatch_ordinal']),
                     'request_id': r['request_id'], 'client_begin_ns': int(r['begin_ns']),
                     'client_start_relative_ms': (int(r['begin_ns']) - origin) / 1e6,
                     'requested_rank': int(r['data_parallel_rank_requested']), 'actual_rank': int(r['rank']),
                     'prompt_tokens': int(r['prompt_tokens']), 'http_status': 200, 'completion_tokens': 1024})
assert len(dispatch) == 8
historical = (O / 'source_snapshot/docs/cscc/BATCH8_OFFICIAL_BASE_RECOMMENDATION.md').read_text()
for text in ['4094', '3582', '6760', '256 MiB', '27 成功 / 23 失败', '39 成功 / 11 失败',
             '111.67', '98.06', '58.87', 'key=[H,K,V,BT]']:
    assert text in historical, text
result = {
    'status': 'complete', 'target_commit': a['target_commit'], 'sources': sources,
    'design': {
        'topology': 'DP2, TP1, PP1; two complete model replicas with independent scheduler and KV cache',
        'router': 'retained official request-level DPLBAsyncMPClient, not a new 4+4 partition algorithm',
        'score': '4 * waiting + running', 'local_waiting_increment': 'client_count',
        'tie_scan_start': 'floor(num_engines * client_index / client_count)',
        'coordinator_stats_update_ms_from_source_comment': 100,
        'length_based_cross_rank_tie_break_implemented': False,
        'prefill_budget': {'prompt_gt_16384': 512, 'prompt_gt_8192': 1024, 'other_prefill': 2048},
        'prefill_applies_to_single_request_per_rank': True,
        'pure_decode': 'does not enter prefill clamp', 'default_graph_capture_max_for_target': 16,
        'chunk_o_autotune_key': ['H', 'K', 'V', 'BT'],
    },
    'illustrative_dispatch': dispatch,
    'historical_oom': {
        'evidence_kind': '2026-08-11 repository ablation report, not OOM events from this fixed trace',
        'source': 'source_snapshot/docs/cscc/BATCH8_OFFICIAL_BASE_RECOMMENDATION.md',
        'original_failure_log_root': '/public/home/tangyu408/Qwen_DCU_Worker_0/batch8_implementation_validation_20260811',
        'original_failure_logs_accessible_now': False,
        'incidents': [
            {'trigger': '4094-token mixed prefill/decode', 'allocation': '(4094,34816) BF16, about 272 MiB', 'site': 'dense MLP'},
            {'trigger': 'one request per rank, about 15.9K input, old multi-request-only gate', 'allocation': '3582-token step, about 238 MiB', 'site': 'dense MLP'},
            {'trigger': 'one 6760-token request, 4096-token step', 'allocation': 'about 272 MiB', 'site': 'dense MLP'},
            {'trigger': 'new T in old chunk_o autotune key', 'allocation': '256 MiB for benchmark L2 clear', 'site': 'online autotuning'},
        ],
        'ablations': [
            {'policy': 'graph16 only', 'input_bucket': '4-8K', 'success': 27, 'failure': 23},
            {'policy': 'graph16 + multi-request prefill2048', 'input_bucket': '4-8K', 'success': 50, 'failure': 0},
            {'policy': 'graph16 + multi-request prefill2048', 'input_bucket': '8-16K', 'success': 39, 'failure': 11},
            {'policy': 'graph16 + length tiers', 'input_bucket': '4-8K', 'success': 50, 'failure': 0, 'output_tokens_per_s': 111.67},
            {'policy': 'graph16 + length tiers', 'input_bucket': '8-16K', 'success': 50, 'failure': 0, 'output_tokens_per_s': 98.06},
            {'policy': 'graph16 + length tiers', 'input_bucket': '16-32K', 'success': 50, 'failure': 0, 'output_tokens_per_s': 58.87},
        ],
    },
}
(O / 'data/scheduling_design.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print('DESIGN_EVIDENCE_COMPLETE', 'source_files', len(sources), 'illustrative_requests', len(dispatch), 'historical_oom_incidents', 4)
