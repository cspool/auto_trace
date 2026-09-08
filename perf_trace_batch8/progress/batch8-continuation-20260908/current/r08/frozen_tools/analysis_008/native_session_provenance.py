"""Audit original native sessions independently of the union producer."""
from pathlib import Path
import hashlib
import itertools
import json
import re
import sqlite3


def record(path):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return {'path': str(path), 'size': path.stat().st_size, 'sha256': digest.hexdigest()}


def q(name):
    if not re.fullmatch('[A-Za-z0-9_]+', name):
        raise RuntimeError('native table name')
    return '"'+name+'"'


def connect(path):
    return sqlite3.connect(Path(path).as_uri()+'?mode=ro&immutable=1', uri=True)


def load(capture, verify_all=False):
    capture = Path(capture)
    execution = json.loads((capture/'execution_manifest.json').read_text())
    if execution.get('native_session_layout') != 'independent_workers_lossless_derived_union':
        return None
    assert record(capture/'NATIVE_SESSION_UNION.json') == execution['native_session_union']
    assert record(capture/'NATIVE_SESSION_UNION_AUDIT.json') == execution['native_session_union_audit']
    union = json.loads((capture/'NATIVE_SESSION_UNION.json').read_text())
    assert union['status'] == 'complete_lossless_derived_union'
    assert len(union['source_sessions']) == 2
    assert {x['rank'] for x in union['source_sessions']} == {0, 1}
    for source in union['source_sessions']:
        bound = next(x for x in execution['original_native_sessions'] if x['rank'] == source['rank'])
        assert source['database'] == bound['database'] and source['csv'] == bound['csv']
    assert record(capture/'capture.db') == union['derived_database']
    assert record(capture/'capture.csv') == union['derived_csv']
    if verify_all:
        verify(union)
    union['_manifest_record'] = execution['native_session_union']
    return union


def source_fields(union, pid, line):
    if union is None:
        return {}
    candidates = []
    for source in union['source_sessions']:
        mapping = source['CSV_identity_mapping']
        start = mapping['derived_first_data_line']
        if start <= line < start+mapping['data_lines']:
            candidates.append(source)
    assert len(candidates) == 1, 'native CSV original source line mapping'
    source = candidates[0]
    assert pid in {int(x[0]) for x in source['config_pid_keys']}, 'native CSV/DB source PID mismatch'
    return {'native_database_source_kind': 'lossless_derived_union_of_retained_native_sessions',
            'native_session_union_sha256': union['_manifest_record']['sha256'],
            'original_native_database_path': source['database']['path'],
            'original_native_database_sha256': source['database']['sha256'],
            'original_native_csv_path': source['csv']['path'],
            'original_native_csv_sha256': source['csv']['sha256'],
            'original_native_csv_line': line-source['CSV_identity_mapping']['derived_first_data_line']+2}


def verify(union):
    combined = connect(union['derived_database']['path'])
    assert combined.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    total_rows = 0
    expected_tables = set()
    seen_pids, seen_keys = set(), set()
    shared = {'CONFIG', 'STR_TABLE', 'TRACE_COUNTER', 'SUMMARY'}
    for source in union['source_sessions']:
        assert record(source['database']['path']) == source['database']
        assert record(source['csv']['path']) == source['csv']
        original = connect(source['database']['path'])
        configs = original.execute('SELECT PID,KEY FROM CONFIG').fetchall()
        assert {tuple(x) for x in source['config_pid_keys']} == set(configs)
        assert not seen_pids.intersection(x[0] for x in configs)
        assert not seen_keys.intersection(x[1] for x in configs)
        seen_pids.update(x[0] for x in configs)
        seen_keys.update(x[1] for x in configs)
        tables = {x[0]: x[1] for x in original.execute("SELECT name,sql FROM sqlite_master WHERE type='table'")}
        assert set(tables) == {x['name'] for x in source['tables']}
        for table in source['tables']:
            name = table['name']
            offset = table['derived_rowid_offset']
            assert name in shared or offset == 0
            assert name not in expected_tables or name in shared
            expected_tables.add(name)
            assert tables[name] == table['source_schema_sql']
            assert combined.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()[0] == tables[name]
            bounds = original.execute('SELECT MIN(rowid),MAX(rowid) FROM '+q(name)).fetchone()
            assert bounds == (table['source_rowid_min'], table['source_rowid_max'])
            a = original.execute('SELECT rowid,* FROM '+q(name)+' ORDER BY rowid')
            b = combined.execute('SELECT rowid,* FROM '+q(name)+' WHERE rowid>=? AND rowid<=? ORDER BY rowid', ((bounds[0] or 0)+offset, (bounds[1] or -1)+offset))
            count = 0
            for first, second in itertools.zip_longest(a, b):
                assert first is not None and second is not None
                assert first[0]+offset == second[0] and first[1:] == second[1:], 'original native row/cell changed'
                count += 1
            assert count == table['row_count']
            total_rows += count
        original.close()
        mapping = source['CSV_identity_mapping']
        with Path(source['csv']['path']).open('rb') as a, Path(union['derived_csv']['path']).open('rb') as b:
            header = a.readline()
            assert header == b.readline()
            b.seek(mapping['derived_body_byte_offset'])
            remaining = mapping['body_bytes']
            while remaining:
                n = min(8 << 20, remaining)
                x, y = a.read(n), b.read(n)
                assert len(x) == n and x == y, 'original native CSV bytes changed'
                remaining -= n
            assert a.read(1) == b''
    actual = {x[0] for x in combined.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert expected_tables == actual
    assert sum(combined.execute('SELECT COUNT(*) FROM '+q(name)).fetchone()[0] for name in actual) == total_rows
    combined.close()
    return {'original_native_rows_compared': total_rows, 'original_native_CSV_bytes_compared': True}
