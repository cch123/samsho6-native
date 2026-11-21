#!/usr/bin/env python3
"""Export camera-independent scenery commands of one battle stage (2..11).

The original task is run unmodified. Calls to the shared leaf helpers are
recorded before projection and culling, grouped by the object row that issued
them, once for every picture of every animated row. Strips a task submits
directly to 1149d0 are stage-specific code and are ported by hand.
"""
import argparse
from hashlib import sha256
import struct

from finite_float import arithmetic
from stage_fixture import HELPERS, QUARTER, SPRITES, STAGES, SUBMIT, animated_rows, clock, prepare, set_camera
from validate_dash_motion import ASSETS, ELF, PIN

CAMERAS = ((320, 120, -400, 0, -120), (170.5, 160, -500, -160, -79.2), (455.25, 190, -540, -155, -61.5))


def floats(p, address, count):
    return struct.unpack_from(f'<{count}f', p.memory, address)


def timeline_keys(p, timeline):
    keys = []
    while (key := struct.unpack_from('<i', p.memory, timeline + 8 * len(keys))[0]) >= 0:
        keys.append(key)
    return keys


def visible(keys):
    """Picture bit 0x100 hides the row for that record; it has no artwork."""
    return [key for key in keys if not key & 0x100]


def group_count(stage):
    """Prefix, one group per row, suffix, then the stage's extra groups."""
    cfg = STAGES[stage]
    return cfg.get('groups', cfg['rows'][1] + 2 + cfg.get('extra_groups', 0))


def prefix_clocks(p, stage):
    """(state, picture ids) of frame clocks a task advances before its row loop.

    cfg['prefix_clocks'] lists the addresses of their {state*, timeline*}
    pairs. Their pictures are exported as the variants of group 0.
    """
    result = []
    for address in STAGES[stage].get('prefix_clocks', ()):
        state, timeline = struct.unpack_from('<2I', p.memory, address)
        result.append((state, timeline_keys(p, timeline)))
    return result


def pictures(p, stage, row):
    """Picture ids used by a frame-animated row, or None for a scrolling row."""
    if 'picture_keys' in STAGES[stage]:
        return STAGES[stage]['picture_keys'](p, row)
    base, _ = STAGES[stage]['rows']
    if p.read(base + 72 * row + 4, 4) & 0x10:
        return None
    _, timeline = clock(p, stage, row)
    keys = []
    while (key := struct.unpack_from('<i', p.memory, timeline + 8 * len(keys))[0]) >= 0:
        keys.append(key)
    return keys


def select(p, stage, picture):
    cfg = STAGES[stage]
    if 'select_replace' in cfg:
        return cfg['select_replace'](p, picture)
    clocks = prefix_clocks(p, stage)
    for row in animated_rows(p, stage):
        keys = pictures(p, stage, row)
        if keys is None:
            continue
        clocks.append((clock(p, stage, row)[0], keys))
    # Clocks that belong to no object row: (state, timeline, group).
    for state, timeline, _ in cfg.get('clocks', ()):
        clocks.append((state, timeline_keys(p, timeline)))
    for state, keys in clocks:
        p.write(state, 0, 4)
        p.write(state + 0x2c, keys.index(picture if picture in keys else 0), 4)
    # Same, but variant k shows the k-th smallest picture id: (group, state, timeline).
    for _, state, timeline in cfg.get('clocks_ranked', ()):
        keys = timeline_keys(p, timeline)
        order = sorted(set(keys))
        p.write(state, 0, 4)
        p.write(state + 0x2c, keys.index(order[picture] if picture < len(order) else order[0]), 4)
    if 'select_extra' in cfg:
        cfg['select_extra'](p, picture)


def collect(p, stage, picture):
    cfg = STAGES[stage]
    base, count = cfg['rows']
    extra = cfg.get('extra', {})
    recorders = cfg.get('recorders', {})
    marks = cfg.get('marks', {})
    normalize = cfg.get('normalize', lambda group, command: command)
    groups = [[] for _ in range(group_count(stage))]
    raw = [0] * group_count(stage)
    group = 0
    active = None
    select(p, stage, picture)
    p.write(0x46a908, 0, 4)

    def observe(pc):
        nonlocal group, active
        reg = p.registers
        if pc == cfg['row_pc']:
            group = 1 + (reg[cfg['row_reg']] - base) // cfg.get('row_size', 72)
        elif pc == cfg['end_pc']:
            group = count + 1
        elif pc in marks:
            group = marks[pc]
        if active and pc == active[0] and reg[29] == active[1]:
            active = None
        if active:
            return
        if pc == SUBMIT:
            raw[group] += 1
            return
        if pc not in HELPERS and pc not in extra and pc not in recorders:
            return
        active = (reg[31], reg[29])
        emit = lambda command, target=group: groups[target].append(normalize(target, command))
        f = p.float_value
        if pc in recorders:
            emit(recorders[pc](p))
        elif pc in SPRITES:
            slot, n, ptr = reg[4:7]
            scale = [f(15), f(16)] if pc in SPRITES[2:] else [1, 1]
            # u, v, w, h and the piece flags; 0x200 submits the piece without vertex alpha.
            rects = [struct.unpack_from('<5i', p.memory, ptr + 24 * i) for i in range(n)]
            emit((1 + (pc in SPRITES[1::2]), slot, [f(12), f(13), f(14), *scale], rects))
        elif pc == QUARTER:
            slot, n, ptr = reg[4:7]
            emit((10, slot, [f(12), f(13), f(14)], [struct.unpack_from('<5i', p.memory, ptr + 24 * i) for i in range(n)]))
        elif pc in (0x1a51b0, 0x1a52e8):
            emit((1 + (pc == 0x1a52e8), reg[4], [f(12), f(13), f(14), f(19), floats(p, reg[29], 1)[0]],
                  [[*(f(i) for i in range(15, 19)), -1]]))
        elif pc in (0x1a4cb8, 0x1a4d98):
            emit((7 + (pc == 0x1a4d98), reg[4], [f(12), f(13), f(14)], [[*(f(i) for i in range(15, 19)), -1]]))
        elif pc == 0x1a4f40:
            emit((3, reg[4], [f(i) for i in range(12, 19)], []))
        elif pc == 0x1a5890:
            slot, ptr, columns, rows = reg[4:8]
            verts = [floats(p, ptr + 20 * (x + dx) + 0x294 * y, 5)
                     for x in range(columns) for y in range(rows + 1) for dx in range(2)]
            # 1a58ec: the horizontal cull margin is the float table 50e050 indexed by
            # the stage number 510cec (200 for stages 0..8, 100 for 9..11).
            emit((4, slot, [*floats(p, ptr + 8, 1), *floats(p, 0x50e050 + 4 * p.read(0x510cec, 4), 1),
                            2 * (rows + 1)], verts))
        elif pc in (0x1a5d40, 0x1a5f68):
            slot, ptr, columns, rows, size = reg[4:9]
            verts = []
            for x in range(columns):
                for y in range(rows + 1):
                    for dx in range(2):
                        at = ptr + 36 * (x + dx) + 0x4a4 * y
                        uv = floats(p, at + 12, 2)
                        if pc == 0x1a5f68:
                            # Binds the current animated atlas frame to a shared mesh.
                            values = []
                            for axis in range(2):
                                norm = p.read(at + 28 + 4 * axis, 4)
                                extent = p.read(ptr + 0x4ee4 + 4 * axis, 4)
                                pos = arithmetic('add', p.floats[12 + axis], arithmetic('mul', extent, norm))
                                value = arithmetic('div', pos, struct.unpack('<I', struct.pack('<f', size))[0])
                                values.append(struct.unpack('<f', struct.pack('<I', value))[0])
                            uv = values
                        verts.append((*floats(p, at + 20, 2), 0, *uv))
            emit((5, slot, [*floats(p, ptr, 3), *floats(p, ptr + 0x4ee4, 2), 2 * (rows + 1)], verts))
        else:
            emit((extra[pc], reg[4], [f(12), f(13), f(14)], [[*(f(i) for i in range(15, 19)), -1]]))

    p.run(0x114e80)
    p.run(cfg['handler'], limit=4000000, observe=observe)
    return groups, raw


def extract(stage):
    assert sha256(ELF.read_bytes()).hexdigest() == PIN
    probes = [prepare(stage) for _ in CAMERAS]
    for p, camera in zip(probes, CAMERAS):
        set_camera(p, camera)
    p = probes[0]
    _, count = STAGES[stage]['rows']
    cfg = STAGES[stage]
    counts = [1] * group_count(stage)
    for group, n in cfg.get('variants', {}).items():
        counts[group] = n
    for _, keys in prefix_clocks(p, stage):
        counts[0] = max(counts[0], max(keys) + 1)
        assert sorted(set(keys)) == list(range(max(keys) + 1))
    for state, timeline, group in cfg.get('clocks', ()):
        keys = timeline_keys(p, timeline)
        assert sorted(set(keys)) == list(range(max(keys) + 1))
        counts[group] = max(counts[group], max(keys) + 1)
    for group, _, timeline in cfg.get('clocks_ranked', ()):
        counts[group] = len(set(timeline_keys(p, timeline)))
    for row in animated_rows(p, stage):
        keys = pictures(p, stage, row)
        if keys is not None:
            keys = visible(keys)
            counts[1 + row] = max(keys) + 1
            assert sorted(set(keys)) == list(range(counts[1 + row]))
    variants = [collect(p, stage, k) for k in range(max(counts))]
    # Neither the projection nor a helper's own visibility test may change
    # what the task asks its helpers to draw.
    for other in probes[1:]:
        assert variants == [collect(other, stage, k) for k in range(max(counts))]
    # Optional hook: picture tables of objects the task draws outside its row
    # loop, appended as extra groups (one variant per picture).
    hook = cfg.get('tables')
    tables = hook(p) if hook else []
    assert not hook or all(hook(q) == tables for q in probes[1:])
    data = bytearray(struct.pack('<4s3I', b'STGX', 2, stage, len(counts) + len(tables)))
    direct = variants[0][1]

    def write(commands):
        data.extend(struct.pack('<I', len(commands)))
        for kind, slot, params, records in commands:
            data.extend(struct.pack('<4I', kind, slot, len(params), len(records)))
            data.extend(struct.pack(f'<{len(params)}f', *params))
            for rec in records:
                data.extend(struct.pack(f'<{len(rec)}f', *rec))

    for group, n in enumerate(counts):
        data.extend(struct.pack('<I', n))
        for k in range(n):
            write(variants[k][0][group])
        assert all(v[0][group] == variants[0][0][group] for v in variants[n:])
        assert all(v[1][group] == direct[group] for v in variants)
    for table in tables:
        data.extend(struct.pack('<I', len(table)))
        for commands in table:
            write(commands)
    return bytes(data), counts, direct


def path(stage):
    return ASSETS / f'combat_stage_{stage:02}.bin'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', type=int, required=True)
    args = parser.parse_args()
    data, counts, direct = extract(args.stage)
    path(args.stage).write_bytes(data)
    print(path(args.stage), len(data), sha256(data).hexdigest())
    print('pictures per group', counts)
    print('direct 1149d0 strips per group (hand-ported)', direct)
