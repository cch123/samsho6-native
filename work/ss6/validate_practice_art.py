#!/usr/bin/env python3
"""Compare the PRACTICE MODE overlay drawing (src/practice_art.cpp) with the original routines.

Every frame reproduces the draw sequence of the battle thread 138f48 in practice: 17c210, the
clock 141dd0, the data display 13a280 (while 2111d8()), then the whole window routine 17f790
with its logic and its draw tail. The frames are the ones the logic validator
(validate_practice_mode.py) reaches: its scripted and randomised sequences are reused unchanged,
and its per-frame comparison of the native logic module stays active. On top of that this
validator decodes the 128-byte submission queue 68c3c0 of every frame and requires from
drawPracticeDisplays + drawPracticeWindow, fed with the native logic state, (a) the same ordered
primitive list (exact float bits, glyph texel blocks) and renderer globals and (b) on sampled
frames the same 640x480 picture over a non-uniform background (reference painter of
validate_menu_canvas.py against EditArt::rasterise).
"""
import argparse
import hashlib
import json
import os
import random
import struct
import subprocess
import sys
import tempfile
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from mips_probe import signed
from extract_console_versus_art import ORIGINAL
from validate_menu_canvas import native_keys, paint, bits, real, STUB
from validate_edit_art import Machine, base_frame
from validate_practice_mode_driver import DRIVER as LOGIC_DRIVER
import validate_practice_mode as logic
import extract_practice_art

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
REPORT = ROOT/'outputs/ss6-feasibility/practice_art_validation.json'
SOURCES = ('practice_art.cpp', 'practice_mode.cpp', 'edit_art.cpp', 'spirits_edit.cpp', 'color_edit.cpp', 'edit_widgets.cpp',
           'menu_canvas.cpp', 'console_menu.cpp', 'system_data.cpp', 'game_random.cpp', 'scalar_float.cpp')
ACTORS = logic.ACTORS
# Draw routines of windows that belong to other slices (key configuration, skill list, sub-list,
# skill detail): replaced by `jr ra` so that the queue holds only what src/practice_art.cpp draws.
FOREIGN_DRAWS = {'key configuration 212478': 0x212478, 'skill list / sub-list 20ef38': 0x20ef38, 'skill detail 210298': 0x210298}


def patched_driver():
    """The logic validator's driver with the help frame, the draw calls and a binary channel on fd 3."""
    s = LOGIC_DRIVER
    def swap(old, new):
        nonlocal s
        assert s.count(old) == 1, old
        s = s.replace(old, new)
    swap('#include "practice_mode.hpp"', '#include "practice_art.hpp"\n#include <bit>\n#include <cstdlib>\n#include <memory>\n#include <unistd.h>')
    swap('    PracticeKeyHistory keys;\n', r'''    PracticeKeyHistory keys;
    MenuCanvas canvas(argv[1]);EditArt art(argv[1],canvas);EditWidgetAssets widgets(argv[1]);PracticeArtTables artTables(argv[1]);
    std::unique_ptr<EditFrame> frame;MenuDrawList list;list.asciiDepth=-200.f;EditPen pen;pen.colour=art.assets().initialTextColour;
    std::vector<uint8_t> pixels(640*480*4),base(pixels.size());
    for(int y=0;y<480;++y)for(int x=0;x<640;++x){auto* p=base.data()+4*(640*y+x);p[0]=x+3*y;p[1]=x^y;p[2]=4*x+y;p[3]=255;}
    const int channel=std::atoi(argv[2]);
    const auto emit=[channel](const void* data,size_t n){const char* p=static_cast<const char*>(data);while(n){const auto k=::write(channel,p,n);if(k<=0)std::abort();p+=k;n-=size_t(k);}};
''')
    swap('            window.init(state,help);\n', '            window.init(state,help);\n'
         '            frame=std::make_unique<EditFrame>(art.assets(),widgets,unsigned(state.localSeat()));applyPracticeHelp(*frame,help,tables);\n')
    swap('            window.begin(pad,state,who,tables);\n', '            frame->tick();\n            window.begin(pad,state,who,tables);\n')
    swap('            const auto result=window.finish(pad,sub,state,who);\n',
         '            const auto result=window.finish(pad,sub,state,who);\n            applyPracticeHelp(*frame,result.help,tables);\n')
    swap("        else if(op=='L') {", r'''        else if(op=='m') {
            std::string t;in>>t;
            frame->hasMessage=t!="-";frame->messageText.clear();
            for(size_t i=1;i+1<t.size();i+=2)frame->messageText.push_back(char(std::stoi(t.substr(i,2),nullptr,16)));
            out<<0;
        } else if(op=='d') {
            // Frame start (17c210 at 138f90), then 141dd0 and 13a280.
            std::array<int,2> index;in>>index[0]>>index[1];
            list.beginFrame();list.resetCursor();
            EditArt::Context c{list,pen,0,true};
            drawPracticeDisplays(art,artTables,c,state,damage,keys,index,tables);
            out<<0;
        } else if(op=='w') {
            int paint;in>>paint;
            EditArt::Context c{list,pen,0,true};
            const auto drawn=drawPracticeWindow(art,artTables,c,window,state,*frame,tables);
            const uint32_t n=uint32_t(list.records.size());emit(&n,4);
            for(auto& r:list.records){
                uint8_t head[6]={uint8_t(r.kind),uint8_t(r.font),r.slot,r.blend,uint8_t(r.additive),0};emit(head,6);emit(&r.glyph,2);emit(&r.colour,4);emit(&r.z,4);
                float g[8]={r.x,r.y,r.w,r.h,r.u,r.v,r.uw,r.vh};emit(g,32);emit(r.corner.data(),32);}
            const uint32_t st[11]={list.colour,uint32_t(list.blend),uint32_t(list.depth),uint32_t(list.glyphs),uint32_t(list.textDepth),
                std::bit_cast<uint32_t>(list.cursor),pen.colour,std::bit_cast<uint32_t>(list.cursorBase),uint32_t(pen.front),uint32_t(pen.middle),
                uint32_t(drawn.battleDim)};
            emit(st,sizeof st);
            if(paint){pixels=base;art.rasterise(list,pixels);emit(pixels.data(),pixels.size());}
            out<<0;
        } else if(op=='L') {''')
    return s


class Native:
    """Text requests and replies as in the logic validator; draw lists and frames on a second pipe."""
    def __init__(self, exe):
        r, w = os.pipe()
        self.proc = subprocess.Popen([exe, PACKAGE, str(w)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, pass_fds=(w,))
        os.close(w); self.binary = os.fdopen(r, 'rb')
    def ask(self, *words):
        self.proc.stdin.write(' '.join(map(str, words))+'\n'); self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line: raise RuntimeError('Native driver stopped')
        reply = list(map(int, line.split()))
        # 17f5a0 calls 139550; the logic module only flags the request (PracticeWindow::resetDamage).
        if words[0] == 'I': self.ask('G', 0, 0)
        return reply
    def request(self, *words):
        """Send a draw request; the caller reads the binary reply and then calls done()."""
        self.proc.stdin.write(' '.join(map(str, words))+'\n'); self.proc.stdin.flush()
    def done(self):
        # The driver writes its text line after the binary reply; reading it first would block
        # both sides once the reply exceeds the pipe buffer.
        if not self.proc.stdout.readline(): raise RuntimeError('Native driver stopped')
    def read(self, n):
        data = self.binary.read(n)
        if len(data) != n: raise RuntimeError('Native driver stopped')
        return data
    def close(self):
        self.proc.stdin.close(); assert self.proc.wait() == 0


class Art(logic.Window):
    """The logic validator's window oracle on a Probe that has the menu sheets, with the draws captured."""
    def __init__(self, native, rng, mode):
        self.m = m = Machine(); p = m.p
        submit = p.read(0x3ec73c, 4)
        logic.prepare = lambda: p          # Oracle.__init__ takes its Probe from here
        self.art = dict(frames=0, painted=0, primitives=0, kinds={}, display_frames=0, clock=[0, 0], dialog=0, dim_plane=0,
                        gauge_window=0, arrows=0, foreign_messages=0, battle_dim=0, history_icons=0, seen=set())
        self.ready = False
        super().__init__(native, rng, mode)
        p.write(0x3ec73c, submit, 4)       # the logic validator switches the queue off; draw for real
        p.write(0x3d3aac, bits(-200.0), 4)
        for at in FOREIGN_DRAWS.values(): p.memory[at:at+8] = STUB
        self.ready = True

    def observer(self, info):
        inner = super().observer(info)
        def obs(pc):
            if pc == 0x109de8: info['battle_dim'] = 1
            elif pc in (0x182268, 0x1820f8, 0x1827c0) and not info.get('help_ra'):
                # Message requests of the unported sub-window logic (key configuration, skill list).
                ra = self.p.registers[31] & 0xffffffff
                if not (0x17f5a0 <= ra < 0x180260 or 0x210368 <= ra < 0x2118a0): info['foreign_help'] = 1
            elif pc == 0x2118a0: info['gauge'] = 1
            elif pc == 0x17dd88: info['arrows'] = info.get('arrows', 0)+1
            inner(pc)
        return obs

    def fixture(self):
        """Random changes of the display state, through the original producers and the native logic module."""
        p, rng, native = self.p, self.rng, self.native
        p.write(0x123a17c, 1, 4); native.ask('G', 1, 0)                 # 13908c
        r = rng.random()
        if r < 0.12:
            d = rng.choice((1, 7, 12, 40, 150, 999, rng.randrange(1, 300)))
            self.run(0x139588, d); native.ask('G', 3, d)
        elif r < 0.17: self.run(0x139578); native.ask('G', 2, 0)
        elif r < 0.18: self.run(0x139550); native.ask('G', 0, 0)
        r = rng.random()
        if r < 0.45:
            directions = (0, 1, 2, 4, 8, 0x10, 0x10, 0x20, 0x40, 0x80, 0x100)
            mask = rng.choice(directions)
            for bit in (0x200, 0x400, 0x800, 0x1000, 0x2000, 0x4000):
                if rng.random() < 0.18: mask |= bit
            if rng.random() < 0.05: mask = rng.getrandbits(15)
            self.run(0x13a1b0, mask); native.ask('H', 1, mask)
        elif r < 0.46: self.run(0x13a160); native.ask('H', 0)
        self.index = [rng.choice((0, 1, 59, 60, 61, 300, 599, 600, 601, 719, rng.randrange(720))) for _ in (0, 1)]
        for seat in (0, 1): p.write(ACTORS+0xf2c*seat+0x2c0, self.index[seat], 4)

    def tick(self, key=0, other=0, label=''):
        p, m, native = self.p, self.m, self.native
        self.fixture()
        held = [other, key] if self.port else [key, other]
        self.sample(held)
        paused = self.rng.random() < 0.15
        p.write(0x123a0c4, int(paused), 4); p.write(0x123a0cc, 0, 4); p.write(0x123a0d4, 7, 4)
        # Frame start: queue reset as the scheduler performs it, then the draw sequence of 138f48.
        for a in (0x345178, 0x345180, 0x378e08, 0x3db8f8, 0x348b10): p.write(a, 0, 4)
        self.run(0x114e80); self.run(0x17c210)
        clock = int(p.read(0x345178, 4)); self.run(0x141dd0); clock = int(p.read(0x345178, 4)) > clock
        display = bool(self.run(0x2111d8))
        if display: self.run(0x13a280, 0, 2)
        before = int(p.read(0x345178, 4))
        native.ask('d', *self.index)
        info = {}; self.help = []
        self.run(0x17f790, limit=60000000, observe=self.observer(info))
        sounds = info.get('sounds', [])
        tail = self.pad(self.port)+[len(sounds)]+sounds
        tail += [p.read(0x123a0c4, 4) if not paused else int(self.w(logic.STATE) > 0), p.read(0x123a0cc, 4), info.get('lock', 0),
                 info.get('clear', 0), info.get('fill', 0), info.get('open', 0), info.get('exit', 0)]
        got = native.ask('T', *held, *self.last_edges, int(paused), info['key'], info['list'], info['sub'], info['detail'], info['cursor'])
        self.compare(got, tail, info, label or hex(key))
        if 'exit' in info: self.exits.append(info['exit'])
        if info.get('foreign_help'):
            # The message those windows left in the help frame (frame+0xa8) is an input of the native frame.
            at = p.read(0x12d3870+0xa8, 4)
            text = bytes(p.memory[at:p.memory.index(b'\0', at)]) if at else None
            native.ask('m', '-' if text is None else 'x'+text.hex())
            self.art['foreign_messages'] += 1
        state = self.w(logic.STATE); self.states[state] += 1
        # Draw comparison.
        a = self.art; a['frames'] += 1
        menu = logic.MENU
        signature = (state, self.w(logic.STATE+4), self.w(menu+0x64), self.w(menu+0x70), self.w(menu+0x14), self.w(menu+0x18),
                     self.w(logic.CONFIRM+0x14), self.w(logic.CONFIRM+0x64), display, clock, bool(self.w(logic.STATE+8)),
                     self.w(0x13738b0) if self.w(menu+0x70) else -1, self.w(menu+0x8c) if self.w(menu+0x70) else -1)
        painted = signature not in a['seen'] or a['frames'] % 11 == 0 or a['frames'] < 20
        a['seen'].add(signature)
        native.request('w', int(painted))
        prims = m.decode()
        count = struct.unpack('<I', native.read(4))[0]; blob = native.read(count*80); st = struct.unpack('<11I', native.read(44))
        pixels = native.read(640*480*4) if painted else None
        native.done()
        where = (self.mode, self.rows, label or hex(key), signature)
        have = native_keys(blob, m); want = [q['key'] for q in prims]
        if have != want:
            for i, (x, y) in enumerate(zip(have, want)):
                if x != y:
                    show = lambda k: tuple(real(v) if isinstance(v, int) and v > 0xffff and j > 1 else v for j, v in enumerate(k[:-1] if k[0] == 'glyph' else k))
                    raise AssertionError((where, 'primitive', i, len(have), len(want), show(x), show(y), [show(k) for k in have[max(0, i-3):i]]))
            raise AssertionError((where, 'primitive count', len(have), len(want)))
        expected = m.globals()+(p.read(0x4ee54c, 4), p.read(0x4ee85c, 4), p.read(0x4ee860, 4), info.get('battle_dim', 0))
        if st != expected: raise AssertionError((where, 'globals', [hex(v) for v in st], [hex(v) for v in expected]))
        if painted:
            wanted = paint(m, prims, base_frame().astype(np.int32)).astype(np.uint8)
            got_pixels = np.frombuffer(pixels, np.uint8).reshape(wanted.shape)
            if not np.array_equal(got_pixels, wanted):
                bad = np.any(got_pixels != wanted, axis=-1); y, x = map(int, np.argwhere(bad)[0])
                raise AssertionError((where, 'pixels', int(bad.sum()), x, y, got_pixels[y, x].tolist(), wanted[y, x].tolist()))
            a['painted'] += 1
        a['primitives'] += len(prims)
        for q in prims: a['kinds'][q['kind']] = a['kinds'].get(q['kind'], 0)+1
        a['display_frames'] += display; a['history_icons'] += sum(q['kind'] == 'quad' and q['slot'] == 0x2e for q in prims[:before])
        if clock: a['clock'][int(p.read(0x123a0d8, 4) != 0)] += 1
        a['dialog'] += bool(self.w(logic.CONFIRM+0x14) and self.w(logic.CONFIRM+0x18)); a['dim_plane'] += self.w(logic.STATE+8) > 0
        a['gauge_window'] += info.get('gauge', 0); a['arrows'] += info.get('arrows', 0); a['battle_dim'] += info.get('battle_dim', 0)


def job(spec):
    exe, mode, kind, seed, frames = spec
    logic.Window = Art
    native = Native(exe); rng = random.Random(seed)
    try:
        w = logic.scripted(native, rng, mode) if kind == 'scripted' else logic.randomized(native, rng, mode, frames)
    except BaseException:
        print(f'practice art job {mode} {kind} failed', file=sys.stderr); traceback.print_exc(); sys.stderr.flush(); raise
    native.close()
    a = w.art; a.pop('seen')
    print(f"practice art {mode} {kind}: {a['frames']} frames, {a['painted']} painted", file=sys.stderr, flush=True)
    return dict(mode=mode, kind=kind, states=dict(sorted(w.states.items())), exits=w.exits, instructions=w.n+w.m.instructions, **a)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--quick', action='store_true'); ap.add_argument('--jobs', type=int, default=4)
    args = ap.parse_args()
    blob, _ = extract_practice_art.extract()
    assert extract_practice_art.OUT.read_bytes() == blob == (PACKAGE/'practice_art.bin').read_bytes(), 'run extract_practice_art.py first'
    start = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp)/'driver.cpp'; exe = Path(tmp)/'driver'; cpp.write_text(patched_driver())
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp, *[ROOT/'src'/s for s in SOURCES], '-o', exe], check=True)
        specs = [(exe, mode, 'scripted', 0x17f790+mode+8, 0) for mode in (9, 10)]
        specs += [(exe, mode, 'random', 0x2109b0+mode, 250 if args.quick else 1300) for mode in (9, 10)]
        if args.quick: specs = specs[:1]+specs[3:]
        with ProcessPoolExecutor(args.jobs) as pool: cases = list(pool.map(job, specs))
    kinds = {}
    for c in cases:
        for k, v in c['kinds'].items(): kinds[k] = kinds.get(k, 0)+v
    total = lambda k: sum(c[k] for c in cases)
    states = sorted({int(s) for c in cases for s in c['states']})
    if not args.quick:
        assert states == list(range(9)), states
        assert total('dialog') and total('dim_plane') and total('gauge_window') and total('arrows') and total('battle_dim')
        assert all(sum(c['clock'][i] for c in cases) for i in (0, 1)), 'REC and PLAY clocks'
    report = dict(status='passed', quick=args.quick, elf_sha256=ORIGINAL,
                  native_sha256={n: hashlib.sha256((ROOT/'src'/n).read_bytes()).hexdigest() for n in ('practice_art.cpp', 'practice_art.hpp')},
                  asset_sha256=hashlib.sha256(blob).hexdigest(),
                  frames=total('frames'), identical_primitive_lists=total('frames'), identical_640x480_frames=total('painted'),
                  queue_entries=total('primitives'), entries_by_kind=kinds, window_states=states,
                  frames_with_data_display=total('display_frames'), history_icon_quads=total('history_icons'),
                  frames_with_rec_clock=sum(c['clock'][0] for c in cases), frames_with_play_clock=sum(c['clock'][1] for c in cases),
                  frames_with_dialog=total('dialog'), frames_with_dim_plane=total('dim_plane'),
                  gauge_window_draws=total('gauge_window'), arrow_draws=total('arrows'), battle_dim_requests=total('battle_dim'), foreign_help_messages=total('foreign_messages'),
                  original_instructions=total('instructions'),
                  stubbed={**{k: hex(v) for k, v in FOREIGN_DRAWS.items()}, 'sound request / scene switch / sound-driver stop (observed)': '0x1e7b70 0x1252f0 0x1e7ad0',
                           'disc: texture and palette by name': '0x1142d8 0x1163c0'},
                  scope='Per frame, in the order of the battle thread 138f48: queue reset (114e80), 17c210, whole 141dd0, whole 13a280 while '
                        '2111d8() is true, whole 17f790 (window logic, 180260 on two fixture actors, and the draw tail: dim plane, 182600 '
                        'help frame with 1817f0/181e88/182118/181c30, 2109b0 menu with 2118a0, 2129d0 dialog) with every primitive routine '
                        '(17c228, 17c718, 17dd88, 17e228, 17e428, 17e038, 17eed8, 1145c0, 1143e0, 1135e8, 109f08, 10a710) running down to '
                        'the queue builders. Frames are those of validate_practice_mode.py (scripted and randomised sequences for modes 9 '
                        'and 10, all nine window states, both exits), whose tick-by-tick comparison of src/practice_mode.cpp stays in '
                        'force; the native draw functions read that native logic state plus an EditFrame driven by the PracticeHelp '
                        'requests. Display inputs (damage counters through 139588/139578/139550, command history through 13a1b0/13a160, '
                        'recording indices actor+0x2c0) are randomised fixtures applied to both sides. Compared every frame: the ordered '
                        'queue (exact float bits, glyph texel blocks, sheet slot, additive tag), the renderer globals 3db900, 3db8fc, '
                        '3db8f4, 345180, 348a8c, the depth cursor 12d3850 and its base 4ee54c, the text colour 4ee548, the text-layer '
                        'words 4ee85c/4ee860 and the 109de8 request. Frames are painted from the original queue by the reference painter '
                        'of validate_menu_canvas.py over a non-uniform 640x480 background (ascending depth; the queue-to-GS translation '
                        'and GS rasterisation are not executed) and compared with EditArt::rasterise on every new combination of window '
                        'state, menu level, cursor, dialog and display flags, on the first 20 frames and on every eleventh frame. '
                        'NOT covered: the draw routines of the key-configuration window, the skill list, its sub-list and the skill '
                        'detail window are replaced by jr ra (their logic still runs), so states 5..8 are compared for the help frame, '
                        'the dim plane and the 109de8 request only, and the help messages those windows set (182268/1820f8/1827c0 called from '
                        'their own logic) are copied from the original frame object into the native EditFrame; the effect of renderer flag 3451c8 bit 0x10 (109de8) on the frame; '
                        'the depth relation between these overlays and the battle scene and HUD primitives of the same frame (no battle '
                        'is drawn; actors are memory fixtures).',
                  cases=cases)
    if not args.quick: REPORT.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('cases', 'scope')}, indent=1))
    print(f"practice art: {report['frames']} frames with identical primitive lists, {report['identical_640x480_frames']} identical painted frames, "
          f"{report['queue_entries']} queue entries, {report['original_instructions']} original instructions; {time.time()-start:.0f}s")


if __name__ == '__main__': main()
