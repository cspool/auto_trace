#!/usr/bin/python -S
"""CPU-only multiprocessing executable supervisor for one native collector."""
from pathlib import Path
import json
import os
import signal
import subprocess
import sys
import time


def write(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def main():
    descriptor = Path(os.environ['QWEN_DCU_R08_NATIVE_COLLECTOR_DESCRIPTOR'])
    config = json.loads(descriptor.read_text())
    assert config['status'] == 'prepared' and config['physical_device_id'] in (0, 1)
    assert sys.argv[-1] == '--multiprocessing-fork' and '-c' in sys.argv
    program = sys.argv[sys.argv.index('-c') + 1]
    assert program.startswith('from multiprocessing.spawn import spawn_main; spawn_main(')
    unit = Path(config['output_directory'])
    os.setsid()
    fields = Path('/proc/self/stat').read_text().split(') ', 1)[1].split()
    identity = {'status': 'started', 'wrapper_pid': os.getpid(), 'wrapper_start_ticks': int(fields[19]),
                'process_group': os.getpgrp(), 'physical_device_id': config['physical_device_id'],
                'descriptor': str(descriptor), 'started_realtime_ns': time.time_ns()}
    write(unit / 'COLLECTOR_WRAPPER_START.json', identity)
    env = os.environ.copy()
    env['QWEN_DCU_R08_NATIVE_COLLECTOR_WORKER'] = '1'
    env['QWEN_DCU_R08_NATIVE_COLLECTOR_RANK'] = str(config['physical_device_id'])
    for key in ['HIPPROF_INPUT_FILE', 'HIPPROF_TMP_OUTPUT_DIR', 'HIP_PROFILE_IPC_ID',
                'HSA_TOOLS_LIB', 'HSA_TOOLS_LIB64', 'LD_PRELOAD', 'ROCP_TOOL_LIB', 'ROCP_HSA_INTERCEPT']:
        env.pop(key, None)
    argv = config['collector_argv_prefix'] + ['/usr/bin/python'] + sys.argv[1:]
    inherited = []
    for entry in Path('/proc/self/fd').iterdir():
        fd = int(entry.name)
        if fd > 2:
            try:
                os.fstat(fd)
            except OSError:
                continue
            inherited.append(fd)
    child = None
    received = []

    def stopped(signum, frame):
        received.append(signum)
        if child is not None and child.poll() is None:
            child.send_signal(signum)

    signal.signal(signal.SIGTERM, stopped)
    signal.signal(signal.SIGINT, stopped)
    timeout = False
    with (unit / 'collector.log').open('x') as log:
        child = subprocess.Popen(argv, cwd=config['working_directory'], env=env,
                                 stdout=log, stderr=subprocess.STDOUT, pass_fds=tuple(inherited))
        write(unit / 'COLLECTOR_CHILD_START.json', {'pid': child.pid, 'wrapper_pid': os.getpid(),
              'physical_device_id': config['physical_device_id'], 'argv': argv,
              'bootstrap_file_descriptors_preserved': inherited, 'started_realtime_ns': time.time_ns()})
        try:
            rc = child.wait(timeout=5400)
        except subprocess.TimeoutExpired:
            timeout = True
            child.terminate()
            try:
                rc = child.wait(timeout=30)
            except subprocess.TimeoutExpired:
                child.kill()
                rc = child.wait(timeout=15)
    result = {**identity, 'status': 'complete' if rc == 0 and not timeout and not received else 'failed',
              'collector_pid': child.pid, 'collector_returncode': rc, 'timeout': timeout,
              'received_signals': received, 'finished_realtime_ns': time.time_ns()}
    write(unit / 'COLLECTOR_EXIT.json', result)
    return 0 if result['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
