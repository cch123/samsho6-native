"""Battle-side practice rules, recording flags and select routing: original functions and explicit slices."""
from collections import Counter
from mips_probe import signed

G, BODY, SCRATCH = 0x4c3808, 0x1f30000, 0x1f40000

class Boundary:
    """Explicit slice end: the run stops before executing one of these addresses."""
    def __init__(self, *addresses): self.addresses = addresses; self.stopped = None
    def __contains__(self, pc):
        if pc in self.addresses: self.stopped = pc; return True
        return False

def rules(native, rng, Oracle, ACTORS, BATTLE):
    o = Oracle(); p = o.p; done = Counter()
    actor = ACTORS
    def clear_actor():
        p.memory[ACTORS:ACTORS+2*0xf2c] = bytes(2*0xf2c); p.memory[BODY:BODY+0x200] = bytes(0x200)
        p.memory[BATTLE:BATTLE+0x600] = bytes(0x600)
        for seat in (0, 1): p.write(ACTORS+0xf2c*seat, BODY, 4); p.write(ACTORS+0xf2c*seat+0xa24, seat, 4)
    def context(mode=None, btype=None, replay=None, recording=None):
        mode = rng.choice((9, 10)) if mode is None else mode
        btype = rng.choice((1, 1, 1, 0, 2)) if btype is None else btype
        replay = rng.randrange(2) if replay is None else replay
        recording = rng.randrange(2) if recording is None else recording
        p.write(G, mode, 4); p.write(0x123a0c0, btype, 1); p.write(0x123a0d8, replay, 4); p.write(0x123a0dc, recording, 4)
        values = [rng.randrange(0, 14) for _ in range(48)]+[rng.randrange(0, 32) for _ in range(32)]
        o.set_settings(values); native.ask('X', btype, mode, replay, recording, *values)
        return mode, btype, replay, recording
    def slice_(start, stops, registers=(), limit=200000):
        for reg, value in registers: p.registers[reg] = value
        boundary = Boundary(*stops)
        _, count = p.run(start, [], limit=limit, stop_before=boundary)
        assert boundary.stopped in stops, hex(start)
        o.n += count; return boundary.stopped

    # 151968 whole: damage commit, timer 28, one-point floor without the KO flag.
    for case in range(400):
        clear_actor(); context()
        life, maximum = rng.choice((1, 5, 60, 200, 260)), rng.choice((100, 200))
        pending = rng.choice((0, 0, 1, 4, 5, 59, 60, 61, 300))
        flag = rng.choice((0, 0x80))
        p.write(actor+0xa30, life, 4); p.write(actor+0xa34, maximum, 4); p.write(actor+0xa38, pending, 4); p.write(actor+0x23c, flag, 4)
        o.run(0x151968, actor)
        ko = int(p.read(actor+0x23c, 4) & 0x80 != 0)
        got = native.ask('L', life, pending, maximum)
        assert o.w(actor+0xa38) == 0 and o.w(actor+0x220) in (0, 30 << 8)
        assert got[0] == o.w(actor+0xa30) and got[2] == int(o.w(actor+0x220) == 30 << 8), (case, got)
        assert got[1] == ko or (got[1] == -1 and ko == int(flag != 0)), (case, got, ko)
        done['life_floor'] += int(got[1] == -1); done['151968'] += 1
    # 14959c..1495e8 refill and 1495e8..149618/1498a0 pad-or-CPU choice.
    for case in range(600):
        clear_actor(); context()
        timer, character, action = rng.choice((0, 0, 1, 30)), rng.choice((0, 0xc, 0xc, 7)), rng.choice((0, 0x279, 0x279, 0x278))
        kind, behaviour, flags = rng.randrange(2), rng.choice((0, 0x23, 0x24, 0x25, 0x26)), rng.choice((0, 1, 2, 4, 8, 0xc, 6))
        for off, value in ((0x220, timer), (0xa10, character), (0xa20, kind), (0xc8, behaviour), (0x240, flags), (0xa30, 37), (0xa34, 180)):
            p.write(actor+off, value, 4)
        p.write(BODY+0x24, action, 4)
        slice_(0x14959c, (0x1495ec, 0x1498d0), [(17, actor)])
        refilled = int(o.w(actor+0xa30) == 180)
        human = int(slice_(0x1495e8, (0x149618, 0x1498a0), [(17, actor)]) == 0x149618)
        assert native.ask('F', timer, character, action, kind, behaviour, flags) == [refilled, human], case
        done['refill_slices'] += 1; done['refilled'] += refilled
    # 13fbe0..13fc18 time mode and whole 1418f8.
    for case in range(300):
        clear_actor(); mode, *_ = context(mode=rng.choice((0, 3, 9, 10, 11)))
        option, submode, clock = rng.choice((0, 1, 2, 3)), rng.choice((2, 3, 5, 6)), rng.randrange(0, 100)
        p.write(0x43d05d, option, 1); p.write(G+0xa0, submode, 4); p.write(BATTLE+0x14, clock, 4); p.write(BATTLE+0x13c, 77, 4)
        slice_(0x13fbe0, (0x13fc18,))
        want = [o.w(BATTLE+0x13c), o.run(0x1418f8)]
        assert native.ask('M', option, int(submode in (5, 6)), clock) == want, (case, mode, option, submode, want)
        done['time_mode'] += 1
    p.write(G+0xa0, 3, 4)
    # 145068 item delivery kind; 443150 = 1 selects the game generator 112290 (seed 3d2e80).
    for case in range(300):
        clear_actor(); mode, *_ = context(btype=1)
        if case % 3 == 0:
            p.write(0x13738d0+4*5, 13, 4); native.ask('X', 1, mode, p.read(0x123a0d8, 4), p.read(0x123a0dc, 4), *o.settings())
        seed = rng.getrandbits(32); p.write(0x3d2e80, seed, 4)
        stop = slice_(0x145068, (0x144fd0, 0x1450b4))
        kind = signed(p.registers[17], 32) if stop == 0x144fd0 else -1
        assert native.ask('D', seed) == [kind, p.read(0x3d2e80, 4)], (case, kind)
        done['item_delivery'] += 1; done['item_random'] += int(o.w(0x13738d0+20) == 13)
    # 172158..172220 get-up decision of the dummy (slice; the pad rule that follows is disabled with +0x2ec = 0).
    for case in range(500):
        clear_actor(); mode, *_ = context()
        if case % 2:
            p.write(0x13738d0+4*3, rng.randrange(4), 4); p.write(0x13738d0+4*2, rng.choice((0, 1, 6, 7, 8)), 4)
            native.ask('X', p.memory[0x123a0c0], mode, p.read(0x123a0d8, 4), p.read(0x123a0dc, 4), *o.settings())
        kind, flags, before = rng.choice((1, 1, 1, 0)), rng.choice((0, 0, 0, 0x20000000, 0x10)), rng.choice((0, 1, 2, 7))
        seed = rng.getrandbits(32); p.write(0x3d2e80, seed, 4)
        for off, value in ((0xa20, kind), (0x248, flags), (0xa4c, before)): p.write(actor+off, value, 4)
        slice_(0x172158, (0x172220, 0x172224), [(16, actor)])
        want = [o.w(actor+0xa4c), p.read(actor+0x248, 4), p.read(0x3d2e80, 4)]
        assert native.ask('U', before, flags, kind, seed) == want, (case, kind, flags, before, want)
        done['get_up'] += 1; done['get_up_changed'] += int(want[0] != before)
    # Damage counters: whole 139550, 139578, 139588; the frame flag is the coroutine's own store.
    def counters(): return [o.w(a) for a in (0x123a0f0, 0x123a0f4, 0x123a0f8, 0x123a0fc, 0x123a17c)]
    o.run(0x139550); p.write(0x123a17c, 0, 4); assert native.ask('G', 0, 0) == counters()
    for case in range(1500):
        kind = rng.choice((1, 2, 3, 3, 3, 3)) if case % 97 else 0
        value = rng.choice((0, 1, 12, 40, 250, 600))
        if kind == 0: o.run(0x139550)
        elif kind == 1: p.write(0x123a17c, 1, 4)
        elif kind == 2: o.run(0x139578)
        else: o.run(0x139588, value)
        assert native.ask('G', kind, value) == counters(), case
        done['damage_counter'] += 1
    # Key history: whole 13a160, 13a1b0 and 13a030 on a fixture actor.
    def history(): return [o.w(0x123a100), o.w(0x123a104)]+[p.read(0x123a108+2*i, 2) for i in range(24)]+[p.read(0x123a138+2*i, 2) for i in range(24)]
    o.run(0x13a160); assert native.ask('H', 0) == history()
    offsets = [0x2dc, 0x2e0, 0x2e4, 0x2e8, 0x2ec, 0x2f0, 0x41c, 0x418, 0x414, 0x420, 0x388, 0x410, 0x424, 0x428, 0x42c]
    p.write(G, 9, 4); p.write(0x123a0dc, 0, 4); clear_actor(); p.write(BODY+0x30, 1, 4)
    for case in range(2500):
        r = rng.random()
        if r < 0.01: o.run(0x13a160); got = native.ask('H', 0)
        elif r < 0.5:
            mask = rng.choice((0x10, 0x10, 0x10, 0, 4, 0x14, 0x204, 0x4000, 0x10200, rng.getrandbits(15)))
            if rng.random() < 0.02:
                for _ in range(0x7a): o.run(0x13a1b0, 0x10); native.ask('H', 1, 0x10)
            o.run(0x13a1b0, mask); got = native.ask('H', 1, mask)
        else:
            features = [rng.choice((0, 0, 0, 1, 5)) for _ in offsets]
            if rng.random() < 0.4: features = [0]*10+[1]+[0]*4
            for off, value in zip(offsets, features): p.write(actor+off, value, 4)
            o.run(0x13a030, 0); got = native.ask('H', 2, *features)
        assert got == history(), case
        done['key_history'] += 1
    # 141dd0 whole: the two integers handed to sprintf (317a10).
    for case in range(200):
        clear_actor(); context()
        index = [rng.choice((0, 1, 59, 60, 599, 600, 601, 719)), rng.choice((0, 30, 61, 340, 600, 700))]
        for seat in (0, 1): p.write(ACTORS+0xf2c*seat+0x2c0, index[seat], 4)
        seen = []
        def obs(pc):
            if pc == 0x317a10: seen.append([{0x5e9bc0: 1, 0x5e9bd0: 0}[p.registers[5]], signed(p.registers[6], 32), signed(p.registers[7], 32)])
        o.run(0x141dd0, observe=obs)
        assert native.ask('P', *index) == ([1]+seen[0] if seen else [0, 0, 0, 0]), (case, seen)
        done['clock'] += 1; done['clock_shown'] += len(seen)
    # 13fb2c..13fbd4 reset control, 149634..1496ac sampling parameters, 149790..1497d0 index advance.
    for case in range(800):
        clear_actor(); context()
        seat = rng.randrange(2); a = ACTORS+0xf2c*seat
        flags, kind, index = rng.choice((0, 1, 2, 4, 8, 10, 12, 5)), rng.randrange(2), rng.choice((0, 5, 598, 599, 600, 718, 719, 720))
        state, positive = rng.choice((1, 3, 4, 5)), rng.choice((0, 0, 1))
        def load():
            for off, value in ((0x240, flags), (0xa20, kind), (0x2c0, index)): p.write(a+off, value, 4)
            p.write(BATTLE, state, 4); p.write(BATTLE+0x18, positive, 4)
        load(); slice_(0x149634, (0x1496ac, 0x1496b0), [(17, a)])
        port, playback, slot = p.registers[16], p.registers[18], signed(p.registers[22], 32)
        running = o.run(0x141820)
        load(); slice_(0x149790, (0x1497d0, 0x1497d4), [(17, a)])
        advanced = o.w(a+0x2c0)
        load(); p.write(BATTLE+0x280+0x108*seat, 55, 4)
        slice_(0x13fb2c, (0x13fbd4, 0x13fbd8, 0x13fd30), [(17, seat), (19, seat+1), (23, 0x4d0000)])
        single = int(o.w(BATTLE+0x280+0x108*seat) == 1)
        want = [single, p.read(a+0x240, 4), o.w(a+0xa20), port, slot, playback, advanced]
        assert native.ask('V', flags, kind, seat, index, running) == want, (case, flags, kind, want)
        done['recording'] += 1
    # 12dbd0..12dc30 character page routing (slice): port in a0 at the pad read, or one of the two early returns.
    for case in range(800):
        mode, seat = rng.choice((9, 10, 9, 10, 3, 6)), rng.randrange(2)
        committed, delay = [rng.choice((0, 1, 1, 2)), rng.choice((0, 1, 1, 2))], rng.choice((10, 2, 1, 0, -3))
        p.write(G, mode, 4); p.write(0x4c8294, delay, 4)
        for s in (0, 1): p.write(0x456890+0x30*s+0x10, committed[s], 4)
        stop = slice_(0x12dbd0, (0x12dc30, 0x12de48, 0x12de4c), [(4, seat), (18, seat)])
        port = signed(p.registers[4], 32) if stop == 0x12dc30 else -1
        assert native.ask('Y', mode, seat, *committed, delay) == [port, o.w(0x4c8294)], (case, mode, seat, committed, delay, port)
        done['character_route'] += 1; done['character_frozen'] += int(port < 0)
    # Whole 134e48: a confirm on exactly one port advances the phase only when that port is the routed one.
    PHASE = SCRATCH
    p.write(0x4c8288, 1, 4); p.write(0x4c8280, 0, 4)      # 127f68: the page accepts input
    for case in range(1200):
        mode, seat, submode = rng.choice((9, 10, 9, 10, 3, 6)), rng.randrange(2), 3 if case % 4 else 2
        kind = rng.choice(('spirit', 'second', 'stage', 'item'))
        progress, spirit = [rng.randrange(0, 4), rng.randrange(0, 4)], [rng.choice((0, 5, 6, 6)), rng.choice((0, 5, 6, 6))]
        if kind == 'spirit': progress[seat] = 0; phase = 2
        elif kind == 'second': progress[seat] = 1; spirit[seat] = 6; phase = 6
        elif kind == 'stage': progress[seat] = rng.choice((1, 2, 3)); spirit[seat] = 0; phase = 0x14
        else: progress[seat] = rng.choice((1, 2)); spirit[seat] = 0; phase = 0xd
        # 135140: the item-option page belongs to seat g+0x10 and precedes the stage page for that seat.
        owner = seat if kind == 'item' or submode == 3 else seat ^ 1
        p.write(G, mode, 4); p.write(G+0xa0, submode, 4); p.write(G+0x10, owner, 4)
        for s in (0, 1):
            p.write(0x4c8d18+0x34*s+0x2c, progress[s], 4); p.write(0x456890+0x30*s+8, spirit[s], 4); p.write(0x456890+0x30*s, 0, 4)
        pressed = rng.randrange(2)
        for port in (0, 1):
            for off in (0, 4, 8): p.write(0x1237cc8+12*port+off, 0x200 if port == pressed else 0, 4)
        p.write(PHASE, phase, 4); p.write(PHASE+4, 99, 4)
        o.run(0x134e48, seat, PHASE, PHASE+4)
        acted = o.w(PHASE) != phase
        spirit_port, stage_port, item_page = native.ask('Z', mode, seat, *progress, *spirit, submode)
        if kind in ('spirit', 'second'): want = spirit_port == pressed
        elif kind == 'stage': want = stage_port == pressed
        else: want = bool(item_page) and stage_port == pressed      # same port rule at 135168 when the page exists
        assert acted == want, (case, kind, mode, seat, progress, spirit, submode, pressed, acted, spirit_port, stage_port, item_page)
        done['spirit_route_'+kind] += 1; done['spirit_acted'] += int(acted)
    p.write(G+0xa0, 3, 4)
    tallies = ('life_floor', 'refilled', 'item_random', 'clock_shown', 'character_frozen', 'spirit_acted', 'get_up_changed')
    return dict(cases=sum(v for k, v in done.items() if k not in tallies), groups=dict(done), instructions=o.n)
