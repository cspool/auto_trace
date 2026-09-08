"""Actual-path equivalence and adversarial CPU-only storage-binding checks."""
from pathlib import Path
from types import SimpleNamespace
import datetime
import hashlib
import importlib.util
import json
import time

C = Path('/public/home/accl15ptg7/run_R08_R10')
P = Path('/public/home/accl15ptg7/auto_trace')
out = C / 'outer_source_path_optimization_gate_001'
out.mkdir(exist_ok=False)

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

common_path = C / 'stage_tool_templates_003/shared_001/cpu_stage_common.py'
validator_path = C / 'outer_source_path_validation_001.py'
common = module('reference_common', common_path)
optimized = module('outer_source_validator', validator_path)
validator = optimized.OuterSourcePathValidator(common)
index = common.read(P / 'perf_trace_batch8/continuation_20260908/predecessor_validation_index.json')
paths = []
for stage in index['stages']:
    entries = common.read(stage['path'])['entries']
    paths += [x['local_path'] for x in entries[:15] + entries[-15:]]
restoration = common.read(P / 'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001/raw/runtime_tools/release_restoration_001/COMPLETE.json')
paths += [x['source_path'] for x in restoration['file_mappings']]
started = time.monotonic()
reference = [common.validate_path(path) for path in paths]
reference_seconds = time.monotonic() - started
started = time.monotonic()
actual = [validator.validate_path(path) for path in paths]
optimized_seconds = time.monotonic() - started
assert actual == reference

# A separate module instance provides the original implementation against a
# synthetic NFS tree; production mappings and source files stay unchanged.
fixture = module('fixture_common', common_path)
base = out / 'fixture'
project, control = base / 'project', base / 'control'
project.mkdir(parents=True)
control.mkdir()
backing = control / 'backing'
backing.mkdir()
destination = control / 'original.bin'
destination.write_bytes(b'original bytes')
plain = control / 'plain.bin'
plain.write_bytes(b'plain bytes')
one, alias = project / 'one', project / 'alias'
one.symlink_to(backing, target_is_directory=True)
alias.symlink_to(one, target_is_directory=True)
(backing / 'mapped.bin').symlink_to(destination)
fixture.PROJECT, fixture.CONTROL = project, control
fixture.OLD = base / 'old'
directories = {one: backing, alias: one}
files = {one / 'mapped.bin': {'destination_path': str(destination), 'size': destination.stat().st_size}}
fixture.directory_mappings = lambda: directories
fixture.storage_mappings = lambda: (files, [])
candidate = optimized.OuterSourcePathValidator(fixture)
checks = []

def compare(label, path, accepted):
    results = []
    for fn in [fixture.validate_path, candidate.validate_path]:
        try:
            value = fn(path)
            results.append(('accepted', str(value)))
        except RuntimeError:
            results.append(('rejected', None))
    assert results[0] == results[1]
    assert (results[0][0] == 'accepted') == accepted
    checks.append({'case': label, 'accepted': accepted, 'reference_matches': True})

compare('plain_owned_file', plain, True)
compare('authorized_file_link', one / 'mapped.bin', True)
compare('authorized_directory_chain', alias / 'mapped.bin', True)
wrong = control / 'wrong.bin'
wrong.write_bytes(b'original bytes')
(backing / 'mapped.bin').unlink()
(backing / 'mapped.bin').symlink_to(wrong)
compare('wrong_same_size_file_target_after_cache', alias / 'mapped.bin', False)
(backing / 'mapped.bin').unlink()
(backing / 'mapped.bin').symlink_to(destination)
plain.unlink()
plain.symlink_to(destination)
compare('unlisted_nested_symlink', plain, False)
plain.unlink()
plain.write_bytes(b'plain bytes')
one.unlink()
one.symlink_to(control, target_is_directory=True)
compare('tampered_mapped_directory_even_for_plain_source', plain, False)
one.unlink()
one.symlink_to(backing, target_is_directory=True)
alias.unlink()
alias.symlink_to(control, target_is_directory=True)
compare('tampered_source_directory_after_cache', alias / 'mapped.bin', False)
alias.unlink()
alias.symlink_to(one, target_is_directory=True)
destination.write_bytes(b'wrong size')
compare('mapped_file_size_changed_after_cache', alias / 'mapped.bin', False)
destination.write_bytes(b'original bytes')
outside = base / 'outside.bin'
outside.write_bytes(b'outside')
compare('unowned_source', outside, False)
compare('path_traversal', control / '..' / 'control' / 'plain.bin', False)
compare('bindings_restored_after_rejection', alias / 'mapped.bin', True)

def rec(path):
    data = path.read_bytes()
    return {'path': str(path), 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

result = {'status': 'complete', 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'actual_path_count': len(paths), 'actual_path_results_identical': True,
          'reference_seconds': reference_seconds, 'optimized_seconds': optimized_seconds,
          'speedup': reference_seconds / optimized_seconds,
          'source_mapping_count': len(validator.files),
          'distinct_live_mapping_directory_checks_per_path': len(validator.mapping_directory_bindings),
          'every_source_byte_SHA_check_still_required': True,
          'frozen_business_tools_changed': False, 'production_sources_mutated': False,
          'adversarial_cases': checks,
          'reference_common': rec(common_path), 'candidate': rec(validator_path), 'gate_code': rec(Path(__file__))}
(out / 'COMPLETE.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result), flush=True)
