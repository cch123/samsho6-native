#!/usr/bin/env python3
"""Convert the game's indexed textures to and from PNG.

Texture files (.tex) are headerless: width*height 8-bit palette indices,
optionally followed by a 256-entry 32-bit palette. Separate palette files
(.pal) hold 256 entries of 16 bits (512 bytes) or 32 bits (1024 bytes).
Nothing in the files records the dimensions or the palette order, so `decode`
writes them to a JSON sidecar next to the PNG and `encode` reads them back.

  ss6tex.py decode bg_title00.tex -o out/bg_title00.png
  ss6tex.py encode out/bg_title00.png -o mods/demo/
  ss6tex.py verify outputs/ss6-feasibility/native-viewer/assets

The PNG stays indexed. Edit it with a tool that preserves the palette and the
index of every colour (Aseprite, GraphicsGale, GIMP in indexed mode); the game
selects palette entries by number, and several screens swap palettes at run
time. Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

SIDECAR_FORMAT = 'ss6-tex/1'
PALETTE_ENTRIES = 256


class TexError(Exception):
    pass


# ---- palette ---------------------------------------------------------------

def csm1(index: int) -> int:
    """GS CSM1 CLUT fetch order: logical index bits 3 and 4 are exchanged."""
    return (index & ~0x18) | ((index & 8) << 1) | ((index & 0x10) >> 1)


def decode_palette(raw: bytes, order: str) -> tuple[list[tuple[int, int, int, int]], int, str]:
    """Returns (RGBA8 entries in logical index order, bits per entry, alpha mode)."""
    if len(raw) == PALETTE_ENTRIES * 2:
        bits, alpha_mode, stored = 16, 'bit', []
        for (value,) in struct.iter_unpack('<H', raw):
            # A1 B5 G5 R5. Five-bit channels are widened by bit replication so
            # that narrowing with >>3 restores the stored value exactly.
            channels = [(value >> shift) & 31 for shift in (0, 5, 10)]
            stored.append((*[(c << 3) | (c >> 2) for c in channels], 255 if value & 0x8000 else 0))
    elif len(raw) == PALETTE_ENTRIES * 4:
        bits = 32
        entries = list(struct.iter_unpack('<4B', raw))
        # GS alpha is 0..0x80 with 0x80 opaque. Doubling shows correctly in
        # image editors and is reversible; palettes that use the upper half
        # of the byte keep it verbatim instead.
        alpha_mode = 'ps2' if all(a <= 0x80 for *_, a in entries) else 'raw'
        stored = [(r, g, b, min(255, a * 2) if alpha_mode == 'ps2' else a) for r, g, b, a in entries]
    else:
        raise TexError(f'palette must be 512 or 1024 bytes, got {len(raw)}')
    if order == 'csm1':
        stored = [stored[csm1(i)] for i in range(PALETTE_ENTRIES)]
    return stored, bits, alpha_mode


def encode_palette(entries: list[tuple[int, int, int, int]], bits: int, order: str, alpha_mode: str) -> bytes:
    entries = (entries + [(0, 0, 0, 0)] * PALETTE_ENTRIES)[:PALETTE_ENTRIES]
    if order == 'csm1':  # the exchange is its own inverse
        entries = [entries[csm1(i)] for i in range(PALETTE_ENTRIES)]
    out = bytearray()
    for r, g, b, a in entries:
        if bits == 16:
            out += struct.pack('<H', (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10) | (0x8000 if a >= 128 else 0))
        else:
            if alpha_mode == 'ps2':
                a = 0x80 if a == 255 else a // 2
            out += bytes((r, g, b, a))
    return bytes(out)


# ---- PNG (indexed only) ----------------------------------------------------

PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


def write_png(path: Path, width: int, height: int, indices: bytes, palette: list[tuple[int, int, int, int]]) -> None:
    rows = b''.join(b'\0' + indices[y * width:(y + 1) * width] for y in range(height))
    alpha = bytes(a for *_, a in palette)
    data = PNG_SIGNATURE + _chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 3, 0, 0, 0))
    data += _chunk(b'PLTE', b''.join(bytes(e[:3]) for e in palette))
    if any(a != 255 for a in alpha):
        data += _chunk(b'tRNS', alpha)
    data += _chunk(b'IDAT', zlib.compress(rows, 9)) + _chunk(b'IEND', b'')
    path.write_bytes(data)


def read_png(path: Path) -> tuple[int, int, bytes, list[tuple[int, int, int, int]]]:
    data = path.read_bytes()
    if data[:8] != PNG_SIGNATURE:
        raise TexError(f'{path} is not a PNG file')
    position, header, plte, trns, idat = 8, None, None, b'', bytearray()
    while position < len(data):
        length, kind = struct.unpack('>I4s', data[position:position + 8])
        body = data[position + 8:position + 8 + length]
        position += 12 + length
        if kind == b'IHDR':
            header = struct.unpack('>IIBBBBB', body)
        elif kind == b'PLTE':
            plte = body
        elif kind == b'tRNS':
            trns = body
        elif kind == b'IDAT':
            idat += body
    if header is None:
        raise TexError(f'{path} has no IHDR chunk')
    width, height, depth, colour, _, _, interlace = header
    if colour != 3 or plte is None:
        raise TexError(f'{path} is not an indexed (palette) PNG. Re-export it in indexed colour mode; '
                       'the game addresses palette entries by number, so true-colour images cannot be imported')
    if interlace:
        raise TexError(f'{path} is interlaced; save it without interlacing')
    stride = (width * depth + 7) // 8
    raw = zlib.decompress(bytes(idat))
    if len(raw) != height * (stride + 1):
        raise TexError(f'{path} has an unexpected amount of pixel data')
    packed, previous = bytearray(), bytearray(stride)
    for y in range(height):
        kind, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        # Indexed PNG has one byte per filter unit at every bit depth.
        for x in range(stride):
            left = line[x - 1] if x else 0
            up, upper_left = previous[x], previous[x - 1] if x else 0
            if kind == 1:
                line[x] = (line[x] + left) & 255
            elif kind == 2:
                line[x] = (line[x] + up) & 255
            elif kind == 3:
                line[x] = (line[x] + (left + up) // 2) & 255
            elif kind == 4:
                estimate = left + up - upper_left
                distances = (abs(estimate - left), abs(estimate - up), abs(estimate - upper_left))
                line[x] = (line[x] + (left, up, upper_left)[distances.index(min(distances))]) & 255
            elif kind != 0:
                raise TexError(f'{path} uses unknown PNG filter {kind}')
        packed += line
        previous = line
    if depth == 8:
        indices = bytes(packed)
    else:  # editors store images with few colours at 1, 2 or 4 bits per index
        indices, mask = bytearray(), (1 << depth) - 1
        for y in range(height):
            row = packed[y * stride:(y + 1) * stride]
            indices += bytes((row[(x * depth) // 8] >> (8 - depth - (x * depth) % 8)) & mask for x in range(width))
        indices = bytes(indices)
    alpha = trns + b'\xff' * (len(plte) // 3 - len(trns))
    palette = [(plte[i * 3], plte[i * 3 + 1], plte[i * 3 + 2], alpha[i]) for i in range(len(plte) // 3)]
    return width, height, indices, palette


# ---- texture layout --------------------------------------------------------

def _is_power_of_two(value: int) -> bool:
    return value > 0 and value & (value - 1) == 0


def guess_layout(size: int, width: int | None) -> tuple[int, int, bool]:
    """Returns (width, height, has embedded palette) for a .tex of `size` bytes."""
    for embedded in (False, True):
        pixels = size - (PALETTE_ENTRIES * 4 if embedded else 0)
        if pixels <= 0:
            continue
        if width:
            if pixels % width == 0:
                return width, pixels // width, embedded
            continue
        if not _is_power_of_two(pixels):
            continue
        exponent = pixels.bit_length() - 1
        # Square when possible; otherwise twice as wide as tall. Pass --width
        # for a page laid out differently.
        return 1 << ((exponent + 1) // 2), 1 << (exponent // 2), embedded
    raise TexError(f'cannot infer dimensions for {size} bytes; pass --width')


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode(tex_path: Path, png_path: Path, pal_path: Path | None = None, width: int | None = None,
           order: str | None = None) -> dict:
    tex = tex_path.read_bytes()
    w, h, embedded = guess_layout(len(tex), width)
    indices = tex[:w * h]
    if pal_path is None and not embedded:
        candidate = tex_path.with_suffix('.pal')
        pal_path = candidate if candidate.exists() else None
    if embedded and pal_path is None:
        source, raw = 'embedded', tex[w * h:]
        # An appended CLUT is normally uploaded as one 16x16 block and fetched
        # in CSM1 order; separate palette files keep linear order.
        order = order or 'csm1'
    elif pal_path is not None:
        source, raw, order = 'file', pal_path.read_bytes(), order or 'linear'
    else:
        source, raw, order = 'none', b'', 'linear'
    meta = {'format': SIDECAR_FORMAT, 'texture': tex_path.name, 'width': w, 'height': h,
            'texture_sha256': sha256(tex), 'embedded_palette': embedded,
            'palette': {'source': source, 'order': order}}
    if source == 'none':
        palette = [(i, i, i, 255) for i in range(PALETTE_ENTRIES)]  # preview ramp only
    else:
        palette, bits, alpha_mode = decode_palette(raw, order)
        meta['palette'].update(bits=bits, alpha=alpha_mode)
        if source == 'file':
            meta['palette'].update(file=pal_path.name, sha256=sha256(raw))
    if embedded and source != 'embedded':
        # The appended palette is not the one shown; keep it so encode can restore the file.
        meta['embedded_palette_hex'] = tex[w * h:].hex()
    png_path.parent.mkdir(parents=True, exist_ok=True)
    write_png(png_path, w, h, indices, palette)
    sidecar(png_path).write_text(json.dumps(meta, indent=2) + '\n')
    return meta


def sidecar(png_path: Path) -> Path:
    return png_path.with_name(png_path.name + '.json')


def encode(png_path: Path, out_dir: Path) -> list[Path]:
    meta_path = sidecar(png_path)
    if not meta_path.exists():
        raise TexError(f'missing {meta_path.name}; it is written by `decode` and records the layout')
    meta = json.loads(meta_path.read_text())
    if meta.get('format') != SIDECAR_FORMAT:
        raise TexError(f'{meta_path} has unsupported format {meta.get("format")!r}')
    width, height, indices, palette = read_png(png_path)
    if (width, height) != (meta['width'], meta['height']):
        print(f'warning: {png_path.name} is {width}x{height} but the original is '
              f'{meta["width"]}x{meta["height"]}; loaders check the original size', file=sys.stderr)
    pal = meta['palette']
    tex, written = bytearray(indices), []
    out_dir.mkdir(parents=True, exist_ok=True)
    if pal['source'] == 'embedded':
        tex += encode_palette(palette, pal['bits'], pal['order'], pal['alpha'])
    elif meta.get('embedded_palette'):
        tex += bytes.fromhex(meta['embedded_palette_hex'])
    if pal['source'] == 'file':
        target = out_dir / pal['file']
        target.write_bytes(encode_palette(palette, pal['bits'], pal['order'], pal['alpha']))
        written.append(target)
    target = out_dir / meta['texture']
    target.write_bytes(bytes(tex))
    return [target, *written]


def verify(directory: Path, scratch: Path) -> int:
    """Decodes and re-encodes every texture and requires identical bytes."""
    failures = checked = 0
    for tex_path in sorted(directory.glob('*.tex')):
        try:
            png = scratch / 'png' / (tex_path.stem + '.png')
            meta = decode(tex_path, png)
            outputs = encode(png, scratch / 'out')
            for produced in outputs:
                if produced.read_bytes() != (directory / produced.name).read_bytes():
                    raise TexError(f'{produced.name} differs after a round trip')
            checked += 1
            for produced in (png, sidecar(png), *outputs):
                produced.unlink()
        except (TexError, OSError, zlib.error) as error:
            failures += 1
            print(f'FAIL {tex_path.name}: {error}')
    print(f'{checked} textures round-tripped byte-identically, {failures} failed')
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    d = commands.add_parser('decode', help='texture (+ palette) -> indexed PNG + JSON sidecar')
    d.add_argument('tex', type=Path)
    d.add_argument('-o', '--output', type=Path, required=True, help='PNG file to write')
    d.add_argument('--pal', type=Path, help='palette file (default: same name with .pal, or the embedded one)')
    d.add_argument('--width', type=int, help='texture width when it cannot be inferred from the size')
    d.add_argument('--order', choices=('linear', 'csm1'), help='palette entry order (default: csm1 if embedded)')
    e = commands.add_parser('encode', help='indexed PNG + sidecar -> texture (+ palette)')
    e.add_argument('png', type=Path)
    e.add_argument('-o', '--output', type=Path, required=True, help='directory for the .tex/.pal, e.g. a mod folder')
    v = commands.add_parser('verify', help='round-trip every .tex in a directory and compare bytes')
    v.add_argument('directory', type=Path)
    v.add_argument('--scratch', type=Path, required=True, help='empty directory for intermediate files')
    args = parser.parse_args(argv)
    try:
        if args.command == 'decode':
            meta = decode(args.tex, args.output, args.pal, args.width, args.order)
            print(f'{args.output}  {meta["width"]}x{meta["height"]}  palette: {meta["palette"]["source"]}')
        elif args.command == 'encode':
            for path in encode(args.png, args.output):
                print(path)
        else:
            return verify(args.directory, args.scratch)
    except TexError as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
