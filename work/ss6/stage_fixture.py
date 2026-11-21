#!/usr/bin/env python3
"""Shared original-program fixture for the battle scenery tasks of stages 2..11.

Every stage constructor at 50e080[stage] creates a priority-10 task (tag fa1),
loads its textures and CLUTs, binds texture slots to CLUT banks and then runs
its own table initializers. The fixture performs the same writes and runs the
post-I/O initializers unmodified; disc I/O itself is not executed.
"""
import struct

from extract_versus_result_layout import canvas

PROJECTION = (0x4a2a58, 0x4a2a5c, 0x4a2a60, 0x4a2a6c, 0x4a2a68)
DELTA = 0x46a908
HIDE = 0x50e04c
SUBMIT = 0x1149d0

# Leaf drawing helpers shared by the stage tasks. A call nested inside
# another listed helper is part of that helper and is not recorded again.
SPRITES = (0x1a6210, 0x1a6460, 0x1a66b8, 0x1a6b08)
QUARTER = 0x1a6f90
HELPERS = SPRITES + (0x1a4f40, 0x1a5890, 0x1a5d40, 0x1a5f68, 0x1a51b0, 0x1a52e8,
                     0x1a4cb8, 0x1a4d98, QUARTER)

# Per-stage configuration lives in stage_fixture_NN.py as a dict named STAGE:
#   handler: task callback. slots: (texture slot, CLUT bank) pairs passed to
#   10add8. globals: plain word writes made by the constructor. init: routines
#   the constructor runs after binding, in order; once: those guarded by the
#   constructor's process-lifetime flag (once_flag). rows: (table address,
#   count) of the 0x48-byte object rows. row_pc/row_reg: first instruction of
#   the object loop body and the register holding the row address. end_pc:
#   first instruction after the loop. extra: {helper pc: private command kind}
#   recorded as (x, y, z) + one rectangle. recorders: {helper pc: function(p)
#   returning (kind, slot, params, records)} for other argument layouts.
#   An init entry may be (routine, argument...).
# Optional keys for tasks that do not fit one row loop:
#   marks: {pc: group} switches the recording group at task code between
#   partial row loops; extra_groups / groups: groups after rows+2 / the total;
#   normalize(group, command): filter applied to each exported command;
#   variants: {group: picture count} with select_extra(p, picture) for state
#   that is not a row clock; clocks: ((state, timeline, group), ...) and
#   clocks_ranked: ((group, state, timeline), ...) for clocks owned by the
#   task; prefix_clocks: addresses of {state*, timeline*} pairs advanced
#   before the loop (variants of group 0); tables(p): extra picture groups.
#   Objects other than 0x48-byte rows: row_size, animated (indices),
#   picture_keys(p, row), select_replace(p, picture), current(p, row).
# Validator-only keys are documented in validate_combat_stage_n.py.
class _Stages(dict):
    def __missing__(self, stage):
        import importlib
        self[stage] = importlib.import_module(f'stage_fixture_{stage:02}').STAGE
        return self[stage]


STAGES = _Stages()


def run_init(p, routine):
    if isinstance(routine, tuple):
        p.run(routine[0], routine[1:], limit=4000000)
    else:
        p.run(routine, limit=4000000)


def prepare(stage):
    cfg = STAGES[stage]
    p = canvas()
    for address, value in cfg['globals']:
        p.write(address, value, 4)
    for slot, bank in cfg['slots']:
        p.run(0x10add8, (slot, bank))
    for routine in cfg['init']:
        run_init(p, routine)
    if 'once_flag' in cfg:
        p.write(cfg['once_flag'], 1, 4)
    p.run(0x13847c, stop_before=[0x1384cc])
    p.write(DELTA, 256, 4)
    return p


def set_camera(p, camera):
    for address, value in zip(PROJECTION, camera, strict=True):
        struct.pack_into('<f', p.memory, address, value)


def animated_rows(p, stage):
    if 'animated' in STAGES[stage]:
        return list(STAGES[stage]['animated'])
    base, count = STAGES[stage]['rows']
    return [n for n in range(count) if p.read(base + 72 * n + 4, 4) & 0x100]


def clock(p, stage, row):
    """(state address, timeline address) of an animated row."""
    base, _ = STAGES[stage]['rows']
    return struct.unpack_from('<2I', p.memory, p.read(base + 72 * row + 0x28, 4))


def submissions(p, stage, limit=4000000, extra=None):
    """Run the whole task once and return every 1149d0 strip in submit order."""
    frame = []

    def observe(pc):
        if extra is not None:
            extra(pc)
        if pc != SUBMIT:
            return
        r = p.registers
        vertices = [struct.unpack_from('<5fI', p.memory, r[4] + 24 * j) for j in range(r[5])]
        # 1149d0 copies vertex zero's color to the whole strip. Most strips
        # are flat in depth; a few stage planes carry one depth per vertex.
        frame.append((vertices[0][2], r[6] & 0xffff, vertices[0][5], int(r[7] == 1),
                      [(x, y, u, v, z) for x, y, z, u, v, _ in vertices]))

    p.run(0x114e80)
    _, steps = p.run(STAGES[stage]['handler'], limit=limit, observe=observe)
    return frame, p.read(0x3db8f4, 4), steps
