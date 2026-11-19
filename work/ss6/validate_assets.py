#!/usr/bin/env python3
"""Structural checks and an independent pixel comparison for the native probe."""
import argparse
import hashlib
import json
import struct
import subprocess
import zlib
from pathlib import Path


def png(path, width, height, pixels):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    scanlines = b''.join(b'\0' + pixels[y*width*4:(y+1)*width*4] for y in range(height))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(scanlines)) + chunk(b'IEND', b''))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    resources = args.root / 'work/ss6/extracted/resources'
    output = args.root / 'outputs/ss6-feasibility'
    checks = []
    for path in sorted(resources.glob('map_*.bin')):
        ident = path.stem[4:]
        maps = path.read_bytes()
        tiles = (resources / f'chr_{ident}.bin').read_bytes()
        indices = (resources / f'idx_{ident}.bin').read_bytes()
        cursor, offsets, odd, errors = 0, set(), [], []
        while cursor + 2 <= len(maps):
            w, h = maps[cursor:cursor+2]
            end = cursor + 2 + w*h*3
            if not w or not h or end > len(maps):
                errors.append(f'Invalid map at {cursor}')
                break
            if w % 2 or h % 2:
                # Dimensions are structurally valid, but the probe deliberately
                # does not guess how an incomplete 2x2 group is traversed.
                odd.append(dict(offset=cursor, width_tiles=w, height_tiles=h))
            offsets.add(cursor)
            for pos in range(cursor+2, end, 3):
                tile = int.from_bytes(maps[pos:pos+3], 'little')
                if tile*32 + 32 > len(tiles):
                    errors.append(f'Tile out of bounds at {pos}')
            cursor = end
        if cursor != len(maps):
            errors.append('Map data not fully consumed')
        if len(indices) % 4 or len(tiles) % 32:
            errors.append('Misaligned index/tile file')
        values = [v for v, in struct.iter_unpack('<I', indices)]
        for index, value in enumerate(values):
            if value != 0xffffffff and value & 0xffffff not in offsets:
                errors.append(f'Index {index} does not point to a map boundary')
        checks.append(dict(resource_id=ident, map_records=len(offsets), map_bytes=len(maps),
                           tile_count=len(tiles)//32, index_slots=len(values),
                           odd_maps_not_supported_by_probe=odd, errors=errors))
    (output / 'structure_checks.json').write_text(json.dumps(checks, indent=2) + '\n')
    assert not any(item['errors'] for item in checks), 'Resource structure validation failed'

    maps = (resources / 'map_00.bin').read_bytes()
    tiles = (resources / 'chr_00.bin').read_bytes()
    indices = struct.unpack('<2048I', (resources / 'idx_00.bin').read_bytes())
    words = struct.unpack('<16H', (resources / 'pal_all.bin').read_bytes()[:32])
    colors = [bytes((((c>>10)&31)*255//31, ((c>>5)&31)*255//31, (c&31)*255//31, 255 if c&0x8000 else 0)) for c in words]
    supported = [i for i,v in enumerate(indices) if v>>24 == 0 and (v != 0 or i == 0)]
    selected = sorted(set(supported[:8] + [supported[i*(len(supported)-1)//15] for i in range(16)]))
    native = output / 'native-viewer/ss6-viewer'
    scratch = args.root / 'work/ss6/native_pixels.rgba'
    pixel_checks = []
    for index in selected:
        offset = indices[index]
        tw, th = maps[offset:offset+2]
        width, height = tw*8, th*8
        expected = bytearray()
        # Iterate pixels rather than the C++ decoder's tile groups. This checks
        # the native integration against the independently explored layout.
        for y in range(height):
            for x in range(width):
                tx, ty = x//8, y//8
                slot = (ty//2)*tw*2 + (tx//2)*4 + (ty%2)*2 + tx%2
                tile = int.from_bytes(maps[offset+2+slot*3:offset+5+slot*3], 'little')
                packed = tiles[tile*32+(y%8)*4+(x%8)//2]
                expected.extend(colors[(packed >> ((x%2)*4)) & 15])
        subprocess.run([str(native), '--frame', str(index), '--dump', str(scratch)], check=True)
        actual = scratch.read_bytes()
        assert struct.unpack('<II', actual[:8]) == (width,height)
        assert actual[8:] == expected, f'Native decode mismatch at index {index}'
        pixel_checks.append(dict(index=index, width=width, height=height,
                                 rgba_sha256=hashlib.sha256(expected).hexdigest()))
        if index == 0:
            png(output / 'haohmaru-first-cell.png', width, height, expected)
    report = dict(character_resource_sets=len(checks), map_records=sum(c['map_records'] for c in checks),
                  structural_errors=0, odd_map_records=sum(len(c['odd_maps_not_supported_by_probe']) for c in checks),
                  native_pixel_comparisons=len(pixel_checks), all_native_pixel_comparisons_passed=True,
                  limitation='Pixel checks compare two decoders, not emulator or real-hardware output; gameplay equivalence remains unverified.',
                  pixel_checks=pixel_checks)
    (output / 'validation_summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k:v for k,v in report.items() if k!='pixel_checks'}, indent=2))


if __name__ == '__main__':
    main()
