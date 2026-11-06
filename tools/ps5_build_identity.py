#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Artifact-bound PS5 startup identity, without linking or running the game.

The caller freezes inputs and command BEFORE adding the generated identity
object. Commit is an annotation, not a claim that a dirty tree matches it.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

MANIFEST_SCHEMA = 'sc2.ps5-build-identity-manifest.v1'
RECORD_SCHEMA = 'sc2.ps5-build-identity.v1'
SYMBOL = 'sc2_ps5_build_id'
MAX_ITEMS = 100000
MAX_MANIFEST_BYTES = 32 * 1024 * 1024


def _text(value, limit, field):
    if not isinstance(value, str) or not value or len(value) > limit or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('invalid build identity ' + field)
    return value


def make_manifest(inputrecords, command, label, commit):
    """Freeze actual input hashes and exact ordered command, excluding identity.

    Input order is immaterial; command order is significant. Repeated identical
    paths are coalesced, while conflicting hashes are rejected. Paths are kept
    exactly as supplied rather than resolved through a mutable filesystem.
    """
    if not isinstance(inputrecords, list) or not 1 <= len(inputrecords) <= MAX_ITEMS:
        raise ValueError('build identity input count outside bound')
    if not isinstance(command, list) or not 1 <= len(command) <= MAX_ITEMS:
        raise ValueError('build identity command count outside bound')
    inputs = {}
    for item in inputrecords:
        if not isinstance(item, dict) or set(item) != {'path', 'sha256'}:
            raise ValueError('build identity input requires path and sha256')
        path = _text(item['path'], 8192, 'input path')
        digest = item['sha256']
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('invalid build identity input hash')
        if path in inputs and inputs[path] != digest:
            raise ValueError('conflicting build identity input: ' + path)
        inputs[path] = digest
    result = dict(schema=MANIFEST_SCHEMA, label=_text(label, 128, 'label'),
                  commit=_text(commit, 128, 'commit annotation'),
                  inputs=[dict(path=p, sha256=inputs[p]) for p in sorted(inputs)],
                  command=[_text(arg, 16384, 'command argument') for arg in command])
    _encode(result)
    return result


def _encode(manifest):
    encoded = json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise ValueError('build identity manifest exceeds byte bound')
    return encoded


def _checked_manifest(manifest):
    if not isinstance(manifest, dict) or set(manifest) != {'schema', 'label', 'commit', 'inputs', 'command'}:
        raise ValueError('invalid build identity manifest fields')
    if manifest['schema'] != MANIFEST_SCHEMA:
        raise ValueError('invalid build identity manifest schema')
    canonical = make_manifest(manifest['inputs'], manifest['command'], manifest['label'], manifest['commit'])
    if manifest != canonical:
        raise ValueError('build identity manifest is not normalized')
    return canonical


def token_for(manifest):
    """Return SHA256 of normalized canonical JSON, independent of dict order."""
    return hashlib.sha256(_encode(_checked_manifest(manifest))).hexdigest()


def _record_file(path):
    path = Path(path).resolve()
    return dict(path=str(path), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def _payload(record):
    if not isinstance(record, dict) or record.get('schema') != RECORD_SCHEMA:
        raise ValueError('invalid build identity record')
    token = token_for(record['manifest'])
    text = 'SC2 build-id: ' + token
    if record.get('token') != token or record.get('text') != text or record.get('symbol') != SYMBOL:
        raise ValueError('build identity record differs from its manifest')
    return text.encode('ascii') + b'\0'


def compile_identity(manifest, sdkPath, llvmPath, outPath):
    """Compile one generated C object; outPath is a private output directory.

    The normal dependency-tracked compiler receipt is retained. The returned
    input paths supplement the object already selected by the caller's linker.
    No application link, conversion, console operation or runtime test occurs.
    """
    from ps5_compile_host import compile_record
    manifest = _checked_manifest(manifest)
    sdk, llvm, out = map(lambda p: Path(p).resolve(), (sdkPath, llvmPath, outPath))
    out.mkdir(parents=True, exist_ok=True)
    source, obj = out / 'sc2_ps5_build_identity.c', out / 'sc2_ps5_build_identity.o'
    manifest_path = out / 'build-identity-manifest.json'
    token = token_for(manifest)
    text = 'SC2 build-id: ' + token
    source.write_text('/* Generated from frozen linker inputs; commit is annotation only. */\n'
                      '__attribute__((visibility("hidden"), used)) const char ' + SYMBOL +
                      '[] = "' + text + '";\n', encoding='ascii')
    manifest_path.write_bytes(_encode(manifest) + b'\n')
    compiler = llvm / ('clang.exe' if sys.platform == 'win32' else 'clang')
    command = [str(compiler), '--target=x86_64-sie-ps5', '-isysroot', str(sdk),
               '-DSC2_PS5=1', '-DSC2_PS5_APPLICATION=1', '-O2', '-std=c11',
               '-fPIC', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
               '-femulated-tls', '-c', str(source), '-o', str(obj)]
    row = compile_record(source, obj, command, sdk, out / 'sc2_ps5_build_identity.log')
    if row['exit_code'] or not row['object']:
        raise ValueError('build identity compile failed: ' + row['log'])
    receipt_path = obj.with_suffix('.object.json')
    record = dict(schema=RECORD_SCHEMA, manifest=copy.deepcopy(manifest), token=token,
                  text=text, symbol=SYMBOL, commit_is_annotation=True,
                  source=_record_file(source), object=_record_file(obj),
                  compile_receipt=_record_file(receipt_path),
                  manifest_file=_record_file(manifest_path), executed=False)
    return obj, record, [source, manifest_path, receipt_path]


def _load_bytes(obj, address, count):
    for program in obj['programs']:
        if (program['type'] == 1 and program['flags'] & 4 and not program['flags'] & 1 and
                program['address'] <= address and address + count <= program['address'] + program['size']):
            at = program['offset'] + address - program['address']
            return obj['data'][at:at + count]
    raise ValueError('build identity is not fully stored in readable non-executable LOAD data')


def bind_identity(elfPath, record):
    """Find the actual defined OBJECT and bind its exact bytes to the record."""
    from ps5_finalize_payload import image
    payload = _payload(record)
    obj = image(Path(elfPath))
    data, sections = obj['data'], obj['sections']
    matches = []
    for table in sections:
        if table['type'] not in (2, 11):
            continue
        if table['entsize'] != 24 or table['size'] % 24 or table['link'] >= len(sections):
            raise ValueError('invalid build identity symbol table')
        strings = sections[table['link']]
        if strings['type'] != 3:
            raise ValueError('build identity symbol table lacks strings')
        names = data[strings['offset']:strings['offset'] + strings['size']]
        for at in range(table['offset'], table['offset'] + table['size'], 24):
            name_at, info, _, section_index, address, size = struct.unpack_from('<IBBHQQ', data, at)
            if name_at >= len(names):
                raise ValueError('build identity symbol name exceeds string table')
            end = names.find(b'\0', name_at)
            if end < 0:
                raise ValueError('unterminated build identity symbol name')
            if names[name_at:end] != SYMBOL.encode('ascii'):
                continue
            if not 0 < section_index < len(sections) or info & 15 != 1 or not address:
                raise ValueError('build identity symbol is not a defined nonzero OBJECT')
            section = sections[section_index]
            if not section['flags'] & 2 or section['flags'] & 4 or size != len(payload) or not (
                    section['address'] <= address and address + size <= section['address'] + section['size']):
                raise ValueError('build identity OBJECT is outside an allocated section or wrong size')
            if _load_bytes(obj, address, size) != payload:
                raise ValueError('build identity OBJECT bytes differ from manifest')
            binding = dict(address=address, address_hex=hex(address), bytes=size,
                           symbol_type='OBJECT', section=section['name'])
            if binding not in matches:
                matches.append(binding)
    if len(matches) != 1:
        raise ValueError('build identity OBJECT is missing or ambiguous')
    result = copy.deepcopy(record)
    result['binding'] = matches[0]
    return result


def validate_identity(elfPath, record):
    """Verify linked or converted ELF LOAD bytes using the recorded binding."""
    from ps5_finalize_payload import image
    payload = _payload(record)
    binding = record.get('binding') or {}
    address = binding.get('address')
    if type(address) is not int or address <= 0 or binding.get('bytes') != len(payload) or binding.get('symbol_type') != 'OBJECT':
        raise ValueError('build identity record lacks a valid OBJECT binding')
    obj = image(Path(elfPath), sections=False)
    if _load_bytes(obj, address, len(payload)) != payload:
        raise ValueError('stored ELF build identity differs from its frozen manifest')
    return True
