"""CPU-safe path, native collector, and exact-literal contract primitives."""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys

TOOLS=Path(__file__).parent
ROOT=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001')
PROJECT=Path('/public/home/accl15ptg7/auto_trace')
RUN=PROJECT/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003'
TARGET=PROJECT/'pra2026-bh408-gqa-page784-k5120-batch8'
R02=RUN/'artifacts/R02'
R02_INVENTORY=R02/'instrumentation/process_range_inventory.json'
HIPPROF=Path('/opt/dtk/bin/hipprof')
DCC=Path('/opt/dtk-26.04-DCC2602-0317/dcc/lib')
MODES={'pmc':'--pmc','pmc_read':'--pmc-read','pmc_write':'--pmc-write'}
HIPPROF_SHA='53f67d3dd4c1fe5aa9850f58d174ecf9f2c688f1e07519b456b19ca699c57f22'

def require(condition,message):
    if not condition:raise ValueError(message)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()

def read(path):return json.loads(Path(path).read_text())

def save(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x') as f:json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())

def source_record(path):
    p=Path(path)
    return {'path':str(p),'size':p.stat().st_size,'sha256':sha(p)}

def output_path(value,create_parent=False):
    p=Path(value)
    require(p.is_absolute() and '..' not in p.parts and p.is_relative_to(ROOT),'output lexical containment')
    authpath=ROOT/'authorization/NFS_output_storage_authorization_001.json';authorization=read(authpath)
    require(authorization['status']=='complete' and sha(authorization['original_root_bulk_authorization']['path'])==authorization['original_root_bulk_authorization']['sha256'],'explicit NFS override preserves original authorization')
    require(sha(authorization['migration_proof']['path'])==authorization['migration_proof']['sha256'],'complete verified NFS migration')
    alias=authorization['original_directory_alias'];require(Path(alias['path']).is_symlink() and os.readlink(alias['path'])==alias['destination'],'exact root alias to physical NFS')
    resolved=p.resolve(strict=False);bound=False
    for lexical,destination in authorization['paths'].items():
        lexical=Path(lexical);destination=Path(destination)
        if p.is_relative_to(lexical):
            require(lexical.is_symlink() and os.readlink(lexical)==authorization['original_logical_bulk_links'][str(lexical)],'original canonical bulk link retained')
            require(resolved==destination/p.relative_to(lexical),'no unlisted nested output link')
            require(destination.stat().st_dev==authorization['NFS_filesystem_device'],'physical NFS output device')
            bound=True
    if not bound:require(resolved==p and p.parent.stat().st_dev==authorization['NFS_filesystem_device'],'unlisted output link or non-NFS metadata')
    if create_parent:
        p.parent.mkdir(parents=True,exist_ok=True)
        require(p.resolve(strict=False)==resolved and p.parent.stat().st_dev==authorization['NFS_filesystem_device'],'post-creation physical NFS containment')
    return p

def r02_bindings(artifact_root,inventory=R02_INVENTORY,r02_root=R02,environ=None):
    env=os.environ if environ is None else environ
    require(env.get('R08_R02_ROOT')==str(R02),'mandatory exact R08_R02_ROOT')
    require(Path(r02_root)==R02 and Path(inventory)==R02_INVENTORY,'R02 lexical bindings')
    require(Path(artifact_root)==ROOT and Path(artifact_root)!=R02,'R02/R08 root separation')
    require(R02.is_symlink() and R02.resolve()==Path('/dev/shm/r08_continuation_predecessors/artifacts/R02'),'explicit canonical R02 relocation')
    require(R02_INVENTORY.resolve().is_relative_to(R02.resolve()),'R02 inventory owner')
    return ['--r02-root',str(R02),'--r02-inventory',str(R02_INVENTORY),'--artifact-root',str(ROOT)]

def _strip_terminal(value,opening,closing):
    if not value.endswith(closing):return value
    depth=0
    for i in range(len(value)-1,-1,-1):
        c=value[i]
        if c==closing:depth+=1
        elif c==opening:
            depth-=1
            if depth==0:return value[:i].rstrip()
            require(depth>=0,'malformed terminal delimiters')
    raise ValueError('unbalanced terminal delimiters')

def collector_token(literal):
    require(isinstance(literal,str) and literal.strip()==literal and literal,'literal bytes')
    require(not any(c in literal for c in ['\n','\r','\x00','\\','^','$','|']),'regex or ambiguous literal transport')
    value=_strip_terminal(literal,'(',')')
    value=_strip_terminal(value,'<','>')
    token=re.split(r'::|\s+',value)[-1]
    require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',token) is not None,'unsupported or malformed collector token: '+literal)
    return token

def collector_argv(mode,token,output,tracee,*,trace=True,disabled=False):
    require(mode in MODES,'counter mode')
    require(token is None or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',token),'collector token argument')
    output=output_path(output)
    argv=[str(HIPPROF),MODES[mode],'--pmc-type','3']
    if token is not None:argv+=['--kernel-name',token]
    if trace:argv+=['--hip-trace','--hiptx-trace','--trace-args','--no-export']
    if disabled:argv+=['--pmc-off','--trace-off']
    return argv+['--follow-fork','--exit-cleanup','-d',str(output/'hipprof_tmp'),'-o',str(output/'capture'),*map(str,tracee)]

def analyzer_argv(literal,capture):
    return [sys.executable,'-B',str(TOOLS/'normalize_r08_pmc.py'),'--capture',str(capture),'--kernel-name-literal',literal]

def clean_env():
    env={k:v for k,v in os.environ.items() if not k.startswith(('HIPPROF_','ROCPROFILER_','QWEN_DCU_')) and k not in ['LD_PRELOAD','HSA_TOOLS_LIB','HSA_TOOLS_LIB64','ROCP_TOOL_LIB','ROCP_HSA_INTERCEPT','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy','ftp_proxy','FTP_PROXY']}
    env.update(HIP_VISIBLE_DEVICES='0,1',CUDA_VISIBLE_DEVICES='0,1',PYTHONDONTWRITEBYTECODE='1',LD_LIBRARY_PATH=str(DCC)+':/opt/dtk/lib:/opt/dtk/hip/lib:/opt/dtk/rocprofiler/lib:/opt/hyhal/lib',NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost')
    return env

def source_binding():
    def git(*args):return subprocess.check_output(['git','-C',str(TARGET),*args],text=True).strip()
    require(git('rev-parse','HEAD')=='2b4b2119ae3cc2c4c626dc5690ef9593c1477f66','target commit')
    require(git('branch','--show-current')=='repro-gqa-page784-k5120-batch8-final','target branch')
    require(not git('status','--porcelain','--untracked-files=all'),'target source is not clean')
    require(sha(HIPPROF)==HIPPROF_SHA,'collector binary')
    return {'commit':git('rev-parse','HEAD'),'branch':git('branch','--show-current'),'clean':True,'collector':source_record(HIPPROF)}

DISPATCH_PATTERN=re.compile(r'^dispatch\[(?P<raw_index>\d+)\], gpu-id\((?P<gpu_id>[^)]*)\), queue-id\((?P<queue_id>[^)]*)\), queue-index\((?P<queue_index>[^)]*)\), pid\((?P<pid>[^)]*)\), tid\((?P<tid>[^)]*)\), grd\((?P<grd>[^)]*)\), wgr\((?P<wgr>[^)]*)\), lds\((?P<lds>[^)]*)\), scr\((?P<scr>[^)]*)\), arch_vgpr\((?P<arch_vgpr>[^)]*)\), accum_vgpr\((?P<accum_vgpr>[^)]*)\), sgpr\((?P<sgpr>[^)]*)\), wave_size\((?P<wave_size>[^)]*)\), sig\((?P<sig>[^)]*)\), kernel-name\("(?P<kernel_name>.*)"\), time\((?P<dispatch_ns>\d+),(?P<begin_ns>\d+),(?P<end_ns>\d+),(?P<complete_ns>\d+)\)$')
COUNTER_PATTERN=re.compile(r'^\s+(.+?) \((-?\d+)\)$')

def raw_pmc_rows(path):
    current=None
    with Path(path).open() as f:
        for number,line in enumerate(f,1):
            line=line.rstrip('\n');match=DISPATCH_PATTERN.fullmatch(line)
            if match:
                if current is not None:yield current
                current={**match.groupdict(),'counters':{},'raw_path':str(path),'raw_line':number}
                continue
            match=COUNTER_PATTERN.fullmatch(line)
            if match:
                require(current is not None,'counter before dispatch')
                name,value=match.groups();require(name not in current['counters'],'duplicate native counter')
                current['counters'][name]=int(value);continue
            require(not line.strip(),'unparsed native PMC line: '+line[:160])
    if current is not None:yield current
