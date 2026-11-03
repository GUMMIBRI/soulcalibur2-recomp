# SPDX-License-Identifier: GPL-3.0-or-later
"""Checks a texture map against a Dolphin pack: each mapped Xbox texture made from the pack by its rule, scaled down
to the Xbox's size, against the Xbox's own pixels. Prints the error per rule (mean absolute difference per channel,
0-255) and the worst textures.

  check_map.py XBOX_ROOT_OLK MAP PACK_FOLDER [SAMPLES]

Needs xxhash, numpy and Pillow.
"""
import os
import random
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "guests"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_map as bm  # noqa: E402
import textures  # noqa: E402


def dds_image(blocks, w, h, fourcc):
    head = bytearray(128)
    head[0:4] = b"DDS "
    struct.pack_into("<IIIIIII", head, 4, 124, 0x81007, h, w, len(blocks), 0, 1)
    struct.pack_into("<II4s", head, 76, 32, 4, fourcc)
    struct.pack_into("<I", head, 108, 0x1000)
    import io
    return Image.open(io.BytesIO(bytes(head) + bytes(blocks))).convert("RGBA")


def xbox_pixels(xd, t):
    """The Xbox texture's RGBA pixels (h, w, 4)."""
    w, h = t.stored
    if t.format == bm.D3D_P8:
        _, _, palette, indices = textures.p8_texture(memoryview(xd)[t.bank:], t.k)
        pal = np.frombuffer(palette, dtype=np.uint8).reshape(256, 4)[:, [2, 1, 0, 3]]
        return pal[np.frombuffer(indices, dtype=np.uint8)].reshape(h, w, 4).astype(int)
    size = (w // 4) * (h // 4) * (8 if t.format == bm.D3D_DXT1 else 16)
    fourcc = {bm.D3D_DXT1: b"DXT1", bm.D3D_DXT3: b"DXT3", bm.D3D_DXT5: b"DXT5"}[t.format]
    return np.asarray(dds_image(xd[t.at:t.at + size], w, h, fourcc)).astype(int)


def made(rule, images, w, h):
    """The texture the importer makes from the pack's images, at the Xbox's size."""
    small = [np.asarray(i.resize((w, h), Image.BOX)).astype(int) for i in images]
    if rule == "copy":
        return small[0]
    if rule == "alpha":
        rgba = small[0].copy()
        rgba[..., 3] = small[1][..., :3].mean(axis=2)
        return rgba
    a, b = small
    return np.stack([a[..., 0], a[..., 3], b[..., 0], b[..., 3]], axis=2)


def main(xbox_path, map_path, pack, samples=400):
    xd = open(xbox_path, "rb").read()
    files = {n[:-4].replace("_arb", ""): n for n in os.listdir(pack) if n.endswith(".dds")}
    textures_by_name = {}
    p = xd.find(b"VXT.")
    while p >= 0:
        try:
            for t in bm.xbox_textures(xd, p):
                name = t.name(xd)
                if name:
                    textures_by_name.setdefault(name, t)
        except struct.error:
            pass
        p = xd.find(b"VXT.", p + 4)
    rows = [line.split() for line in open(map_path) if not line.startswith("#")]
    random.seed(7)
    random.shuffle(rows)
    errors = {}
    for row in rows:
        name, rule = row[0], row[1]
        found = [next((files[a] for a in n.split("|") if a in files), None) for n in row[4:]]
        t = textures_by_name.get(name)
        if None in found or t is None or len(errors.get(rule, [])) >= samples:
            continue
        w, h = (int(v) for v in row[2].split("x"))
        try:
            images = [Image.open(os.path.join(pack, f)).convert("RGBA") for f in found]
            ours, theirs = made(rule, images, w, h), xbox_pixels(xd, t)[:h, :w]
        except Exception as error:  # noqa: BLE001
            print("skipped", name, error)
            continue
        visible = theirs[..., 3:4] > 8 if rule != "copy" else np.ones((h, w, 1), bool)
        diff = np.abs(ours - theirs)
        colour = (diff[..., :3] * visible).sum() / max(1, visible.sum() * 3)
        alpha = diff[..., 3].mean()
        errors.setdefault(rule, []).append((max(colour, alpha), colour, alpha, name, w, h))
    for rule, values in sorted(errors.items()):
        worst = sorted(values, reverse=True)
        median = sorted(v[0] for v in values)[len(values) // 2]
        bad = sum(v[0] > 20 for v in values)
        print("%-8s %4d checked, median error %.1f, %d over 20; worst: %s" % (
            rule, len(values), median, bad, ", ".join("%s %dx%d (rgb %.0f a %.0f)" % (v[3], v[4], v[5], v[1], v[2])
                                                      for v in worst[:4])))


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3], *(int(a) for a in sys.argv[4:5]))
