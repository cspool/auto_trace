"""Lossless, explicitly derived union of closed independent native sessions.

Original DBs and CSVs remain authoritative and are retained unchanged. Native
per-PID table rowids stay exact. Shared metadata rowids have recorded offsets.
No native timestamp, counter value, device ID, PID, or correlation ID changes.
"""
from pathlib import Path
import csv
import hashlib
import json
import re
import sqlite3
import os

SHARED_TABLES = {'CONFIG', 'STR_TABLE', 'TRACE_COUNTER', 'SUMMARY'}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def record(path):
    path = Path(path)
    return {'path': str(path), 'size': path.stat().st_size, 'sha256': sha(path)}


def save(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def q(name):
    if not re.fullmatch(r'[A-Za-z0-9_]+', name):
        raise ValueError('unsupported native SQL identifier')
    return '"' + name + '"'


def readonly(path):
    return sqlite3.connect(Path(path).as_uri() + '?mode=ro&immutable=1', uri=True)


def row_digest(cursor, offset=0):
    digest = hashlib.sha256()
    count = 0
    for row in cursor:
        identity = [row[0] - offset, *row[1:]]
        digest.update((json.dumps(identity, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode())
        count += 1
    return count, digest.hexdigest()


def merge(source_directories, output):
    output = Path(output)
    assert len(source_directories) == 2
    assert not (output / 'capture.db').exists() and not (output / 'capture.csv').exists()
    originals = [Path(p) for p in source_directories]
    sources = []
    pids, keys = set(), set()
    for rank, directory in enumerate(originals):
        db_record = record(directory / 'capture.db')
        csv_record = record(directory / 'capture.csv')
        con = readonly(directory / 'capture.db')
        assert con.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        config = con.execute('SELECT PID,KEY FROM CONFIG').fetchall()
        assert config and not (pids & {x[0] for x in config}) and not (keys & {x[1] for x in config})
        pids.update(x[0] for x in config)
        keys.update(x[1] for x in config)
        assert not con.execute("SELECT name FROM sqlite_master WHERE type NOT IN ('table','index')").fetchall()
        sources.append({'rank': rank, 'database': db_record, 'csv': csv_record,
                        'config_pid_keys': config, 'tables': []})
        con.close()
    destination = sqlite3.connect(str(output / 'capture.db'), uri=True)
    destination.execute('PRAGMA journal_mode=OFF')
    destination.execute('PRAGMA synchronous=OFF')
    destination.execute('PRAGMA temp_store=MEMORY')
    known_tables, known_indexes = {}, {}
    for source in sources:
        original = readonly(source['database']['path'])
        destination.execute('ATTACH DATABASE ? AS native_source', (Path(source['database']['path']).as_uri()+'?mode=ro&immutable=1',))
        for name, sql in original.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name"):
            if name in known_tables:
                assert name in SHARED_TABLES and known_tables[name] == sql
                offset = destination.execute('SELECT COALESCE(MAX(rowid),0) FROM '+q(name)).fetchone()[0]
            else:
                destination.execute(sql)
                known_tables[name] = sql
                offset = 0
            columns = [r[1] for r in original.execute('PRAGMA table_info('+q(name)+')')]
            assert columns and 'rowid' not in [c.lower() for c in columns]
            selected = ','.join(q(c) for c in columns)
            destination.execute('INSERT INTO '+q(name)+' (rowid,'+selected+') SELECT rowid+?,'+selected+' FROM native_source.'+q(name)+' ORDER BY rowid', (offset,))
            native_count, native_digest = row_digest(original.execute('SELECT rowid,* FROM '+q(name)+' ORDER BY rowid'))
            bounds = original.execute('SELECT MIN(rowid),MAX(rowid) FROM '+q(name)).fetchone()
            derived_count, derived_digest = row_digest(destination.execute('SELECT rowid,* FROM '+q(name)+' WHERE rowid>=? AND rowid<=? ORDER BY rowid', ((bounds[0] or 0)+offset, (bounds[1] or -1)+offset)), offset)
            assert (native_count, native_digest) == (derived_count, derived_digest)
            assert name in SHARED_TABLES or offset == 0
            source['tables'].append({'name': name, 'source_schema_sql': sql, 'row_count': native_count,
                                     'source_rowid_min': bounds[0], 'source_rowid_max': bounds[1],
                                     'derived_rowid_offset': offset, 'ordered_native_row_and_cell_sha256': native_digest,
                                     'native_per_PID_rowids_unchanged': name not in SHARED_TABLES})
        for name, sql in original.execute("SELECT name,sql FROM sqlite_master WHERE type='index' ORDER BY name"):
            if sql is None:
                continue
            if name in known_indexes:
                assert known_indexes[name] == sql
            else:
                destination.execute(sql)
                known_indexes[name] = sql
        destination.commit()
        destination.execute('DETACH DATABASE native_source')
        original.close()
        assert record(source['database']['path']) == source['database']
    assert destination.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    destination.close()
    common_header = None
    line_offset = 0
    with (output / 'capture.csv').open('xb') as target:
        for source in sources:
            with Path(source['csv']['path']).open('rb') as origin:
                header = origin.readline()
                assert header.endswith(b'\n') and header
                if common_header is None:
                    common_header = header
                    target.write(header)
                else:
                    assert common_header == header
                start = target.tell()
                body_digest = hashlib.sha256()
                rows = 0
                last = b''
                for block in iter(lambda: origin.read(8 << 20), b''):
                    target.write(block)
                    body_digest.update(block)
                    rows += block.count(b'\n')
                    last = block[-1:]
                assert last in (b'', b'\n'), 'complete native CSV lines required'
                source['CSV_identity_mapping'] = {'source_first_data_line': 2, 'derived_first_data_line': 2+line_offset,
                    'data_lines': rows, 'derived_body_byte_offset': start, 'body_bytes': target.tell()-start,
                    'body_sha256': body_digest.hexdigest(), 'all_original_body_bytes_preserved': True}
                line_offset += rows
    proof = {'status': 'complete_lossless_derived_union', 'source_sessions': sources,
             'derived_database': record(output / 'capture.db'), 'derived_csv': record(output / 'capture.csv'),
             'original_native_files_retained_unmodified': True, 'derived_union_is_not_a_new_native_collection': True,
             'timestamps_counters_PID_device_and_correlation_values_unchanged': True,
             'per_PID_native_table_rowids_unchanged': True, 'shared_metadata_rowid_offsets_explicit': True,
             'producer': record(Path(__file__))}
    save(output / 'NATIVE_SESSION_UNION.json', proof)
    return proof


def audit(output):
    output = Path(output)
    proof = json.loads((output / 'NATIVE_SESSION_UNION.json').read_text())
    assert proof['status'] == 'complete_lossless_derived_union'
    assert record(output / 'capture.db') == proof['derived_database']
    assert record(output / 'capture.csv') == proof['derived_csv']
    combined = readonly(output / 'capture.db')
    total_rows = 0
    expected_tables = set()
    for source in proof['source_sessions']:
        assert record(source['database']['path']) == source['database']
        assert record(source['csv']['path']) == source['csv']
        native = readonly(source['database']['path'])
        for table in source['tables']:
            name, offset = table['name'], table['derived_rowid_offset']
            expected_tables.add(name)
            assert name in SHARED_TABLES or offset == 0
            assert native.execute("SELECT sql FROM sqlite_master WHERE name=? AND type='table'", (name,)).fetchone()[0] == table['source_schema_sql']
            cursor_a = native.execute('SELECT rowid,* FROM '+q(name)+' ORDER BY rowid')
            cursor_b = combined.execute('SELECT rowid,* FROM '+q(name)+' WHERE rowid>=? AND rowid<=? ORDER BY rowid', ((table['source_rowid_min'] or 0)+offset, (table['source_rowid_max'] or -1)+offset))
            count = 0
            for a in cursor_a:
                b = cursor_b.fetchone()
                assert b is not None and a[0]+offset == b[0] and a[1:] == b[1:], 'native row identity/value drift'
                count += 1
            assert cursor_b.fetchone() is None and count == table['row_count']
            total_rows += count
        native.close()
        mapping = source['CSV_identity_mapping']
        with Path(source['csv']['path']).open('rb') as a, (output / 'capture.csv').open('rb') as b:
            a.readline()
            b.seek(mapping['derived_body_byte_offset'])
            remaining = mapping['body_bytes']
            while remaining:
                size = min(8 << 20, remaining)
                assert a.read(size) == b.read(size), 'native CSV body bytes changed'
                remaining -= size
            assert a.read(1) == b''
    actual = {x[0] for x in combined.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert actual == expected_tables
    assert sum(combined.execute('SELECT COUNT(*) FROM '+q(name)).fetchone()[0] for name in actual) == total_rows
    combined.close()
    result = {'status': 'complete', 'independent_cell_comparison': True, 'native_rows_compared': total_rows,
              'native_CSV_body_bytes_compared': True, 'union_manifest': record(output / 'NATIVE_SESSION_UNION.json'),
              'auditor': record(Path(__file__)), 'no_native_data_values_recalculated': True}
    save(output / 'NATIVE_SESSION_UNION_AUDIT.json', result)
    return result
