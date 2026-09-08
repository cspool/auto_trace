"""Restore verified archive streams to fast tmpfs; retain NFS archive originals."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import shutil
import os

CONTROL = Path('/public/home/accl15ptg7/run_R08_R10')
CATALOG = Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/releases/batch8-r08-continuation-20260908/RELEASE_CATALOG.json')
STREAM_HASHES = {
    'r01-r03': '4a55990b77a4a5eea0e0d38aeccf474f220b0c0b8c1054d10090ed711567a530',
    'r04-r06': 'ffd4f191083aaed418345e42c92d0e3dc6e0e2b500e7ee0a902f56cc7dc735d2',
}

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('family');ap.add_argument('--destination',type=Path,required=True)
    args=ap.parse_args()
    releases=json.loads(CATALOG.read_text())['releases']
    release=next(r for r in releases if args.family+'-batch8' in r['tag'])
    folder=CONTROL/'downloads'/release['tag']
    assets=sorted((a for a in release['assets'] if '.tar.gz.part-' in a['name']),key=lambda a:a['name'])
    stream=hashlib.sha256();parts=[]
    for a in assets:
        p=folder/a['name'];assert p.stat().st_size==a['size'],p
        h=hashlib.sha256()
        with p.open('rb') as f:
            for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b);stream.update(b)
        assert h.hexdigest()==a['sha256'],p
        parts.append(p)
    expected=STREAM_HASHES.get(args.family)
    if expected is None:
        expected=(folder/'ARCHIVE_STREAM_SHA256').read_text().split()[0]
    assert stream.hexdigest()==expected,('stream hash',stream.hexdigest(),expected)
    print('STREAM_VERIFIED',args.family,len(parts),flush=True)
    dest=args.destination.resolve();dest.mkdir(parents=True,exist_ok=True)
    proc=subprocess.Popen(['cat',*map(str,parts)],stdout=subprocess.PIPE)
    records=[];links=[];count=0;total=0
    try:
        with tarfile.open(fileobj=proc.stdout,mode='r|gz') as archive:
            for m in archive:
                relative=Path(m.name)
                assert not relative.is_absolute() and '..' not in relative.parts,m.name
                out=dest/relative
                assert out.resolve().is_relative_to(dest),m.name
                if m.isdir():out.mkdir(parents=True,exist_ok=True);continue
                if m.issym() or m.islnk():
                    links.append({'member':m.name,'target':m.linkname,'type':m.type.decode()});continue
                assert m.isfile(),('unsupported type',m.name,m.type)
                out.parent.mkdir(parents=True,exist_ok=True)
                src=archive.extractfile(m);h=hashlib.sha256()
                if out.exists():
                    for b in iter(lambda:src.read(8*1024*1024),b''):h.update(b)
                    assert out.stat().st_size==m.size and digest(out)==h.hexdigest(),('conflict',out)
                else:
                    with out.open('xb') as f:
                        for b in iter(lambda:src.read(8*1024*1024),b''):f.write(b);h.update(b)
                    out.chmod(m.mode & 0o777)
                records.append({'member':m.name,'size':m.size,'sha256':h.hexdigest()})
                count+=1;total+=m.size
                if count%2000==0:print('EXTRACTED',count,total,flush=True)
        assert proc.wait()==0
    finally:
        proc.stdout.close()
        if proc.poll() is None:proc.terminate();proc.wait()
    result={'family':args.family,'destination':str(dest),'stream_sha256':expected,'entries':records,'historical_links_not_created':links,'file_count':count,'logical_bytes':total}
    (CONTROL/f'{args.family}_restore_manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print('RESTORE_COMPLETE',args.family,count,total,'links recorded',len(links),flush=True)

if __name__=='__main__':main()
