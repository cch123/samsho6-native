"""Stage 5: constructor 1ac1f8, task 1ac360.

The task has no row loop of its own: 1ad298(first, last) draws rows 0..1 and,
later, rows 2..5. Group 8 holds everything between the two calls.
"""
import struct


def _edge(p):
    # 1ace00: one vertical edge (x, y, z, height, texel height, u, v) of a receding wall.
    return 11, 4, [p.float_value(i) for i in range(12, 19)], []


def _pieces(p):
    # 1af1f8: atlas pieces mapped into the quadrilateral of the two preceding edges.
    slot, _, table, count = p.registers[4:8]
    return 12, slot, [count], [struct.unpack_from('<5i', p.memory, table + 24 * i) for i in range(count)]


def _mesh(p):
    # 1ad0f0: a world mesh, vertex {x, y, z, u, v}, 33 vertices per stored row.
    slot, ptr, columns, rows = p.registers[4:8]
    verts = [struct.unpack_from('<5f', p.memory, ptr + 20 * (x + dx) + 0x294 * y)
             for x in range(columns) for y in range(rows + 1) for dx in range(2)]
    key = struct.unpack_from('<f', p.memory, ptr + 0x294 * rows + 20 * columns - 12)[0]
    return 13, slot, [key, 2 * (rows + 1)], verts


def _watch(p, frame):
    """Coverage of the drifting sprite 544300: wrapped position, and whether it reached 1149d0."""
    x = struct.unpack_from('<f', p.memory, 0x12f14c8)[0]
    tags = {'drift wrapped'} if x > 0 else set()
    # The sprite is the only slot-6 strip keyed at Z 1550 (key 9845000 + order, order >= 100).
    drawn = any(slot == 6 and 9845100 <= key < 9846000 for key, slot, *_ in frame)
    if frame:
        tags.add('drift drawn' if drawn else 'drift culled')
    if any(color == 0x90000000 for _, _, color, *_ in frame):
        tags.add('shadow 90000000')
    return tags


STAGE = dict(
    handler=0x1ac360, slots=((4, 32), (5, 32), (6, 48)),
    globals=((0x510ce8, 0x3e4ccccd), (0x50e048, 0x60000000), (0x510ce4, 0), (0x510cec, 5), (0x50e04c, 0)),
    init=(0x1abdd0, 0x1abf20, 0x1abcd8, 0x1abd80), once=(0x1abcd8,), once_flag=0x544618,
    rows=(0x544468, 6), row_pc=0x1ad2ec, row_reg=16, end_pc=0x1acc6c,
    extra_groups=1, marks={0x1ac4e0: 8},
    # (group, state, timeline) of the clock the task advances itself at 1acc6c.
    clocks_ranked=((7, 0x12f1594, 0x5443b0),),
    watch_tags=_watch, expect_tags={'drift wrapped', 'drift drawn', 'drift culled', 'shadow 90000000'},
    recorders={0x1ace00: _edge, 0x1af1f8: _pieces, 0x1ad0f0: _mesh},
)
