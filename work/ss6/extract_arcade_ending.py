#!/usr/bin/env python3
"""Turn the 50 compiled ending scripts (pointer table 4eefe8) into a data script.

Every script function is straight-line code: no branch instruction exists between its prologue and
its return. The decoder below walks each function with a constant tracker for the handful of
instruction forms the compiler emitted (anything else is an error) and writes one record per
primitive call, plus one record per inline store into the eight scene objects at 4ef0d0.
work/ss6/validate_arcade_ending.py executes every original script function with the primitives
intercepted and requires the same record sequence, so this static decoding is not trusted alone.

Asset arcade_ending.bin (little endian):
  'AED1', u32 version
  u32 scripts (50), u32 records, u32 string bytes
  scripts x { u32 first record, u32 record count, u32 function address }
  records x { u32 opcode, u32 argument[6] }      floats as IEEE bits, strings as pool offsets,
                                                 scene objects as their index 0..7
  string pool: NUL terminated Shift-JIS, verbatim
  f32 portrait[14]     60a050..60a084 (1a22a8 / 1a2380 quads, balloon depth 60a080 / 60a084)
  f32 background[6]    652ae8..652afc (1a4c20)
  f32 flash[3]         5dd584..5dd58c (113b28)
  i32 balloon[6][9]    4eeef8 (1a26b0)
  i32 pictures[12][2]  50e0b0: {ed_bg file number, half} for background ids 0x64..0x6f
  u32 default glyph colours: 112f30 arguments of 182858 (0xffffff, 0x404040)
  f32 object scale     5df3ac, stored at object+0x70 by 1202e8
"""
import hashlib
import json
import shutil
import struct
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH

ROOT = Path(__file__).resolve().parents[2]
NAME = 'arcade_ending.bin'
TABLE, SCRIPTS, END = 0x4eefe8, 50, 0x1a0ad8
OBJECTS, OBJECT_SIZE = 0x4ef0d0, 0x138
# Opcode order is the asset contract (src/arcade_ending.hpp EndingOp).
# Signature letters: i integer register, f float register, o scene object pointer, s string pointer.
PRIMITIVES = [
    (0x1a4a98, 'background', 'i'), (0x1a1878, 'backgroundSwitch', 'i'),
    (0x122e98, 'camera', 'fff'), (0x122eb8, 'cameraOffset', 'fff'),
    (0x120378, 'objectStart', 'oiiiii'), (0x120390, 'objectAction', 'oi'), (0x120428, 'objectVelocity', 'oii'),
    (0x120438, 'objectColour', 'oiiiii'), (0x1a18a8, 'objectPalette', 'i'),
    (0x1e7c00, 'music', 'ii'), (0x1e7b70, 'sound', 'ii'), (0x1a1728, 'cameraDelta', 'ii'),
    (0x1a1740, 'wait', 'i'), (0x1a1780, 'waitB', 'i'), (0x112f30, 'textColours', 'ii'), (0x1a18e0, 'portrait', 'ii'),
    (0x1a1aa8, 'messageClear', ''), (0x1a1ad8, 'messageAdd', 's'), (0x1a1b00, 'messageShow', 'i'),
    (0x1a17e8, 'fadeIn', 'ii'), (0x1a1830, 'fadeOut', 'ii'), (0x1a17c0, 'flash', 'ii'),
    (0x1a1e98, 'rollClear', ''), (0x1a1ea8, 'rollAdd', 's'), (0x1a1fe8, 'rollShow', 'i'), (0x1a1ed0, 'rollScroll', 'i'),
    (0x117108, 'fadeWrite', 'ii'), (0x1170c8, 'fadeMode', 'i'), (0x117180, 'fadeRange', 'iii'),
    (0x1174b8, 'paletteBake', 'ii'), (0x117438, 'paletteSave', ''),
]
STORE = len(PRIMITIVES)    # pseudo opcode: object index, field offset, value
NAMES = [p[1] for p in PRIMITIVES]+['objectStore']
BY_ADDRESS = {p[0]: (i, p[2]) for i, p in enumerate(PRIMITIVES)}
INT_ARGS, FLOAT_ARGS = (4, 5, 6, 7, 8, 9), (12, 13, 14)
SAVED = set(range(16, 24))|{30}
TEXTURES = ['hukidasi.tex', 'hukidasi.pal', 'hukidasi2.tex', 'hukidasi2.pal']+[f'{k}_99a.bin' for k in ('aid', 'idx', 'act', 'pil', 'jdg', 'chr', 'map')]


def signed16(v): return v-0x10000 if v & 0x8000 else v


class Reader:
    def __init__(self, raw):
        self.raw = raw; self.elf = Elf(raw)
    def chunk(self, at, size):
        o = self.elf.offset(at); return self.raw[o:o+size]
    def word(self, at): return struct.unpack('<I', self.chunk(at, 4))[0]
    def words(self, at, n): return struct.unpack(f'<{n}i', self.chunk(at, 4*n))
    def floats(self, at, n): return struct.unpack(f'<{n}f', self.chunk(at, 4*n))
    def string(self, at):
        o = self.elf.offset(at); return self.raw[o:self.raw.index(b'\0', o)]


def decode(reader, start, end):
    """Records of one script function as (opcode, [arguments]); arguments are ints, ('f', bits) or ('s', address)."""
    reg, freg, out = {0: 0}, {}, []
    def step(pc):
        w = reader.word(pc); op, rs, rt, rd, fn = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31, w & 63
        imm = w & 0xffff
        if w == 0: return
        if op == 0x0f: reg[rt] = imm << 16
        elif op == 0x09:
            if rs == 29 and rt == 29: return
            reg[rt] = (reg[rs]+signed16(imm)) & 0xffffffff if rs in reg else None
        elif op == 0x0d: reg[rt] = reg[rs] | imm if rs in reg else None
        elif op == 0 and fn in (0x21, 0x25, 0x2d) and (rt == 0 or rs == 0):
            src = rs if rt == 0 else rt; reg[rd] = reg.get(src)
        elif op == 0x31:      # lwc1
            if rs == 29: freg.pop(rt, None)        # epilogue restore
            else: freg[rt] = reader.word((reg[rs]+signed16(imm)) & 0xffffffff)
        elif op == 0x11 and rs == 4 and rt == 0: freg[rd] = 0                 # mtc1 zero
        elif op == 0x11 and rs == 0x10 and fn == 6: freg[(w >> 6) & 31] = freg[rd]  # mov.s fd, fs
        elif op in (0x3f, 0x39) and rs == 29: return                           # sd / swc1 to the frame
        elif op == 0x37 and rs == 29: reg.pop(rt, None)                        # ld from the frame
        elif op == 0x2b:      # sw into a scene object
            at = (reg[rs]+signed16(imm)) & 0xffffffff
            assert OBJECTS <= at < OBJECTS+8*OBJECT_SIZE, hex(pc)
            out.append((STORE, [(at-OBJECTS)//OBJECT_SIZE, (at-OBJECTS) % OBJECT_SIZE, reg[rt]]))
        else: raise ValueError(f'unsupported instruction {w:08x} at {pc:#x}')
        if reg.get(rt, 0) is None and op in (0x09, 0x0d): raise ValueError(f'untracked register at {pc:#x}')
    pc = start
    while True:
        assert pc < end, hex(start)
        w = reader.word(pc); op = w >> 26
        if op in (2, 3):
            target = (w & 0x3ffffff) << 2
            step(pc+4)
            code, signature = BY_ADDRESS[target]
            args, ints, floats = [], iter(INT_ARGS), iter(FLOAT_ARGS)
            for kind in signature:
                if kind == 'f': args.append(('f', freg[next(floats)]))
                else:
                    value = reg[next(ints)]; assert value is not None, hex(pc)
                    if kind == 'o':
                        assert (value-OBJECTS) % OBJECT_SIZE == 0 and 0 <= (value-OBJECTS)//OBJECT_SIZE < 8, hex(pc)
                        value = (value-OBJECTS)//OBJECT_SIZE
                    args.append(('s', value) if kind == 's' else value)
            out.append((code, args))
            for r in list(reg):
                if r and r not in SAVED: del reg[r]
            for f in list(freg):
                if f < 20: del freg[f]
            pc += 8
            if op == 2: break           # tail call: the primitive returns to 182a98
        elif w == 0x03e00008:
            break                       # jr ra
        else:
            step(pc); pc += 4
    return out


def build(raw):
    reader = Reader(raw)
    table = reader.words(TABLE, SCRIPTS)
    assert sorted(table) == list(table) and reader.word(0x182b8c) == 0x25ceefe8   # addiu t6,t6,-0x1018 in 182a98
    pool, offsets, records, directory, summary = bytearray(), {}, [], [], []
    def intern(address):
        if address not in offsets:
            text = reader.string(address); text.decode('cp932')
            offsets[address] = len(pool); pool.extend(text+b'\0')
        return offsets[address]
    for index, start in enumerate(table):
        end = table[index+1] if index+1 < SCRIPTS else END
        ops = decode(reader, start, end)
        directory.append((len(records), len(ops), start))
        for code, args in ops:
            words = []
            for a in args:
                if isinstance(a, tuple): words.append(a[1] if a[0] == 'f' else intern(a[1]))
                else: words.append(a & 0xffffffff)
            records.append(struct.pack('<7I', code, *(words+[0]*(6-len(words)))))
        used = lambda name: [a for code, a in ops if NAMES[code] == name]
        summary.append(dict(index=index, address=hex(start), records=len(ops),
                            music=[a[0] for a in used('music')],
                            backgrounds=[a[0] for a in used('background')+used('backgroundSwitch')],
                            portraits=sorted({a[1] & 0xffffffff for a in used('portrait')}),
                            pages=len(used('messageShow')),
                            actions=sorted({a[1]*32+(a[2] & 31) for a in used('objectStart')})))
    pictures = []
    for i in range(12):
        name, half = reader.words(0x50e0b0+8*i, 2)
        text = reader.string(name).decode('ascii'); assert text.startswith('ed_bg') and half in (0, 1)
        pictures.append((int(text[5:]), half))
    balloons = reader.words(0x4eeef8, 54)
    data = b'AED1'+struct.pack('<4I', 1, SCRIPTS, len(records), len(pool))
    data += b''.join(struct.pack('<3I', *d) for d in directory)+b''.join(records)+bytes(pool)
    data += b'\0'*(-len(data) % 4)
    data += struct.pack('<14f', *reader.floats(0x60a050, 14))+struct.pack('<6f', *reader.floats(0x652ae8, 6))
    data += struct.pack('<3f', *reader.floats(0x5dd584, 3))+struct.pack('<54i', *balloons)
    data += b''.join(struct.pack('<2i', *p) for p in pictures)
    # 182858: 112f30(0xffffff, 0x404040) -- lui a0,0xff; ori a0,0xffff; lui a1,0x40; ori a1,0x4040.
    assert reader.word(0x1828b0) == 0x3484ffff and reader.word(0x1828b4) == 0x34a54040
    data += struct.pack('<2I', 0xffffff, 0x404040)
    assert reader.word(0x120300) == 0x25eff3ac   # addiu t7,t7,-0xc54 in 1202e8
    data += struct.pack('<f', *reader.floats(0x5df3ac, 1))
    return data, dict(scripts=summary, pictures=pictures, opcodes=NAMES, strings=len(offsets),
                      records_by_opcode={NAMES[i]: sum(1 for r in records if struct.unpack_from('<I', r)[0] == i) for i in range(len(NAMES))})


def resources(summary):
    """Disc members the scripts name: ed_bg pictures (two 640x480 halves each) and demo portraits."""
    used = set()
    for script in summary['scripts']:
        for n in script['backgrounds']:
            if 0xc <= n < 0x64: used.add((n-0xc)//2+1)
            elif n >= 0x64: used.add(summary['pictures'][n-0x64][0])
    portraits = sorted({p for s in summary['scripts'] for p in s['portraits'] if p < 0x31})
    return sorted(used), portraits


def main():
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    data, summary = build(raw)
    source = ROOT/'work/ss6/extracted/resources'
    (source/NAME).write_bytes(data)
    assets = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
    shutil.copyfile(source/NAME, assets/NAME)
    pictures, portraits = resources(summary)
    members = TEXTURES+[f'ed_bg{n:02d}.{e}' for n in pictures for e in ('tex', 'pal')]+[f'demo_{n:02d}.{e}' for n in portraits for e in ('tex', 'pal')]
    missing = [m for m in members if not (source/m).exists()]
    assert not missing, missing
    hashes = {}
    for m in members:
        if not (assets/m).exists() or (assets/m).stat().st_size != (source/m).stat().st_size: shutil.copyfile(source/m, assets/m)
        hashes[m] = hashlib.sha256((assets/m).read_bytes()).hexdigest()
    # The picture table 50e0b0 also names ed_bg19 (ids 0x68 / 0x69). SAM_DATA.BIN has no such member.
    archive = json.loads((ROOT/'outputs/ss6-feasibility/resource_manifest.json').read_text())
    names = {e['name'] for e in archive['entries']}
    table_only = sorted({n for n, _ in summary['pictures']}-set(pictures))
    absent = [n for n, _ in summary['pictures'] if f'ed_bg{n:02d}.tex' not in names]
    report = dict(elf_sha256=SOURCE_HASH, asset=NAME, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  pictures_used=pictures, portraits_used=portraits, picture_table_numbers_unused_by_scripts=table_only,
                  picture_table_numbers_absent_from_SAM_DATA=sorted(set(absent)), resources=hashes, **summary)
    (ROOT/'outputs/ss6-feasibility/arcade_ending_tables.json').write_text(json.dumps(report, indent=1, ensure_ascii=False)+'\n')
    print(json.dumps({k: report[k] for k in ('asset', 'bytes', 'sha256', 'strings', 'records_by_opcode', 'pictures_used', 'portraits_used',
                                             'picture_table_numbers_unused_by_scripts', 'picture_table_numbers_absent_from_SAM_DATA')}, indent=1))


if __name__ == '__main__':main()
