#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Finalize a genuine application-ABI SC2 link with pinned public PS5 tooling.

No target execution, network, installation, title-ID creation or game assets.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import zlib

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'private'
CONVERTER_SHA256 = '78fdfec756c6e7fa132bd2fbf6eeaea753d9b01349d09a8993bba76eed77fd84'
COMPANION_SHA256 = 'e6ff45d16adf687855cc3b33b0c8a4132b6504360b221e0a34c7e99fb3ba0036'
MAX_ELF = 1024 * 1024 * 1024


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def plain(path):
    path = path.absolute()
    for item in (path, *path.parents):
        if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
            raise ValueError('links/junctions are not accepted: ' + str(item))
    return path.resolve()


def record(path):
    return dict(path=str(path), bytes=path.stat().st_size, sha256=digest(path))


def png_icon(path):
    """Check the actual bounded PNG stream, not a filename or IHDR alone."""
    if not path.is_file() or not 57 <= path.stat().st_size <= 8 * 1024 * 1024:
        raise ValueError('required app icon missing/oversized: ' + str(path))
    data = path.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('app icon must contain a real PNG signature: ' + str(path))
    at, count, width, height, channels = 8, 0, 0, 0, 0
    compressed = bytearray()
    ended = False
    while at < len(data):
        count += 1
        if count > 4096 or len(data) - at < 12:
            raise ValueError('truncated/excessive PNG chunks')
        size, = struct.unpack_from('>I', data, at)
        if size > len(data) - at - 12:
            raise ValueError('PNG chunk exceeds icon file')
        kind = data[at + 4:at + 8]
        body = data[at + 8:at + 8 + size]
        crc, = struct.unpack_from('>I', data, at + 8 + size)
        if not re.fullmatch(b'[A-Za-z]{4}', kind) or zlib.crc32(kind + body) & 0xffffffff != crc:
            raise ValueError('invalid PNG chunk type/CRC')
        if count == 1 and (kind != b'IHDR' or size != 13):
            raise ValueError('PNG must begin with its13-byte IHDR')
        if kind == b'IHDR':
            if count != 1:
                raise ValueError('duplicate PNG IHDR')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', body)
            if (width, height) != (512, 512) or depth != 8 or color not in (2, 6) or compression or filtering or interlace:
                raise ValueError('app icon must be512x512 noninterlaced8-bit RGB/RGBA PNG')
            channels = 3 if color == 2 else 4
        elif kind == b'IDAT':
            compressed.extend(body)
        elif kind == b'IEND':
            if size != 0 or at + 12 != len(data):
                raise ValueError('invalid PNG IEND/trailing bytes')
            ended = True
            break
        elif kind[0] < ord('a') and kind != b'PLTE':
            raise ValueError('unsupported critical PNG chunk')
        at += size + 12
    if not ended or not compressed:
        raise ValueError('PNG icon lacks IDAT/IEND')
    expected = height * (1 + width * channels)
    decoder = zlib.decompressobj()
    pixels = decoder.decompress(compressed, expected + 1)
    if len(pixels) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError('invalid or oversized PNG pixel stream')
    if any(pixels[y * (1 + width * channels)] > 4 for y in range(height)):
        raise ValueError('invalid PNG scanline filter')
    return dict(width=width, height=height, channels=channels, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def image(path, sections=True):
    if not path.is_file() or not 64 <= path.stat().st_size <= MAX_ELF:
        raise ValueError('ELF missing or outside 64B–1GiB bound')
    data = path.read_bytes()
    if data[:7] != b'\x7fELF\x02\x01\x01':
        raise ValueError('require little-endian ELF64')
    kind, machine, version, entry, phoff, shoff = struct.unpack_from('<HHIQQQ', data, 16)
    ehsize, phsize, phcount, shsize, shcount, names = struct.unpack_from('<6H', data, 52)
    if machine != 62 or version != 1 or not entry or ehsize != 64 or phsize != 56 or not 1 <= phcount <= 128:
        raise ValueError('require x86-64 ELF with executable entry and bounded program headers')
    if phoff + phsize * phcount > len(data):
        raise ValueError('program headers exceed ELF')
    programs = []
    for i in range(phcount):
        t, flags, offset, address, _, size, memory, align = struct.unpack_from('<II6Q', data, phoff + i * 56)
        if (t == 1 and size > memory) or offset + size > len(data):
            raise ValueError('program segment outside ELF or memory range')
        programs.append(dict(type=t, flags=flags, offset=offset, address=address, size=size, memory=memory, align=align))
    if not any(p['type'] == 1 and p['flags'] & 1 and p['address'] <= entry < p['address'] + p['memory'] for p in programs):
        raise ValueError('entry outside executable LOAD')
    headers = []
    if sections:
        if shsize != 64 or not 1 <= shcount <= 32768 or not names < shcount or shoff + shsize * shcount > len(data):
            raise ValueError('bounded standard section headers required before conversion')
        for i in range(shcount):
            n, t, flags, address, offset, size, link, info, align, entsize = struct.unpack_from('<II4QII2Q', data, shoff + i * 64)
            if t != 8 and offset + size > len(data):
                raise ValueError('section exceeds ELF')
            headers.append(dict(name_at=n, type=t, flags=flags, address=address, offset=offset, size=size, link=link, entsize=entsize))
        strings = headers[names]
        table = data[strings['offset']:strings['offset'] + strings['size']]
        for h in headers:
            end = table.find(b'\0', h['name_at'])
            if end < 0:
                raise ValueError('unterminated section name')
            h['name'] = table[h['name_at']:end].decode('ascii')
    return dict(data=data, type=kind, entry=entry, programs=programs, sections=headers)


def preflight(elf, nm):
    obj = image(elf)
    if obj['type'] != 3:
        raise ValueError('require intermediate application PIE, not already-converted ELF or payload module')
    sections = {h['name']:h for h in obj['sections']}
    if '.text' not in sections or sections['.text']['address'] != 0:
        raise ValueError('application linker layout must place text at zero')
    if any(p['type'] == 7 for p in obj['programs']) or any(h['flags'] & 0x400 for h in obj['sections']):
        raise ValueError('native TLS unsupported by this converter; compile with emulated TLS')
    for p in obj['programs']:
        if p['type'] == 1 and (p['align'] != 0x4000 or p['offset'] % 0x4000 != p['address'] % 0x4000):
            raise ValueError('application LOAD segments require matching16KiB alignment')
    dyn = sections.get('.dynsym')
    if not dyn or dyn['entsize'] != 24 or dyn['size'] % 24:
        raise ValueError('valid dynamic symbol table required')
    for at in range(dyn['offset'] + 24, dyn['offset'] + dyn['size'], 24):
        if struct.unpack_from('<H', obj['data'], at + 6)[0] != 0:
            raise ValueError('converter cannot publish application exports; use app-symbols.map')
    for h in obj['sections']:
        if h['type'] == 4:
            if h['entsize'] != 24 or h['size'] % 24:
                raise ValueError('invalid RELA table')
            for at in range(h['offset'], h['offset'] + h['size'], 24):
                if struct.unpack_from('<Q', obj['data'], at + 8)[0] & 0xffffffff not in (1, 6, 7, 8):
                    raise ValueError('unsupported application relocation')
    result = subprocess.run([str(nm), '--defined-only', '--just-symbol-name', str(elf)], capture_output=True, text=True, check=True)
    symbols = set(result.stdout.splitlines())
    if '_start' not in symbols or symbols.intersection({'__crt_start', 'payload_get_args', 'kernel_init'}):
        raise ValueError('payload CRT cannot be SELF-wrapped into an application; link application CRT first')
    return obj


def retained(original, converted):
    obj = image(converted, sections=False)
    if obj['type'] != 0xfe10 or obj['entry'] != original['entry'] or obj['data'][7:9] != bytes((9, 2)):
        raise ValueError('SCE type/ABI/entry mismatch')
    types = {p['type'] for p in obj['programs']}
    sce_dynamic = any(0x61000000 <= struct.unpack_from('<Q', obj['data'], at)[0] < 0x62000000
                      for p in obj['programs'] if p['type'] == 2
                      for at in range(p['offset'], p['offset'] + p['size'] - 15, 16))
    if 0x61000001 not in types or not (0x61000000 in types or sce_dynamic):
        raise ValueError('converted application lacks SCE dynamic/process parameters')
    result = []
    for h in original['sections']:
        if not h['flags'] & 2 or not h['size'] or re.match(r'^\.(dynstr|dynsym|dynamic|hash|gnu\.hash|rela\.)', h['name']):
            continue
        for p in obj['programs']:
            end = p['address'] + (p['memory'] if h['type'] == 8 else p['size'])
            if p['type'] == 1 and p['address'] <= h['address'] and h['address'] + h['size'] <= end:
                at = p['offset'] + h['address'] - p['address']
                if h['type'] == 8:
                    if h['address'] < p['address'] + p['size']:
                        raise ValueError('BSS overlaps stored bytes after conversion')
                elif original['data'][h['offset']:h['offset'] + h['size']] != obj['data'][at:at + h['size']]:
                    raise ValueError('conversion changed retained bytes: ' + h['name'])
                result.append(dict(section=h['name'], bytes=h['size'], preserved=True))
                break
        else:
            raise ValueError('conversion omitted retained section: ' + h['name'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', required=True, type=Path)
    parser.add_argument('--link-receipt', required=True, type=Path)
    parser.add_argument('--converter', required=True, type=Path)
    parser.add_argument('--sdk', required=True, type=Path)
    parser.add_argument('--llvm', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--metadata', type=Path, help='explicit owner-authored app folder containing sce_sys/param.json')
    parser.add_argument('--companion', type=Path, required=True,
                        help='reviewed source-derived signed public loader shim libc.prx')
    args = parser.parse_args()
    try:
        elf, receipt_path, converter, sdk, llvm, out = map(plain, (args.elf, args.link_receipt, args.converter, args.sdk, args.llvm, args.output))
        if not out.is_relative_to(PRIVATE.resolve()) or out == PRIVATE.resolve() or out.exists():
            raise ValueError('output must be a fresh absent private/ subdirectory')
        receipt = json.loads(receipt_path.read_text())
        if receipt.get('exit_code') != 0 or not receipt.get('fully_linked') or receipt.get('application_abi') != 'sc2.ps5-application.v1':
            raise ValueError('require successful authentic application-ABI link receipt')
        selected = receipt.get('output') or receipt.get('elf')
        if not selected or plain(Path(selected['path'])) != elf or digest(elf) != selected['sha256'] or elf.stat().st_size != selected['bytes']:
            raise ValueError('actual ELF differs from linked output receipt')
        if receipt.get('unresolved_without_sdk_import') or receipt.get('unresolved_link_errors'):
            raise ValueError('application receipt still has unresolved dependencies')
        for item in receipt['inputs']:
            if digest(plain(Path(item['path']))) != item['sha256']:
                raise ValueError('linked input changed: ' + item['path'])
        if digest(converter) != CONVERTER_SHA256:
            raise ValueError('converter differs from reviewed public PSXS5 build')
        stubdir = sdk / 'target/lib'
        nm = llvm / ('llvm-nm.exe' if __import__('os').name == 'nt' else 'llvm-nm')
        if not stubdir.is_dir() or not nm.is_file():
            raise ValueError('existing public SDK import directory and LLVM nm required')
        original = preflight(elf, nm)
        from ps5_audit_syscalls import audit_syscalls
        decoder = llvm / ('llvm-objdump.exe' if __import__('os').name == 'nt' else 'llvm-objdump')
        syscall_audit = audit_syscalls(elf, decoder)
        if syscall_audit['count']:
            raise ValueError('application contains direct syscall instructions; use native application services')
        metadata = []
        if args.metadata:
            folder = plain(args.metadata)
            param = folder / 'sce_sys/param.json'
            value = json.loads(plain(param).read_text())
            title = value.get('titleId')
            if not isinstance(title, str) or not re.fullmatch(r'[A-Z]{4}[0-9]{5}', title):
                raise ValueError('explicit metadata must carry a valid owner-selected titleId')
            png_icon(plain(folder / 'sce_sys/icon0.png'))
            for relative in ('sce_sys/param.json', 'sce_sys/icon0.png', 'sce_sys/pic0.dds', 'sce_sys/pic1.dds', 'icon0.png'):
                source = plain(folder / relative)
                if source.is_file():
                    if relative.endswith('icon0.png'): png_icon(source)
                    metadata.append((source, Path(relative)))
        companion = plain(args.companion)
        if (not companion.is_file() or companion.stat().st_size != 1284674 or
                digest(companion) != COMPANION_SHA256):
            raise ValueError('require the reviewed signed public loader companion, not a raw ELF or retail module')
        metadata.append((companion, Path('sce_module/libc.prx')))
        for source in (elf, receipt_path, converter, *(p for p, _ in metadata)):
            if out == source or source.is_relative_to(out) or out.is_relative_to(source):
                raise ValueError('final output overlaps an input')
        out.mkdir(parents=True, exist_ok=False)
        commands = []
        def run(label, command):
            commands.append(command)
            done = subprocess.run(command, capture_output=True, text=True, errors='replace')
            (out / (label + '.log')).write_text(done.stdout + done.stderr)
            if done.returncode:
                raise ValueError(label + ' failed; partial output retained')
            return done.stdout
        converted, self_file = out / 'eboot.elf', out / 'eboot.bin'
        run('convert', [str(converter), 'link', '--in', str(elf), '--out', str(converted), '--stub-dir', str(stubdir), '--file-name', 'eboot.elf'])
        sections = retained(original, converted)
        run('self', [str(converter), 'self', '--sign', '--in', str(converted), '--out', str(self_file)])
        inspection = run('inspect', [str(converter), 'self', '--inspect', '--file', str(self_file)])
        if not re.search(r'^integrity:\s*valid\s*$', inspection, re.M):
            raise ValueError('development SELF integrity check failed')
        for source, relative in metadata:
            target = out / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open('rb') as incoming, target.open('xb') as outgoing:
                shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
            if relative.as_posix().endswith('icon0.png'): png_icon(target)
        # Preserve rights/credit in the local artifact; no game files are copied.
        for source in (ROOT / 'LICENSE', ROOT / 'platform/ps5/app/LICENSE'):
            target = out / 'legal' / ('PSXS5-GPL-3.0.txt' if source.parent.name == 'app' else 'SC2-GPL-3.0.txt')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        shutil.copyfile(ROOT / 'platform/ps5/app/SOURCE.json', out / 'legal/PSXS5-SOURCE.json')
        shutil.copyfile(ROOT / 'platform/ps5/app/LOADER-COMPANION.json', out / 'legal/PSXS5-LOADER-SOURCE.json')
        platform_notices = []
        if receipt.get('title_heap'):
            for name in ('LICENSE-GPL-3.0.txt', 'LICENSE-DLMALLOC-MIT-0.txt', 'SOURCE.json'):
                source = ROOT / 'platform/ps5/memory' / name
                relative = Path('legal/PS5-Platform') / name
                target = out / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                platform_notices.append(dict(path=relative.as_posix(), source=record(source)))
        shutil.copyfile(ROOT / 'platform/ps5/RELEASE-ENDNOTE.md', out / 'RELEASE-ENDNOTE.md')
        result = dict(schema='sc2.ps5-finalized-app.v1', input=record(elf), link_receipt=record(receipt_path), converter=record(converter),
                      output=record(converted), self=record(self_file), retained_sections=sections, commands=commands,
                      metadata_supplied=bool(args.metadata), metadata=[dict(path=str(r), source=record(p)) for p, r in metadata],
                      loader_companion=record(out / 'sce_module/libc.prx'),
                      syscall_audit=syscall_audit,
                      platform_notices=platform_notices,
                      application_linked=True, console_executed=False, installed=False, gameplay_verified=False)
        (out / 'FINALIZATION.json').write_text(json.dumps(result, indent=2) + '\n')
        print('Converted application ELF/development SELF locally; no installation or target execution.')
    except (ValueError, OSError, KeyError, TypeError, struct.error, subprocess.SubprocessError) as error:
        parser.exit(1, f'finalization rejected: {error}\n')


if __name__ == '__main__':
    main()
