"""Publish retained failed raw attempts without accepting or evicting them."""
from pathlib import Path
import ast
import json
import os
import time
import hashlib
import tarfile
import zstandard
import datetime

C=Path('/public/home/accl15ptg7/run_R08_R10')
P=Path('/public/home/accl15ptg7/auto_trace')
R=P/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001'
B=R/'raw/runtime_tools'
OUT=C/'publication_emergency/r08_capture09_closed_prehealth_failures_001'
publisher_source=(C/'publish_accepted_captures_004.py').read_text()
namespace={}
exec(compile(publisher_source.split('while time.time()<DEADLINE:')[0],'<verified-publication-helpers>','exec'),namespace)
sha,save,read=namespace['sha'],namespace['save'],namespace['read']
SplitWriter,ConcatReader=namespace['SplitWriter'],namespace['ConcatReader']
node=next(n for n in ast.parse(publisher_source).body if isinstance(n,ast.FunctionDef) and n.name=='publish')
definition=ast.get_source_segment(publisher_source,node).replace('def publish(item,out,package_manifest):','def publish_diagnostic(item,out,package_manifest):')
definition=definition.replace("tag='perf-trace-batch8-r08-'+item['segment_id'].replace('_','-')+'-20260908'","tag='perf-trace-batch8-r08-capture09-prehealth-failures-20260908-001'")
body='R08 第9组 attempts001–005 在正式八并发测量前因原生 PMC 缺失而失败。本 Release 保留全部已关闭尝试的原始 DB、CSV、PMC 快照、控制凭证和日志，以及已完成的原生诊断探针。\n\n这些失败尝试不计入 R08 验收；不得将本 Release 当成 R08、R09 或 R10 完成。当前已验收的前八组分别在原有 Release 中。所有原始失败数据在 NFS 上继续保留，本次不删除任何原始文件。\n\n按 ASSET_MANIFEST 顺序拼接 capture.tar.zst.partNNN，再以 zstd/tar 解包。FILE_MANIFEST 记录每个成员的原始路径与 SHA256；CONTROL_LOGS 成员恢复到其中 original_path 指定的控制目录。'
start=definition.index(";body='R08 已通过独立审计")
end=definition.index('\n  response=api.post',start)
definition=definition[:start]+';body='+repr(body)+definition[end:]
definition=definition.replace("'name':'R08 accepted capture '+item['segment_id']","'name':'R08 第9组前五次采集失败原始检查点'")
definition=definition.replace("'accepted_item':item","'diagnostic_item':item")
definition=definition.replace('ACCEPTED_CAPTURE_','CLOSED_FAILED_CAPTURE_')
exec(compile(definition,'<closed-failure-publication>','exec'),namespace)
publish=namespace['publish_diagnostic']


def package():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'ASSET_MANIFEST.json').exists():
        value=read(OUT/'ASSET_MANIFEST.json')
        for item in value['assets']:
            path=OUT/item['name'];assert path.stat().st_size==item['size'] and sha(path)==item['sha256']
        return value
    assert not list(OUT.glob('capture.tar.zst.part*')),'preserve interrupted package for explicit recovery'
    files=set()
    groups=[]
    failed=[]
    for number in range(1,6):
        root=R/'raw/captures/09_chunk_gated_delta_rule_fwd_kernel_h_blockdim64_pmc_write'/f'attempt_{number:03d}'
        failure=read(root/'RAW_CAPTURE_FAILURE.json');cleanup=read(root/'control/tracee_process_cleanup.json')
        assert failure['status']=='failed_not_accepted' and not (root/'workload/driver.json').exists()
        groups.extend([failure['profiler_cleanup']['leader_pid'],cleanup['service']['leader_pid'],cleanup['workload']['leader_pid']])
        for original in read(root/'raw_inventory_at_exit.json')['files']:
            path=Path(original['path']);assert path.stat().st_size==original['size'] and sha(path)==original['sha256']
        files.update(p for p in root.rglob('*') if p.is_file())
        failed.append({'attempt':root.name,'failure_path':str(root/'RAW_CAPTURE_FAILURE.json'),'failure_sha256':sha(root/'RAW_CAPTURE_FAILURE.json')})
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:fields=(proc/'stat').read_text().split(') ',1)[1].split()
        except OSError:continue
        assert int(fields[2]) not in groups,'failed attempt still has a live process group'
    for directory in sorted(B.glob('native_PMC_*probe_*')):
        if (directory/'RESULT.json').exists():files.update(p for p in directory.rglob('*') if p.is_file())
    files.update(p for p in B.glob('capture09*diagnostic*.json') if p.is_file())
    files.update(p for p in B.glob('capture09*native_device_context*.json') if p.is_file())
    files.update(p for p in C.glob('probe_native_*.log') if p.is_file())
    for name in ['query_capture09_attempt004_device_context_001.log','publish_closed_capture09_failures_001.py']:
        path=C/name
        if path.exists():files.add(path)
    manifest=[]
    for path in sorted(files):
        member=str(path.relative_to(P)) if path.is_relative_to(P) else 'CONTROL_LOGS/'+path.name
        manifest.append({'path':member,'original_path':str(path),'size':path.stat().st_size,'sha256':sha(path)})
    assert len({x['path'] for x in manifest})==len(manifest)
    save(OUT/'FILE_MANIFEST.json',{'schema_version':1,'status':'closed_failed_diagnostic_sources_not_accepted','failed_attempts':failed,'files':manifest,'R08_complete_claimed':False,'failed_attempts_count_toward_acceptance':False,'original_local_sources_retained':True})
    writer=SplitWriter(OUT)
    try:
        with zstandard.ZstdCompressor(level=3,threads=2).stream_writer(writer,closefd=False) as compressed:
            with tarfile.open(fileobj=compressed,mode='w|',dereference=True) as archive:
                for entry in manifest:archive.add(entry['original_path'],arcname=entry['path'],recursive=False)
                archive.add(OUT/'FILE_MANIFEST.json',arcname='PUBLICATION_FILE_MANIFEST.json',recursive=False)
    finally:writer.close()
    expected={x['path']:x for x in manifest};seen=set();concat=ConcatReader(writer.paths)
    with zstandard.ZstdDecompressor().stream_reader(concat) as stream:
        with tarfile.open(fileobj=stream,mode='r|') as archive:
            for member in archive:
                if member.name=='PUBLICATION_FILE_MANIFEST.json':assert json.load(archive.extractfile(member))==read(OUT/'FILE_MANIFEST.json');continue
                assert member.isfile() and member.name in expected and member.name not in seen
                digest=hashlib.sha256();source=archive.extractfile(member)
                for block in iter(lambda:source.read(8<<20),b''):digest.update(block)
                assert member.size==expected[member.name]['size'] and digest.hexdigest()==expected[member.name]['sha256']
                seen.add(member.name)
    assert seen==set(expected)
    assets=[{'name':p.name,'size':p.stat().st_size,'sha256':sha(p)} for p in writer.paths+[OUT/'FILE_MANIFEST.json']]
    result={'status':'verified_ready_for_release','member_count':len(manifest),'member_bytes':sum(x['size'] for x in manifest),'archive_codec':'zstd concatenated stream; concatenate parts in manifest order','assets':assets}
    save(OUT/'ASSET_MANIFEST.json',result)
    (OUT/'SHA256SUMS').write_text(''.join(x['sha256']+'  '+x['name']+'\n' for x in assets))
    print('FAILED_NATIVE_SOURCES_ARCHIVE_VERIFIED',len(manifest),result['member_bytes'],sum(x['size'] for x in assets),flush=True)
    return result


if __name__=='__main__':
    manifest=package()
    item={'segment_id':'capture09_closed_prehealth_failures_attempts001_005','status':'failed_not_accepted','failed_attempt_count':5,'R08_complete_claimed':False}
    for attempt in range(3):
        try:
            if not (OUT/'PUBLICATION_COMPLETE.json').exists():publish(item,OUT,manifest)
            break
        except Exception as error:
            print('FAILED_CHECKPOINT_PUBLICATION_RETRY',attempt+1,type(error).__name__,flush=True)
            if attempt==2:raise
            time.sleep(10)
    receipt=read(OUT/'PUBLICATION_COMPLETE.json');assert receipt['status']=='published' and receipt['all_server_asset_sha256_match']
    print('CLOSED_FAILURE_CHECKPOINT_REMOTE_COMPLETE',receipt['url'],flush=True)
