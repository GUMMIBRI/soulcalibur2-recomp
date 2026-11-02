# SPDX-License-Identifier: GPL-3.0-or-later
"""Namco's "olnk" containers (root.olk on every Soulcalibur II disc) and the numbered packs inside them.

An olnk container (always little-endian, even on the GameCube):
  +0x00 u32 count   +0x04 'olnk'   +0x08 u32 alignment (0x800)   +0x0C 0
  +0x10 u32 header size (the data starts this far from the container's start)
  +0x14 u32 data size (or 0)   +0x18 u32 time   +0x1C 0
  +0x20 count x {u32 offset (from the data start), u32 size, u32 time, u32 0}
Entries are addressed by index only; size 0 is a hole. A container's entries may be containers.

A numbered pack: u32 count, u32 offsets[count + 1] (in the platform's byte order: big-endian on the GameCube),
each part running to the next offset.

Only reads the player's files. Nothing derived from them is written outside the player's own folders.
"""
import mmap
import struct


class Olnk:
    """A container in a file (or a buffer), read in place."""

    def __init__(self, data, base=0, size=None):
        self.data = data
        self.base = base
        self.size = len(data) - base if size is None else size
        if bytes(data[base + 4:base + 8]) != b"olnk":
            raise ValueError("not an olnk container at %#x" % base)
        self.count, = struct.unpack_from("<I", data, base)
        self.alignment, = struct.unpack_from("<I", data, base + 8)
        self.header_size, self.data_size, self.time = struct.unpack_from("<III", data, base + 0x10)

    @classmethod
    def open(cls, path):
        f = open(path, "rb")
        return cls(mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ))

    def entry(self, index):
        """(absolute offset, size, time) of entry `index`."""
        if not 0 <= index < self.count:
            raise IndexError(index)
        offset, size, time, _ = struct.unpack_from("<IIII", self.data, self.base + 0x20 + index * 16)
        return self.base + self.header_size + offset, size, time

    def bytes(self, index):
        at, size, _ = self.entry(index)
        return bytes(self.data[at:at + size])

    def is_container(self, index):
        at, size, _ = self.entry(index)
        return size >= 0x20 and bytes(self.data[at + 4:at + 8]) == b"olnk"

    def child(self, index):
        at, size, _ = self.entry(index)
        return Olnk(self.data, at, size)

    def entries(self):
        """Every entry's bytes (None for a hole) and every entry's time, for build()."""
        return ([self.bytes(i) if self.entry(i)[1] else None for i in range(self.count)],
                [self.entry(i)[2] for i in range(self.count)])

    def get(self, path):
        """The bytes at a path such as "4/46" (containers on the way down)."""
        parts = [int(p) for p in str(path).strip("/").split("/")]
        node = self
        for p in parts[:-1]:
            node = node.child(p)
        return node.bytes(parts[-1])


def pack_parts(data, big_endian=False):
    """The parts of a numbered pack, or None if `data` is not one."""
    order = ">" if big_endian else "<"
    if len(data) < 8:
        return None
    count, = struct.unpack_from(order + "I", data, 0)
    if count == 0 or count > 4096 or 4 + 4 * (count + 1) > len(data):
        return None
    offsets = struct.unpack_from(order + "%dI" % (count + 1), data, 4)
    if offsets[0] < 4 + 4 * (count + 1) or any(b < a for a, b in zip(offsets, offsets[1:])) or offsets[-1] > len(data):
        return None
    return [data[a:b] for a, b in zip(offsets, offsets[1:])]


def build(entries, alignment=0x800, time=0, times=None):
    """A container of `entries` (bytes, or None for a hole), as the discs lay them out (`times`: each entry's)."""
    count = len(entries)
    header = (0x20 + 16 * count + alignment - 1) // alignment * alignment
    index, body = [], bytearray()
    for e in entries:
        if not e:
            index.append((0, 0))
            continue
        index.append((len(body), len(e)))
        body += e
        body += bytes(-len(body) % alignment)
    out = bytearray(header)
    struct.pack_into("<I4sII", out, 0, count, b"olnk", alignment, 0)
    struct.pack_into("<III", out, 0x10, header, len(body), time)
    for i, (offset, size) in enumerate(index):
        struct.pack_into("<IIII", out, 0x20 + 16 * i, offset, size, times[i] if times else time, 0)
    return bytes(out + body)


def pack_alignment(data):
    """The alignment a little-endian pack's parts start on (its first part's offset: 0x80 or 0x800)."""
    first, = struct.unpack_from("<I", data, 4)
    return first if first in (0x80, 0x800) else 0x80


def build_pack(parts, big_endian=False, alignment=0x80):
    """A numbered pack of `parts`, each starting on `alignment` (as both discs lay them out)."""
    order = ">" if big_endian else "<"
    count = len(parts)
    at = (4 + 4 * (count + 1) + alignment - 1) // alignment * alignment
    offsets, body = [], bytearray()
    for p in parts:
        offsets.append(at + len(body))
        body += p
        body += bytes(-len(body) % alignment)
    offsets.append(at + len(body))
    head = bytearray(at)
    struct.pack_into(order + "I%dI" % (count + 1), head, 0, count, *offsets)
    return bytes(head + body)
