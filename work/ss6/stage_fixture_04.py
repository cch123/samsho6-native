"""Stage 4: constructor 1ab368, task 1ab518."""


def _wave(p, picture):
    # 12eae30 is the 8.8 clock of the six prebuilt sea meshes (0x1e00 each).
    p.write(0x12eae30, min(picture, 5) * 0x1e00, 4)


def _steer(n, delta, memo):
    # The sway amplitude is redrawn only when the 16-bit phase 5331bc is
    # exactly zero. Steer the phase back to zero regularly (steps of at most
    # 0x4000 keep the sea clock 12eae30 in range), then hold it with zero deltas.
    phase = memo.get('phase', 0)
    if n % 37 >= 30:
        delta = min(-phase & 0xffff, 0x4000)
    memo['phase'] = (phase + delta) & 0xffff
    return delta


def _before(p, counter):
    counter['sea_mesh_%d' % (p.read(0x12eae30, 4) // 0x1e00)] += 1


def _after(p, counter):
    counter['sway_amplitude_index_%d' % p.read(0x5331c8, 4)] += 1
    counter['sway_phase_quarter_%d' % (p.read(0x5331bc, 4) >> 14)] += 1


STAGE = dict(
    steer=_steer, before=_before, after=_after,
    handler=0x1ab518, slots=((4, 32), (5, 32), (6, 48), (7, 48), (8, 48)),
    globals=((0x510ce8, 0x3dcccccd), (0x50e048, 0x60000000), (0x510ce4, 0), (0x510cec, 4), (0x50e04c, 0)),
    # The constructor rebuilds both floor meshes and the mesh shadow on every
    # load; only the row clocks (1ab0e8) are guarded by 5331b0.
    init=(0x1ab158, (0x1ab228, 0), (0x1ab228, 1), (0x1ab228, 2), (0x1ab228, 3), (0x1ab228, 4), (0x1ab228, 5),
          0x1ab0e8, 0x1ab078),
    once=(0x1ab0e8,), once_flag=0x5331b0,
    # The task runs the row loop 1ab958 three times: rows 0, 1..12, 13..30.
    rows=(0x5328f8, 31), row_pc=0x1ab9c4, row_reg=16, end_pc=0x1ab910,
    # Group 33: between rows 0 and 1; group 34: between rows 12 and 13.
    marks={0x1ab7d8: 33, 0x1ab848: 34}, groups=35,
    variants={0: 6}, select_extra=_wave,
)
