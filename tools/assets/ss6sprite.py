#!/usr/bin/env python3
"""Export a fighter's sprite images to indexed PNG and import edited ones.

A fighter resource NN stores its pictures in three files:

  idx_NN.bin  one 32-bit word per image: bits 0..23 offset into map, bits
              24..28 palette bank, ffffffff for an unused image number
  map_NN.bin  per image: width and height in 8-pixel tiles (one byte each,
              both even), then width*height 3-byte tile numbers stored as
              2x2 groups, groups in row order
  chr_NN.bin  8x8 tiles, 4 bits per pixel, low nibble first; tile 0 is empty

Colours come from pal_all.bin, shared by all fighters: 16-colour groups of
16-bit A1R5G5B5 entries, group number (palette key * 32 + bank), where the stock key
is resource * 5 + colour choice. Entry 0 of every group is transparent.

  ss6sprite.py export --assets ASSETS --resource 0 -o art/haohmaru
  ss6sprite.py import art/haohmaru --assets ASSETS -o mods/my-mod

`import` leaves every unedited image exactly as it is in the original files.
An edited image gets new tiles appended to chr and a new record appended to
map, so nothing else that refers to the old data changes. Standard library
only.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ss6tex  # noqa: E402

FORMAT = 'ss6-sprite/1'
TILE_BYTES = 32
GROUP_BYTES = 32            # one 16-colour palette group in pal_all.bin
UNUSED = 0xffffffff
MAX_TILES = 1 << 20         # tile numbers are 20 bits
MAX_MAP_OFFSET = 1 << 24    # idx keeps 24 bits of offset


class SpriteError(Exception):
    pass


def resource_file(assets: Path, kind: str, resource: int) -> Path:
    return assets / f'{kind}_{resource:02}.bin'


class Sheet:
    """idx/map/chr of one resource, plus the shared palette arena."""

    def __init__(self, assets: Path, resource: int):
        self.resource = resource
        self.idx = bytearray(resource_file(assets, 'idx', resource).read_bytes())
        self.map = bytearray(resource_file(assets, 'map', resource).read_bytes())
        self.chr = bytearray(resource_file(assets, 'chr', resource).read_bytes())
        self.pal = bytearray((assets / 'pal_all.bin').read_bytes())
        if len(self.idx) % 4 or len(self.chr) % TILE_BYTES:
            raise SpriteError(f'resource {resource:02} has an unexpected idx or chr size')

    def images(self):
        """Yields (image number, palette bank, map offset) for every used image."""
        for number, (entry,) in enumerate(struct.iter_unpack('<I', self.idx)):
            if entry != UNUSED:
                yield number, (entry >> 24) & 31, entry & 0xffffff

    def size(self, offset: int) -> tuple[int, int]:
        width, height = self.map[offset], self.map[offset + 1]
        if not width or not height or width & 1 or height & 1:
            raise SpriteError(f'image record at map offset {offset:#x} has unsupported size {width}x{height} tiles')
        if offset + 2 + width * height * 3 > len(self.map):
            raise SpriteError(f'image record at map offset {offset:#x} runs past the end of the map')
        return width, height

    def pixels(self, offset: int) -> tuple[int, int, bytes]:
        """Returns (pixel width, pixel height, one palette index per pixel)."""
        width, height = self.size(offset)
        out = bytearray(width * 8 * height * 8)
        stride = width * 8
        for group in range(width * height // 4):
            cell_x, cell_y = group % (width // 2) * 16, group // (width // 2) * 16
            for part in range(4):
                at = offset + 2 + (group * 4 + part) * 3
                tile = int.from_bytes(self.map[at:at + 3], 'little') & 0xfffff
                if not tile:
                    continue
                if (tile + 1) * TILE_BYTES > len(self.chr):
                    raise SpriteError(f'tile {tile} is outside chr_{self.resource:02}.bin')
                data = self.chr[tile * TILE_BYTES:(tile + 1) * TILE_BYTES]
                left, top = cell_x + (part % 2) * 8, cell_y + (part // 2) * 8
                for y in range(8):
                    row = (top + y) * stride + left
                    for half in range(4):
                        byte = data[y * 4 + half]
                        out[row + half * 2] = byte & 15
                        out[row + half * 2 + 1] = byte >> 4
        return width * 8, height * 8, bytes(out)

    def group_offset(self, key: int, bank: int) -> int:
        offset = (key * 32 + bank) * GROUP_BYTES
        if offset + GROUP_BYTES > len(self.pal):
            raise SpriteError(f'palette key {key} bank {bank} is outside pal_all.bin; '
                              'pass --palette-key for a resource without stock colours')
        return offset

    def colours(self, key: int, bank: int) -> list[int]:
        offset = self.group_offset(key, bank)
        return [value for (value,) in struct.iter_unpack('<H', self.pal[offset:offset + GROUP_BYTES])]


def to_rgba(value: int, index: int) -> tuple[int, int, int, int]:
    # Unlike the .pal files, this arena keeps red in the high bits (A1 R5 G5 B5).
    channels = [(value >> shift) & 31 for shift in (10, 5, 0)]
    # The runtime clears entry 0 of a group when it loads it.
    alpha = 255 if (value & 0x8000) and index else 0
    return (*[(c << 3) | (c >> 2) for c in channels], alpha)


def to_colour(rgba: tuple[int, int, int, int]) -> int:
    r, g, b, a = rgba
    return (b >> 3) | ((g >> 3) << 5) | ((r >> 3) << 10) | (0x8000 if a >= 128 else 0)


def export(assets: Path, resource: int, out: Path, colour: int = 0, key: int | None = None) -> dict:
    sheet = Sheet(assets, resource)
    key = resource * 5 + colour if key is None else key
    out.mkdir(parents=True, exist_ok=True)
    listing, skipped = [], []
    for number, bank, offset in sheet.images():
        try:
            width, height, pixels = sheet.pixels(offset)
        except SpriteError as error:
            # The runtime rejects such a record too; it is left for whole-file replacement.
            skipped.append({'image': number, 'reason': str(error)})
            print(f'skipped image {number}: {error}', file=sys.stderr)
            continue
        name = f'{number:04}.png'
        palette = [to_rgba(value, index) for index, value in enumerate(sheet.colours(key, bank))]
        ss6tex.write_png(out / name, width, height, pixels, palette)
        listing.append({'image': number, 'file': name, 'bank': bank, 'width': width, 'height': height})
    meta = {'format': FORMAT, 'resource': resource, 'palette_key': key, 'images': listing, 'skipped': skipped}
    (out / 'sprites.json').write_text(json.dumps(meta, indent=1) + '\n')
    return meta


def encode_tiles(width: int, height: int, pixels: bytes) -> list[bytes]:
    """Splits an image into 8x8 tiles in the map's storage order (2x2 groups)."""
    tiles = []
    for group in range((width // 16) * (height // 16)):
        cell_x, cell_y = group % (width // 16) * 16, group // (width // 16) * 16
        for part in range(4):
            left, top = cell_x + (part % 2) * 8, cell_y + (part // 2) * 8
            tile = bytearray(TILE_BYTES)
            for y in range(8):
                row = (top + y) * width + left
                for half in range(4):
                    tile[y * 4 + half] = pixels[row + half * 2] | (pixels[row + half * 2 + 1] << 4)
            tiles.append(bytes(tile))
    return tiles


def import_sheet(source: Path, assets: Path, out: Path, rebuild_all: bool = False) -> list[Path]:
    meta = json.loads((source / 'sprites.json').read_text())
    if meta.get('format') != FORMAT:
        raise SpriteError(f'{source / "sprites.json"} has unsupported format {meta.get("format")!r}')
    resource, key = meta['resource'], meta['palette_key']
    sheet = Sheet(assets, resource)
    records = {number: (bank, offset) for number, bank, offset in sheet.images()}
    known = {}
    for tile in range(len(sheet.chr) // TILE_BYTES):
        known.setdefault(bytes(sheet.chr[tile * TILE_BYTES:(tile + 1) * TILE_BYTES]), tile)
    empty = bytes(TILE_BYTES)
    edited_groups: dict[int, tuple[list[int], str]] = {}
    images_changed = palettes_changed = 0
    for item in meta['images']:
        number, name = item['image'], item['file']
        if number not in records:
            raise SpriteError(f'{name}: image {number} is unused in resource {resource:02}')
        bank, offset = records[number]
        width, height, pixels, palette = ss6tex.read_png(source / name)
        if width % 16 or height % 16 or not width or not height or width > 254 * 8 or height > 254 * 8:
            raise SpriteError(f'{name}: {width}x{height} is not a multiple of 16 pixels within 2032x2032')
        if max(pixels) > 15:
            raise SpriteError(f'{name}: uses palette index {max(pixels)}; a sprite has 16 colours (0..15)')

        # Palette: compare at the stored 15-bit precision, entry 0 excluded.
        original = sheet.colours(key, bank)
        wanted = [original[0]] + [to_colour(c) for c in (palette + [(0, 0, 0, 0)] * 16)[1:16]]
        shown = [original[0]] + [to_colour(to_rgba(v, i)) for i, v in enumerate(original)][1:]
        if wanted != shown:
            previous = edited_groups.get(bank)
            if previous and previous[0] != wanted:
                raise SpriteError(f'{name} and {previous[1]} both use palette bank {bank} but their palettes differ; '
                                  'images of one bank share one palette')
            edited_groups[bank] = (wanted, name)

        if not rebuild_all and (width, height, pixels) == sheet.pixels(offset):
            continue
        record = bytearray((width // 8, height // 8))
        for tile in encode_tiles(width, height, pixels):
            if tile == empty:
                index = 0
            else:
                index = known.get(tile)
                if index is None:
                    index = len(sheet.chr) // TILE_BYTES
                    if index >= MAX_TILES:
                        raise SpriteError('chr would exceed the 20-bit tile number range')
                    sheet.chr += tile
                    known[tile] = index
            record += index.to_bytes(3, 'little')
        if len(sheet.map) >= MAX_MAP_OFFSET:
            raise SpriteError('map would exceed the 24-bit offset range')
        entry = struct.unpack_from('<I', sheet.idx, number * 4)[0]
        struct.pack_into('<I', sheet.idx, number * 4, (entry & 0xff000000) | len(sheet.map))
        sheet.map += record
        images_changed += 1

    for bank, (wanted, _) in edited_groups.items():
        struct.pack_into('<16H', sheet.pal, sheet.group_offset(key, bank), *wanted)
        palettes_changed += 1

    out.mkdir(parents=True, exist_ok=True)
    written = []
    if images_changed:
        for kind, data in (('idx', sheet.idx), ('map', sheet.map), ('chr', sheet.chr)):
            target = resource_file(out, kind, resource)
            target.write_bytes(data)
            written.append(target)
    if palettes_changed:
        # pal_all.bin is one file for every fighter. Start from the copy already
        # in the output directory so that several imports accumulate.
        target = out / 'pal_all.bin'
        if target.exists():
            merged = bytearray(target.read_bytes())
            for bank in edited_groups:
                offset = sheet.group_offset(key, bank)
                merged[offset:offset + GROUP_BYTES] = sheet.pal[offset:offset + GROUP_BYTES]
            sheet.pal = merged
        target.write_bytes(sheet.pal)
        written.append(target)
    print(f'{images_changed} images and {palettes_changed} palette banks changed', file=sys.stderr)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    e = commands.add_parser('export', help='resource -> one indexed PNG per image + sprites.json')
    e.add_argument('--assets', type=Path, required=True, help='base asset directory')
    e.add_argument('--resource', type=int, required=True, help='fighter resource number, e.g. 0 for Haohmaru')
    e.add_argument('--colour', type=int, default=0, choices=range(5), help='stock colour choice shown in the PNGs')
    e.add_argument('--palette-key', type=int, help='palette key, overriding resource * 5 + colour')
    e.add_argument('-o', '--output', type=Path, required=True)
    i = commands.add_parser('import', help='edited PNG directory -> idx/map/chr (and pal_all.bin) for a mod')
    i.add_argument('source', type=Path, help='directory written by export')
    i.add_argument('--assets', type=Path, required=True, help='base asset directory the export came from')
    i.add_argument('-o', '--output', type=Path, required=True, help='mod directory')
    i.add_argument('--rebuild-all', action='store_true', help='re-encode every image, not only edited ones')
    args = parser.parse_args(argv)
    try:
        if args.command == 'export':
            meta = export(args.assets, args.resource, args.output, args.colour, args.palette_key)
            print(f'{len(meta["images"])} images -> {args.output}')
        else:
            for path in import_sheet(args.source, args.assets, args.output, args.rebuild_all):
                print(path)
    except (SpriteError, ss6tex.TexError, OSError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
