#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Upload a private authenticated SC2 package to fresh USB folders via PS5 WFM.

Default is a local-only plan. --execute is explicit and never launches a game.
"""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import time
from urllib.parse import quote, urlencode, urlsplit
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'private'
CHUNK = 1024 * 1024
MAX_JSON = 16 * 1024 * 1024
MAX_FILES = 30000
MAX_BYTES = 12 * 1024 * 1024 * 1024
TOPS = {'homebrew', 'soulcalibur2'}
APP_REL = 'homebrew/Soulcalibur II'
CRITICAL = {'homebrew/Soulcalibur II/eboot.bin', 'homebrew/Soulcalibur II/sce_sys/param.json', 'soulcalibur2/game files/Default.xbe',
            'homebrew/Soulcalibur II/sce_module/libc.prx',
            'soulcalibur2/game files/root.olk', 'soulcalibur2/guests.olk',
            'soulcalibur2/game files/Soulcalibur II (USA).iso'}


def sha256(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(CHUNK), b''):
            value.update(block)
    return value.hexdigest()


def plain(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            raise ValueError('links/junctions rejected: ' + str(part))
    return path.resolve()


def relative(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value or any(ord(c) < 32 for c in value):
        raise ValueError('invalid package relative path')
    parts = value.split('/')
    if any(p in ('', '.', '..') for p in parts) or parts[0] not in TOPS:
        raise ValueError('package member must stay in the two SC2 folders')
    if parts[0] == 'homebrew' and (len(parts) < 2 or parts[1] != 'Soulcalibur II'):
        raise ValueError('only the exact SC2 app child is permitted under homebrew')
    if parts[0] == 'homebrew' and len(parts) > 2 and parts[2].casefold() in {
            'storage', 'saves', 'settings.ini', 'startup.log', 'shader-requests', 'shader-cache',
            'driver-cache', 'cache', '.mesa-streams', 'screenshots'}:
        raise ValueError('active saves/config/cache must never be shipped')
    if value.lower().endswith('.iso') and value != 'soulcalibur2/game files/Soulcalibur II (USA).iso':
        raise ValueError('donor ISO is not an upload asset')
    return PurePosixPath(value)


def usb_path(value):
    if not isinstance(value, str) or not re.fullmatch(r'/mnt/usb[0-9]+(?:/[^\\\r\n]+)?', value):
        raise ValueError('remote paths must stay under a numeric /mnt/usbN mount')
    parts = value.split('/')[1:]
    if any(p in ('', '.', '..') for p in parts) or any(ord(c) < 32 for c in value):
        raise ValueError('invalid USB path components')
    return value


def load_package(path, expected_hash, destination):
    path = plain(path)
    if not path.is_relative_to(PRIVATE.resolve()) or path.name != 'PACKAGE-MANIFEST.json':
        raise ValueError('require a private package manifest')
    if not re.fullmatch('[0-9a-f]{64}', expected_hash) or sha256(path) != expected_hash:
        raise ValueError('package manifest identity differs from selected artifact')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('format') != 'SC2-PRIVATE-PACKAGE-4':
        raise ValueError('outdated layout: require package v4 with homebrew/Soulcalibur II; no automatic migration')
    if manifest.get('original_xbe_sha256') not in {
            '7ce12851850ab46766f77c612b251afe7c8bd81f879e11b4836bdf766be542c6',
            'd7c2e1fc993350821e3f7e13cfd1c9d4ba6a7bf91011005bdd1f843899efb730'}:
        raise ValueError('package does not authenticate a supported USA executable')
    if manifest.get('application_relative_dir') != APP_REL:
        raise ValueError('package application relative directory is not the exact SC2 homebrew child')
    if manifest.get('console_eboot_dir') != destination + '/' + APP_REL:
        raise ValueError('package eboot path differs from the USB destination')
    rows = manifest.get('files')
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_FILES:
        raise ValueError('package file count outside upload bound')
    seen, files, total = set(), [], 0
    for row in rows:
        rel = relative(row['path'])
        key = str(rel).casefold()
        if key in seen:
            raise ValueError('case-insensitive package path collision')
        seen.add(key)
        source = plain(path.parent / Path(*rel.parts))
        if not source.is_relative_to(path.parent) or not source.is_file():
            raise ValueError('package member missing or outside package')
        size = row['bytes']
        if isinstance(size, bool) or not isinstance(size, int) or size < 0 or source.stat().st_size != size:
            raise ValueError('package size differs: ' + str(rel))
        if not re.fullmatch('[0-9a-f]{64}', row['sha256']) or sha256(source) != row['sha256']:
            raise ValueError('package hash differs: ' + str(rel))
        total += size
        if total > MAX_BYTES:
            raise ValueError('package exceeds12GiB upload budget; donor discs must not be copied')
        files.append(dict(path=str(rel), source=source, bytes=size, sha256=row['sha256']))
    if 'homebrew/soulcalibur ii/eboot.bin' not in seen:
        raise ValueError('finalized eboot.bin is missing')
    by_name = {row['path']: row for row in files}
    if manifest.get('disc_mode') == 'extracted':
        required = ['soulcalibur2/game files/' + name for name in ('Default.xbe', 'root.olk', 'bgm.afs', 'movie.afs')]
        if any(name not in by_name for name in required):
            raise ValueError('required extracted game files missing from package manifest')
        if by_name[required[0]]['sha256'] != manifest['original_xbe_sha256']:
            raise ValueError('extracted XBE row differs from package executable identity')
        roster = by_name['soulcalibur2/game files/root.olk']
    elif manifest.get('disc_mode') == 'iso':
        if 'soulcalibur2/game files/Soulcalibur II (USA).iso' not in by_name or 'soulcalibur2/guests.olk' not in by_name:
            raise ValueError('required base Xbox ISO/converted roster missing from package')
        roster = by_name['soulcalibur2/guests.olk']
    else:
        raise ValueError('unsupported package disc mode')
    if roster['sha256'] != manifest.get('guest_roster_sha256'):
        raise ValueError('converted character/weapon roster differs from package identity')
    if manifest.get('metadata_supplied') and 'homebrew/Soulcalibur II/sce_sys/param.json' not in by_name:
        raise ValueError('package metadata flag lacks actual app parameter JSON')
    # Include declared empty layout folders, but never arbitrary unmanifested files.
    directories = set()
    for row in files:
        for parent in PurePosixPath(row['path']).parents:
            if str(parent) not in ('.', 'homebrew'): directories.add(str(parent))
    for current, dirs, _ in os.walk(path.parent / 'soulcalibur2', followlinks=False):
        for name in dirs:
            folder = plain(Path(current) / name)
            rel = folder.relative_to(path.parent).as_posix()
            relative(rel)
            if len(directories) >= MAX_FILES:
                raise ValueError('package directory count outside upload bound')
            directories.add(rel)
    for name in ('game files', 'textures', 'textures/ps2', 'textures/gamecube', 'textures/spawn', 'saves', 'maps', 'characters'):
        folder = plain(path.parent / 'soulcalibur2' / name)
        if not folder.is_dir():
            raise ValueError('required empty/layout directory missing: ' + name)
        directories.add('soulcalibur2/' + name)
    return manifest, files, sorted(directories), total


class Wfm:
    def __init__(self, server, timeout=120):
        parsed = urlsplit(server)
        if (parsed.scheme != 'http' or parsed.hostname != '192.168.1.23' or parsed.port != 8888 or
                parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
            raise ValueError('this transfer targets only the owner PS5 http://192.168.1.23:8888')
        self.host, self.port, self.timeout = parsed.hostname, parsed.port, timeout
        self.owned_archives = set()

    def connection(self):
        return http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)

    def api(self, endpoint, values=None, form=False):
        # Exclude game launch/install/exit, arbitrary deletion, chmod and internal paths.
        allowed = {'/api/list', '/api/space', '/api/upload/prepare', '/api/upload/finish',
                   '/api/tasks', '/api/cancel', '/api/extract', '/api/download/prepare', '/api/delete', '/api/mkdir'}
        if endpoint not in allowed:
            raise ValueError('unsupported file-transfer endpoint')
        values = values or {}
        for name in ('path', 'destination', 'paths'):
            if name in values:
                usb_path(str(values[name]))
        if endpoint == '/api/delete' and (set(values) != {'paths'} or values['paths'] not in self.owned_archives):
            raise ValueError("only this run's exact fresh transport archive may be deleted")
        if endpoint == '/api/mkdir':
            name = values.get('name')
            if (set(values) != {'path', 'name'} or not isinstance(name, str) or name in ('', '.', '..') or
                    '/' in name or '\\' in name or ':' in name or any(ord(c) < 32 for c in name)):
                raise ValueError('USB mkdir requires one ordinary directory name')
        encoded = urlencode(values)
        target = endpoint if form or not encoded else endpoint + '?' + encoded
        headers = {'Content-Type': 'application/x-www-form-urlencoded'} if form else {}
        body = encoded.encode() if form else b''
        connection = self.connection()
        try:
            connection.request('POST', target, body, headers)
            response = connection.getresponse()
            data = response.read(MAX_JSON + 1)
            if len(data) > MAX_JSON:
                raise ValueError('file manager JSON exceeds response bound')
            value = json.loads(data)
            if response.status != 200 or not value.get('ok'):
                raise ValueError(f'file manager {endpoint} failed: ' + str(value.get('error') or value.get('error_code') or response.status))
            return value
        finally:
            connection.close()

    def listing(self, path):
        usb_path(path)
        value = self.api('/api/list', {'path': path})
        if value.get('path') != path or not isinstance(value.get('entries'), list):
            raise ValueError('file manager listing path/shape differs')
        if len(value['entries']) > MAX_FILES:
            raise ValueError('remote directory exceeds bounded inventory')
        return value['entries']

    def assert_fresh(self, destination, archive_name=None):
        entries = self.listing(destination)
        names = {row['name'].casefold() for row in entries}
        if 'soulcalibur2' in names or (archive_name and archive_name.casefold() in names):
            raise ValueError('USB assets/archive destination exists; never merge or overwrite')
        parents = [row for row in entries if row['name'].casefold() == 'homebrew']
        if parents:
            if len(parents) != 1 or parents[0]['name'] != 'homebrew' or parents[0].get('type') != 'd':
                raise ValueError('homebrew parent must be the exact ordinary directory')
            if any(row['name'].casefold() == 'soulcalibur ii' for row in self.listing(destination + '/homebrew')):
                raise ValueError('SC2 app child already exists; other homebrew apps are preserved')

    def upload(self, task_id, destination, source, archive_name, expected_hash, expected_size=None):
        usb_path(destination)
        connection = self.connection()
        value = hashlib.sha256()
        size = source.stat().st_size
        if expected_size is not None and size != expected_size:
            raise ValueError('local file size changed before upload')
        try:
            connection.putrequest('POST', '/api/upload-file')
            for key, item in {'Content-Type': 'application/octet-stream', 'Content-Length': str(size),
                              'X-WFM-Task-ID': str(task_id), 'X-WFM-Path': quote(destination, safe=''),
                              'X-WFM-Rel': quote(archive_name, safe=''), 'X-WFM-Size': str(size),
                              'X-WFM-Overwrite': '0'}.items():
                connection.putheader(key, item)
            connection.endheaders()
            sent = 0
            with source.open('rb') as stream:
                for block in iter(lambda: stream.read(CHUNK), b''):
                    connection.send(block)
                    value.update(block)
                    sent += len(block)
            if sent != size or value.hexdigest() != expected_hash:
                raise ValueError('local transport archive changed during upload')
            response = connection.getresponse()
            body = response.read(MAX_JSON + 1)
            if response.status < 200 or response.status >= 300 or len(body) > MAX_JSON:
                raise ValueError('archive upload failed: HTTP' + str(response.status))
        finally:
            connection.close()

    def wait(self, task_id, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            tasks = self.api('/api/tasks').get('tasks', [])
            task = next((row for row in tasks if row.get('id') == task_id), None)
            if task:
                if task.get('state') == 'done': return task
                if task.get('state') in ('failed', 'canceled'):
                    raise ValueError('file task failed: ' + str(task.get('error') or task.get('current')))
            time.sleep(1)
        raise ValueError('bounded file task wait timed out')

    def readback(self, path, expected_size, expected_hash, timeout):
        usb_path(path)
        task = self.api('/api/download/prepare', {'paths': path}, form=True)
        task_id = task['task_id']
        connection = self.connection()
        value, size = hashlib.sha256(), 0
        try:
            connection.request('GET', '/api/download?id=' + quote(str(task_id), safe=''))
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError('remote readback failed: HTTP' + str(response.status))
            while block := response.read(CHUNK):
                size += len(block)
                if size > expected_size:
                    raise ValueError('remote download exceeds exact file size; not raw file content')
                value.update(block)
        finally:
            connection.close()
        if size != expected_size or value.hexdigest() != expected_hash:
            raise ValueError('remote streamed SHA256 mismatch: ' + path)
        self.wait(task_id, timeout)
        self.api('/api/tasks', {'download_ack': task_id})
        return dict(path=path, bytes=size, sha256=value.hexdigest(), verified='streamed-download-sha256')


def ensure_remote_directories(wfm, destination, directories):
    """Create missing declared folders only, using the observed immediate API."""
    listings = {}
    created = []
    for directory in sorted(directories, key=lambda name: (name.count('/'), name)):
        rel = relative(directory)
        parent = str(rel.parent)
        remote_parent = destination if parent == '.' else destination + '/' + parent
        usb_path(remote_parent)
        if remote_parent not in listings:
            listings[remote_parent] = {row['name']: row for row in wfm.listing(remote_parent)}
        existing = listings[remote_parent].get(rel.name)
        if existing:
            if existing.get('type') != 'd':
                raise ValueError('declared directory is not a remote directory: ' + directory)
            continue
        if rel.name.casefold() in {name.casefold() for name in listings[remote_parent]}:
            raise ValueError('case-only remote directory conflict: ' + directory)
        wfm.api('/api/mkdir', {'path': remote_parent, 'name': rel.name})
        listings[remote_parent][rel.name] = dict(name=rel.name, type='d')
        created.append(destination + '/' + directory)
    return created


def execute_files(wfm, args, destination, files, directories, total, report, save):
    """Observed direct-file upload, without the optional archive helper."""
    wfm.assert_fresh(destination)
    spaces = wfm.api('/api/space', {'path': destination}).get('spaces', [])
    available = next((row for row in spaces if row.get('path') == destination), None)
    if not available or available.get('free', 0) < total + 64 * CHUNK:
        raise ValueError('USB free-space preflight cannot cover direct-file upload')
    task = wfm.api('/api/upload/prepare', dict(path=destination, src=files[0]['path'], total=total,
                   count=len(files), rels='\n'.join(row['path'] for row in files),
                   sizes='\n'.join(str(row['bytes']) for row in files), overwrite='0'), form=True)
    task_id = task['task_id']
    report.update(state='uploading-individual-files', upload_task_id=task_id,
                  transport='individual-files-no-archive-helper', uploaded_files=0, uploaded_bytes=0,
                  prior_transport_archives_untouched=True)
    save()
    sent = 0
    last_progress_bytes = 0
    try:
        for index, row in enumerate(files, 1):
            wfm.upload(task_id, destination, row['source'], row['path'], row['sha256'], row['bytes'])
            sent += row['bytes']
            report.update(uploaded_files=index, uploaded_bytes=sent, current=row['path'])
            if index == 1 or index % 100 == 0 or sent - last_progress_bytes >= 128 * CHUNK or index == len(files):
                print(f'uploaded {index}/{len(files)} files, {sent}/{total} bytes: {row["path"]}', flush=True)
                last_progress_bytes = sent
                save()
        wfm.api('/api/upload/finish', {'task_id': task_id})
        report['upload_task'] = wfm.wait(task_id, args.task_timeout)
        report['all_files_transferred'] = True
        report['state'] = 'creating-missing-empty-layout-directories'
        save()
    except Exception:
        try:
            wfm.api('/api/cancel', {'id': task_id})
            wfm.api('/api/upload/finish', {'task_id': task_id})
        except Exception:
            pass
        raise
    # Relative file uploads create their populated parents. Once that task is
    # terminal, create only missing declared empty folders through /api/mkdir.
    report['created_empty_directories'] = ensure_remote_directories(wfm, destination, directories)
    report['remote_sizes'] = verify_sizes(wfm, destination, files, directories)
    report['file_readbacks'] = []
    selected = files if args.verify == 'all' else ([row for row in files if row['path'] in CRITICAL] if args.verify == 'critical' else [])
    for row in selected:
        report['file_readbacks'].append(wfm.readback(destination + '/' + row['path'], row['bytes'], row['sha256'], args.task_timeout))
        save()
    report.update(state='usb-transfer-verified', uploaded=True,
                  verification=('local-sha256+remote-all-file-sizes' if args.verify == 'sizes' else 'all-file-sizes+' + args.verify + '-file-sha256'),
                  no_archive_extraction=True)
    save()
    print('Direct USB file transfer verified; no helper, app install, launch or save/config overwrite.', flush=True)
    return 0


def make_zip(path, files, directories):
    # No member is an outside link or absolute path; no local ISO copies are made.
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
        for directory in directories:
            info = zipfile.ZipInfo(directory + '/')
            info.external_attr = (0o40755 << 16) | 0x10
            archive.writestr(info, b'')
        for row in files:
            value, size = hashlib.sha256(), 0
            info = zipfile.ZipInfo(row['path'])
            info.file_size = row['bytes']
            info.compress_type = zipfile.ZIP_DEFLATED
            info._compresslevel = 1  # ZipInfo-level setting used by ZipFile.open.
            info.external_attr = 0o100644 << 16
            with row['source'].open('rb') as incoming, archive.open(info, 'w', force_zip64=row['bytes'] >= 2**31) as outgoing:
                for block in iter(lambda: incoming.read(CHUNK), b''):
                    outgoing.write(block)
                    value.update(block)
                    size += len(block)
            if size != row['bytes'] or value.hexdigest() != row['sha256']:
                raise ValueError('package member changed during archive creation: ' + row['path'])
    return dict(bytes=path.stat().st_size, sha256=sha256(path))


def verify_sizes(wfm, destination, files, directories):
    listings = {}
    for directory in directories:
        entries = wfm.listing(destination + '/' + directory)
        listings[directory] = {row['name']: row for row in entries}
    for row in files:
        path = PurePosixPath(row['path'])
        remote = listings.get(str(path.parent), {}).get(path.name)
        if not remote or remote.get('type') != '-' or remote.get('size') != row['bytes']:
            raise ValueError('extracted remote file type/size differs: ' + row['path'])
    return dict(file_count=len(files), bytes=sum(row['bytes'] for row in files), verified='all-file-sizes-and-directories')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True, help='exact selected PACKAGE-MANIFEST.json identity')
    parser.add_argument('--destination', default='/mnt/usb0', help='USB root only; app/asset folders must both be absent')
    parser.add_argument('--server', default='http://192.168.1.23:8888')
    parser.add_argument('--report', type=Path, required=True, help='new local receipt below private/')
    parser.add_argument('--verify', choices=('sizes', 'critical', 'all'), default='sizes')
    parser.add_argument('--mode', choices=('zip', 'files'), default='files', help='default files streams directly and needs no 7zip helper')
    parser.add_argument('--task-timeout', type=int, default=1800)
    parser.add_argument('--execute', action='store_true', help='perform the explicitly authorized USB transfer')
    parser.add_argument('--keep-local-zip', action='store_true')
    parser.add_argument('--keep-remote-zip', action='store_true', help='retain the exact newly uploaded transport archive after verification')
    args = parser.parse_args()
    report = None
    try:
        destination = usb_path(args.destination)
        if not re.fullmatch(r'/mnt/usb[0-9]+', destination):
            raise ValueError('select a USB root so the exact two-folder layout remains discoverable')
        if not 30 <= args.task_timeout <= 7200:
            raise ValueError('task timeout must be30–7200 seconds')
        output = plain(args.report)
        if not output.is_relative_to(PRIVATE.resolve()) or output.exists():
            raise ValueError('report must be a fresh absent local file under private/')
        manifest, files, directories, total = load_package(args.manifest, args.manifest_sha256, destination)
        package_root = plain(args.manifest).parent
        if output.is_relative_to(package_root):
            raise ValueError('transfer receipt/scratch must be outside the immutable package tree')
        # Validate target endpoint even for a local plan, but perform no network I/O.
        wfm = Wfm(args.server)
        report = dict(schema='sc2.usb-transfer.v1', manifest_sha256=args.manifest_sha256, destination=destination,
                      files=len(files), uncompressed_bytes=total, execute=args.execute, mode=args.mode, uploaded=False,
                      verification_requested=args.verify, manifest_path=str(plain(args.manifest)),
                      local_eboot_identity=next(dict(path=destination + '/' + row['path'], bytes=row['bytes'], sha256=row['sha256']) for row in files if row['path'] == 'homebrew/Soulcalibur II/eboot.bin'),
                      installed=False, console_launched=False, gameplay_verified=False)
        output.parent.mkdir(parents=True, exist_ok=True)
        def save(): output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        if not args.execute:
            report['state'] = 'local-plan-validated-no-network'
            save()
            print('Validated local package; no network operation. Use --execute only with current USB transfer authorization.')
            return 0
        if args.mode == 'files':
            return execute_files(wfm, args, destination, files, directories, total, report, save)
        archive_name = '.sc2-transfer-' + args.manifest_sha256[:12] + '-' + uuid.uuid4().hex[:8] + '.zip'
        archive_path = output.parent / archive_name
        remote_archive = destination + '/' + archive_name
        wfm.assert_fresh(destination, archive_name)
        spaces = wfm.api('/api/space', {'path': destination}).get('spaces', [])
        available = next((row for row in spaces if row.get('path') == destination), None)
        # Peak remote use is archive plus extracted bytes. The local ZIP is derived
        # staging, not a duplicated disc-image folder, and is removed after success.
        if not available or available.get('free', 0) < 2 * total + 64 * CHUNK:
            raise ValueError('USB free-space preflight cannot cover archive plus extracted data')
        if shutil.disk_usage(output.parent).free < total + 64 * CHUNK:
            raise ValueError('local scratch free space insufficient for streamed ZIP staging')
        wfm.owned_archives.add(remote_archive)
        report.update(state='building-transport-zip', archive=remote_archive)
        save()
        archive = make_zip(archive_path, files, directories)
        report['transport'] = archive
        wfm.assert_fresh(destination, archive_name)
        task = wfm.api('/api/upload/prepare', dict(path=destination, src=archive_name, total=archive['bytes'],
                       count=1, rels=archive_name, sizes=str(archive['bytes']), overwrite='0'), form=True)
        task_id = task['task_id']
        report.update(state='uploading-archive', upload_task_id=task_id)
        save()
        try:
            wfm.upload(task_id, destination, archive_path, archive_name, archive['sha256'])
            wfm.api('/api/upload/finish', {'task_id': task_id})
            report['upload_task'] = wfm.wait(task_id, args.task_timeout)
        except Exception:
            # Only our own task is canceled; no file deletion or app operation.
            try:
                wfm.api('/api/cancel', {'id': task_id})
                wfm.api('/api/upload/finish', {'task_id': task_id})
            except Exception:
                pass
            raise
        report['archive_uploaded'] = True
        if args.verify != 'sizes':
            report['archive_readback'] = wfm.readback(remote_archive, archive['bytes'], archive['sha256'], args.task_timeout)
        archive_entry = next((row for row in wfm.listing(destination) if row['name'] == archive_name), None)
        if not archive_entry or archive_entry.get('type') != '-' or archive_entry.get('size') != archive['bytes']:
            raise ValueError('uploaded archive metadata does not identify a regular file')
        # Recheck only app/assets names; the verified archive now exists.
        wfm.assert_fresh(destination)
        extract = wfm.api('/api/extract', dict(paths=remote_archive, destination=destination, separate='0', overwrite='0'), form=True)
        report.update(state='extracting-new-folders', extract_task_id=extract['task_id'])
        save()
        report['extract_task'] = wfm.wait(extract['task_id'], args.task_timeout)
        report['remote_sizes'] = verify_sizes(wfm, destination, files, directories)
        selected = files if args.verify == 'all' else ([row for row in files if row['path'] in CRITICAL] if args.verify == 'critical' else [])
        report['file_readbacks'] = []
        for row in selected:
            report['file_readbacks'].append(wfm.readback(destination + '/' + row['path'], row['bytes'], row['sha256'], args.task_timeout))
            save()
        report.update(state='usb-transfer-verified', uploaded=True,
                      verification=('local-sha256+remote-all-file-sizes' if args.verify == 'sizes' else 'archive-sha256+all-file-sizes+' + args.verify + '-file-sha256'),
                      remote_archive_retained=True, local_zip_retained=args.keep_local_zip)
        if not args.keep_remote_zip:
            try:
                now = next((row for row in wfm.listing(destination) if row['name'] == archive_name), None)
                if (not now or now.get('path') != remote_archive or now.get('type') != '-' or
                        now.get('size') != archive['bytes'] or now.get('mtime') != archive_entry.get('mtime')):
                    raise ValueError('transport archive identity changed; cleanup refused')
                cleanup = wfm.api('/api/delete', {'paths': remote_archive}, form=True)
                report['archive_cleanup_task'] = wfm.wait(cleanup['task_id'], args.task_timeout)
                if any(row['name'] == archive_name for row in wfm.listing(destination)):
                    raise ValueError('transport archive remains after delete task')
                report['remote_archive_retained'] = False
            except (ValueError, OSError, KeyError, TypeError, http.client.HTTPException) as error:
                report['archive_cleanup_warning'] = str(error)
        if not args.keep_local_zip:
            archive_path.unlink()
        save()
        print('USB transfer verified; no app install, launch, close or save/config overwrite.')
        return 0
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, zipfile.BadZipFile, http.client.HTTPException) as error:
        if report is not None:
            report.update(state='failed-partial-usb-state-preserved', error=str(error))
            output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        parser.exit(1, 'USB transfer rejected/failed: ' + str(error) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
