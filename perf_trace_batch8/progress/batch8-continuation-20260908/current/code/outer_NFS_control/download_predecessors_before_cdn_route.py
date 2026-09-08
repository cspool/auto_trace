import concurrent.futures
import hashlib
import json
from pathlib import Path
import time
import requests
import sys
import os
import re

ROOT = Path('/public/home/accl15ptg7/run_R08_R10')
CATALOG = Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/releases/batch8-r08-continuation-20260908/RELEASE_CATALOG.json')

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()

def download(item):
    tag, a = item
    dest = ROOT / 'downloads' / tag / a['name']
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size == a['size'] and sha(dest) == a['sha256']:
        print('VERIFIED existing', dest.name, flush=True)
        return
    tmp = dest.with_name(dest.name + '.partial')
    session = requests.Session()
    download_url = a['url']
    for attempt in range(80):
        try:
            offset = tmp.stat().st_size if tmp.exists() else 0
            while offset < a['size']:
                end = min(a['size'] - 1, offset + 64 * 1024 * 1024 - 1)
                with session.get(download_url, headers={'Range': f'bytes={offset}-{end}'}, stream=True, timeout=(30, 90)) as r:
                    if r.status_code in (401, 403) and download_url != a['url']:
                        download_url = a['url']
                        raise RuntimeError('Refreshing expired signed asset URL')
                    r.raise_for_status()
                    if r.status_code == 206:
                        parsed = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', r.headers.get('Content-Range', ''))
                        assert parsed and int(parsed[1]) == offset and int(parsed[3]) == a['size'], ('invalid content range', r.headers.get('Content-Range'), offset)
                    else:
                        assert offset == 0, ('server ignored resume range', offset)
                    download_url = r.url
                    before = offset
                    with tmp.open('ab' if offset else 'wb') as f:
                        for b in r.iter_content(1024 * 1024):
                            f.write(b)
                            offset += len(b)
                            if offset >= end + 1:
                                break
                    assert offset > before, 'empty transfer'
            assert tmp.stat().st_size == a['size'], (tmp, tmp.stat().st_size, a['size'])
            if sha(tmp) != a['sha256']:
                tmp.rename(tmp.with_name(tmp.name + f'.badsha-{int(time.time())}'))
                raise RuntimeError('Preserved corrupt downloaded bytes; retrying original asset')
            tmp.rename(dest)
            print('VERIFIED downloaded', dest.name, a['size'], flush=True)
            return
        except Exception as e:
            print('RETRY', a['name'], attempt, str(e)[:300], flush=True)
            time.sleep(min(30, 2 ** attempt))
    raise RuntimeError(a['name'])

releases = json.loads(CATALOG.read_text())['releases']
items = []
for key in (sys.argv[1:] or ['offline-recovery', 'r04-r06-batch8', 'r01-r03-batch8']):
    for r in releases:
        if key in r['tag']:
            for a in r['assets']:
                if '.db.gz' in a['name'] or '.tar.gz' in a['name'] or '.tar.zst' in a['name'] or a['name'] in ['SHA256SUMS', 'ARCHIVE_STREAM_SHA256', 'runtime_handoff_ledger.R06.snapshot.json', 'README.md', 'PARTS.tsv', 'DB_PACKAGE_MANIFEST.json', 'PACKAGE_COMPLETE.json', 'RECOVERY_ENTRYPOINT.json', 'RECOVERY_INDEX.json', 'SOURCE_DB_SHA256']:
                    items.append((r['tag'], a))
with concurrent.futures.ThreadPoolExecutor(max_workers=int(os.environ.get('ARCHIVE_DOWNLOAD_WORKERS', '2'))) as pool:
    list(pool.map(download, items))
print('ALL_DOWNLOADS_VERIFIED', flush=True)
