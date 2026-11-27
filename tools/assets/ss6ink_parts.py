"""Assemble the Haohmaru preview pack with weapons/effects from the local game."""
import argparse
import hashlib
import os
import struct
import tempfile
from functools import lru_cache
from pathlib import Path

from ss6sprite import Sheet


@lru_cache(maxsize=65536)
def sample(centre, horizontal, vertical, diagonal):
    # A 2x texel centre lies a quarter pixel from the nearest stock texel in
    # each direction. Preserve coverage independently from the two CLUT colours.
    weights = {}
    for index, weight in ((centre, 9), (horizontal, 3), (vertical, 3), (diagonal, 1)):
        if index:
            weights[index] = weights.get(index, 0) + weight
    if not weights:
        return 0, 0
    ranked = sorted(weights, key=weights.get, reverse=True)
    first = ranked[0]
    second = ranked[1] if len(ranked) > 1 else first
    mix = round(15 * weights[second] / (weights[first] + weights[second])) if first != second else 0
    coverage = round(15 * sum(weights.values()) / 16)
    return first + 16 * second, 16 * coverage + mix


def doubled_group(pixels, width, height, left, top):
    group = bytearray()
    visible = False
    for y in range(top, top + 32):
        row = y // 2 * width
        adjacent = min(height - 1, max(0, y // 2 + (1 if y % 2 else -1))) * width
        for x in range(left, left + 32):
            col = x // 2
            neighbour = min(width - 1, max(0, col + (1 if x % 2 else -1)))
            pair = sample(pixels[row + col], pixels[row + neighbour],
                          pixels[adjacent + col], pixels[adjacent + neighbour])
            group.extend(pair)
            visible |= bool(pair[1] >> 4)
    return b'\x01' + group if visible else b'\x00'


def assemble(assets, art, output):
    digest = hashlib.sha256(Path(__file__).read_bytes())
    for path in (art, *(assets / f'{kind}_00.bin' for kind in ('idx', 'map', 'chr'))):
        digest.update(path.read_bytes())
    target = output / 'haohmaru_actions.ink'
    stamp = output / 'haohmaru_actions.sha256'
    fingerprint = digest.hexdigest()
    if target.is_file() and stamp.exists() and stamp.read_text() == fingerprint:
        return
    pack = bytearray(art.read_bytes())
    if pack[:4] != b'INK1':
        raise ValueError(f'Unexpected ink body pack: {art}')
    count, = struct.unpack_from('<I', pack, 4)
    sheet = Sheet(assets, 0)
    for number, bank, offset in sheet.images():
        # These bank-zero records are scattered particles and gourd fragments.
        # Their negative space is part of the effect, so keep the source silhouette.
        if bank == 0 and number not in (533, 534, 535, 744, 745, 746, 747):
            continue
        width, height, pixels = sheet.pixels(offset)
        pack.extend(struct.pack('<HBB', number, width // 16, height // 16))
        for top in range(0, height * 2, 32):
            for left in range(0, width * 2, 32):
                pack.extend(doubled_group(pixels, width, height, left, top))
        count += 1
    struct.pack_into('<I', pack, 4, count)
    output.mkdir(parents=True, exist_ok=True)
    # A second launcher can start while the first is preparing its local cache.
    with tempfile.NamedTemporaryFile(dir=output, delete=False) as tmp:
        tmp.write(pack)
    os.replace(tmp.name, target)
    stamp.write_text(fingerprint)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('assets', 'art', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    assemble(args.assets, args.art, args.output)
