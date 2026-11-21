"""Stage 3: constructor 1aa250, task 1aa3e8.

The task has no single object loop: 1aad60(first, last) draws the row ranges
[0,3), [3,7) and [7,29). Everything the task draws between and after those
calls is therefore exported in the last group, in call order: one 1a4e80
rectangle, eight wall edges (1aaa38) and six 17-link chains (1a55c0).
"""
import struct


def _link(p):
    # 1a55c0(slot, count, pieces, -; x, y, z, scale): a multi-piece sprite centered on a world point.
    slot, n, ptr = p.registers[4:7]
    f = p.float_value
    return 11, slot, [f(12), f(13), f(14), f(15)], [struct.unpack_from('<5i', p.memory, ptr + 24 * i) for i in range(n)]


def _edge(p):
    # 1aaa38(out; x, y, z, height, u, v): the two vertices of one vertical edge of a direct slot-4 strip.
    f = p.float_value
    return 12, 4, [f(i) for i in range(12, 18)], []


STAGE = dict(
    handler=0x1aa3e8, slots=((4, 32), (5, 48), (6, 48), (7, 48), (8, 48)),
    # 510ce8 = 0.2 (shadow Y skew), 510ce4 = 0.
    globals=((0x510ce8, 0x3e4ccccd), (0x50e048, 0x60000000), (0x510ce4, 0), (0x510cec, 3), (0x50e04c, 0)),
    init=(0x1a9f30, 0x1aa118, 0x1a9fa0), once=(0x1a9f30,), once_flag=0x51c920,
    rows=(0x51cfa0, 29), row_pc=0x1aadb4, row_reg=16, end_pc=0x1aae74,
    recorders={0x1a55c0: _link, 0x1aaa38: _edge},
)
