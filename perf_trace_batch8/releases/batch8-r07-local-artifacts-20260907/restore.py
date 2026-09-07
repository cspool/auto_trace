#!/usr/bin/env python3
"""Restore the hash-indexed R07 snapshot from its original and supplement releases."""

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def destination(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or not relative.parts:
        raise ValueError(f'Unsafe archive path: {name}')
    target = root.joinpath(*relative.parts)
    current = target
    while current != root:
        if current.is_symlink():
            raise ValueError(f'Refusing to write through symlink: {current}')
        current = current.parent
    return target


def download(item, cache):
    target = cache / item['sha256']
    if target.is_file() and target.stat().st_size == item['size'] and sha256(target) == item['sha256']:
        return target
    partial = target.with_suffix('.partial')
    for attempt in range(5):
        try:
            print('Downloading', item.get('asset', item['url']), flush=True)
            request = urllib.request.Request(item['url'], headers={'User-Agent': 'auto-trace-r07-restore'})
            with urllib.request.urlopen(request, timeout=60) as response, partial.open('wb') as out:
                shutil.copyfileobj(response, out, 8 * 1024 * 1024)
            if partial.stat().st_size != item['size'] or sha256(partial) != item['sha256']:
                raise ValueError('Downloaded size/hash mismatch')
            partial.replace(target)
            return target
        except Exception:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)


def assemble(source, cache):
    if 'parts' not in source:
        return download(source, cache)
    target = cache / source['sha256']
    if target.is_file() and target.stat().st_size == source['size'] and sha256(target) == source['sha256']:
        return target
    partial = target.with_suffix('.partial')
    digest = hashlib.sha256()
    with partial.open('wb') as output:
        for part in source['parts']:
            path = download(part, cache)
            with path.open('rb') as input_file:
                for block in iter(lambda: input_file.read(8 * 1024 * 1024), b''):
                    digest.update(block)
                    output.write(block)
    if partial.stat().st_size != source['size'] or digest.hexdigest() != source['sha256']:
        raise ValueError('Assembled archive size/hash mismatch')
    partial.replace(target)
    return target


def write_verified(stream, entry, root):
    target = destination(root, entry['path'])
    if target.exists():
        if target.is_file() and target.stat().st_size == entry['size'] and sha256(target) == entry['sha256']:
            return
        raise FileExistsError(f'Existing file differs from snapshot: {target}')
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.r07-', delete=False) as output:
        temporary = Path(output.name)
        try:
            while block := stream.read(8 * 1024 * 1024):
                digest.update(block)
                output.write(block)
            output.flush()
            if output.tell() != entry['size'] or digest.hexdigest() != entry['sha256']:
                raise ValueError(f'Extracted file size/hash mismatch: {entry["path"]}')
            temporary.chmod(entry['mode'])
            # The exclusive link fails if another process created the destination.
            target.hardlink_to(temporary)
        finally:
            temporary.unlink(missing_ok=True)


def restore_archive(path, members, root, compression='gzip'):
    wanted = dict(members)
    command = ['zstd', '-dc', str(path)] if compression == 'zstd' else ['gzip', '-dc', str(path)]
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdout, mode='r|') as archive:
            for member in archive:
                if member.name not in wanted:
                    continue
                if not member.isfile():
                    raise ValueError(f'Expected regular file: {member.name}')
                entries = wanted.pop(member.name)
                first = entries[0]
                with archive.extractfile(member) as source:
                    write_verified(source, first, root)
                for entry in entries[1:]:
                    with destination(root, first['path']).open('rb') as source:
                        write_verified(source, entry, root)
        # Consume any trailing padding so the decompressor can exit normally.
        while process.stdout.read(8 * 1024 * 1024):
            pass
    except BaseException:
        process.terminate()
        process.wait()
        raise
    finally:
        process.stdout.close()
    if process.wait() != 0 or wanted:
        raise ValueError(f'Archive incomplete: {list(wanted)[:5]}')


def verify(entries, root):
    failures = []
    for entry in entries:
        path = destination(root, entry['path'])
        if not path.is_file() or path.stat().st_size != entry['size'] or sha256(path) != entry['sha256']:
            failures.append(entry['path'])
    if failures:
        raise ValueError(f'{len(failures)} missing/changed files; first: {failures[:5]}')
    print(f'Verified {len(entries)} regular files. Historical links are recorded in SYMLINKS.json.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Destination project root')
    parser.add_argument('--manifest', type=Path, default=Path(__file__).with_name('FILE_MANIFEST.json'))
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--supplement-only', action='store_true', help='Restore/verify only newly published files')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    entries = manifest['files']
    if args.supplement_only:
        entries = [e for e in entries if e['coverage']['type'].startswith('supplement_')]
    root = args.root.resolve()
    if args.verify_only:
        verify(entries, root)
        return
    root.mkdir(parents=True, exist_ok=True)
    cache = root / '.r07_restore_cache'
    if cache.is_symlink():
        raise ValueError('Restore cache must not be a symlink')
    cache.mkdir(exist_ok=True)
    archive_groups = defaultdict(lambda: defaultdict(list))
    direct_groups = defaultdict(list)
    direct_sources = {}
    for entry in entries:
        target = destination(root, entry['path'])
        if target.is_file() and target.stat().st_size == entry['size'] and sha256(target) == entry['sha256']:
            continue
        coverage = entry['coverage']
        if coverage['type'].startswith('supplement_'):
            member = coverage.get('canonical_path', entry['path'])
            archive_groups['supplement'][member].append(entry)
        elif coverage['kind'] == 'release_archive_member':
            archive_groups[coverage['archive']][coverage['member']].append(entry)
        else:
            direct_groups[entry['sha256']].append(entry)
            direct_sources[entry['sha256']] = coverage
    sources = {s.get('asset', s.get('stream')): s for s in manifest['archive_sources']}
    sources['supplement'] = manifest['supplement']
    for name, members in archive_groups.items():
        source = sources[name]
        archive = assemble(source, cache)
        restore_archive(archive, members, root, source.get('compression', 'gzip'))
    for digest, group in direct_groups.items():
        source = direct_sources[digest]
        payload = assemble(source, cache)
        for entry in group:
            with payload.open('rb') as stream:
                write_verified(stream, entry, root)
    verify(entries, root)


if __name__ == '__main__':
    main()
