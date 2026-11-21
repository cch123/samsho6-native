#!/usr/bin/env python3
"""Pin the OPTION MODE label, value and help-text tables of SLPS-25559."""
import hashlib
import json
import shutil
import struct
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH

ROOT = Path(__file__).resolve().parents[2]
NAME = 'console_option.bin'

# (group name, pointer-table address, entries) or (group name, [string addresses]).
# The group order is the enum ConsoleOptionTables::Group.
GROUPS = [
    ('top_label', 0x656d98, 5), ('top_help', 0x582c40, 5, 'help'),
    # 1d0f18 takes rows 0..12 from 657358 and draws 657398 / 657350 below them.
    ('game_label', [('table', 0x657358, 13), 0x657398, 0x657350]), ('game_help', 0x582d10, 15, 'help'),
    ('game_time', 0x6573d0, 3), ('game_mode', 0x6573f8, 2), ('cpu_match_point', 0x657478, 15),
    ('spirits_1p', 0x6574c8, 3), ('spirits_2p', 0x6574e8, 3),
    ('game_format', [0x6573a8, 0x6574d8, 0x6574e0]),
    ('sound_label', [('table', 0x658fd0, 4), 0x658fb8, 0x658fc8]), ('sound_help', 0x583000, 6, 'help'),
    ('sound_output', 0x659000, 2), ('sound_bgm', 0x659030, 2), ('sound_voice', 0x659048, 2),
    ('sound_format', [0x659008, 0x659010]),
    ('save_label', 0x6578f0, 4), ('save_help', 0x582df8, 4, 'help'), ('auto_save', 0x657910, 2),
]
HELP_ORDER = ['top_help', 'game_help', 'sound_help', 'save_help']
# 1d21a0 (1.0, 3.0), 1dc0e0 commit, 1dc2b0 revert and 1b8bc0 unpack volume factors.
SCALARS = [0x657534, 0x657538, 0x658e08, 0x658e0c, 0x658e38, 0x658e3c, 0x6546a8, 0x6546ac]

def build(raw):
    elf = Elf(raw)
    word = lambda at: struct.unpack_from('<I', raw, elf.offset(at))[0]
    def text(at):
        start = elf.offset(at)
        return raw[start:raw.index(b'\0', start)]
    groups, flags, manifest = [], {}, {}
    for group in GROUPS:
        name = group[0]
        if isinstance(group[1], list):
            addresses = []
            for item in group[1]:
                addresses += [word(item[1]+4*i) for i in range(item[2])] if isinstance(item, tuple) else [item]
        elif len(group) == 4:
            # Help tables hold {char* text; int scroll} pairs.
            addresses = [word(group[1]+8*i) for i in range(group[2])]
            flags[name] = [word(group[1]+8*i+4) for i in range(group[2])]
            assert all(f in (0, 1) for f in flags[name])
        else:
            addresses = [word(group[1]+4*i) for i in range(group[2])]
        groups.append([text(a) for a in addresses])
        manifest[name] = dict(source=hex(group[1]) if isinstance(group[1], int) else 'literal addresses',
                              strings=[hex(a) for a in addresses])
    colours = [word(0x657240+4*i) for i in range(15)]+[word(0x658f70+4*i) for i in range(6)]
    # 1d0840 reads the factory MIKIRI and KYOUCHI gauges from 50d858+c4 / +b4.
    gauges = [raw[elf.offset(0x50d91c)], raw[elf.offset(0x50d90c)]]
    # 1dbee8 restores the mixer word with the immediate at 1dbefc.
    assert word(0x1dbefc) == 0x240d3fff
    data = bytearray(b'OPTN'+struct.pack('<IH', 1, len(groups)))
    for strings in groups:
        data += struct.pack('<H', len(strings))
        for s in strings:data += struct.pack('<H', len(s))+s
    for name in HELP_ORDER:data += bytes(flags[name])
    data += struct.pack('<21I', *colours)+bytes(gauges)+struct.pack('<I', word(0x1dbefc)&0xffff)
    data += b''.join(raw[elf.offset(a):elf.offset(a)+4] for a in SCALARS)
    return bytes(data), groups, manifest, flags

def main():
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    data, groups, manifest, flags = build(raw)
    assert groups[0][0] == b'GAME OPTION' and groups[2][13] == b'DEFAULT SETTING' and groups[12] == [b'STEREO', b'MONAURAL']
    target = ROOT/'work/ss6/extracted/resources'/NAME
    target.write_bytes(data)
    shutil.copyfile(target, ROOT/'outputs/ss6-feasibility/native-viewer/assets'/NAME)
    report = dict(elf_sha256=SOURCE_HASH, asset=NAME, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  encoding='Shift-JIS bytes verbatim', groups=manifest, help_scroll_flags=flags,
                  colour_tables=['0x657240', '0x658f70'], gauge_defaults=['0x50d91c', '0x50d90c'],
                  mixer_default_instruction='0x1dbefc', scalar_addresses=list(map(hex, SCALARS)),
                  strings=sum(map(len, groups)))
    (ROOT/'outputs/ss6-feasibility/console_option_tables.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('groups',)}, indent=2))

if __name__ == '__main__':main()
