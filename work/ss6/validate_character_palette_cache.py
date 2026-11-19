#!/usr/bin/env python3
"""Compare every ordinary character palette cache slot through the original renderer."""
import hashlib
import json
import struct
import subprocess
from collections import Counter
from pathlib import Path

from character_tiles_oracle import ASSETS, ATLAS, ROOT, begin, bits, fixture
from validate_character_tiles import BIN, SOURCE_HASH, digest

CACHE = 0x439A48
SLOTS = 24
EMPTY = 0xFFFFFFFF
PHYSICAL = (*range(16, 32), *range(12, 16), *range(8, 12))
IMAGE = 409
PALETTES = 0x3F8A40


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def layouts():
    yield "fully-used", None, None
    yield "fully-reserved", None, None
    for slot in range(SLOTS):
        other = (slot + 1) % SLOTS
        yield "reuse-over-empty", slot, slot
        yield "reserved-match-refused", slot, None
        yield "reserved-match-fallback", slot, other
        yield "evict-unused", slot, slot
        yield "empty-before-unused", slot, slot


def cache_rows(kind, slot, tag):
    keys = [0x20000 + i for i in range(SLOTS)]
    used = [1] * SLOTS
    reserved = [0] * SLOTS
    if kind == "fully-reserved":
        keys = [EMPTY] * SLOTS
        used = [0] * SLOTS
        reserved = [1] * SLOTS
    elif slot is not None:
        other = (slot + 1) % SLOTS
        if kind == "reuse-over-empty":
            keys[other] = EMPTY
            keys[slot] = tag
            used[slot] = 0
        elif kind.startswith("reserved-match"):
            keys[slot] = tag
            reserved[slot] = 1
            used[slot] = 0
            if kind == "reserved-match-fallback":
                keys[other] = EMPTY
        elif kind == "evict-unused":
            used[slot] = 0
        elif kind == "empty-before-unused":
            keys[slot] = EMPTY
            used[other] = 0
    return keys, used, reserved


def compare_native(commands, expected):
    result = subprocess.run(
        [str(BIN), str(ASSETS)], input="\n".join(commands) + "\n",
        check=True, capture_output=True, text=True)
    lines = result.stdout.splitlines()
    assert len(lines) == len(expected), (len(lines), len(expected))
    for line, (label, original) in zip(lines, expected):
        native = list(map(int, line.split()))
        assert native == original, (label, len(native), len(original), [
            (i, x, y) for i, (x, y) in enumerate(zip(native, original)) if x != y
        ][:8])


def main():
    elf = ROOT / "work/ss6/extracted/SLPS_255.59"
    assert sha(elf) == SOURCE_HASH
    pins = {str(f.name): sha(f) for f in (
        Path(__file__), BIN, ASSETS/"idx_51.bin", ASSETS/"pal_all.bin",
        Path(__file__).with_name("character_tiles_oracle.py"),
        Path(__file__).with_name("validate_character_tiles.py"),
        Path(__file__).with_name("mips_probe.py"))}
    probe = fixture()
    commands = ["render 0 0 0 0"]
    expected = []
    cases = Counter()
    calls = Counter()
    instructions = 0
    packets = 0
    source_mutations = 0
    idx = struct.unpack_from("<I", (ASSETS / "idx_51.bin").read_bytes(), 4 * IMAGE)[0]
    bank = (idx >> 24) & 31
    assert idx != EMPTY and bank == 25

    def seed_color(op, base, index, value, size):
        probe.write(base + size * index, value, size)
        commands.append(f"{op} {index} {value}")

    for i in range(1024):
        seed_color("raw16", 0x43AB70, i, (i * 253 + 0x128F) & 0xFFFF, 2)
        seed_color("raw32", 0x43B370, i, 0xFF003311 + i, 4)
        seed_color("format", 0x439B70, i, 1, 4)

    for index, (kind, slot, target) in enumerate(layouts()):
        label = (kind, slot)
        cases[kind] += 1
        # Distinct source palettes make an accidental copy on a cache hit observable.
        key = index
        logical = key * 32 + bank
        tag = logical + 0x10000
        source_at = PALETTES + logical * 32
        first_color = probe.read(source_at, 2)
        rows = cache_rows(kind, slot, tag)
        for row, values in enumerate(rows):
            for i, value in enumerate(values):
                probe.write(CACHE + 4 * (row * SLOTS + i), value, 4)
                commands.append(f"cache {row} {i} {value}")
        begin(probe, index)
        commands.append(f"begin {index} 0 0")
        floats = list(map(bits, (280.125, 210.75, -10, 1, 1)))
        words = [2, key, IMAGE, 0x10, 0, *floats, 1, 0xFF808080, 0, EMPTY, 0, bits(.25)]
        commands.append("sprite " + " ".join(map(str, words)))
        probe.floats[12:17] = floats
        for a, value in zip((0x479244, 0x3DB900, 0x47923C, 0x479240, 0x348B10, 0x1239D8C), words[10:]):
            probe.write(a, value, 4)

        quads = []
        def observe(pc):
            if pc == 0x115D40:
                calls["palette_resolver"] += 1
            elif pc == 0x108910:
                ptr = probe.registers[4]
                assert probe.registers[5] == 4
                quads.append([*struct.unpack_from("<24I", probe.memory, ptr),
                              probe.registers[6] & 0xFFFFFFFF, probe.read(0x3A8E44, 4),
                              probe.read(0x348B10, 4)])

        _, count = probe.run(0x121B80, words[:5], limit=800000, observe=observe)
        instructions += count
        packets += len(quads)
        assert bool(quads) == (target is not None), label
        if target is not None:
            assert {q[24] & 255 for q in quads} == {PHYSICAL[target]}, label
            rows[0][target] = tag
            rows[1][target] = 1
        for row, values in enumerate(rows):
            actual = struct.unpack_from("<24I", probe.memory, CACHE + 4 * row * SLOTS)
            assert list(actual) == values, (label, row)
        # Hits re-use resident colors. Only a fresh allocation clears the source's
        # first color, even when the same key is already resident in a reserved slot.
        allocates = target is not None and kind != "reuse-over-empty"
        assert probe.read(source_at, 2) == (0 if allocates else first_color), label
        source_mutations += int(allocates and first_color != 0)
        snapshot = [probe.read(a, 4) for a in (0x3EB910, 0x3DB8F8, 0x3DB900, 0x3A8E44)]
        snapshot.extend(digest(values) for values in rows)
        for base, fmt in ((0x43AB70, "H"), (0x43B370, "I"), (0x439B70, "I"), (0x11E7980, "I")):
            snapshot.append(digest(struct.unpack_from("<1024" + fmt, probe.memory, base)))
        snapshot.extend([digest(probe.memory[PALETTES:0x439A40]),
                         digest(probe.memory[ATLAS:ATLAS + 131072]), len(quads)])
        snapshot.extend(word for quad in quads for word in quad)
        expected.append((label, snapshot))
        commands.append("snapshot")

    assert calls["palette_resolver"] == len(expected)
    compare_native(commands, expected)
    assert pins[str(BIN.name)] == sha(BIN)
    report = dict(status="passed", slots=SLOTS, scenarios=len(expected), cases=dict(cases),
                  original_palette_calls=calls["palette_resolver"], original_instructions=instructions,
                  quad_snapshots=packets, observable_source_clears=source_mutations,
                  physical_slots=list(PHYSICAL), elf_sha256=SOURCE_HASH, sha256=pins,
                  scope="Resource 51 image 409, bank 25, ordinary palette mode. Each scenario runs the complete original 121b80 including 115d40 and all reached callees. Compared all cache rows, retained raw colors, formats, converted colors, source palette and atlas hashes, draw counters and all 108910 vertex/palette/blend arguments against the native sprite path. No GS raster or alternate-source check.")
    output = ROOT / "outputs/ss6-feasibility/character_palette_cache_validation.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
