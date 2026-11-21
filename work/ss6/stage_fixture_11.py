"""Stage 11: constructor 1b3aa8, task 1b3bb8.

The task has no 0x48-byte row table. Its loop at 1b3d98 walks seven 0x9c-byte
drift objects at 132bc60 (built by 1b3e20/1b3ee0 on every constructor run;
none of the three initializers is guarded, 5733e4 is only written).
"""
import struct

OBJECTS, COUNT, SIZE = 0x132bc60, 7, 0x9c


def _keys(p, row):
    # 1b3ee0 groups an object's pieces by their flag word (less 0x200).
    return [k for k in range(10) if p.read(OBJECTS + SIZE * row + 0x4c + 4 * k, 4)]


def _select(p, picture):
    for row in range(COUNT):
        at = OBJECTS + SIZE * row
        p.write(at + 0x30, 0xc00 * (picture if picture in _keys(p, row) else 0), 4)
        # No bobbing while the camera-independent commands are recorded.
        p.write(at + 0x24, 0, 4)


def _current(p, row):
    return p.read(OBJECTS + SIZE * row + 0x28, 4)


def _observe(p, seen):
    for row in range(COUNT):
        at = OBJECTS + SIZE * row
        amplitude = struct.unpack_from('<f', p.memory, at + 0x24)[0]
        seen.setdefault('amplitudes', {}).setdefault(row, set()).add(amplitude)
        seen.setdefault('alpha', {}).setdefault(row, set()).add(p.read(at + 0x44, 4))
        seen.setdefault('fade_restarts', {}).setdefault(row, 0)
        seen['fade_restarts'][row] += p.read(at + 0x3c, 4) == 0x1500


def _covered(seen):
    # Every object must have bobbed with at least two amplitudes (two phase
    # wraps), restarted its fade and shown both transparent and opaque alpha.
    for row in range(COUNT):
        assert len(seen['amplitudes'][row] - {0.0}) >= 1 and len(seen['amplitudes'][row]) >= 3, ('bob', row, seen['amplitudes'][row])
        assert seen['fade_restarts'][row] >= 2, ('fade', row)
        assert min(seen['alpha'][row]) == 0 and max(seen['alpha'][row]) >= 254, ('alpha', row)
    return dict(amplitudes={str(k): sorted(v) for k, v in seen['amplitudes'].items()},
                fade_restarts={str(k): v for k, v in seen['fade_restarts'].items()},
                alpha_range={str(k): [min(v), max(v)] for k, v in seen['alpha'].items()})


STAGE = dict(
    handler=0x1b3bb8, slots=((4, 32), (5, 48)),
    globals=((0x50e048, 0x60000000), (0x510cec, 11), (0x50e04c, 0)),
    init=(0x1b39a8, 0x1b3e20, 0x1b3ee0), once=(), once_flag=0x5733e4,
    rows=(OBJECTS, COUNT), row_size=SIZE, row_pc=0x1b3d98, row_reg=17, end_pc=0x1b3dec,
    animated=tuple(range(COUNT)), picture_keys=_keys, select_replace=_select, current=_current,
    # 1b3e20 draws from the library generator, so the validator repeats the
    # constructor tail once its seed is in place.
    seeded_init=True,
    # The bob amplitude is zero until an object's phase wraps (683..1024
    # visits after a constructor run; the plan reloads at visit 400), so the
    # default run is longer than the shared 900 visits.
    visits=3200, observe=_observe, covered=_covered,
    # The picture clock is reduced by 0x2400 at most once per visit. Steps of
    # 0x4000 alternating with 0x900 gain 0x100 per pair, so a 30-visit window
    # reaches the empty entries 3..6 and never entries past 9 (foreign
    # object fields).
    long_deltas=(0x4000, 0x900), empty_pictures=(3, 4, 5, 6),
)
