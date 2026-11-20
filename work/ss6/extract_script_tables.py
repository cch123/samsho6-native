#!/usr/bin/env python3
"""Extract move-script rows (4e2788), action locks (4e5458) and projectile descriptors (4e4b38) from the pinned ELF.

script_rows.bin: 51 headers (u32 original row-base address, u32 row count
including the terminator row), then every character's raw 20-byte rows in order.
The original base addresses are kept because the actor registry r[11] stores
them, and validators compare that word with the Japanese executable.
action_locks.bin: 51 x 8 (s16 ACT, s16 ticks) pairs read by 168c18.
victim_rows.bin: the victim-side table B (4e4a68) in the same layout as
script_rows.bin; 1633c0 stops on byte 0 == 0xff (checked after the id).
depth_rules.bin: 148900's (u8 character, pad, s16 ACT, u8 mode, pad) rows at
4d3d18 through the ACT -1 terminator.
victim_facing_pairs.bin / victim_hold_pairs.bin: the (character, k) byte
pairs read by 168f48 (4e8098) and 169218 (4e8328), through the 0xff byte.
fighter_stubs.bin: 51 x (u32 attack handler 4e8fe8, u32 damage-source
handler 4e97a8, u8 attack form, u8 damage form, u16 0). Form 1 means the
handler is instruction-for-instruction the common stub (163570 -> 163590 /
169810, resp. 165780 -> 1657b0 -> 165a78 / 169810) with only the character
immediate differing; attack form 2 still calls 163570 and tail-calls 163590
but runs character code when the selector has no script (Ukyo, Yumeji ...);
damage form 2 is that stub plus Gaira's branch (1f3be0):
k == 4 without a row tail-calls a character routine instead of 169810;
0 means character-specific code.
"""
import hashlib
import json
import struct
from pathlib import Path
from inspect_iso import Elf

ROOT = Path(__file__).resolve().parents[2]
SOURCE_HASH = '72420e74e04d7ac39119d1b6ec7d70ed004fc98c5035fade96e87d05d4b9ffbf'


def main():
    data = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_HASH, 'Unrecognized original executable'
    elf = Elf(data)
    headers, rows = bytearray(), bytearray()
    counts = []
    for character in range(51):
        base, = struct.unpack_from('<I', data, elf.offset(0x4e2788 + 4*character))
        n = 0
        # 163348 compares the id first and stops on END CODE 0xff (byte +4).
        while True:
            row = data[elf.offset(base + 20*n):elf.offset(base + 20*n) + 20]
            rows += row; n += 1
            if row[4] == 0xff: break
            assert n < 0x1000
        headers += struct.pack('<II', base, n); counts.append(n)
    script = bytes(headers + rows)
    vheaders, vrows = bytearray(), bytearray()
    for character in range(51):
        base, = struct.unpack_from('<I', data, elf.offset(0x4e4a68 + 4*character))
        n = 0
        while True:
            row = data[elf.offset(base + 20*n):elf.offset(base + 20*n) + 20]
            vrows += row; n += 1
            if row[0] == 0xff: break
            assert n < 0x1000
        vheaders += struct.pack('<II', base, n)
    victims = bytes(vheaders + vrows)
    locks = data[elf.offset(0x4e5458):elf.offset(0x4e5458) + 51*32]
    # 163430: 190 twelve-byte projectile descriptors (ids 0x00..0xbd).
    descriptors = data[elf.offset(0x4e4b38):elf.offset(0x4e4b38) + 190*12]
    depth = bytearray()
    for i in range(0x1000):
        row = data[elf.offset(0x4d3d18 + 6*i):elf.offset(0x4d3d18 + 6*i) + 6]
        depth += row
        if struct.unpack_from('<h', row, 2)[0] == -1: break
    def pairs(address):
        out = bytearray()
        for i in range(0x100):
            pair = data[elf.offset(address + 2*i):elf.offset(address + 2*i) + 2]
            out += pair
            if pair[0] == 0xff: return bytes(out)
        raise AssertionError('Unterminated pair table')
    facing, hold = pairs(0x4e8098), pairs(0x4e8328)
    # 14d788's form ACT remaps (14e5d0..14e7e0): s16 rows of (from, to[, companion]) through from == -1.
    # Order: character 1 (23c 0x100000), 0x400000, 0x800000 (triples), characters 22/23/25 (0x100000).
    forms_out = bytearray()
    for address, width in ((0x4d4d50, 2), (0x4d4d88, 2), (0x4d4ea0, 3), (0x4d5928, 2), (0x4d59a0, 2), (0x4d5a08, 2)):
        rows = []
        while True:
            at = elf.offset(address + 2*width*len(rows))
            if struct.unpack_from('<h', data, at)[0] == -1: break
            rows.append(data[at:at + 2*width])
        forms_out += struct.pack('<HH', len(rows), width) + b''.join(rows)
    form_actions = bytes(forms_out)
    def words(address, n):
        return [struct.unpack_from('<I', data, elf.offset(address + 4*k))[0] for k in range(n)]
    def matches(handler, reference, length, immediates, character):
        # Compare whole instruction words; only the listed `addiu rX, zero,
        # character` immediates may differ, and they must equal the character.
        if not handler: return False
        mine, ref = words(handler, length//4), words(reference, length//4)
        for k, (x, y) in enumerate(zip(mine, ref)):
            if k*4 in immediates:
                if (x & 0xffff0000) != (y & 0xffff0000) or (x & 0xffff) != character: return False
            elif x != y: return False
        return True
    def damage_prefix(handler):
        # Damage form 2: the stub still looks the row up with 165780 and starts
        # it with a tail call of 165a78, but runs character code when the row
        # is missing (Gaira 1f3be0 k == 4, Sogetsu 1f7918 k == 0 ...).
        if not handler: return False
        code = words(handler, 0x40)
        jal = 0x0c000000 | (0x165780 >> 2); j = 0x08000000 | (0x165a78 >> 2)
        return jal in code[:12] and j in code
    def script_prefix(handler):
        # Form 2: the handler still looks the selector up with 163570 and
        # starts the script through a tail call of 163590 (j), but its
        # no-script branch is character code (Ukyo 1f1d38, Yumeji 1ff270...).
        if not handler: return False
        code = words(handler, 0x40)
        jal = 0x0c000000 | (0x163570 >> 2); j = 0x08000000 | (0x163590 >> 2)
        return jal in code[:12] and j in code
    # Gaoh's 1fe2f0 / 1fe368 are the reference forms (verified by hand in
    # docs/development-plan.txt). Jumps are absolute and branches relative,
    # so equal words mean equal behaviour.
    attack_forms = ((0x1fe2f0, 0x74, ()), (0x1f7dc0, 0x74, ()))
    stubs = bytearray(); forms = []
    for character in range(51):
        attack = struct.unpack_from('<I', data, elf.offset(0x4e8fe8 + 4*character))[0]
        damage = struct.unpack_from('<I', data, elf.offset(0x4e97a8 + 4*character))[0]
        a = 1 if any(matches(attack, r, n, i, character) for r, n, i in attack_forms) else \
            2 if script_prefix(attack) else 0
        d = 1 if matches(damage, 0x1fe368, 0x98, (0x20, 0x6c), character) else \
            2 if damage_prefix(damage) else 0
        stubs += struct.pack('<IIBBH', attack, damage, a, d, 0); forms.append((a, d))
    # knockdown.cpp transcribes the fall table 4e8c50 (type, armed ACT, back):
    # the 14 rows for damage states 62..73 then 59/60 must match the ELF.
    import re
    source = (ROOT/'src/knockdown.cpp').read_text()
    body = re.search(r'fallRows\[14\]\{(.*?)\};', source, re.S).group(1)
    native = [(int(t), int(act, 0), back == 'true') for t, act, back in
              re.findall(r'\{(\d+),(0x[0-9a-f]+|\d+),(true|false)\}', body)]
    elf_rows = [tuple(words(0x4e8c50 + 12*r, 3)) for r in range(14)]
    assert native == [(t, a, bool(b)) for t, a, b in elf_rows], (native, elf_rows)
    out = []
    for target in (ROOT/'work/ss6/extracted/resources', ROOT/'outputs/ss6-feasibility/native-viewer/assets'):
        if not target.exists(): continue
        (target/'script_rows.bin').write_bytes(script)
        (target/'action_locks.bin').write_bytes(locks)
        (target/'projectile_descriptors.bin').write_bytes(descriptors)
        (target/'victim_rows.bin').write_bytes(victims)
        (target/'depth_rules.bin').write_bytes(depth)
        (target/'victim_facing_pairs.bin').write_bytes(facing)
        (target/'victim_hold_pairs.bin').write_bytes(hold)
        (target/'fighter_stubs.bin').write_bytes(bytes(stubs))
        (target/'form_actions.bin').write_bytes(form_actions)
        out.append(str(target))
    report = dict(elf_sha256=SOURCE_HASH,
                  script_rows=dict(size=len(script), sha256=hashlib.sha256(script).hexdigest(), rows=counts,
                                   source='0x4e2788 pointer table'),
                  action_locks=dict(size=len(locks), sha256=hashlib.sha256(locks).hexdigest(), source='0x4e5458'),
                  victim_rows=dict(size=len(victims), sha256=hashlib.sha256(victims).hexdigest(), source='0x4e4a68 pointer table'),
                  depth_rules=dict(size=len(depth), sha256=hashlib.sha256(depth).hexdigest(), source='0x4d3d18'),
                  victim_facing_pairs=dict(size=len(facing), sha256=hashlib.sha256(facing).hexdigest(), source='0x4e8098'),
                  victim_hold_pairs=dict(size=len(hold), sha256=hashlib.sha256(hold).hexdigest(), source='0x4e8328'),
                  fighter_stubs=dict(size=len(stubs), sha256=hashlib.sha256(stubs).hexdigest(),
                                     generic_attack=[c for c, f in enumerate(forms) if f[0] == 1],
                                     attack_with_character_branch=[c for c, f in enumerate(forms) if f[0] == 2],
                                     generic_damage=[c for c, f in enumerate(forms) if f[1] == 1],
                                     damage_with_character_branch=[c for c, f in enumerate(forms) if f[1] == 2]),
                  form_actions=dict(size=len(form_actions), sha256=hashlib.sha256(form_actions).hexdigest(),
                                    source='4d4d50/4d4d88/4d4ea0/4d5928/4d59a0/4d5a08 (14d788)'),
                  projectile_descriptors=dict(size=len(descriptors), sha256=hashlib.sha256(descriptors).hexdigest(), source='0x4e4b38'),
                  written=out)
    (ROOT/'outputs/ss6-feasibility/script_tables.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'{len(script)} script bytes, {len(locks)} lock bytes')


if __name__ == '__main__':
    main()
