"""Preserve the DP2 service; wrap only its two TP1 GPU worker processes."""
from pathlib import Path
import functools
import hashlib
import inspect
import json
import multiprocessing
import os
import threading
import time
import shutil
import signal

EXPECTED_EXECUTOR_SHA256 = 'REPLACE_AT_FREEZE'
_lock = threading.RLock()
_installed = False


def record(path):
    path = Path(path)
    data = path.read_bytes()
    return {'path': str(path), 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def physical_rank(config, local_rank, rank):
    p = config.parallel_config
    dp = int(p.data_parallel_index)
    local_dp = p.data_parallel_rank_local
    if local_dp is None:
        local_dp = dp
    if (dp not in (0, 1) or int(local_dp) != dp or local_rank != 0 or rank != 0
            or p.tensor_parallel_size != 1 or p.pipeline_parallel_size != 1
            or p.data_parallel_size != 1 or p.nnodes_within_dp != 1):
        raise RuntimeError('unexpected original internal DP2/TP1 worker topology')
    return dp


def wrap_make(original):
    signature = inspect.signature(original)

    @functools.wraps(original)
    def wrapped(*args, **kwargs):
        from multiprocessing import resource_tracker, spawn
        from r08_native import ROOT, TARGET, collector_argv
        bound = signature.bind(*args, **kwargs)
        dp = physical_rank(bound.arguments['vllm_config'], bound.arguments['local_rank'], bound.arguments['rank'])
        with _lock:
            if os.environ.get('QWEN_DCU_R08_NATIVE_COLLECTOR_WORKER') == '1':
                raise RuntimeError('nested native worker collector prohibited')
            if any(os.environ.get(k) != '0,1' for k in ['HIP_VISIBLE_DEVICES', 'CUDA_VISIBLE_DEVICES']):
                raise RuntimeError('original two-device visibility changed')
            root = Path(os.environ['QWEN_DCU_R08_PASS_ROOT'])
            plan = json.loads((ROOT / 'plans/r08_capture_plan.json').read_text())
            unit_plan = next(x for x in plan['physical_captures'] if x['segment_id'] == os.environ['QWEN_DCU_R08_SEGMENT_ID'])
            unit = root / 'native_collectors' / f'rank{dp}'
            unit.mkdir(parents=True, exist_ok=False)
            (unit / 'hipprof_tmp').mkdir()
            descriptor = unit / 'COLLECTOR_DESCRIPTOR.json'
            prefix = collector_argv(unit_plan['mode'], unit_plan['collector_kernel_name_token'], unit, [], trace=True, disabled=False)
            shim = Path(__file__).parent / 'r08_collector_python.py'
            write(descriptor, {'status': 'prepared', 'physical_device_id': dp, 'output_directory': str(unit),
                  'working_directory': str(TARGET), 'collector_argv_prefix': prefix,
                  'original_service_DP2_TP1_unchanged': True, 'native_collection_initially_on': True,
                  'wrapper': record(shim), 'parent_pid': os.getpid()})
            # The resource tracker must use ordinary Python, never the profiler wrapper.
            resource_tracker.ensure_running()
            previous_executable = spawn.get_executable()
            previous_descriptor = os.environ.get('QWEN_DCU_R08_NATIVE_COLLECTOR_DESCRIPTOR')
            os.environ['QWEN_DCU_R08_NATIVE_COLLECTOR_DESCRIPTOR'] = str(descriptor)
            multiprocessing.set_executable(str(shim))
            try:
                result = original(*args, **kwargs)
            finally:
                multiprocessing.set_executable(previous_executable)
                if previous_descriptor is None:
                    os.environ.pop('QWEN_DCU_R08_NATIVE_COLLECTOR_DESCRIPTOR', None)
                else:
                    os.environ['QWEN_DCU_R08_NATIVE_COLLECTOR_DESCRIPTOR'] = previous_descriptor
            result.proc._qwen_r08_native_collector = True
            write(unit / 'MP_WORKER_LAUNCH.json', {'status': 'spawned', 'physical_device_id': dp,
                  'wrapper_pid': result.proc.pid, 'parent_pid': os.getpid(),
                  'original_executable_restored': spawn.get_executable() == previous_executable,
                  'descriptor': record(descriptor)})
            return result
    return wrapped


def wrap_termination(original):
    def terminate(procs):
        selected = [p for p in procs if getattr(p, '_qwen_r08_native_collector', False)]
        ordinary = [p for p in procs if p not in selected]
        if ordinary:
            original(ordinary)
        # GPU workers have received their original death-pipe EOF. Let the
        # independent collector finish writing its original native DB/CSV.
        deadline = time.monotonic() + 900
        for process in selected:
            process.join(max(0, deadline-time.monotonic()))
            if process.is_alive():
                raise RuntimeError('native collector failed to close within 900 seconds')
    return terminate


def wrap_device_init(original):
    @functools.wraps(original)
    def init(worker, *args, **kwargs):
        if os.environ.get('QWEN_DCU_R08_NATIVE_COLLECTOR_WORKER') != '1':
            raise RuntimeError('GPU worker reached device initialization without its native collector')
        rank = physical_rank(worker.vllm_config, worker.local_rank, worker.rank)
        if int(os.environ['QWEN_DCU_R08_NATIVE_COLLECTOR_RANK']) != rank:
            raise RuntimeError('collector and GPU worker physical ranks differ')
        input_path = Path(os.environ['HIPPROF_INPUT_FILE'])
        native_directory = Path(os.environ['HIPPROF_TMP_OUTPUT_DIR'])
        descriptor = Path(os.environ['QWEN_DCU_R08_NATIVE_COLLECTOR_DESCRIPTOR'])
        config = json.loads(descriptor.read_text())
        assert config['physical_device_id'] == rank
        unit = Path(config['output_directory'])
        snapshot = unit / 'native_input_at_worker_start.txt'
        snapshot.write_bytes(input_path.read_bytes())
        root = Path(os.environ['QWEN_DCU_R08_PASS_ROOT'])
        write(root / 'control/worker_native_collectors' / f'rank{rank}.json', {
            'status': 'native_collector_bound_before_device_initialization', 'rank': rank,
            'worker_pid': os.getpid(), 'native_output_directory': str(native_directory),
            'native_input_snapshot': record(snapshot), 'native_injected_input': record(input_path),
            'collector_descriptor': record(descriptor), 'unit_directory': str(unit),
            'HIP_VISIBLE_DEVICES': os.environ['HIP_VISIBLE_DEVICES'],
            'CUDA_VISIBLE_DEVICES': os.environ['CUDA_VISIBLE_DEVICES'],
            'realtime_ns': time.time_ns()})
        return original(worker, *args, **kwargs)
    return init


def snapshot_native_files(root, snapshot):
    root, snapshot = Path(root), Path(snapshot)
    for path in sorted((root / 'control/worker_native_collectors').glob('rank*.json')):
        binding = json.loads(path.read_text())
        directory = Path(binding['native_output_directory'])
        for source in directory.rglob('*'):
            if source.is_file() and ('pmc' in source.name.lower() or source.suffix in ['.txt', '.csv']):
                destination = snapshot / ('rank'+str(binding['rank'])) / source.relative_to(directory)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)


def process_group_members(group):
    members = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            fields = (path/'stat').read_text().split(') ', 1)[1].split()
        except (OSError, IndexError):
            continue
        if int(fields[2]) == group and fields[0] != 'Z':
            members.append(int(path.name))
    return members


def close_native_collectors(root, timeout=900):
    root = Path(root)
    units = sorted((root/'native_collectors').glob('rank*'))
    results = []
    deadline = time.monotonic()+timeout
    for unit in units:
        start_path = unit/'COLLECTOR_WRAPPER_START.json'
        if not start_path.exists():
            results.append({'unit': str(unit), 'status': 'not_started_or_start_record_missing'})
            continue
        start = json.loads(start_path.read_text())
        group = start['process_group']
        assert group == start['wrapper_pid']
        forced = False
        while process_group_members(group) and time.monotonic() < deadline:
            time.sleep(.2)
        if process_group_members(group):
            forced = True
            os.killpg(group, signal.SIGTERM)
            end = time.monotonic()+10
            while process_group_members(group) and time.monotonic() < end:
                time.sleep(.2)
            if process_group_members(group):
                os.killpg(group, signal.SIGKILL)
                time.sleep(.5)
        remaining = process_group_members(group)
        exit_path = unit/'COLLECTOR_EXIT.json'
        exit_record = json.loads(exit_path.read_text()) if exit_path.exists() else None
        good = not forced and not remaining and exit_record is not None and exit_record['status'] == 'complete' and exit_record['collector_returncode'] == 0
        results.append({'unit': str(unit), 'rank': start['physical_device_id'],
                        'status': 'complete' if good else 'failed', 'process_group': group,
                        'forced_group_cleanup': forced, 'remaining_live_group_members': remaining,
                        'wrapper_start': record(start_path), 'wrapper_exit': record(exit_path) if exit_path.exists() else None})
    good = len(results) == 2 and {r.get('rank') for r in results} == {0, 1} and all(r['status'] == 'complete' for r in results)
    result = {'status': 'complete' if good else 'failed', 'collectors': results,
              'all_started_native_groups_terminated': all(not r.get('remaining_live_group_members') for r in results),
              'complete_requires_both_native_returncodes_zero': True}
    write(root/'control/NATIVE_COLLECTORS_CLOSED.json', result)
    return result


def install():
    global _installed
    if _installed:
        return
    from vllm.v1.executor import multiproc_executor
    from vllm.v1.worker.gpu_worker import Worker
    if record(multiproc_executor.__file__)['sha256'] != EXPECTED_EXECUTOR_SHA256:
        raise RuntimeError('pinned multiprocessing executor source changed')
    cls = multiproc_executor.WorkerProc
    cls.make_worker_process = staticmethod(wrap_make(cls.make_worker_process))
    executor = multiproc_executor.MultiprocExecutor
    executor._ensure_worker_termination = staticmethod(wrap_termination(executor._ensure_worker_termination))
    Worker.init_device = wrap_device_init(Worker.init_device)
    _installed = True
