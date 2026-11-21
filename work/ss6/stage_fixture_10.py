"""Stage 10: constructor 1b2350, task 1b24e0.

The task has no inline row loop: 1b3588(first, end) draws rows of the table at
5723e0 and is called for rows 0..6 and 7..18, with two plain rectangles in
between (recorded at the end of row 6's group). Everything before the first
row except the floor mesh depends on private clocks and is ported by hand;
group 0 holds whatever those clocks showed in the initial state and only its
floor command (kind 4) is used.
"""
import struct

SCROLL = 0x57294c           # 8.8 clock of the fourteen blinking far rectangles
CLOCKS = 0x5723a0           # eight {state, timeline} pairs of the task's own clocks


def _flipped_shadow(p):
    # 1a5078 (via 1a5488): 1a4f40 with the two vertex pairs exchanged.
    f = p.float_value
    return 11, p.registers[4], [f(i) for i in range(12, 19)], []


def _watch(p):
    """Private state reached by a visit; the validator reports its coverage."""
    out = {'scroll_index': p.read(SCROLL, 4) // 0x600 % 12}
    for k in range(8):
        state = p.read(CLOCKS + 8 * k, 4)
        out[f'clock{k}_step'] = p.read(state + 0x2c, 4)
        out[f'clock{k}_picture'] = p.read(state + 4, 4)
    return out


STAGE = dict(
    handler=0x1b24e0, slots=((4, 32), (5, 32), (6, 48), (7, 48), (8, 48)),
    globals=((0x510ce8, struct.unpack('<I', struct.pack('<f', 0.1))[0]), (0x50e048, 0xa0000000),
             (0x510ce4, 0), (0x510cec, 10), (0x50e04c, 0)),
    init=(0x1b2290, 0x1b2170), once=(0x1b2170,), once_flag=0x5720a0,
    rows=(0x5723e0, 19), row_pc=0x1b35f4, row_reg=16, end_pc=0x1b3188,
    recorders={0x1a5078: _flipped_shadow},
    watch=_watch,
    expect={'scroll_index': set(range(12)),
            **{f'clock{k}_step': set(range(n)) for k, n in enumerate((8, 9, 8, 9, 12, 9, 9, 9))},
            **{f'clock{k}_picture': {0, 1, 2, 256} for k in range(5)},
            **{f'clock{k}_picture': {0, 1, 256} for k in range(5, 8)}},
)
