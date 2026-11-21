#!/usr/bin/env python3
"""Pin the practice-window strings, the skill-list records and the sword-gauge caps."""
import hashlib
import json
import struct
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH

ROOT = Path(__file__).resolve().parents[2]
NAME = 'practice_mode.bin'
# Pointer tables of the practice menu (address, entries); order = PracticeText group id.
GROUPS = [('rows', 0x59cd70, 12), ('cpu_type', 0x59cda0, 9), ('stand', 0x59cdc8, 10), ('crouch', 0x59cdf0, 9),
          ('jump', 0x59ce18, 5), ('action', 0x59ce30, 32), ('gauge_rows', 0x59ceb0, 6), ('ukemi', 0x59cec8, 4),
          ('off_on', 0x59ced8, 2), ('gauge_long', 0x59cee0, 3), ('gauge_short', 0x59cef0, 3),
          ('items', 0x59cf00, 14), ('key_config', 0x59cfb8, 10)]
# Single strings; order = PracticeText::Misc index.
MISC = [('hyper_slash', 0x664e98), ('combo_slash', 0x664ea8), ('prompt_select', 0x5f2070), ('prompt_title', 0x5f2098),
        ('confirm_caption', 0x665240), ('legend', 0x664d88), ('gauge_format', 0x664d90), ('percent_format', 0x664ee8),
        ('damage', 0x5e1a68), ('total_damage', 0x5e1a80), ('max_damage', 0x5e1a98), ('play_clock', 0x5e9bc0),
        ('rec_clock', 0x5e9bd0), ('action_fallback', 0x664e18)]
SKILLS = 0x4dc1a8      # 15f4e8: 12-byte records, a list starts at id >= 0, continues with -1, table ends at -2
SYSTEMS = 0x50dee0     # 14f220: sword-gauge cap words +0x18/+0x1c/+0x20 of the 40-byte system record
# Switch tables whose case order the native port transcribes; pinned so a different ELF cannot pass silently.
JUMPS = {0x664df0: [0x211090, 0x2110d0, 0x2110e0, 0x2110f0, 0x211100, 0x211110, 0x211130, 0x211138, 0x211140],
         0x664e30: [0x211260, 0x2112b8, 0x2112c4, 0x2112d0, 0x2112dc, 0x2112e8] + [0x211378]*6,
         0x664e60: [0x211378, 0x211378, 0x2113bc, 0x2113cc, 0x2113dc, 0x2113ec, 0x2113fc],
         0x664e7c: [0x2114f0, 0x2114f0, 0x21145c, 0x2114f8, 0x21150c, 0x211520, 0x211534],
         0x664eb4: [0x2115ac, 0x211674, 0x211688, 0x211688, 0x211688, 0x21169c, 0x211754, 0x211754, 0x211768,
                    0x211768, 0x211784, 0x211784],
         0x5f20b4: [0x17f874, 0x17fa40, 0x17fafc, 0x17fb08, 0x17fb90, 0x17fbbc, 0x17fc00, 0x17fc7c, 0x17fde8],
         0x5f20d8: [0x17fe98, 0x17ff10, 0x17ff10, 0x180110, 0x17fec8, 0x1801c0, 0x1801d0, 0x180218, 0x180240],
         0x5eb774: [0x15a540, 0x15a698, 0x15a6b0, 0x15a6bc, 0x15a718, 0x15a724, 0x15a758, 0x15a778, 0x15a7b8, 0x15a7b8,
                    0x15a7b8, 0x15a7e8, 0x15a800, 0x15a91c, 0x15a818, 0x15a818, 0x15a818, 0x15a818, 0x15a818, 0x15a824,
                    0x15a830, 0x15a844, 0x15a864, 0x15a8c4, 0x15a8e0, 0x15a904, 0x15a91c, 0x15a540, 0x15a938, 0x15a938]}
# Static transcription of the dummy ACTION sequence builder 15a428 (prefix switch 15a540..15a948 on skill byte +3).
# It is code, not data: this table documents it for the CPU port and is not read by the native module.
# "emit" appends CPU sequence opcodes to S (+0x14, four words); actor = the dummy, opponent = 1400a8(seat).
ACTION_PREFIX = {
    'before_switch': [
        'S cleared by 15d580, S+4 = a2; actor byte +0xf21 = 0xff when kind == 0x1b else 0',
        'character 3 and technique 0x19: emit 3, 3; if actor+0x1f4 <= 0 also emit 0 (switch skipped)',
        'character 0xb: technique >= 0xc and !(actor+0x23c & 0x400000): emit 0xb9; technique < 0xc and (+0x23c & 0x400000): emit 0xc5 (switch skipped)',
        'character 0x13: (actor+0x23c & 0x800000) and kind not in (6, 7): emit 0xb6 (switch skipped)'],
    'kinds': {
        '0,27': 'repeat = 1',
        '1': 'emit 0x60', '2': 'emit 0x63',
        '3': 'actor+0x194 == 0x170000: nothing; actor+0x178 != 0: emit 0x1a, 0x2c, 0; else emit 0x2b',
        '4': 'emit 0x1b',
        '5': '!(actor+0x23c & 0x200000): emit 0xc2 for character 0x2d, else 0xc9',
        '6': '!(actor+0x23c & 0x800000): emit 0xc5',
        '7': 'actor+0x23c & 0x800000: emit 0x60; else emit 0xc5, 0x60',
        '8,9,10': 'actor byte +0xf15 < kind - 7: emit 0xbc, 0',
        '11': 'actor byte +0xf17 == 0: emit 0xb5',
        '12': 'actor+0x23c & 0x1000: emit 0x0e',
        '13,26': 'actor+0x23c & 0x1000: emit 0x0e; else emit 0x2b',
        '14..18': 'actor byte +0xf18 = kind - 0xd',
        '19': 'actor byte +0xf19 = 0xff',
        '20': 'actor+0x244 |= 0x20000000',
        '21': '!(actor+0x244 & 0x200000): emit 0xb8',
        '22': '!(opponent+0x23c & 0x10): emit 0xff, 0x1b, 0xc5, 0',
        '23': 'opponent+0x23c & 0x10: emit 0x60; else emit 0xff, 0x1b, 0xc5, 0',
        '24': 'emit 0x1b, 0x72',
        '25': 'actor+0x23c & 0x1000: emit 0x0e, 0; else emit 0x1b',
        '28,29': 'repeat = 1; emit 3',
        '>=30': 'no prefix'},
    'after_switch': [
        'only while fewer than four words were emitted',
        't = technique (skill byte +2)',
        'kind 0x1a: t += 2 when the rage state (actor+0x10c+0x14) is 1 or 2',
        'kind 0x1c: v = [actor+4]+0x128; v == 0xe: t = 3; v == 0x11: t = 1; v >= 0xa otherwise: t = -1',
        'kind 0x1d: same v rules; v < 0xa: t += 1 when 140fa0() != 0',
        'emit 0 when t == -1, else 0xb0 + t; then emit 3 when repeat is set and a word is free',
        'S+0xc = S[S+8]'],
    'missing_record': 'S cleared; S+4 = a2; S[0] = AI+0xc0 + 0x8a; S+0xc = S[S+8]',
    'other_codes': {'4..10': 'table 5eb744: 0x70, 0x71, 0x72, 0x73, 0x78, 0x83, 0x84', '15..19': 'table 5eb760: 0x74, 0x75, 0x76, 0x77, 0x79',
                    '21..24,26..29,31..34': 'S[0] = 0xa4 + (code - base) + 4 * direction (0 vertical, 1 forward, 2 back); S[1] = 0'}}

def tables(raw):
    elf = Elf(raw)
    word = lambda at: struct.unpack_from('<I', raw, elf.offset(at))[0]
    def text(at):
        o = elf.offset(at); return raw[o:raw.index(b'\0', o)]
    for at, want in JUMPS.items():
        assert [word(at+4*i) for i in range(len(want))] == want, hex(at)
    strings, index = [], {}
    def intern(s):
        if s not in index: index[s] = len(strings); strings.append(s)
        return index[s]
    groups = [[intern(text(word(at+4*i))) for i in range(n)] for _, at, n in GROUPS]
    groups.append([intern(text(at)) for _, at in MISC])
    skills, at = [], SKILLS
    while struct.unpack_from('<h', raw, elf.offset(at))[0] != -2:
        o = elf.offset(at); name = word(at+8)
        skills.append((raw[o:o+8], intern(text(name)) if name else 0xffffffff)); at += 12
    caps = [[word(SYSTEMS+40*s+o) for o in (0x18, 0x1c, 0x20)] for s in range(9)]
    return strings, groups, skills, caps

def build(raw):
    strings, groups, skills, caps = tables(raw)
    out = bytearray(b'PRC1') + struct.pack('<I', len(strings))
    for s in strings: out += struct.pack('<H', len(s)) + s          # Shift-JIS bytes, verbatim
    out += struct.pack('<I', len(groups))
    for g in groups: out += struct.pack(f'<H{len(g)}H', len(g), *g)
    out += struct.pack('<I', len(skills))
    for head, name in skills: out += head + struct.pack('<I', name)
    for row in caps: out += struct.pack('<3I', *row)
    return bytes(out), strings, groups, skills, caps

def main():
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    data, strings, groups, skills, caps = build(raw)
    assert len(skills) == 833 and strings[groups[0][0]] == b'PRACTICE START' and strings[groups[2][9]] == b''
    for target in (ROOT/'work/ss6/extracted/resources', ROOT/'outputs/ss6-feasibility/native-viewer/assets'):
        (target/NAME).write_bytes(data)
    lists = sorted({struct.unpack_from('<h', h)[0] for h, _ in skills} - {-1})
    report = dict(elf_sha256=SOURCE_HASH, asset=NAME, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  strings=len(strings), encoding='shift_jis',
                  groups={name: dict(address=hex(at), entries=n) for name, at, n in GROUPS},
                  misc={name: hex(at) for name, at in MISC},
                  skill_table=dict(address=hex(SKILLS), records=len(skills), record_bytes=12, list_ids=lists,
                                   fields='+0 id (h), +2 technique, +3 prefix kind, +4 type, +8 name pointer'),
                  sword_caps=dict(address=hex(SYSTEMS), systems=caps),
                  pinned_jump_tables=[hex(a) for a in JUMPS], action_prefix_15a428=ACTION_PREFIX)
    (ROOT/'outputs/ss6-feasibility/practice_mode_tables.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('groups', 'misc')}, indent=1)[:900])

if __name__ == '__main__':main()
