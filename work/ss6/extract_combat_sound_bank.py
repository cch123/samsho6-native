#!/usr/bin/env python3
"""Copy the Japanese versus banks directly from their ISO9660 extents."""
from fighter_roster import PLAYABLE, SELECTABLE
import argparse
from hashlib import sha256
from pathlib import Path
import struct

from inspect_iso import Iso

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'work/ss6/extracted/resources/combat_sound_bank.bin'
ISO = Path('/Users/xargin/Downloads/ps2/Samurai Spirits - Tenka-ichi Kenkakuden (Japan).iso')
ELF_SHA = '72420e74e04d7ac39119d1b6ec7d70ed004fc98c5035fade96e87d05d4b9ffbf'
# 213270 loads the three MSH tables. 212dd8 uses 0x250/0x110 byte rows,
# 213180 uses 0x210, and 1e7e20 loads BVOICE2[50] into common sound RAM.
GROUPS = [
    ('BVOICE2', 50, 0x250), ('BVOICE2', 0, 0x250), ('BVOICE1', 0, 0x110),
    ('BVOICE1', 49, 0x110), ('NAL', 0, 0x210), ('NAL', 1, 0x210),
]
MAGIC = b'S6ADPCM1'


def extract(iso, groups=GROUPS):
    if sha256(iso.read('/SLPS_255.59')).hexdigest() != ELF_SHA:
        raise ValueError('Unsupported game revision')
    parts = [MAGIC]
    for name, index, stride in groups:
        header = iso.read(f'/VOICE/{name}.MSH')[index * stride:(index + 1) * stride]
        sector, count, size, reserved = struct.unpack_from('<4I', header)
        body = iso.by_path[f'/VOICE/{name}.MSB']
        if (len(header) != stride or reserved or not 0 < count <= (stride - 16) // 8
                or size % 64 or sector * iso.block + size > body['size']):
            raise ValueError(f'Invalid bank directory for {name}[{index}]')
        data = iso.read_at((body['lba'] + sector) * iso.block, size)
        next_offset = 0
        for tone in range(count):
            size_and_volume, offset = struct.unpack_from('<2I', header, 16 + 8 * tone)
            length = size_and_volume >> 16 if name == 'BVOICE2' else size_and_volume
            if not length or length % 16 or offset != next_offset or offset + length > size:
                raise ValueError(f'Invalid sample extent for {name}[{index}][{tone}]')
            # An already aligned entry still has an entire 64-byte guard after it.
            next_offset = (offset + length + 64) & ~63
        if next_offset != size:
            raise ValueError(f'Invalid group end for {name}[{index}]')
        # Preserve the original directory, alignment gaps, terminating blocks and
        # physical SPU sample bytes. Only the six selected groups are packaged.
        parts.extend((header, data))
    return b''.join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('iso', type=Path, nargs='?', default=ISO)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    data = extract(Iso(args.iso))
    args.output.write_bytes(data)
    # 128180 installs menu banks 51/52 in the player slots. The face-off
    # announces each chosen fighter from the final two BVOICE1 lines.
    iso=Iso(args.iso)
    for name,index,stride in [('BVOICE2',i,0x250) for i in (*(c for c in SELECTABLE if c),51,52)]+[('BVOICE1',i,0x110) for i in (*range(1,43),*range(44,49))]:
        group=extract(iso,[(name,index,stride)])[len(MAGIC):]
        stem='vs_sounds' if name=='BVOICE2' else 'vs_voice'
        (args.output.parent/f'{stem}_{index:02}.bin').write_bytes(group)
    print(f'{len(data)} bytes, SHA-256 {sha256(data).hexdigest()}')


if __name__ == '__main__':
    main()
