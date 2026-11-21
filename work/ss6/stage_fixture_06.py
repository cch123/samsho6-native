"""Stage 6: constructor 1ae020, task 1ae1b8."""
import struct


def _floats(p, first, count):
    return [p.float_value(first + i) for i in range(count)]


def _pieces(p, address, count):
    return [struct.unpack_from('<5i', p.memory, address + 24 * i) for i in range(count)]


def _edge(kind):
    # 1aedb8 / 1aeef8: x, y, z, height of one vertical edge of a banner quad
    # (the u, v arguments in f16/f17 are stored but never read by 1af1f8).
    return lambda p: (kind, 5, _floats(p, 12, 4), [])


def _banner(p):
    # 1af1f8(slot, four corner records, pieces, count): record zero is the
    # bounding rectangle, the others are submitted directly to 1149d0.
    r = p.registers
    return 11, r[4], [], _pieces(p, r[6], r[7])


def _rope(p):
    # 1af030(rectangle; two end points): 21 centered copies along a sagging line.
    return 14, 5, _floats(p, 12, 6), _pieces(p, p.registers[4], 1)


STAGE = dict(
    handler=0x1ae1b8, slots=((4, 32), (5, 32), (6, 48), (7, 48), (8, 48)),
    globals=((0x510ce8, 0x3dcccccd), (0x50e048, 0x60000000), (0x510ce4, 0), (0x510cec, 6), (0x50e04c, 0)),
    init=(0x1ad838, 0x1ad748, 0x1ad580), once=(0x1ad748,), once_flag=0x551248,
    rows=(0x550af8, 26), row_pc=0x1aeacc, row_reg=16, end_pc=0x1aeb88,
    recorders={0x1aedb8: _edge(12), 0x1aeef8: _edge(13), 0x1af1f8: _banner, 0x1af030: _rope},
    # {state*, timeline*} pairs of the two banners the task animates before its row loop.
    prefix_clocks=(0x550ae8, 0x550af0),
    # Extra validation projections. The lantern lines (1af030) hang at Y 602.5..737 and only
    # reach the screen when the view is zoomed out; these follow the published camera relations
    # (StageCamera::publish, 122ed8) for widths 444, 400, 444 and 330 at several heights.
    cameras=((320, 120, -477.5, -133.36, -86.49), (250, 180, -450, -90, -96),
             (400, 260.5, -477.5, -133.36, -86.49), (320, 120, -406.25, -12.31, -116.36)),
)
