"""Stage 2 (ship deck): constructor 1a8b90, task 1a8cf0."""
STAGE = dict(
    handler=0x1a8cf0, slots=((4, 32), (5, 32), (6, 48), (7, 48)),
    globals=((0x50e048, 0x60000000), (0x510cec, 2), (0x50e04c, 0)),
    init=(0x1a8a68, 0x1a8b20, 0x1a9908), once=(0x1a8b20,), once_flag=0x51ba40,
    rows=(0x51b0b0, 0x22), row_pc=0x1a8e58, row_reg=16, end_pc=0x1a8f14,
    # 1a95f0 turns a single atlas rectangle about its center.
    extra={0x1a95f0: 9},
)
