#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Inventory an owned OLNK archive without extracting or changing its contents.

Format basis: this project's guest/olnk.cpp. This is a container inspector,
not a character/model compatibility detector. JSON output contains source
identities and belongs in private/, not in the public repository.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

MAX_ENTRIES = 100_000
MAX_DEPTH = 8
CHUNK = 1024 * 1024


class InvalidArchive(ValueError):
    pass


def inventory(source, hash_leaves=False):
    """Return bounded, validated structural metadata; never write source data."""
    source = Path(source)
    rows = []
    entry_budget = MAX_ENTRIES
    with source.open('rb') as stream:
        length = stream.seek(0, 2)

        def read(at, size):
            if at < 0 or size < 0 or at + size > length:
                raise InvalidArchive('read outside source archive')
            stream.seek(at)
            data = stream.read(size)
            if len(data) != size:
                raise InvalidArchive('source changed or became unreadable')
            return data

        def digest(at, size):
            result = hashlib.sha256()
            while size:
                part = min(size, CHUNK)
                result.update(read(at, part))
                at += part
                size -= part
            return result.hexdigest()

        def visit(base, size, path, depth):
            nonlocal entry_budget
            if depth > MAX_DEPTH:
                raise InvalidArchive('container nesting exceeds limit')
            if size < 0x20:
                raise InvalidArchive(f'{path or "/"}: truncated container')
            header = read(base, 0x20)
            if header[4:8] != b'olnk':
                raise InvalidArchive(f'{path or "/"}: expected olnk signature')
            count, = struct.unpack_from('<I', header)
            alignment, = struct.unpack_from('<I', header, 8)
            data_start, = struct.unpack_from('<I', header, 0x10)
            index_end = 0x20 + 16 * count
            if count > entry_budget or index_end > size:
                raise InvalidArchive(f'{path or "/"}: invalid or excessive entry count')
            entry_budget -= count
            if data_start < index_end or data_start > size:
                raise InvalidArchive(f'{path or "/"}: invalid data start')
            index = read(base + 0x20, 16 * count)
            for number in range(count):
                offset, item_size, timestamp, reserved = struct.unpack_from('<4I', index, number * 16)
                name = f'{path}/{number}'
                absolute = base + data_start + offset
                # Empty entries can carry unused offsets; do not dereference them.
                if item_size and (data_start + offset > size or data_start + offset + item_size > size):
                    raise InvalidArchive(f'{name}: entry outside parent container')
                prefix = read(absolute, min(item_size, 0x20)) if item_size else b''
                nested = item_size >= 0x20 and prefix[4:8] == b'olnk'
                row = {'path': name, 'offset': absolute if item_size else None,
                       'size': item_size, 'kind': 'container' if nested else 'leaf',
                       'prefix_hex': prefix.hex(), 'timestamp_raw': timestamp,
                       'reserved_raw': reserved, 'parent_alignment_raw': alignment}
                if hash_leaves and not nested:
                    row['sha256'] = digest(absolute, item_size) if item_size else hashlib.sha256(b'').hexdigest()
                rows.append(row)
                if nested:
                    visit(absolute, item_size, name, depth + 1)

        before = source.stat()
        visit(0, length, '', 0)
        archive_hash = digest(0, length)
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise InvalidArchive('source changed while inventorying')
    return {'schema': 'sc2.olk-inventory.v1', 'source_name': source.name,
            'source_bytes': length, 'source_sha256': archive_hash,
            'compatibility': 'container structure only; donor game and asset semantics unverified',
            'entries': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--hash-leaves', action='store_true', help='also hash each leaf (extra source reads)')
    parser.add_argument('--out', type=Path, required=True, help='new JSON file below this checkout private/')
    args = parser.parse_args()
    private = Path(__file__).resolve().parents[2] / 'private'
    output = args.out.resolve()
    if not output.is_relative_to(private.resolve()):
        parser.error('--out must be below this checkout private/')
    if output == args.archive.resolve():
        parser.error('output must differ from input')
    if output.exists():
        parser.error('output already exists; choose a new filename')
    try:
        result = inventory(args.archive, args.hash_leaves)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8', newline='\n') as target:
            json.dump(result, target, indent=2)
            target.write('\n')
    except (OSError, InvalidArchive) as error:
        print(f'olk_inventory: {error}', file=sys.stderr)
        return 1
    print(f'{len(result["entries"])} entries inventoried into {output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
