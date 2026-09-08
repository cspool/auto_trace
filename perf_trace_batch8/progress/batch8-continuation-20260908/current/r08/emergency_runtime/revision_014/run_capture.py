"""One bounded full-batch DP2 replay; each invocation creates a unique attempt."""
from r08_native import *
import shutil
import threading
import argparse
import http.client
import signal
import time
import traceback

CONTROL=Path('/public/home/accl15ptg7/run_R08_R10')
MODEL=Path('/root/Qwen3.5-27B')
DATASET=CONTROL/'snapshot/inputs/testdata/16-32K_throughput.jsonl'
MANIFEST=RUN/'artifacts/R01/contract/request_selection.json'
R01_PATCH=RUN/'artifacts/R01/tools/runtime_patch'
CACHE=ROOT/'raw/runtime_cache'

def terminate(process,grace=45):
    if process.poll() is None:
        os.killpg(process.pid,signal.SIGTERM)
        try:process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=15)
    # The group may retain grandchildren after its leader has exited.
    members=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            if os.getpgid(int(p.name))==process.pid:members.append(int(p.name))
        except (ProcessLookupError,PermissionError):pass
    for pid in members:
        try:os.kill(pid,signal.SIGTERM)
        except ProcessLookupError:pass
    if members:
        time.sleep(2)
        for pid in members:
            try:
                if os.getpgid(pid)==process.pid:os.kill(pid,signal.SIGKILL)
            except ProcessLookupError:pass
    return {'leader_pid':process.pid,'returncode':process.returncode,'remaining_group_members_before_final_cleanup':members}

def runtime_env(passroot,segment):
    # Preserve the collector's injected variables and shared libraries across
    # the supervised exec. Clearing these produced silent zero-PMC failures.
    env=os.environ.copy()
    env.update(HIP_VISIBLE_DEVICES='0,1',CUDA_VISIBLE_DEVICES='0,1',MODEL_DIR=str(MODEL),PORT='8001',VLLM_BIN=str(TOOLS/'vllm_r08_contract_shim.sh'),VLLM_ENGINE_READY_TIMEOUT_S='2400',VLLM_NO_USAGE_STATS='1',DO_NOT_TRACK='1',ROCPROFILER_FLUSH_INTERVAL='1000',PYTHONPATH=':'.join([str(TARGET),str(TOOLS),str(R01_PATCH),'/usr/local/lib/python3.10/dist-packages']),PYTHONPYCACHEPREFIX=str(CACHE/'pycache'),PYTHONDONTWRITEBYTECODE='1',TORCHINDUCTOR_CACHE_DIR=str(CACHE/'torchinductor'),TRITON_CACHE_DIR=str(CACHE/'triton'),VLLM_CACHE_ROOT=str(CACHE/'vllm'),XDG_CACHE_HOME=str(CACHE/'xdg'),HF_HOME=str(CACHE/'huggingface'),PYTHONHASHSEED='0',LD_LIBRARY_PATH=str(DCC)+':/opt/dtk/lib:/opt/dtk/hip/lib:/opt/dtk/rocprofiler/lib:/opt/hyhal/lib',VLLM_ROCM_TUNABLEOP_PROFILE='gfx936_qwen3_5_27b_bf16_tn_m4096',VLLM_ROCM_TUNABLEOP_PROFILE_SHA256='169c7b11a0340d9e22405327b5e5667b2aa9e9e8d899bd59e10ca4fb7fb52030',PYTORCH_TUNABLEOP_ENABLED='1',PYTORCH_TUNABLEOP_TUNING='0',PYTORCH_TUNABLEOP_RECORD_UNTUNED='0',PYTORCH_TUNABLEOP_ROCBLAS_ENABLED='1',PYTORCH_TUNABLEOP_HIPBLASLT_ENABLED='0',QWEN_DCU_R01_ENABLE_RUNTIME_PATCH='1',QWEN_DCU_R01_TARGET_ROOT=str(TARGET),QWEN_DCU_R01_ABI_PACKAGE_DIR='/usr/local/lib/python3.10/dist-packages/vllm',QWEN_DCU_R01_RUNTIME_VARIANT='qwen3.5-27b-cscc-dp2',QWEN_DCU_R01_RUNTIME_ATTEMPT_ID='batch8-dp2-fresh-003-R01-attempt-001',QWEN_DCU_R01_TRACE_PROFILE_SHA256='3b4c952063f48ae662b48b5ce9d8fd76e0ac4d74e170bdb1839ae8b1aaa23cce',QWEN_DCU_R01_REQUEST_MANIFEST_SHA256='d4873c7474cbf1eff0029ab1620a67954802715c1471853a528bff9c237ae889',QWEN_DCU_R01_REQUEST_MANIFEST_FILE_BYTE_SHA256='dc8b848a360d977d1c30adcace393459bce536aa2278ff997d6c71b9e94be280',QWEN_DCU_R01_REQUEST_MANIFEST_CANONICAL_JSON_SHA256='d4873c7474cbf1eff0029ab1620a67954802715c1471853a528bff9c237ae889',QWEN_DCU_R01_REQUEST_MANIFEST=str(MANIFEST),QWEN_DCU_R01_PASS_ID='hipprof',QWEN_DCU_R01_SYNC_TIMING='0',QWEN_DCU_R01_EVENT_ROOT=str(passroot/'workload/r01_events'),QWEN_DCU_R08_ENABLE_PROCESS_OVERLAY='1',QWEN_DCU_R08_ENABLE_PMC_GATE='1',QWEN_DCU_R08_PASS_ROOT=str(passroot),QWEN_DCU_R08_RUNTIME_ATTEMPT_ID='batch8-dp2-fresh-003-R08-'+segment+'-'+passroot.name,QWEN_DCU_R08_SEGMENT_ID=segment,QWEN_DCU_R08_PMC_GATE_EVENT_ROOT=str(passroot/'control/pmc_gate_events'),QWEN_DCU_R08_PMC_GATE_STOP_FILE=str(passroot/'control/pmc_gate_stop.json'),QWEN_DCU_FX_PROCESS_PROFILE='off',R08_R02_ROOT=str(R02),NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost')
    for key in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy','ftp_proxy','FTP_PROXY','PYTORCH_TUNABLEOP_FILENAME','PYTORCH_TUNABLEOP_VERBOSE','PYTORCH_TUNABLEOP_VEROBSE']:env.pop(key,None)
    # Keep Unix domain socket names below their platform length limit.
    tmp=Path('/tmp')/('r8-'+str(os.getpid()))
    tmp.mkdir(exist_ok=False);env['TMPDIR']=str(tmp);env['VLLM_RPC_BASE_PATH']=str(tmp/'rpc');(tmp/'rpc').mkdir()
    return env

def tracee(args):
    require(Path.cwd()==TARGET,'HIPProf tracee source-root cwd')
    root=output_path(Path(args.pass_root));env=runtime_env(root,args.segment)
    r02_bindings(ROOT,environ=env)
    for key in ['HIPPROF_INPUT_FILE','HIPPROF_TMP_OUTPUT_DIR']:require(bool(env.get(key)),'live collector injection '+key)
    (root/'control/live_collector_input.txt').write_bytes(Path(env['HIPPROF_INPUT_FILE']).read_bytes())
    save(root/'control/live_collector_exec.json',{'injected_input_file':source_record(env['HIPPROF_INPUT_FILE']),'injected_output_directory':env['HIPPROF_TMP_OUTPUT_DIR'],'preserved_to_service':True})
    visible_keys=[k for k in env if k.startswith(('QWEN_DCU_','VLLM_','PYTORCH_TUNABLEOP_','HIPPROF_')) or k in ['HIP_VISIBLE_DEVICES','CUDA_VISIBLE_DEVICES','PYTHONPATH','LD_LIBRARY_PATH','MODEL_DIR','TMPDIR','R08_R02_ROOT']]
    save(root/'control/runtime_environment.json',{k:env[k] for k in sorted(visible_keys)})
    service=None;workload=None
    native_directory=Path(env['HIPPROF_TMP_OUTPUT_DIR'])
    snapshot=root/'control/native_pmc_before_collector_merge';snapshot.mkdir()
    def snapshot_native():
        for f in native_directory.rglob('*'):
            if f.is_file() and ('pmc' in f.name.lower() or f.suffix in ['.txt','.csv']):
                dest=snapshot/f.relative_to(native_directory);dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(f,dest)
    try:
        with (root/'logs/service.log').open('x') as out:
            service=subprocess.Popen(['/usr/bin/bash',str(TARGET/'scripts/serve_cscc_dp2.sh')],cwd=TARGET,env=env,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
        save(root/'control/service_identity.json',{'pid':service.pid,'process_group':service.pid,'started_realtime_ns':time.time_ns()})
        started=time.monotonic();last=started
        while True:
            ready=False
            try:
                connection=http.client.HTTPConnection('127.0.0.1',8001,timeout=2);connection.request('GET','/v1/models');response=connection.getresponse();response.read();ready=response.status==200;connection.close()
            except OSError:pass
            if ready:break
            require(service.poll() is None,'vLLM service exited before readiness')
            require(time.monotonic()-started<2400,'bounded vLLM readiness timeout')
            if time.monotonic()-last>30:print('R08_MODEL_INITIALIZING',args.segment,int(time.monotonic()-started),'seconds',flush=True);last=time.monotonic()
            time.sleep(2)
        print('R08_MODEL_READY',args.segment,round(time.monotonic()-started,2),flush=True)
        helper=clean_env();helper['PYTHONPATH']=str(TOOLS)
        argv=[sys.executable,'-B',str(TOOLS/'r08_workload_driver.py'),'--attempt-root',str(root),'--manifest',str(MANIFEST),'--dataset',str(DATASET),'--selection',str(ROOT/'contract/r07_full_request_selection.json'),'--port','8001','--gate-stop-file',str(root/'control/pmc_gate_stop.json'),'--gate-event-root',str(root/'control/pmc_gate_events')]
        with (root/'logs/workload.log').open('x') as out:
            workload=subprocess.Popen(argv,cwd=TARGET,env=helper,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
            try:rc=workload.wait(timeout=3600)
            except subprocess.TimeoutExpired:terminate(workload);raise
        require(rc==0,'full batch8 workload failed')
        driver=read(root/'workload/driver.json');require(driver['completed']==8 and driver['total_completion_tokens']==8192,'complete measured workload')
        summaries=list((root/'control/workers').glob('rank*/overlay_summary.*.json'))
        require(len(summaries)==2 and all(read(p)['status']=='complete' for p in summaries),'both-rank exact process marker coverage')
        snapshot_native()
        save(root/'control/tracee_workload_complete.json',{'status':'complete','driver':source_record(root/'workload/driver.json'),'overlay_summaries':[source_record(p) for p in summaries],'model_initializations':2,'service_launches':1,'warmups':2,'measured_requests':8,'completion_tokens':8192,'observed_latency_evidence':False})
    finally:
        cleanup={}
        if workload is not None:cleanup['workload']=terminate(workload)
        if service is not None:cleanup['service']=terminate(service)
        snapshot_native()
        save(root/'control/tracee_process_cleanup.json',cleanup)

def capture(args):
    plan=read(ROOT/'plans/r08_capture_plan.json')
    gate=read(ROOT/'raw/runtime_tools/runtime_capture_gate_008.json')
    require(gate['status']=='complete','runtime capture gate')
    require(read(ROOT/'preflight/source_abi_probe_002.json')['status']=='complete','separate source/ABI/device checkpoint')
    for record in gate['frozen_tools']:require(sha(record['path'])==record['sha256'],'frozen runtime tool drift')
    require(sha(ROOT/'plans/r08_capture_plan.json')==gate['capture_plan_sha256'],'immutable physical plan')
    unit=next(u for u in plan['physical_captures'] if u['segment_id']==args.segment)
    source=source_binding()
    root=output_path(ROOT/'raw/captures'/args.segment/args.attempt,True)
    require(not root.exists(),'immutable new capture attempt');root.mkdir()
    for name in ['logs','control','workload','hipprof_tmp']:(root/name).mkdir()
    env=clean_env();env['PYTHONPATH']=str(TOOLS)
    argv=collector_argv(unit['mode'],unit['collector_kernel_name_token'],root,[sys.executable,'-B',str(Path(__file__)),'tracee','--pass-root',str(root),'--segment',args.segment],disabled=False)
    contract={'runtime_run_id':'batch8-dp2-fresh-003','runtime_goal':'R08','lineage_id':'batch8-dp2-fresh-003','segment':unit,'attempt':args.attempt,'argv':argv,'cwd':str(TARGET),'source_binding':source,'plan':source_record(ROOT/'plans/r08_capture_plan.json'),'runtime_gate':source_record(ROOT/'raw/runtime_tools/runtime_capture_gate_008.json'),'started_realtime_ns':time.time_ns(),'started_monotonic_ns':time.perf_counter_ns(),'profiling_mode':'replay_projected_attributes_only','latency_axis':'observed_R07_only'}
    save(root/'control/capture_contract.json',contract)
    started=time.monotonic();rc=None;error=None
    with (root/'logs/hipprof.log').open('x') as log:
        profiler=subprocess.Popen(argv,cwd=TARGET,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        save(root/'control/profiler_identity.json',{'pid':profiler.pid,'process_group':profiler.pid})
        try:rc=profiler.wait(timeout=5400)
        except subprocess.TimeoutExpired:error='bounded profiler timeout';terminate(profiler)
    cleanup=terminate(profiler)
    # Keep all raw data even when a postcheck fails.
    inventory=[source_record(p) for p in sorted(root.rglob('*')) if p.is_file()]
    save(root/'raw_inventory_at_exit.json',{'files':inventory,'returncode':rc,'error':error,'elapsed_seconds':time.monotonic()-started,'cleanup':cleanup})
    require(rc==0 and error is None,'profiler did not exit successfully')
    require((root/'capture.db').is_file() and (root/'capture.db').stat().st_size>0,'native database missing')
    require((root/'capture.csv').is_file() and (root/'capture.csv').stat().st_size>0,'native PMC CSV missing')
    workload=read(root/'control/tracee_workload_complete.json');require(workload['status']=='complete','sealed full workload proof')
    source_binding()
    save(root/'execution_manifest.json',{'status':'raw_capture_complete_pending_exact_attribution','runtime_run_id':'batch8-dp2-fresh-003','runtime_goal':'R08','lineage_id':'batch8-dp2-fresh-003','segment':unit,'attempt':args.attempt,'returncode':rc,'elapsed_seconds':time.monotonic()-started,'raw_inventory':source_record(root/'raw_inventory_at_exit.json'),'workload':workload,'both_ranks_and_devices':[0,1],'all_started_processes_terminated':True,'model_initializations':2,'service_launches':1,'profiler_starts':1,'warmups':2,'measured_requests':8,'replay_time_used_as_observed_latency':False})
    print('R08_RAW_CAPTURE_COMPLETE',args.segment,args.attempt,round(time.monotonic()-started,2),flush=True)

def main():
    ap=argparse.ArgumentParser();sp=ap.add_subparsers(dest='command',required=True)
    p=sp.add_parser('tracee');p.add_argument('--pass-root',required=True);p.add_argument('--segment',required=True)
    p=sp.add_parser('capture');p.add_argument('--segment',required=True);p.add_argument('--attempt',required=True)
    args=ap.parse_args()
    if args.command=='tracee':
        def scoped_stop(signum,frame):raise SystemExit(128+signum)
        signal.signal(signal.SIGTERM,scoped_stop)
        tracee(args)
    else:capture(args)

if __name__=='__main__':main()
