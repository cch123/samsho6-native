"""Stage 9: constructor 1b15b0, task 1b1730."""
STAGE = dict(
    handler=0x1b1730, slots=((4, 32), (5, 48), (6, 48), (7, 48)),
    globals=((0x510ce8, 0x3dcccccd), (0x50e048, 0x60000000), (0x510ce4, 0), (0x510cec, 9), (0x50e04c, 0)),
    init=(0x1b14f0, 0x1b13b8, 0x1b1428, 0x1b1d90), once=(0x1b13b8,), once_flag=0x570388,
    rows=(0x56ff08, 16), row_pc=0x1b1eac, row_reg=16, end_pc=0x1b18d4,
    # The three animated objects drawn after the row loops (handles 1320f78/80/88).
    # Group 17 is the suffix; one variant per picture, all three at the same picture.
    clocks=((0x132ae44, 0x56fe60, 17), (0x132afec, 0x56fe60, 17), (0x132b194, 0x56fe60, 17)),
)
