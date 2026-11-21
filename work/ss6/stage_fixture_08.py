"""Stage 8: constructor 1b05b8, task 1b0738.

The task has no single row loop: 1b10a0(first, end) draws rows 0..2, seven
hand-coded moving objects follow, then 1b10a0 draws rows 3..18. `marks`
moves the helper calls of the moving objects into their own command group
(index rows + 2, after the empty suffix group).
"""
STAGE = dict(
    handler=0x1b0738, slots=((4, 32), (5, 32), (6, 48), (7, 48)),
    # 510ce8 = [6537b4] is written by prepare-time code below (float bits).
    globals=((0x510ce8, 0x3dcccccd), (0x50e048, 0x60000000), (0x510ce4, 0), (0x510cec, 8), (0x50e04c, 0)),
    init=(0x1b0500, 0x1b0490, 0x1b0298, 0x1b1030), once=(0x1b0490,), once_flag=0x56f468,
    rows=(0x56ef10, 19), row_pc=0x1b10f4, row_reg=16, end_pc=0x1b0f20,
    marks={0x1b08a0: 21}, extra_groups=1,
)


def _normalize(group, command):
    # The moving objects' X and Y are task state; only Z and the atlas
    # pieces are constants of the command.
    if group != 21:
        return command
    kind, slot, params, records = command
    return kind, slot, [0.0, 0.0, *params[2:]], records


STAGE['normalize'] = _normalize

# Object 6 (13203e0) moves -0.3 per visit regardless of delta and would need
# about 4,400 visits to reach its wrap at -830. Visit 200 presets its X to
# -829.5 in the original descriptor and in the native state (poke index 0).
STAGE['pokes'] = {200: ((0x13203e0 + 8, 0xc44f6000, 0),)}
