"""Stage 7: constructor 1af840, task 1afa48, object rows drawn by 1afef0."""
import struct

from inspect_iso import Elf
from validate_dash_motion import ELF

_elf = Elf(ELF.read_bytes())


def _word(address):
    return struct.unpack_from('<I', _elf.data, _elf.offset(address))[0]


# The two hopping objects: 0xd4-byte records at 130b920 (A) and 130b9f4 (B),
# {+0 flight clock 8.8, +8 x, +c y, +10 z}; heights at 130bac8 / 130bacc and
# wait timers at 130bad0 / 130bad4. The constructor clears and seeds them on
# every load (1af99c..1afa34).
A, B, HEIGHTS, TIMERS = 0x130b920, 0x130b9f4, 0x130bac8, 0x130bad0
ANIM_A, ANIM_B = 0x131ad74, 0x131ae48  # 1a7290 descriptors built by 1af7f0

_private = tuple((A + 4 * i, 0) for i in range(0x1a8 // 4)) + (
    (B, 0xf00), (B + 0x10, _word(0x6536c0)), (A + 8, _word(0x6536c4)), (A + 0x10, _word(0x6536c8)),
    (B + 8, _word(0x6536cc)), (HEIGHTS, 0), (HEIGHTS + 4, 0), (TIMERS, 0xa00), (TIMERS + 4, 0x1400))


def _backdrop(p):
    """1a6d90: a multi-piece picture stretched between two projected points."""
    reg, f = p.registers, p.float_value
    slot, n, ptr = reg[4:7]
    return (11, slot, [f(12), f(13), f(14), f(15), f(16)],
            [struct.unpack_from('<5i', p.memory, ptr + 24 * i) for i in range(n)])


def _shadow(p):
    """1a4f40 with the skew in force at the call (row prologue 2 scales it)."""
    f = p.float_value
    skew = struct.unpack_from('<2f', p.memory, 0x510ce4)
    return (3, p.registers[4], [f(i) for i in range(12, 19)], [[*skew, 0, 0, 0]])


def _tables(p):
    """One extra group per hopping object: its four pictures as sprite commands."""
    groups = []
    for record, anim, x in ((A, ANIM_A, None), (B, ANIM_B, 0x653704)):
        xyz = list(struct.unpack_from('<3f', p.memory, record + 8))
        if x is not None:
            # B's sprite X is the literal at 653704; record +8 is its shadow X.
            xyz[0] = struct.unpack_from('<f', p.memory, x)[0]
        variants = []
        for picture in range(4):
            count = p.read(anim + 0x34 + 4 * picture, 4)
            pieces = p.read(anim + 0x84 + 4 * picture, 4)
            assert count and pieces
            variants.append([(1, 6, [*xyz, 1, 1],
                              [struct.unpack_from('<5i', p.memory, pieces + 24 * i) for i in range(count)])])
        groups.append(variants)
    return groups


def _probe(p, pc, seen):
    """Picture index chosen for each hopper, and whether the visit was paused."""
    # 1afc8c / 1afdcc are the first instructions common to every path of A / B.
    if pc in (0x1afc8c, 0x1afdcc):
        seen.add(('A' if pc == 0x1afc8c else 'B', p.registers[14], p.read(0x46a908, 4) == 0))


# Picture 2 needs a newly computed negative height, which a paused visit
# cannot produce after an unpaused one accepted the same clock.
_EXPECTED = {(o, k, paused) for o in 'AB' for k in range(4) for paused in (False, True)} - {('A', 2, True), ('B', 2, True)}


STAGE = dict(
    handler=0x1afa48, slots=((4, 32), (5, 32), (6, 48), (7, 48)),
    globals=((0x510ce8, _word(0x6536bc)), (0x50e048, 0x60000000), (0x510ce4, 0), (0x50e04c, 0),
             *_private, (0x510cec, 7)),
    init=(0x1af510, 0x1af7f0, 0x1af698, 0x1af580), once=(0x1af510, 0x1af7f0), once_flag=0x56ac38,
    # The row loop is 1afef0(0, 17), called from the task at 1afbe0.
    rows=(0x56b168, 17), row_pc=0x1aff5c, row_reg=16, end_pc=0x1afbe8,
    recorders={0x1a6d90: _backdrop, 0x1a4f40: _shadow},
    tables=_tables,
    probe=_probe, probe_expected=_EXPECTED,
)
