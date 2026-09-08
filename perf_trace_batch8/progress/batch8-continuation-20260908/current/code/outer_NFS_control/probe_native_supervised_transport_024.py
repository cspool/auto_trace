"""Model-free spawn/pipe test with one native collector per MP child."""
from pathlib import Path
import sys, os, json, time, multiprocessing as mp, csv, collections, sqlite3

R = Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001')
B = R / 'raw/runtime_tools/native_PMC_supervised_transport_probe_024'


def worker(rank, connection):
    source = R / 'raw/runtime_tools/native_PMC_visibility_probe_001/gqa6_visibility_probe.py'
    code = source.read_text().replace('BASE=Path(__file__).parent', 'BASE=Path(__file__).parent.parent')
    code = code.replace(' graph=None', ' torch.cuda.set_device(1-d);other_context_tensor=torch.randn((1,),device="cuda");torch.cuda.synchronize();torch.cuda.set_device(d)\n graph=None')
    code = code.replace(' assert lib.hipProfilerStart()==0', ' assert lib.hipProfilerStart()==0\n lib.roctxRangePushA.argtypes=[ctypes.c_char_p];lib.roctxRangePushA.restype=ctypes.c_int;lib.roctxRangePop.argtypes=[];lib.roctxRangePop.restype=ctypes.c_int\n assert lib.roctxRangePushA(("MODEL_FREE_MP_NATIVE_024.rank"+str(d)).encode())>=0')
    code = code.replace(" write('before_stop.rank'", " assert lib.roctxRangePop()>=0\n write('before_stop.rank'")
    sys.argv = ['worker_payload.py', 'worker', str(rank), 'direct']
    namespace = {'__file__': str(B / f'rank{rank}/worker_payload.py'), '__name__': '__main__'}
    exec(compile(code, namespace['__file__'], 'exec'), namespace)
    connection.send({'rank': rank, 'worker_pid': os.getpid(), 'complete': True})
    connection.close()


def wait_files(prefix, processes):
    deadline = time.monotonic() + 90
    while not all((B / (prefix + '.rank' + str(d) + '.json')).exists() for d in [0, 1]):
        if any(p.exitcode is not None for p in processes):
            raise RuntimeError('MP collector child exited before handshake')
        if time.monotonic() >= deadline:
            raise RuntimeError('bounded MP handshake timeout')
        time.sleep(.05)


def main():
    sys.path.insert(0, str(R / 'raw/runtime_tools/revision_020'))
    from r08_native import collector_argv, save, clean_env, source_record
    B.mkdir()
    from multiprocessing import resource_tracker
    resource_tracker.ensure_running()
    context = mp.get_context('spawn')
    processes, connections = [], []
    try:
        for rank in [0, 1]:
            unit = B / f'rank{rank}'
            unit.mkdir()
            (unit / 'hipprof_tmp').mkdir()
            prefix = collector_argv('pmc_write', '_gqa6', unit, [], trace=True, disabled=False)
            descriptor = unit / 'COLLECTOR_DESCRIPTOR.json'
            save(descriptor, {'status': 'prepared', 'physical_device_id': rank, 'output_directory': str(unit), 'working_directory': '/public/home/accl15ptg7/auto_trace/pra2026-bh408-gqa-page784-k5120-batch8', 'collector_argv_prefix': prefix})
            shim = Path('/public/home/accl15ptg7/run_R08_R10/r08_collector_python_021.py')
            os.environ['QWEN_DCU_R08_NATIVE_COLLECTOR_DESCRIPTOR'] = str(descriptor)
            os.environ['TRITON_CACHE_DIR'] = str(R/'raw/runtime_cache/triton')
            os.environ['PYTHONPYCACHEPREFIX'] = str(R/'raw/runtime_cache/pycache')
            os.environ['LD_LIBRARY_PATH'] = '/opt/dtk-26.04-DCC2602-0317/dcc/lib:/opt/dtk/lib:/opt/dtk/hip/lib:/opt/dtk/rocprofiler/lib:/opt/hyhal/lib'
            receiver, sender = context.Pipe(duplex=False)
            process = context.Process(target=worker, args=(rank, sender))
            mp.set_executable(str(shim))
            try:
                process.start()
            finally:
                mp.set_executable(sys.executable)
            sender.close()
            processes.append(process)
            connections.append(receiver)
        wait_files('before_stop', processes)
        observations = []
        for rank in [0, 1]:
            identity = json.loads((B / f'before_stop.rank{rank}.json').read_text())
            paths = list((B / f'rank{rank}').rglob('pmc_results_' + str(identity['pid']) + '.txt'))
            observations.append({'rank': rank, 'pid': identity['pid'], 'native_files': [{'path': str(p), 'size': p.stat().st_size} for p in paths]})
        save(B / 'BOTH_BEFORE_STOP.json', {'workers': observations, 'both_MP_collector_processes_alive': all(p.is_alive() for p in processes)})
        (B / 'ALLOW_STOP').touch()
        wait_files('after_stop', processes)
        (B / 'ALLOW_LIBC_FLUSH').touch()
        wait_files('after_libc_flush', processes)
        (B / 'ALLOW_EXIT').touch()
        pipe_results = []
        for receiver in connections:
            assert receiver.poll(60), 'spawned child pipe result missing'
            pipe_results.append(receiver.recv())
        results = []
        for rank, process in enumerate(processes):
            process.join(60)
            assert process.exitcode == 0, 'native collector process exit'
            unit = B / f'rank{rank}'
            assert json.loads((unit/'COLLECTOR_EXIT.json').read_text())['status']=='complete'
            rows = list(csv.DictReader((unit / 'capture.csv').open()))
            counts = collections.Counter(int(row['gpu-id']) for row in rows)
            assert counts == {rank: 4}, 'complete physical device counters'
            assert all(int(row['DispatchNs']) > 0 for row in rows)
            assert {int(row['pid']) for row in rows} == {pipe_results[rank]['worker_pid']}
            connection_db = sqlite3.connect((unit / 'capture.db').as_uri()+'?mode=ro&immutable=1',uri=True)
            config = connection_db.execute('SELECT KEY FROM CONFIG WHERE PID=?',(pipe_results[rank]['worker_pid'],)).fetchone()
            assert config is not None
            tx_table = 'HIPTX_'+config[0]
            assert connection_db.execute('SELECT COUNT(*) FROM "'+tx_table+'" WHERE message=?',('MODEL_FREE_MP_NATIVE_024.rank'+str(rank),)).fetchone()[0] == 1, 'native HIPTX marker'
            connection_db.close()
            results.append({'rank': rank, 'native_marker_count': 1, 'counts': dict(counts), 'pipe_result': pipe_results[rank], 'native_csv': source_record(unit / 'capture.csv'), 'native_db': source_record(unit / 'capture.db')})
        save(B / 'RESULT.json', {'status': 'complete', 'model_free': True, 'spawn_pipe_transport_preserved': True, 'independent_collector_per_MP_child': True, 'both_workers_touched_both_devices': True, 'all_started_processes_terminated': True, 'results': results, 'source': source_record(Path(__file__))})
        print(json.dumps({'status': 'complete_MP_native_probe', 'results': results}), flush=True)
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(15)
                if process.is_alive():
                    process.kill()
                    process.join(15)


if __name__ == '__main__':
    main()
