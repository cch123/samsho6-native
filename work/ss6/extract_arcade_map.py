#!/usr/bin/env python3
"""Pin the tables of the arcade MAP scene 1c1b20 and the WALK-IN scene 1c4428.

arcade_map.bin (little endian), in order:
  'AMAP', u32 version
  u32 n, n x float       constants in the order of FLOATS (index = position)
  u32 n, n x double      double immediates of 1c3608 / 1c3888 in the order of DOUBLES
  60 x {double argument, double sine}
                         the argument 1c3608 / 1c3888 / 1c4118 / 1c4230 pass to the C library
                         sine 30bd00 for steps 1..60 and the value it returns. Both columns are
                         captured from the ORIGINAL routine 1c4118 executed in Probe (the four
                         callers use four copies of the same four float constants).
  records (6 x int32: u, v, w, h, +0x10, slot):
      1   backdrop tile 4c6208
      17  clouds: layer 0 (654db0[0..4]), layer 1 (654dd8[0..3]), layer 2 (654dd8[4..6]),
          layer 3 (654db0[5..9])
      1   map picture 4c6598
      11  stage markers 5823b0[stage]       + 11 x int32 x (5823e0), 11 x int32 y (582410)
      11  stage labels 655000[stage]        + 11 x int32 x (655030), 11 x int32 y (655060)
      9   stage name, first sheet 654ef8    + 9 x int32 x (654f20), 9 x int32 y (654f48)
      9   stage name, second sheet 654f70   + 9 x int32 x (654f98), 9 x int32 y (654fc0)
      2   common name parts 4c65b0, 4c6760
  8 x int32              stage-name voices 654ea8 (map)
  11 x int32             stage voices 6551b8 (walk-in)
  12 x float, 12 x float arrival offsets 6550b0 / 6550e0, indexed by gameData+4
  6 x int32[9]           balloon rows 4eeef8 {slot, x, y, u, v, w, h, text x, text y}
  messages (text service 1a3168):
      u32 n, n x {u16 length, bytes}        Shift-JIS strings
      u32 n, n x int32[6]                   lists {balloon id, word +4, 4 x string index or -1}
      2 x { u32 characters, per character: int32 generic[2], int32 pair[51] (list index or -1) }
                                            tables 50d550 (byte 43d052 == 0) and 50d618

Textures are archive members of SAM_DATA.BIN already extracted by extract_resources.py; they are
copied unchanged to the package: map_main (slot 0x29) and map_cloud (slot 0x2a) with the CLUT of
map_main.pal (113980), moji4 / moji5 (slots 0x1e / 0x2b), hukidasi / hukidasi2 (0x1f / 0x20) and
map_icon_00..09 (slot 0x22, bank 0x30).
"""
import hashlib
import json
import shutil
import struct
from pathlib import Path

from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH
from mips_probe import Probe

ROOT = Path(__file__).resolve().parents[2]
RESOURCES = ROOT/'work/ss6/extracted/resources'
PACKAGE = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
NAME = 'arcade_map.bin'
VERSION = 1
TEXTURES = (['map_main.tex', 'map_main.pal', 'map_cloud.tex', 'moji4.tex', 'moji5.tex', 'hukidasi.tex', 'hukidasi2.tex', 'obj0.pal']
            + [f'map_icon_{i:02d}.{ext}' for i in range(10) for ext in ('tex', 'pal')])

# name -> address; the C++ enum ArcadeMapTables::Constant follows this order.
FLOATS = dict(
    InitC=0x654e74, InitD=0x654e78, InitE=0x654e7c,                                   # 1c1f88
    Layer0Step=0x654e80, SpeedUnit=0x654e84, Layer3Y=0x654e88, Word648=0x654e8c,      # 1c2010
    Layer1Y=0x654e90, Layer2Y=0x654e94, Layer1Step=0x654e98, Layer2Step=0x654e9c, Layer3Step=0x654ea0,
    MeshE=0x654ec8, MeshD=0x654ecc, MeshScale=0x655090, MeshEighth=0x655094,          # 1c2920, 1c32c8
    CloudLimit=0x654ed4, CloudZ=0x654ed8, Respawn0=0x654edc, RespawnUnit=0x654ee0,    # 1c2a38
    Respawn1=0x654ee4, CloudLeft=0x654ee8, Respawn2=0x654eec, Respawn3=0x654ef0,
    NameAlphaStep=0x654fe4, NameAlpha=0x654fe8, NameZ=0x654fec,                       # 1c2fe8
    NameCommonX0=0x654ff0, NameCommonY0=0x654ff4, NameCommonX1=0x654ff8, NameCommonY1=0x654ffc,
    PathPi=0x6550a0, PathSteps=0x6550a4, PathHalf=0x6550a8, PathQuarter=0x6550ac,     # 1c3608
    ArrivalPi=0x655110, ArrivalSteps=0x655114, ArrivalHalf=0x655118, ArrivalQuarter=0x65511c,  # 1c3888
    ArrivalScale=0x655120, ArrivalBase=0x655124,
    OpenY0=0x655128, OpenShrink=0x65512c, OpenY1From=0x655130, OpenY1To=0x655134,     # 1c3b78
    OpenY2From=0x655138, OpenY2To=0x65513c, OpenY3From=0x655140, OpenY3To=0x655144,
    CloseY0=0x655148, CloseShrink=0x65514c, CloseY1From=0x655150, CloseY1To=0x655154, # 1c3ec8
    CloseY2From=0x655158, CloseY2To=0x65515c, CloseY3From=0x655160, CloseY3To=0x655164,
    EasePi=0x655168, EaseSteps=0x65516c, EaseHalf=0x655170, EaseQuarter=0x655174,     # 1c4118
    Ease2Pi=0x655178, Ease2Steps=0x65517c, Ease2Half=0x655180, Ease2Quarter=0x655184, # 1c4230
    MapCamera0=0x654df4, MapCamera1=0x654df8, MapCamera2=0x654dfc, MapCamera3=0x654e00, MapCamera4=0x654e04,   # 1c1c30
    RedrawCamera0=0x655188, RedrawCamera1=0x65518c, RedrawCamera2=0x655190, RedrawCamera3=0x655194, RedrawCamera4=0x655198,  # 1c4358
    WalkCamera0=0x6551a0, WalkCamera1=0x6551a4, WalkCamera2=0x6551a8, WalkCamera3=0x6551ac, WalkCamera4=0x6551b0,  # 1c4428
    BalloonZ=0x60a080)                                                                # 1a26b0
# name -> instruction addresses that build the 64-bit immediate (or the address of a literal).
DOUBLES = dict(
    PathA=(0x1c3644, 0x1c365c), PathB=(0x1c3664, 0x1c3668), PathCScale=(0x1c375c, 0x1c3764, 0x1c376c), PathCBase=0x655098,
    PathDScale=(0x1c37bc, 0x1c37c8), PathDBase=(0x1c37cc, 0x1c37d4, 0x1c37dc),
    PathEScale=(0x1c3820, 0x1c382c), PathEBase=(0x1c3830, 0x1c3838, 0x1c3840),
    ArrivalDScale=(0x1c3aa4, 0x1c3aac, 0x1c3ab4), ArrivalDBase=(0x1c3ab8, 0x1c3ac4),
    ArrivalEScale=(0x1c3b08, 0x1c3b10, 0x1c3b18), ArrivalEBase=(0x1c3b1c, 0x1c3b28))
LANGUAGES = ((0x50d550, 49), (0x50d618, 43))
PAIRS = 51


def immediate(word_at, addresses):
    """Evaluates a lui / ori / addiu-from-zero / dsll / dsll32 chain into one register."""
    value = 0; register = None
    for at in addresses:
        word = word_at(at); op, rs, rt, rd, sa, fn = word >> 26, (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31, (word >> 6) & 31, word & 63
        imm = word & 0xffff; signed = imm-0x10000 if imm & 0x8000 else imm
        if op == 0x0f: target, value = rt, (signed << 16) & 0xffffffffffffffff
        elif op == 0x0d: target = rt; assert rs in (0, rt); value = (value if rs else 0) | imm
        elif op == 0x09: target = rt; assert rs == 0; value = signed & 0xffffffffffffffff
        elif op == 0 and fn in (0x38, 0x3c): target = rd; assert rt == rd; value = (value << (sa+(32 if fn == 0x3c else 0))) & 0xffffffffffffffff
        else: raise ValueError(f'unexpected instruction {word:08x} at {at:#x}')
        assert register in (None, target), hex(at); register = target
    return value


def sines(raw):
    """Runs the original 1c4118 for steps 1..60 and records the argument and result of 30bd00."""
    p = Probe(raw, finite_model=True); counter, out = 0x1f00000, 0x1f00010; rows = []
    for step in range(1, 61):
        seen = {}
        def observe(pc):
            if pc == 0x30bd00 and 'arg' not in seen: seen['arg'] = p.registers[4]
            elif pc == 0x1c41d8: seen['sin'] = p.registers[2]
        p.write(counter, step-1, 4)
        p.floats[12] = struct.unpack('<I', struct.pack('<f', 0.0))[0]; p.floats[13] = struct.unpack('<I', struct.pack('<f', 1.0))[0]
        done, _ = p.run(0x1c4118, [counter, out], limit=200000, observe=observe)
        assert p.read(counter, 4) == step and (done & 0xffffffff) == int(step == 60)
        rows.append((seen['arg'] & 0xffffffffffffffff, seen['sin'] & 0xffffffffffffffff))
    assert rows[-1][0] < 0x3f00000000000000 and struct.unpack('<d', struct.pack('<Q', rows[29][1]))[0] > 0.7
    return rows


def build(raw):
    elf = Elf(raw)
    def chunk(at, size):
        offset = elf.offset(at); return raw[offset:offset+size]
    word = lambda at: struct.unpack('<I', chunk(at, 4))[0]
    words = lambda at, count: struct.unpack(f'<{count}i', chunk(at, 4*count))
    pointers = lambda at, count: struct.unpack(f'<{count}I', chunk(at, 4*count))
    floats = lambda at, count: struct.unpack(f'<{count}f', chunk(at, 4*count))
    record = lambda at: words(at, 6)
    # Table bases named by the routines.
    assert word(0x1c287c) == 0x25d16208 and word(0x1c2a78) == 0x25fe4db0 and word(0x1c2bc0) == 0x25f74dd8
    assert word(0x1c2960) == 0x3c0f0133 and word(0x1c29c4) == 0x25cf6598 and word(0x1c2944) == 0x24040029
    assert word(0x1c3200) == 0x256b23b0 and word(0x1c3298) == 0x25ef5000 and word(0x1c3070) == 0x25ef4ef8 and word(0x1c30d8) == 0x25ef4f70
    assert word(0x1c25ec) == 0x25cf4ea8 and word(0x1c457c) == 0x25ef51b8 and word(0x1c3890) == 0x25ef50b0 and word(0x1c38f4) == 0x25ef50e0
    assert word(0x1a2724) == 0x25efeef8 and word(0x1a3188) == 0x25efd550 and word(0x1a31d8) == 0x25efd618
    for copy in (0x6550a0, 0x655110, 0x655168, 0x655178):
        assert chunk(copy, 16) == chunk(0x6550a0, 16), 'the four sine argument constant sets differ'
    out = bytearray(b'AMAP'+struct.pack('<I', VERSION))
    out += struct.pack('<I', len(FLOATS))+b''.join(chunk(at, 4) for at in FLOATS.values())
    doubles = {}
    for name, source in DOUBLES.items():
        bits = struct.unpack('<Q', chunk(source, 8))[0] if isinstance(source, int) else immediate(word, source)
        doubles[name] = struct.unpack('<d', struct.pack('<Q', bits))[0]
    assert list(doubles.values()) == [94.0, 90.0, -0.24199998378753662, 0.7580000162124634, 57.0, 697.0, -46.0, 434.0, 583.0, 1280.0, 526.0, 960.0], doubles
    out += struct.pack('<I', len(doubles))+struct.pack(f'<{len(doubles)}d', *doubles.values())
    table = sines(raw)
    out += b''.join(struct.pack('<QQ', *row) for row in table)

    records = []
    def emit(rec):
        nonlocal out; out += struct.pack('<6i', *rec); records.append(list(rec))
    emit(record(0x4c6208))
    a, b = pointers(0x654db0, 10), pointers(0x654dd8, 7)
    clouds = [*a[:5], *b[:4], *b[4:], *a[5:]]
    for at in clouds:
        rec = record(at); assert rec[5] == 0x2a and rec[4] == 0, rec; emit(rec)
    assert record(0x4c6208)[5] == 0x2a and record(0x4c6598)[:4] == (0, 0, 1024, 819)
    emit(record(0x4c6598))
    for base, xs, ys, count in ((0x5823b0, 0x5823e0, 0x582410, 11), (0x655000, 0x655030, 0x655060, 11),
                                (0x654ef8, 0x654f20, 0x654f48, 9), (0x654f70, 0x654f98, 0x654fc0, 9)):
        table_pointers = pointers(base, count+1)
        assert all(0x4c6000 < at < 0x4c6900 for at in table_pointers[:count]), [hex(v) for v in table_pointers]
        for at in table_pointers[:count]: emit(record(at))
        out += struct.pack(f'<{count}i', *words(xs, count))+struct.pack(f'<{count}i', *words(ys, count))
    assert pointers(0x5823b0, 12)[11] == 0 and pointers(0x655000, 12)[11] == 0   # no marker exists for stage 11
    emit(record(0x4c65b0)); emit(record(0x4c6760))
    out += struct.pack('<8i', *words(0x654ea8, 8))+struct.pack('<11i', *words(0x6551b8, 11))
    out += struct.pack('<12f', *floats(0x6550b0, 12))+struct.pack('<12f', *floats(0x6550e0, 12))
    balloons = [words(0x4eeef8+36*i, 9) for i in range(6)]
    assert balloons[0] == (0,)*9 and [row[0] for row in balloons[1:]] == [0x1f, 0x1f, 0x1f, 0x20, 0x20]
    for row in balloons: out += struct.pack('<9i', *row)

    strings, string_index, lists, list_index, languages = [], {}, [], {}, []
    def string(at):
        if at == 0: return -1
        if at not in string_index:
            offset = elf.offset(at); end = raw.index(b'\0', offset)
            string_index[at] = len(strings); strings.append(raw[offset:end])
        return string_index[at]
    def message(at):
        if at == 0: return -1
        if at not in list_index:
            balloon, extra, *text = words(at, 6)
            assert 1 <= balloon <= 5, (hex(at), balloon)
            list_index[at] = len(lists); lists.append((balloon, extra, *[string(v & 0xffffffff) for v in text]))
        return list_index[at]
    for base, count in LANGUAGES:
        rows = []
        for character, at in enumerate(pointers(base, count)):
            entries = pointers(at+4, 2+PAIRS)
            rows.append([message(v) for v in entries])
        languages.append(rows)
    out += struct.pack('<I', len(strings))+b''.join(struct.pack('<H', len(s))+s for s in strings)
    out += struct.pack('<I', len(lists))+b''.join(struct.pack('<6i', *row) for row in lists)
    for rows in languages:
        out += struct.pack('<I', len(rows))+b''.join(struct.pack(f'<{2+PAIRS}i', *row) for row in rows)
    summary = dict(constants={k: struct.unpack('<f', chunk(a, 4))[0] for k, a in FLOATS.items()}, doubles=doubles,
                   records=len(records), strings=len(strings), message_lists=len(lists),
                   characters=[len(rows) for rows in languages],
                   pair_messages=[sum(v >= 0 for row in rows for v in row[2:]) for rows in languages])
    return bytes(out), summary


def main():
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    data, summary = build(raw)
    target = RESOURCES/NAME; target.write_bytes(data)
    shutil.copyfile(target, PACKAGE/NAME)
    copied = []
    for name in TEXTURES:
        source = RESOURCES/name
        if not (PACKAGE/name).exists() or (PACKAGE/name).read_bytes() != source.read_bytes():
            shutil.copyfile(source, PACKAGE/name); copied.append(name)
    report = dict(elf_sha256=SOURCE_HASH, asset=NAME, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  constant_addresses={k: hex(a) for k, a in FLOATS.items()},
                  double_sources={k: hex(v) if isinstance(v, int) else [hex(a) for a in v] for k, v in DOUBLES.items()},
                  sine_table='argument and result of 30bd00 captured from the original 1c4118 in Probe, steps 1..60',
                  textures={name: hashlib.sha256((RESOURCES/name).read_bytes()).hexdigest() for name in TEXTURES},
                  textures_copied_to_package=copied, **summary)
    (ROOT/'outputs/ss6-feasibility/arcade_map_tables.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'{target} {len(data)} bytes {report["sha256"]} strings={summary["strings"]} lists={summary["message_lists"]} copied={len(copied)}')


if __name__ == '__main__': main()
