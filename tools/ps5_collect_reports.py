# SPDX-License-Identifier: GPL-3.0-or-later
"""Collect bounded SC2 reports; optional verified-log cleanup requires games closed."""
import argparse
import hashlib
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode

from ps5_upload_usb import Wfm

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'private'
REPORT = re.compile(r'run-[0-9a-f]{16}-[0-9a-f]{2}\.log\Z')
APP = re.compile(r'/mnt/usb[0-9]+/homebrew/Soulcalibur II\Z')
BUILD = re.compile(r'SC2 build-id:\s*([0-9a-f]{64})\Z')
LINE = re.compile(r'([0-9]+) (.*)\Z')
PER_FILE = 2 * 1024 * 1024
TOTAL = 16 * 1024 * 1024
SHUTDOWN = {'CRT: shutdown complete', 'SC2 shutdown complete'}


def parse_report(raw, limit=PER_FILE):
    """Parse observed markers, never infer a crash from an incomplete report."""
    if len(raw) > limit:
        raise ValueError('report exceeds parser byte bound')
    runs, current = [], []
    for line in raw.decode('utf-8', errors='replace').splitlines():
        match = LINE.fullmatch(line)
        if not match:
            continue
        sequence, text = int(match[1]), match[2]
        if sequence == 1 and text == 'application entry before CRT' and current:
            runs.append(current)
            current = []
        current.append((sequence, text))
    if current:
        runs.append(current)
    result = []
    for stages in runs:
        build_ids = sorted({m[1] for _, text in stages if (m := BUILD.fullmatch(text))})
        returns = []
        for index, (_, text) in enumerate(stages[:-1]):
            if text == 'CRT: main returned; status follows' and re.fullmatch(r'-?[0-9]+', stages[index + 1][1]):
                returns.append(int(stages[index + 1][1]))
        closed = any(text in SHUTDOWN for _, text in stages)
        fatal = [text for _, text in stages if text.startswith('SC2 fatal POSIX observation v1; signal=')]
        opaque_count = sum(text.startswith('SC2 opaque-context unverified offset=') for _, text in stages)
        gpu_errors = [text for _, text in stages if text.startswith('GPU stage=') and
                      re.search(r'(?:^| )first_negative=1(?: |$)', text)]
        capture_statuses = [text for _, text in stages if text.startswith(('fatal-capture signal=', 'fatal-capture:'))]
        anchors = [text for _, text in stages if re.fullmatch(
            r'(?:anchor (?:app entry|libkernel open|libc malloc)|throw wrapper)=0x[0-9a-f]{16}\s*', text)]
        result.append(dict(build_ids=build_ids, build_identity_observed=bool(build_ids),
                           stage_count=len(stages), last_sequence=stages[-1][0],
                           last_stage=stages[-1][1], main_return_statuses=returns,
                           closure='shutdown marker observed' if closed else 'no shutdown marker',
                           crash_proven=False,
                           fatal_observations=fatal,
                           fatal_observation_meaning=('received POSIX signal; root cause and OS dialog not identified' if fatal else None),
                           opaque_context_records=opaque_count,
                           opaque_context_interpretation='unverified opaque bytes; not decoded registers or a backtrace',
                           gpu_first_errors=gpu_errors,
                           capture_registration_statuses=capture_statuses,
                           safe_address_anchors=anchors,
                           entry_marker_observed=stages[0] == (1, 'application entry before CRT')))
    return dict(runs=result, run_count=len(result), utf8_replacement_used='\ufffd' in raw.decode('utf-8', errors='replace'))


def choose_reports(entries, max_files, per_file, total):
    """Prefer validated listing mtime, with deterministic missing-time fallback.

    Remote mtime is a selection hint, never proof of launch chronology/build.
    """
    accepted, skipped, budget = [], [], 0
    occurrences = {}
    for row in entries:
        name = row.get('name')
        if isinstance(name, str):
            occurrences[name] = occurrences.get(name, 0) + 1
    def recency_key(row):
        stamp = row.get('mtime')
        valid = isinstance(stamp, int) and not isinstance(stamp, bool) and 0 <= stamp <= (1 << 63) - 1
        return (0 if valid else 1, -stamp if valid else 0, str(row.get('name', '')))
    for row in sorted(entries, key=recency_key):
        name = row.get('name')
        if not isinstance(name, str) or not REPORT.fullmatch(name):
            continue
        reason = None
        size = row.get('size')
        if occurrences[name] != 1:
            reason = 'duplicate filename'
        elif row.get('type') != '-':
            reason = 'not an ordinary file'
        elif isinstance(size, bool) or not isinstance(size, int) or size < 0:
            reason = 'invalid listed byte size'
        elif size > per_file:
            reason = 'per-file byte bound'
        elif len(accepted) >= max_files:
            reason = 'file-count bound'
        elif size > total - budget:
            reason = 'total byte bound'
        if reason:
            skipped.append(dict(name=name, reason=reason))
        else:
            accepted.append(row)
            budget += size
    return accepted, skipped


def validated_output_path(path):
    path = path.absolute()
    for component in (path, *path.parents):
        if component.is_symlink() or getattr(component, 'is_junction', lambda: False)():
            raise ValueError('output links/junctions are rejected')
    # Resolve BEFORE mkdir: lexical is_relative_to accepts private/../../outside.
    # Reject traversal explicitly as well, including one that normalizes inward.
    if '..' in path.parts:
        raise ValueError('output traversal is rejected')
    resolved = path.resolve(strict=False)
    private = PRIVATE.resolve(strict=False)
    if not resolved.is_relative_to(private) or resolved == private:
        raise ValueError('output must be a fresh child under C:/SC2/private')
    return resolved


def fresh_output(path):
    path = validated_output_path(path)
    path.mkdir(parents=True, exist_ok=False)
    return path


def fetch_report(wfm, remote, limit):
    """Only diagnostic-file download prepare/GET/task acknowledgement; no mutation."""
    task = wfm.api('/api/download/prepare', {'paths': remote}, form=True)
    task_id = task['task_id']
    connection = wfm.connection()
    raw, failure, acknowledgement_error = bytearray(), None, None
    try:
        connection.request('GET', '/api/download?id=' + quote(str(task_id), safe=''),
                           headers={'Accept-Encoding': 'identity'})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError('report download HTTP' + str(response.status))
        if response.getheader('Content-Encoding', 'identity') not in ('', 'identity'):
            raise ValueError('unexpected compressed diagnostic transport')
        while True:
            block = response.read(min(65536, limit - len(raw) + 1))
            if not block:
                break
            raw.extend(block)
            if len(raw) > limit:
                raise ValueError('report download exceeds remaining byte bound')
    except Exception as error:
        failure = str(error)
    finally:
        connection.close()
        try:
            wfm.api('/api/tasks', {'download_ack': task_id})
        except Exception as error:
            acknowledgement_error = str(error)
    # At most one over-limit probe byte is read to diagnose growth. Keep the
    # saved diagnostic fragment within the configured byte budget.
    return bytes(raw[:limit]), failure, acknowledgement_error


def report_remote_path(app, name):
    if not APP.fullmatch(app) or (name != 'startup.log' and not REPORT.fullmatch(name)):
        raise ValueError('cleanup permits only exact SC2 diagnostic report files')
    return app + ('/' if name == 'startup.log' else '/reports/') + name


def verify_local_archive(output, row):
    name = row['name']
    if name != 'startup.log' and not REPORT.fullmatch(name):
        raise ValueError('invalid archived report name')
    local = output / name
    if local.is_symlink() or getattr(local, 'is_junction', lambda: False)() or not local.is_file():
        raise ValueError('local report is not an ordinary archived file')
    if local.stat().st_size != row['bytes']:
        raise ValueError('local archived report size changed')
    value, consumed = hashlib.sha256(), 0
    with local.open('rb') as stream:
        while True:
            block = stream.read(min(65536, row['bytes'] - consumed + 1))
            if not block:
                break
            consumed += len(block)
            if consumed > row['bytes']:
                raise ValueError('local archived report grew during verification')
            value.update(block)
    if consumed != row['bytes'] or value.hexdigest() != row['local_sha256']:
        raise ValueError('local archived report bytes/hash changed')


def delete_remote_report(wfm, app, name):
    # Deliberately separate from Wfm's transport-archive deletion admission.
    # This narrow user-authorized action never adds logs to owned_archives.
    remote = report_remote_path(app, name)
    connection = wfm.connection()
    try:
        connection.request('POST', '/api/delete',
                           body=urlencode({'paths': remote}).encode(),
                           headers={'Content-Type': 'application/x-www-form-urlencoded'})
        response = connection.getresponse()
        data = response.read(65537)
        if len(data) > 65536:
            raise ValueError('log deletion response exceeds bound')
        value = json.loads(data)
        if response.status != 200 or not value.get('ok'):
            raise ValueError('log deletion request failed')
        task_id = value['task_id']
    finally:
        connection.close()
    return wfm.wait(task_id, 60)


def clean_pulled_reports(wfm, app, output, summary, save, games_closed):
    if not games_closed:
        raise ValueError('cleanup requires a fresh games-closed confirmation')
    if not APP.fullmatch(app):
        raise ValueError('cleanup app path is outside exact SC2 USB app')
    cleanup = summary['cleanup'] = dict(requested=True, state='running', deleted=[], skipped=[], errors=[])
    save()
    for row in summary['reports']:
        name = row.get('name')
        try:
            remote = report_remote_path(app, name)
            if row.get('remote_path') != remote:
                raise ValueError('remote report path mismatch')
            if row.get('download_complete') is not True or any(row.get(key) for key in
                    ('download_error', 'collection_error', 'task_ack_error')):
                raise ValueError('report collection was not completely successful')
            before, after = row.get('listed_before'), row.get('listed_after')
            if not isinstance(before, dict) or before != after or row.get('changed_during_collection') is not False:
                raise ValueError('report changed or has no stable collection metadata')
            if before.get('type') != '-' or before.get('name') != name or before.get('size') != row.get('bytes'):
                raise ValueError('report type/name/byte size is not verified')
            verify_local_archive(output, row)
            parent = remote.rsplit('/', 1)[0]
            current = [entry for entry in wfm.listing(parent) if entry.get('name') == name]
            if len(current) != 1 or current[0] != after:
                raise ValueError('report is missing/active/changed since collection')
            row['cleanup_archive_verified'] = True
            row['cleanup_status'] = 'archive verified; pending exact file deletion'
            # Persist the verified local archive receipt before any remote delete.
            save()
        except Exception as error:
            row['cleanup_status'] = 'preserved'
            cleanup['skipped'].append(dict(name=name, reason=str(error)))
            save()
            continue
        try:
            summary['console_mutations'] = True
            row['cleanup_status'] = 'exact file deletion attempted'
            row['delete_task'] = delete_remote_report(wfm, app, name)
            remaining = [entry for entry in wfm.listing(parent) if entry.get('name') == name]
            if remaining:
                raise ValueError('report still listed after deletion task')
            row['cleanup_status'] = 'remote report deleted; local archive retained'
            cleanup['deleted'].append(name)
        except Exception as error:
            row['cleanup_status'] = 'delete failed or result uncertain; local archive retained'
            cleanup['errors'].append(dict(name=name, error=str(error)))
        save()
    cleanup['state'] = ('complete with errors' if cleanup['errors'] else
                        'complete with preserved files' if cleanup['skipped'] else 'complete')
    save()


def collect(args):
    wfm = Wfm(args.server, timeout=args.timeout)
    output = fresh_output(args.output)
    summary = dict(schema='sc2.collected-reports.v1', app=args.app,
                   collected_at=datetime.now(timezone.utc).isoformat(),
                   console_mutations=False, console_launched=False,
                   remote_hash_readback=False, logs_may_still_grow=True,
                   ordering='validated nonnegative integer mtime descending, filename ascending ties; missing/invalid mtime after valid; not asserted launch chronology',
                   reports=[], skipped=[], errors=[])
    summary_path = output / 'SUMMARY.json'
    def save():
        summary_path.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    save()
    try:
        app_entries = wfm.listing(args.app)
        directories = [e for e in app_entries if e.get('name') == 'reports']
        candidates = []
        if directories:
            if len(directories) != 1 or directories[0].get('type') != 'd':
                raise ValueError('reports child is not one ordinary directory')
            candidates, summary['skipped'] = choose_reports(
                wfm.listing(args.app + '/reports'), args.max_files, args.max_file_bytes, args.max_total_bytes)
        if not candidates:
            fallback = [e for e in app_entries if e.get('name') == 'startup.log']
            if len(fallback) == 1 and fallback[0].get('type') == '-':
                row = fallback[0]
                size = row.get('size')
                if isinstance(size, int) and not isinstance(size, bool) and 0 <= size <= min(args.max_file_bytes, args.max_total_bytes):
                    candidates = [row]
                else:
                    summary['errors'].append('startup.log fallback exceeds byte bound or has invalid size')
        if not candidates:
            summary['errors'].append('No eligible per-run reports or startup.log fallback found')
        consumed = 0
        for before in candidates:
            name = before['name']
            parent = args.app if name == 'startup.log' else args.app + '/reports'
            row = dict(name=name, remote_path=parent + '/' + name, listed_before=before,
                       integrity='local collected-byte hash only; not remote file integrity proof')
            limit = min(args.max_file_bytes, args.max_total_bytes - consumed)
            if limit <= 0:
                summary['skipped'].append(dict(name=name, reason='download total byte bound'))
                continue
            try:
                raw, failure, ack_error = fetch_report(wfm, row['remote_path'], limit)
                consumed += len(raw)
                (output / name).write_bytes(raw)
                row.update(bytes=len(raw), local_sha256=hashlib.sha256(raw).hexdigest(), download_error=failure, download_complete=not failure)
                if ack_error:
                    row['task_ack_error'] = ack_error
                after = [e for e in wfm.listing(parent) if e.get('name') == name]
                row['listed_after'] = after[0] if len(after) == 1 else None
                row['changed_during_collection'] = row['listed_after'] != before or len(raw) != before['size']
                row['unchanged_listing_does_not_prove_snapshot'] = True
                if not failure:
                    row['parsed'] = parse_report(raw, args.max_file_bytes)
            except Exception as error:
                row['collection_error'] = str(error)
            summary['reports'].append(row)
            save()
    except Exception as error:
        summary['errors'].append(str(error))
    finally:
        notes = ['Optional human test notes. Leave unknown fields blank.',
                 'A missing shutdown marker alone does not establish a crash.', '']
        for row in summary['reports']:
            notes += [row['name'], 'Mode:', 'Action:', 'Outcome:', 'On-screen error:', '']
        (output / 'TEST-NOTES.txt').write_text('\n'.join(notes), encoding='utf-8')
        save()
    summary['collection_ok'] = not summary['errors'] and not any(
        r.get('download_error') or r.get('collection_error') or r.get('task_ack_error') for r in summary['reports'])
    save()
    if args.clean_pulled:
        clean_pulled_reports(wfm, args.app, output, summary, save, args.games_closed)
    else:
        summary['cleanup'] = dict(requested=False, state='not requested')
        save()
    print(summary_path)
    return 0 if summary['collection_ok'] and not summary['cleanup'].get('errors') else 1


def self_test():
    build = 'a' * 64
    one = f'1 application entry before CRT\n2 SC2 build-id: {build}\n3 runner:save-ready\n'
    two = '1 application entry before CRT\n2 CRT: main returned; status follows\n3 2\n'
    value = parse_report((one + two).encode())
    assert value['run_count'] == 2
    assert value['runs'][0]['build_ids'] == [build]
    assert value['runs'][1]['main_return_statuses'] == [2]
    assert value['runs'][1]['closure'] == 'no shutdown marker'
    assert not value['runs'][1]['build_identity_observed']
    assert not value['runs'][1]['crash_proven']
    assert parse_report(b'1 application entry before CRT\n2 CRT: shutdown complete\n')['runs'][0]['closure'] == 'shutdown marker observed'
    fatal_header = 'SC2 fatal POSIX observation v1; signal=11 si_code=1 si_addr=0x0000000000000010 context=0x0000000000010000'
    gpu_error = 'GPU stage=create-device result=-1 a=0 b=0 first_negative=1'
    capture_status = 'fatal-capture signal=11 status=installed errno=0'
    anchor = 'anchor app entry=0x0000000000400000'
    fault_stages = ['application entry before CRT', capture_status, anchor, fatal_header]
    fault_stages += [f'SC2 opaque-context unverified offset=0x{i * 16:016x} bytes=' + '00' * 16 for i in range(16)]
    fault_stages += [gpu_error, 'GPU stage=later result=-2 a=0 b=0',
                     'SC2 fatal observation end; OS error text/code not captured']
    fault_run = ''.join(f'{index} {text}\n' for index, text in enumerate(fault_stages, 1))
    observed = parse_report((one + fault_run).encode())['runs']
    assert len(observed) == 2 and observed[0]['fatal_observations'] == []
    assert observed[0]['opaque_context_records'] == 0 and observed[0]['gpu_first_errors'] == []
    assert observed[1]['fatal_observations'] == [fatal_header]
    assert observed[1]['opaque_context_records'] == 16
    assert observed[1]['gpu_first_errors'] == [gpu_error]
    assert observed[1]['capture_registration_statuses'] == [capture_status]
    assert observed[1]['safe_address_anchors'] == [anchor]
    assert observed[1]['closure'] == 'no shutdown marker' and not observed[1]['crash_proven']

    try:
        parse_report(b'12345', limit=4)
        raise AssertionError('oversized report accepted')
    except ValueError:
        pass
    name = 'run-' + '0' * 16 + '-00.log'
    rows = [dict(name=name, type='-', size=10), dict(name=name.replace('-00', '-01'), type='-', size=11)]
    accepted, skipped = choose_reports(rows, 2, 10, 10)
    assert len(accepted) == 1 and skipped[0]['reason'] == 'per-file byte bound'
    assert choose_reports(rows, 0, 20, 30)[0] == []
    assert choose_reports(rows, 2, 20, 9)[0] == []
    assert choose_reports([rows[0], rows[0]], 2, 20, 30)[0] == []
    assert choose_reports([dict(name=name, type='d', size=0)], 2, 20, 30)[0] == []
    newest = dict(name=name.replace('-00', '-03'), type='-', size=1, mtime=300)
    oldest = dict(name=name.replace('-00', '-04'), type='-', size=1, mtime=100)
    missing = dict(name=name.replace('-00', '-05'), type='-', size=1)
    invalid = dict(name=name.replace('-00', '-06'), type='-', size=1, mtime=True)
    chosen, omitted = choose_reports([oldest, missing, invalid, newest], 1, 10, 10)
    assert chosen == [newest] and len(omitted) == 3
    chosen, _ = choose_reports([missing, oldest, newest, invalid], 4, 10, 10)
    assert chosen == [newest, oldest, missing, invalid]
    # Regression must fail before mkdir, including lexical private-prefix escapes.
    from unittest.mock import patch
    with patch.object(Path, 'mkdir', side_effect=AssertionError('mkdir reached')):
        for invalid_output in (PRIVATE / '..' / '..' / 'collector-escape-regression', PRIVATE,
                               ROOT / 'collector-outside-private'):
            try:
                fresh_output(invalid_output)
                raise AssertionError('invalid output accepted')
            except ValueError:
                pass
    assert not APP.fullmatch('/mnt/usb0/homebrew/Other App')
    assert not REPORT.fullmatch('../startup.log')
    print('Parser and collection-budget tests passed; no network or game execution.')


def cleanup_self_test():
    from copy import deepcopy
    from io import BytesIO
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    app = '/mnt/usb0/homebrew/Soulcalibur II'
    name = 'run-' + '1' * 16 + '-00.log'
    raw = b'log'
    entry = dict(name=name, type='-', size=len(raw), mtime=1)
    base = dict(name=name, remote_path=report_remote_path(app, name),
                bytes=len(raw), local_sha256=hashlib.sha256(raw).hexdigest(),
                listed_before=entry, listed_after=entry, changed_during_collection=False,
                download_complete=True, download_error=None)

    def exercise(change=None, tampered=False, current_changed=False, delete_failure=False):
        row = deepcopy(base)
        if change:
            row.update(change)
        summary = dict(reports=[row], console_mutations=False)
        receipts, deleted, calls = [], [], []
        local = MagicMock()
        local.is_symlink.return_value = local.is_junction.return_value = False
        local.is_file.return_value = True
        local.stat.return_value = SimpleNamespace(st_size=len(raw))
        local.open.return_value = BytesIO(b'bad' if tampered else raw)
        output = MagicMock()
        output.__truediv__.return_value = local
        def listing(parent):
            assert parent == app + '/reports'
            return [] if deleted else [dict(entry, mtime=2) if current_changed else entry]
        def request(method, endpoint, body, headers):
            assert method == 'POST' and endpoint == '/api/delete'
            assert body == urlencode({'paths': report_remote_path(app, name)}).encode()
            assert receipts[-1]['reports'][0]['cleanup_archive_verified'] is True
            calls.append(endpoint)
        def wait(task_id, timeout):
            assert task_id == 'test-task' and timeout == 60
            if delete_failure:
                raise ValueError('synthetic task failure')
            deleted.append(name)
            return dict(state='done')
        response = SimpleNamespace(status=200, read=lambda bound: b'{"ok":true,"task_id":"test-task"}')
        connection = SimpleNamespace(request=request, getresponse=lambda: response, close=lambda: None)
        wfm = SimpleNamespace(listing=listing, connection=lambda: connection, wait=wait)
        clean_pulled_reports(wfm, app, output, summary,
                             lambda: receipts.append(deepcopy(summary)), True)
        return summary, calls

    result, calls = exercise()
    assert calls == ['/api/delete'] and result['cleanup']['deleted'] == [name]
    assert result['console_mutations'] is True
    for change, tampered, current_changed in (
            ({'changed_during_collection': True}, False, False),
            ({'download_error': 'incomplete'}, False, False),
            ({'task_ack_error': 'failed'}, False, False),
            ({'download_complete': False}, False, False),
            (None, True, False), (None, False, True)):
        result, calls = exercise(change, tampered, current_changed)
        assert not calls and not result['console_mutations']
        assert result['cleanup']['skipped'] and not result['cleanup']['deleted']
    result, calls = exercise(delete_failure=True)
    assert calls and result['cleanup']['errors'] and not result['cleanup']['deleted']
    assert 'local archive retained' in result['reports'][0]['cleanup_status']
    try:
        clean_pulled_reports(None, app, None, {}, lambda: None, False)
        raise AssertionError('cleanup accepted games running/unconfirmed')
    except ValueError:
        pass
    print('Cleanup mocked-WFM tests passed; no network or filesystem writes.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', default='/mnt/usb0/homebrew/Soulcalibur II')
    parser.add_argument('--server', default='http://192.168.1.23:8888')
    parser.add_argument('--output', type=Path, default=PRIVATE / ('ps5-reports-' + uuid.uuid4().hex))
    parser.add_argument('--execute', action='store_true', help='collect remote diagnostic logs; no cleanup unless --clean-pulled is also given')
    parser.add_argument('--clean-pulled', action='store_true', help='delete only fully archived unchanged diagnostic files after collection')
    parser.add_argument('--games-closed', action='store_true', help='caller affirms fresh human confirmation that all games are closed')
    parser.add_argument('--self-test', action='store_true', help='synthetic parser/budget checks only')
    parser.add_argument('--max-files', type=int, default=32)
    parser.add_argument('--max-file-bytes', type=int, default=PER_FILE)
    parser.add_argument('--max-total-bytes', type=int, default=TOTAL)
    parser.add_argument('--timeout', type=int, default=15)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        cleanup_self_test()
        return 0
    if args.clean_pulled and (not args.execute or not args.games_closed):
        parser.error('--clean-pulled requires --execute and --games-closed')
    if not APP.fullmatch(args.app):
        parser.error('--app must be exact /mnt/usbN/homebrew/Soulcalibur II')
    if not 1 <= args.max_files <= 128 or not 1 <= args.max_file_bytes <= 8 * 1024 * 1024 or not 1 <= args.max_total_bytes <= 64 * 1024 * 1024 or not 1 <= args.timeout <= 60:
        parser.error('collection bounds outside supported limits')
    # Validate owner server even in local plan mode, without opening a connection.
    Wfm(args.server, timeout=args.timeout)
    if not args.execute:
        print(json.dumps(dict(mode='local plan; no network or filesystem writes', app=args.app,
                              report_pattern=REPORT.pattern, fallback='startup.log only if no report candidates',
                              output=str(args.output), max_files=args.max_files,
                              max_file_bytes=args.max_file_bytes, max_total_bytes=args.max_total_bytes), indent=2))
        return 0
    return collect(args)


if __name__ == '__main__':
    sys.exit(main())
