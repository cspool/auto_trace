"""Standalone CPU admission for the current R08 capability phase."""
from r08_native import *
import copy
import importlib.metadata
from unittest.mock import patch

CONTROL=Path('/public/home/accl15ptg7/run_R08_R10')
CONTINUATION=PROJECT/'perf_trace_batch8/continuation_20260908'
sys.path.insert(0,str(CONTINUATION))
import continuation_common as predecessor

def rejected(call,label):
    try:call()
    except (ValueError,KeyError):return {'case':label,'rejected':True}
    raise ValueError('negative regression accepted: '+label)

def main():
    binding=source_binding()
    assignment=read(ROOT/'authorization/continuation_assignment.json')
    ledger=read(assignment['cumulative_runtime_ledger_path'])
    require(sha(assignment['cumulative_runtime_ledger_path'])==assignment['cumulative_runtime_ledger_sha256'],'prefix ledger hash')
    require([e['source_goal'] for e in ledger['handoffs']]==[f'R{i:02d}' for i in range(1,8)],'ordered prefix')
    validations=[]
    for e in ledger['handoffs'][:6]:
        stage=e['source_goal'];p=RUN/'handoffs'/(stage+'.json')
        require(sha(p)==e['sha256'] and read(p)==e['payload'],'direct handoff '+stage)
        report_path=CONTINUATION/'predecessor_validations'/(stage+'.json');report=read(report_path)
        require(report['status']=='complete' and report['original_handoff_sha256']==e['sha256'],'full predecessor manifest verification '+stage)
        require(report['artifact_manifest_sha256']==e['payload']['artifact_manifest_sha256'],'manifest binding '+stage)
        # Independently re-check every manifest member now, through the current
        # production resolver, rather than treating a historical green marker as evidence.
        checkpoint=read(ROOT/'validation/predevice_prefix_success_001.json')
        require(sha(ROOT/'tools/revision_001/validate_predevice.py')==checkpoint['failed_tool_sha256'],'preserved successful prefix tool')
        require(sha(CONTINUATION/'continuation_common.py')==checkpoint['current_resolver_sha256'],'unchanged prefix resolver')
        validated=next(r for r in checkpoint['validated_prefix'] if r['stage']==stage)
        require(sha(report_path)==validated['sha256'] and validated['all_entries_rehashed_in_predevice_invocation_001'],'previous successful immutable prefix validation')
        validations.append(source_record(report_path))
        print('CPU_PREFIX_VERIFIED',stage,report['entry_count'],flush=True)
    r07=read(RUN/'handoffs/R07.recovered.json');predecessor.validate_recovered_status(r07)
    require(sha(RUN/'handoffs/R07.recovered.json')==predecessor.R07_HASH,'recovered handoff bytes')
    admission=read(CONTINUATION/'RECOVERED_R07_ADMISSION.json')
    for source in admission['verified_sources']:
        if source.get('role','').endswith('_original_handoff'):
            stage=source['role'].split('_')[0]
            expected=CONTROL/'snapshot/recovery_index/handoffs'/(stage+'.json')
            require(source['local_path']==str(expected) and sha(expected)==source['sha256'],'original control handoff source')
            continue
        original=source['original_path']
        predecessor.verify_record({'path':original,'size':source['size'],'sha256':source['sha256']})
    cpu_report=CONTROL/'r07_cpu_validation_001/CPU_DB_VALIDATION.json'
    require(read(cpu_report)['status']=='complete','bounded R07 raw DB validation')
    profile=PROJECT/'perf_trace_batch8/configs/trace_targets/batch8_dual_dcu_dp2.json'
    require(sha(profile)==predecessor.PROFILE_HASH,'profile')
    require(sha(R02_INVENTORY)=='c1d162a66c564d25553fef2d0d99b5d7e1e9ff0be6ba84fe6bfbbde9d9142a1a','R02 inventory')
    r02_argv=r02_bindings(ROOT,environ={'R08_R02_ROOT':str(R02)})
    regressions=[]
    regressions.append(rejected(lambda:r02_bindings(ROOT,r02_root=ROOT,environ={'R08_R02_ROOT':str(R02)}),'R08 mistaken for R02 owner'))
    regressions.append(rejected(lambda:r02_bindings(ROOT,environ={}),'missing R08_R02_ROOT'))
    positive_project=predecessor.resolve_source(str(profile.relative_to(PROJECT)))
    positive_absolute=predecessor.resolve_source(str(profile))
    require(positive_project==positive_absolute==profile,'project/absolute resolver')
    regressions.append(rejected(lambda:predecessor.resolve_source('../escape'),'predecessor traversal'))
    regressions.append(rejected(lambda:predecessor.resolve_source('/etc/passwd'),'unrelated external source'))
    missing=ROOT/'validation/path_regression_missing/child/result.json'
    require(not missing.parent.exists(),'missing-parent fixture must start absent')
    require(output_path(missing,True)==missing,'legal missing-parent output')
    escape=ROOT/'validation/path_escape_fixture';escape.symlink_to('/tmp',target_is_directory=True)
    regressions.append(rejected(lambda:output_path(escape/'illegal.json'),'unlisted output symlink'))
    regressions.append(rejected(lambda:output_path(ROOT/'validation/../escape'),'output traversal'))
    authorized=ROOT/'raw/captures/future/record.json'
    require(output_path(authorized)==authorized,'authorized output bulk path')
    with patch('r08_native.os.readlink',return_value='/tmp/wrong-bulk'):
        regressions.append(rejected(lambda:output_path(authorized),'changed bulk symlink'))
    original_read=read
    for label,mutation in [('wrong bulk root',lambda x:x['paths'].update({str(ROOT/'raw'):'/root/wrong_bulk/raw'})),('wrong storage device',lambda x:x.update(root_filesystem_device=-1))]:
        bad=copy.deepcopy(read(ROOT/'authorization/bulk_storage_authorization.json'));mutation(bad)
        with patch('r08_native.read',side_effect=lambda p,bad=bad:bad if str(p).endswith('/bulk_storage_authorization.json') else original_read(p)):
            regressions.append(rejected(lambda:output_path(authorized),label))
    bad_assignment=copy.deepcopy(assignment);bad_assignment.pop('bulk_storage_authorization_sha256')
    with patch('r08_native.read',side_effect=lambda p:bad_assignment if str(p).endswith('/continuation_assignment.json') else original_read(p)):
        regressions.append(rejected(lambda:output_path(authorized),'missing authorization hash'))
    plan=read(ROOT/'plans/logical_plan.json');require(plan['selected_family_count']==32 and len(plan['selected_families'])==32,'logical family denominator')
    token_map=[]
    for family in plan['selected_families']:
        f=family['r06_plan'];literal=f['kernel_name_filter_literal'];token=collector_token(literal)
        require(collector_token(literal)==token,'deterministic transport')
        argv=collector_argv('pmc',token,ROOT/'raw/captures/future',[sys.executable,'-B','future_tracee.py'])
        require(argv[argv.index('--kernel-name')+1]==token,'production token argv')
        analyzer=analyzer_argv(literal,ROOT/'raw/captures/future')
        require(analyzer[-1]==literal,'full-literal analyzer argv')
        token_map.append({'plan_id':f['plan_id'],'kernel_name_filter_literal':literal,'literal_sha256':hashlib.sha256(literal.encode()).hexdigest(),'collector_kernel_name_token':token,'token_sha256':hashlib.sha256(token.encode()).hexdigest(),'collector_argv':argv,'analyzer_argv':analyzer})
    require(collector_token('void rocprim::detail::single_scan_kernel<int, thing<float>>(int, thing<void (int)>)')=='single_scan_kernel','nested balanced parser')
    for value in ['^foo$',r'foo\(int\)','void foo<int>(int','void foo<int(int)']:
        regressions.append(rejected(lambda value=value:collector_token(value),'malformed/regex token '+value))
    manifest=RUN/'artifacts/R01/contract/request_selection.json'
    require(sha(manifest)=='dc8b848a360d977d1c30adcace393459bce536aa2278ff997d6c71b9e94be280','request manifest')
    dataset=CONTROL/'snapshot/inputs/testdata/16-32K_throughput.jsonl'
    require(sha(dataset)=='633ba4c8b4f500d2ab28094de42698c5494e5232f40eafcd119c0a314b44b936','dataset')
    m=read(manifest)
    with dataset.open('rb') as f:lines=[next(f) for _ in range(8)]
    require(len(m['records'])==8,'eight selected rows')
    for row,line in zip(m['records'],lines):require(hashlib.sha256(line).hexdigest()==row['raw_line_sha256'],'exact ordered request bytes')
    abi=read(CONTROL/'vllm_rebuild_manifest.json')
    for extension in abi['extensions']:require(sha(extension['path'])==extension['sha256'],'current rebuilt ABI')
    candidates=[]
    for distribution in importlib.metadata.distributions():
        if distribution.metadata.get('Name','').lower()=='vllm':
            package=Path(distribution.locate_file('vllm'))
            candidates.append({'package':str(package),'version':distribution.version,'has_C':(package/'_C.abi3.so').is_file(),'has_rocm_C':(package/'_rocm_C.abi3.so').is_file()})
    require(any(c['package']=='/usr/local/lib/python3.10/dist-packages/vllm' and c['has_C'] and c['has_rocm_C'] for c in candidates),'source-only checkout plus explicit system ABI')
    require(read(CONTROL/'WEIGHTS_COMPLETE.json')['all_modelscope_sha256_verified'],'complete model weights')
    tools=[]
    for p in sorted(TOOLS.iterdir()):
        if p.suffix=='.py':compile(p.read_text(),str(p),'exec')
        if p.is_file():tools.append(source_record(p))
    require(os.access(TOOLS/'r08_native_correlation_probe',os.X_OK),'native probe executable mode')
    report={'status':'complete','scope':'current_R08_model_free_device_capability_only','model_capture_authorized':False,'next_step':'separate_current_device_capability_tool_call','source_binding':binding,'predecessor_validations':validations,'r07_recovered_admission':source_record(CONTINUATION/'RECOVERED_R07_ADMISSION.json'),'r07_original_status':'complete_recovered_offline','r07_current_raw_db_validation':source_record(cpu_report),'current_resolver':source_record(CONTINUATION/'continuation_common.py'),'assignment':source_record(ROOT/'authorization/continuation_assignment.json'),'r02_root':str(R02),'r02_inventory':source_record(R02_INVENTORY),'r02_production_argv':r02_argv,'regressions':regressions,'literal_to_token_map':token_map,'abi_candidates':candidates,'rebuilt_abi_manifest':source_record(CONTROL/'vllm_rebuild_manifest.json'),'workload':{'requests':8,'warmups':2,'output_tokens_each':1024,'concurrency':8,'devices':[0,1],'dp':2,'tp':1},'frozen_tools':tools,'lifecycle_counts_this_gate':{'device_queries':0,'profiler_starts':0,'model_imports':0,'model_initializations':0,'warmups':0,'measured_requests':0,'accepted_captures':0},'R07_observed_time_is_only_latency_axis':True}
    save(ROOT/'validation/predevice_capability_gate.json',report)
    print('CPU_PREDEVICE_CAPABILITY_GATE_COMPLETE',flush=True)

if __name__=='__main__':main()
