#!/usr/bin/env python3
"""Compare the arcade overlay / Continue / Game Over drawing with the original draw routines.

Every case runs the ORIGINAL routine in Probe, decodes the submission queue 68c3c0 and requires
(a) the same ordered primitive list from src/arcade_art.cpp and (b), on the painted cases, the
same 640x480 frame when the original packets are painted over a patterned background by the
reference painter of validate_menu_canvas.py and the native list by ArcadeArt::rasterise.
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
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import validate_menu_canvas as base
from validate_menu_canvas import bits, real, paint
from character_tiles_oracle import ROOT, ASSETS
from extract_console_versus_art import ORIGINAL
from mips_probe import signed
import extract_arcade_art
import validate_arcade_tally as tally_logic

REPORT = ROOT/'outputs/ss6-feasibility/arcade_art_validation.json'
G, BATTLE, HUD, SEATS, PADS = 0x4c3808, 0x1b00000, 0x132f3a0, 0x456890, 0x1237cc8
BAR = (0x00, 0x08, 0x10, 0x14, 0x54, 0x68, 0x7c, 0x94)
FADES = [(False, 0, 0), (True, 0, 0xff000000), (True, 100, 0xffffffff), (True, 175, 0xff000000), (True, 256, 0xff000000),
         (True, 75, 0xff204080)]
DRIVER = r'''
#include "arcade_art.hpp"
#include <bit>
#include <iostream>
#include <sstream>
using namespace ss6;
template<class T> static void put(const T& v){std::cout.write(reinterpret_cast<const char*>(&v),sizeof v);}
int main(int argc,char** argv){
 if(argc!=2)return 2;
 MenuCanvas canvas(argv[1]);ArcadeArt art(argv[1]);ArcadeTallyTables tables(argv[1]);
 MenuDrawList list;ArcadeTally t;ArcadeTallyWorld w;FreeSeatPrompt prompt;ArcadeFighterRequest object;
 std::vector<uint8_t> pixels(640*480*4),base(pixels.size());
 for(int y=0;y<480;++y)for(int x=0;x<640;++x){auto* p=base.data()+4*(640*y+x);p[0]=x+3*y;p[1]=x^y;p[2]=4*x+y;p[3]=255;}
 std::string line;
 while(std::getline(std::cin,line)){
  std::istringstream in(line);std::string op;in>>op;
  auto u=[&]{uint32_t v;in>>v;return v;};auto i=[&]{int v;in>>v;return v;};
  if(op=="fade"){int en=i(),level=i();uint32_t c=u();canvas.setFade(en,level,c);art.setFade(en,level,c);}
  else if(op=="begin"){list.beginFrame();list.colour=u();list.blend=i();list.additive=false;object={};}
  else if(op=="score"){int mode=i(),sub=i();drawArcadeScore(canvas,list,tables,art.tables(),mode,sub,i());}
  else if(op=="clock"){prompt.count2230=i();prompt.shown2234=i();}
  else if(op=="prompt"){int mode=i(),sub=i(),en=i();drawFreeSeatPrompt(canvas,list,tables,prompt,mode,sub,en,i());}
  else if(op=="E"){
   int survival,option;in>>w.clockOption13c>>w.roundClock114>>survival>>option;w.survival=survival;w.timeOption43d05d=uint8_t(option);
   for(auto& b:w.life)in>>b.x00>>b.width08>>b.lag10>>b.life14>>b.mark54>>b.mark68>>b.mark7c>>b.kind94;
   in>>w.wins28[0]>>w.wins28[1]>>w.required2c[0]>>w.required2c[1]>>w.seatRequired20[0]>>w.seatRequired20[1]
     >>w.score90>>w.sceneSwitch18>>w.postMatchMenuA4>>w.finishBonus582950;
   t=ArcadeTally{};t.enter(w);}
  else if(op=="T"){std::array<uint32_t,2> pressed;in>>pressed[0]>>pressed[1]>>w.sceneSwitch18;t.tick(pressed,w);drawArcadeTally(canvas,list,tables,t.draw);}
  else if(op=="P")t.setPaused(i());
  else if(op=="cont"){ArcadeContinueDraw d;d.frame=i();d.remaining=u();d.loserSeat=i();d.loserCharacter=i();d.loserColour=i();
   object=drawArcadeContinue(canvas,list,art.tables(),d);}
  else if(op=="over"){ArcadeGameOverDraw d;d.frame=i();int level=i();d.loserSeat=i();d.loserCharacter=i();
   object=drawArcadeGameOver(canvas,list,art.tables(),d,level);}
  else if(op=="cubic"){int a[6];for(auto& v:a)v=i();float f[2];for(auto& v:f)v=std::bit_cast<float>(u());
   put(arcadeArtCubic(a[0],a[1],a[2],a[3],a[4],a[5],f[0],f[1]));std::cout.flush();}
  else if(op=="flush"){
   int paint=i();
   uint32_t n=uint32_t(list.records.size());put(n);
   for(auto& r:list.records){uint8_t head[6]={uint8_t(r.kind),uint8_t(r.font),r.slot,r.blend,uint8_t(r.additive),0};put(head);put(r.glyph);put(r.colour);put(r.z);
    float g[8]={r.x,r.y,r.w,r.h,r.u,r.v,r.uw,r.vh};put(g);put(r.corner);}
   uint32_t st[12]={list.colour,uint32_t(list.blend),uint32_t(list.depth),uint32_t(prompt.count2230),uint32_t(prompt.shown2234),
    uint32_t(object.visible),uint32_t(object.seat),uint32_t(object.character),uint32_t(object.colour),uint32_t(object.action),
    uint32_t(object.underRecords),uint32_t(t.phase40)};put(st);
   if(paint){
    pixels=base;
    // Two passes as the scene composes them: records behind the loser object, then the rest.
    art.rasterise(canvas,list,pixels,0,object.underRecords);
    art.rasterise(canvas,list,pixels,object.underRecords);
    std::cout.write(reinterpret_cast<const char*>(pixels.data()),pixels.size());}
   std::cout.flush();
  }
  else return 3;
 }
}
'''
SCENE = 0xc00   # painter key of slot 0xc: SCENE + CLUT bank


class Oracle(base.Oracle):
    """validate_menu_canvas.Oracle plus the sheets of slots 0x0a, 0x0c and 0x28."""
    def __init__(self):
        self.ready = False
        super().__init__()
        p = self.p
        hud = (ASSETS/'obj2_16.tex').read_bytes(); p.memory[0x1c80000:0x1c80000+len(hud)] = hud
        for off, value in ((0, 0x1c80000), (4, 512), (8, 512), (12, 19), (20, 9), (24, 9), (36, 1)):
            p.write(0x3a9680+10*40+off, value, 4)
        scene = (ASSETS/'font_otherscene16.tex').read_bytes(); p.memory[0x1fc0000:0x1fc0000+len(scene)] = scene
        for off, value in ((0, 0x1fc0000), (4, 512), (8, 512), (12, 20), (20, 9), (24, 9), (36, 0)):
            p.write(0x3a9680+12*40+off, value, 4)
        coin = (ASSETS/'font_coin.tex').read_bytes(); at = p.read(0x3a9680+40*40, 4); p.memory[at:at+len(coin)] = coin
        assert p.read(0x3a9680+40*40+4, 4) == 128 and p.read(0x3a9680+40*40+36, 4) == 0
        # Resident CLUT as 113890 leaves it: obj0.pal with entry 0 of every bank cleared,
        # uploaded through the unmodified 116478 and processed by 116588 on every refresh.
        palette = bytearray((ASSETS/'obj0.pal').read_bytes())
        for i in range(0, len(palette), 32): palette[i:i+2] = bytes(2)
        p.memory[0x1e80000:0x1e80000+512] = palette; p.write(0x439b68, 0, 4)
        p.run(0x116478, [0, 128, 0x1e80000], limit=150000)
        raw = np.frombuffer(hud, np.uint8)
        clut = raw[-1024:].reshape(8, 4, 8, 4)[:, [0, 2, 1, 3]].reshape(256, 4)
        self.hud = clut[raw[:512*512]].reshape(512, 512, 4)
        raw = np.frombuffer(coin, np.uint8)
        self.coin = raw[128*128:].reshape(256, 4)[raw[:128*128]].reshape(128, 128, 4)
        blob = np.frombuffer(scene, np.uint8).reshape(512, 256)
        self.scene = np.empty((512, 512), np.uint8); self.scene[:, ::2] = blob & 15; self.scene[:, 1::2] = blob >> 4
        self.ready = True; self.refresh()
        for key, slot, bank in ((10, 10, 0), (0x28, 0x28, 0), (SCENE, 12, 0), (SCENE+1, 12, 1)):
            self.reset(); p.run(0x10add8, [slot, bank]); self.sprite(slot, 0, 0, 0, 8, 8, 0, 0, 8, 8)
            tex = p.read(base.PACKETS+16, 8); self.slots[tex & 0x3fff, (tex >> 37) & 0x3fff] = key
        assert len(self.slots) == 7, self.slots
        p.write(0x4d3d00, BATTLE, 4); p.write(0x345188, 0, 4)
        self.instructions = 0; self.packets = 0

    def refresh(self):
        super().refresh()
        if not self.ready: return
        self.tex[10] = self.hud; self.tex[0x28] = self.coin
        for bank in (0, 1):
            entries = np.frombuffer(self.p.memory, np.uint8, 64, 0x11e7980+bank*64).reshape(16, 4)
            self.tex[SCENE+bank] = entries[self.scene]

    def run(self, pc, args=(), limit=3000000, observe=None):
        value, count = self.p.run(pc, list(args), limit=limit, observe=observe); self.instructions += count; return value

    def word(self, at): return signed(self.p.read(at, 4), 32)


def native_keys(blob, oracle):
    keys = []
    for kind, font, slot, blend, raw, _, glyph, colour, z, *g in struct.iter_unpack('<6BHIf16f', blob):
        x, y, w, h, u, v, uw, vh = g[:8]; c = g[8:]
        key = SCENE+glyph if slot == 12 else slot
        if kind == 0: keys.append(('flat', colour, bits(z), int(x), int(y), int(w), int(h)))
        elif kind == 2:
            corners = [(x, y, u, v), (x, y+h, u, v+vh), (x+w, y, u+uw, v), (x+w, y+h, u+uw, v+vh)]
            keys.append(('quad', key, bool(raw), colour, bits(z), *[bits(np.float32(t)) for q in corners for t in q]))
        elif kind == 3:
            uvs = [(u, v), (u, v+vh), (u+uw, v), (u+uw, v+vh)]
            keys.append(('quad', key, bool(raw), colour, bits(z), *[bits(np.float32(t)) for i in range(4) for t in (c[2*i], c[2*i+1], *uvs[i])]))
        elif kind == 4:
            assert font == 1
            cols = np.arange(int(u), int(u+w)); cell = (oracle.half[int(v):int(v+h), cols//2] >> (4*(cols % 2))) & 15
            keys.append(('glyph', 'half', colour, bits(z), int(x), int(y), int(w), int(h), int(u), int(v), cell.tobytes()))
        else: raise AssertionError(kind)
    return keys


class Session:
    def __init__(self, exe):
        self.o = Oracle()
        self.proc = subprocess.Popen([exe, ASSETS], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.lines = []
        y, x = np.mgrid[:480, :640]; self.base = np.stack((x+3*y, x ^ y, 4*x+y, np.full_like(x, 255)), axis=-1).astype(np.uint8)
        self.frames = self.primitives = self.cases = 0; self.kinds = {}; self.slots = set()
    def close(self):
        self.proc.stdin.close(); assert self.proc.wait() == 0
    def send(self, *parts): self.lines.append(' '.join(str(int(v)) if isinstance(v, (bool, np.integer)) else str(v) for v in parts))
    def push(self):
        self.proc.stdin.write(('\n'.join(self.lines)+'\n').encode()); self.proc.stdin.flush(); self.lines = []
    def read(self, n):
        data = self.proc.stdout.read(n)
        if len(data) != n: raise RuntimeError('Native driver stopped')
        return data
    def fade(self, enabled, level, colour):
        self.o.fade = (enabled, level, colour); self.o.refresh(); self.send('fade', int(enabled), level, colour)
    def begin(self, colour=0xffffffff, blend=1):
        # 3d3aac keeps its boot value -200 (113838); nothing in these scenes calls 113828.
        self.o.reset(colour, blend, ascii_depth=-200.0); self.send('begin', colour, blend)
    def flush(self, label, paint_frame=True, extra=()):
        """Returns the native state words after comparing primitives, renderer globals and the frame."""
        o = self.o; p = o.p; prims = o.decode()
        self.send('flush', int(paint_frame)); self.push()
        count = struct.unpack('<I', self.read(4))[0]; blob = self.read(count*80); state = struct.unpack('<12I', self.read(48))
        native = native_keys(blob, o); expected = [q['key'] for q in prims]
        if native != expected:
            for i, (a, b) in enumerate(zip(native, expected)):
                if a != b: raise AssertionError((label, 'primitive', i, a[:-1] if a[0] == 'glyph' else a, b[:-1] if b[0] == 'glyph' else b))
            raise AssertionError((label, 'primitive count', len(native), len(expected)))
        original = (p.read(0x3db900, 4), p.read(0x3db8fc, 4), p.read(0x3db8f4, 4))
        if state[:3] != original: raise AssertionError((label, 'renderer state', state[:3], original))
        if tuple(extra) != state[3:3+len(extra)]: raise AssertionError((label, 'state', state, extra))
        for q in prims:
            self.kinds[q['kind']] = self.kinds.get(q['kind'], 0)+1
            if q['kind'] == 'quad': self.slots.add(q['slot'])
        self.primitives += len(prims); self.cases += 1
        if paint_frame:
            # The backdrop of 138b50 is the far end of the depth order, so the painter's
            # ascending sort reproduces the two native passes.
            expected_frame = paint(o, prims, self.base.astype(np.int32)).astype(np.uint8)
            got = np.frombuffer(self.read(self.base.size), np.uint8).reshape(self.base.shape)
            if not np.array_equal(got, expected_frame):
                bad = np.any(got != expected_frame, axis=-1); y, x = map(int, np.argwhere(bad)[0])
                raise AssertionError((label, 'pixels', int(bad.sum()), x, y, got[y, x].tolist(), expected_frame[y, x].tolist()))
            self.frames += 1
        return prims, state
    def counts(self):
        return dict(cases=self.cases, frames=self.frames, primitives=self.primitives, kinds=self.kinds, slots=sorted(self.slots),
                    instructions=self.o.instructions)


def merge(parts):
    out = dict(cases=0, frames=0, primitives=0, instructions=0, kinds={}, slots=set())
    for part in parts:
        for k in ('cases', 'frames', 'primitives', 'instructions'): out[k] += part[k]
        for k, v in part['kinds'].items(): out['kinds'][k] = out['kinds'].get(k, 0)+v
        out['slots'] |= set(part['slots'])
    out['slots'] = sorted(out['slots'])
    return out


# ---------------------------------------------------------------------------
def tally_job(job):
    """The 48 scenarios of validate_arcade_tally.py with the draws of 1c7f08 left enabled."""
    exe, seed, first, count, quick = job
    rng = random.Random(seed); s = Session(exe); o = s.o; p = o.p
    stats = dict(scenarios=0, ticks=0, phases=[0]*7, texts=0, straight_rows=0, perfect=0, paused=0)
    for index in range(first, first+count):
        world, steps = tally_logic.scenario(rng, index)
        s.fade(*FADES[index % len(FADES)] if index % 4 == 3 else FADES[0])
        p.write(BATTLE+0x13c, world['option13c'], 4); p.write(BATTLE+0x114, world['clock'], 4)
        p.write(0x123a0c0, 2 if world['survival'] else 0, 1); p.write(0x43d05d, world['option43d05d'], 1)
        for seat in (0, 1):
            for off, value in zip(BAR, world['bars'][seat]): p.write(HUD+0x98*seat+off, value, 4)
            p.write(BATTLE+0x254+0x108*seat+0x28, world['wins'][seat], 4)
            p.write(BATTLE+0x254+0x108*seat+0x2c, world['required'][seat], 4)
            p.write(SEATS+0x30*seat+0x20, world['seat_required'][seat], 4)
        p.write(G+0x90, world['score'], 4); p.write(G+0x18, world['switch'], 4); p.write(G+0xa4, world['menu'], 4)
        p.write(0x582950, world['finish'], 4)
        o.run(0x1c7ce8); s.send(tally_logic.enter_line(world))
        assert o.word(0x3d3aa0) == -1
        after = 0; last = None
        for frame, (pressed, pause, switch) in enumerate(steps[:60] if quick else steps):
            if pause is not None:
                o.run(0x1c9820 if pause else 0x1c9810); s.send('P', int(pause))
            phase = o.word(0x582940); stats['phases'][min(phase, 6)] += 1
            p.write(G+0x18, switch, 4)
            for seat in (0, 1): p.write(PADS+0xc*seat+4, pressed[seat], 4)
            s.begin(colour=rng.getrandbits(32), blend=rng.randrange(2))
            texts = []
            def observe(pc):
                if pc == 0x113028:
                    at = p.registers[4] & 0xffffffff; texts.append(bytes(p.memory[at:at+32]).split(b'\0')[0])
            o.run(0x1c7f08, observe=observe); s.send('T', pressed[0], pressed[1], switch)
            # Painted: the first frames, every phase change and a sparse sample.
            shown = frame < 2 or phase != last or frame % 23 == 0
            prims, state = s.flush(('tally', index, frame), paint_frame=shown, extra=())
            assert state[11] == o.word(0x582940) & 0xffffffff
            assert sum(q['kind'] == 'quad' for q in prims) == 247 and sum(q['kind'] == 'glyph' for q in prims) == sum(len(t.replace(b' ', b'')) for t in texts)
            last = phase; stats['ticks'] += 1; stats['texts'] += len(texts)
            stats['straight_rows'] += b'STRAIGHT' in texts; stats['perfect'] += b'PERFECT' in texts; stats['paused'] += o.word(0x582994) != 0
            if o.word(0x582948):
                after += 1
                if after == 3: break
        o.run(0x1c7d20); stats['scenarios'] += 1
    s.close()
    return stats, s.counts()


def cubic_checks(s):
    """Whole 1382a8 and 138eb0 against arcadeArtCubic."""
    o = s.o; p = o.p; rng = random.Random(0x1382a8); count = 0
    cases = [(fn, step, total, a1, a2, a3, t0) for fn, total in ((0x1382a8, 20), (0x138eb0, 50)) for step in range(total+1)
             for a1, a2, a3, t0 in ((70, 700, 4, 700), (134, 0, 268, 0), (2350, 470, 2350, 2350), (660, 132, 660, 660))]
    cases += [(rng.choice((0x1382a8, 0x138eb0)), rng.randrange(0, 60), rng.randrange(1, 60), rng.randrange(-900, 3000), rng.randrange(-900, 3000),
               rng.randrange(-900, 3000), rng.randrange(-900, 3000)) for _ in range(400)]
    for fn, step, total, a1, a2, a3, t0 in cases:
        want = signed(o.run(fn, [step, a1, a2, a3, t0, total]), 32)
        one, three = (0x5e163c, 0x5e1640) if fn == 0x1382a8 else (0x5e191c, 0x5e1920)
        # Register order a1, a3, t0, a2 = control values 0..3.
        s.send('cubic', step, total, a1, a3, t0, a2, p.read(one, 4), p.read(three, 4)); s.push()
        got = struct.unpack('<i', s.read(4))[0]
        assert got == want, (hex(fn), step, total, a1, a2, a3, t0, got, want)
        count += 1
    return count


def scene_job(job):
    exe, quick = job
    s = Session(exe); o = s.o; p = o.p; rng = random.Random(0x137d20); stats = {}
    stats['cubic_whole_1382a8_138eb0'] = cubic_checks(s)

    # 1bc098 behind the gate of 1bab38 (1bac20..1bac44 is an inline test; the gate is run as a tail slice).
    values = [0, 1, 9, 10, 99, 100, 12345, 987654321, 2147483647, -1, -9, -10, -150, -1000, -987654321, -2147483647]
    values += [rng.randrange(0, 10**rng.randrange(1, 10)) for _ in range(12 if quick else 60)]
    values += [-rng.randrange(0, 10**rng.randrange(1, 10)) for _ in range(4 if quick else 16)]
    n = 0
    for index, value in enumerate(values):
        for mode in (1, 2):
            if index % 5 == 0: s.fade(*FADES[(index//5) % len(FADES)])
            p.write(0x58223c, mode, 4); p.write(G, mode, 4); p.write(G+0x90, value, 4)
            s.begin(colour=rng.getrandbits(32), blend=rng.randrange(2))
            o.run(0x1bc098); s.send('score', mode, 0, value)
            prims, _ = s.flush(('score', mode, value)); n += 1
            # 1b9838 returns 31 for the largest values; digits left of the screen are culled by 114e98.
            assert len(prims) <= o.run(0x1b9838, [value]) and (abs(value) >= 10**9 or len(prims) == len(str(abs(value))))
    stats['score_whole_1bc098'] = n
    # Gate: 1bac1c..1bac4c, a self-contained slice of the HUD task 1bab38 (words 582240 and 58223c).
    n = 0
    for mode in range(0, 5):
        for sub in (0, 1, 2, 5, 6):
            p.write(0x58223c, mode, 4); p.write(0x582240, sub, 4); p.write(G, mode, 4); p.write(G+0xa0, sub, 4); p.write(G+0x90, 4321, 4)
            s.fade(*FADES[0]); s.begin()
            p.run(0x1bac1c, [], limit=200000, stop_before=(0x1bac4c,))
            s.send('score', mode, sub, 4321)
            s.flush(('score gate', mode, sub), paint_frame=False); n += 1
    stats['score_gate_slices_1bac1c'] = n

    # 1ba1b0: the free-seat legend with its own blink clock, 300 frames per configuration.
    n = shown = 0
    configs = [(mode, sub, enabled, latch) for mode in (0, 1, 2, 3) for sub in (0, 5) for enabled in (1, 0) for latch in (0, 1, 2)]
    for index, (mode, sub, enabled, latch) in enumerate(configs):
        s.fade(*FADES[index % len(FADES)])
        p.write(G, mode, 4); p.write(G+0xa0, sub, 4); p.write(0x582208, enabled, 4)
        p.write(G+0x2c, int(latch == 1), 4); p.write(G+0x30, int(latch == 2), 4)
        o.run(0x1ba120); s.send('clock', 10, 0)
        for frame in range(130 if quick else 300):
            if enabled and not sub and frame == 150:
                # The latch may change while the legend is up.
                latch = (latch+1) % 3; p.write(G+0x2c, int(latch == 1), 4); p.write(G+0x30, int(latch == 2), 4)
            s.begin(colour=rng.getrandbits(32), blend=rng.randrange(2))
            o.run(0x1ba1b0); s.send('prompt', mode, sub, enabled, int(latch != 0))
            prims, _ = s.flush(('prompt', mode, sub, enabled, latch, frame), paint_frame=frame % 30 == 0 or frame in (49, 50, 51, 109, 110),
                               extra=(p.read(0x582230, 4), p.read(0x582234, 4)))
            n += 1; shown += bool(prims)
    stats['prompt_whole_1ba1b0'] = n; stats['prompt_frames_with_legend'] = shown

    # 137d20(frame): every countdown value of the scene, all three seat modes for the sound gate's branch.
    n = animated = 0
    limit = 0x4eb
    remaining = list(range(limit, -1, -1)) if not quick else list(range(limit, limit-140, -1))+list(range(130, -1, -1))
    for index, r in enumerate(remaining):
        if index % 97 == 0: s.fade(*FADES[(index//97) % len(FADES)])
        mode = 1+index % 3
        p.write(G, mode, 4); p.write(0x4c8288, limit, 4); p.write(0x4c8280, limit-r, 4); p.write(G+0x10, index & 1, 4)
        for seat in (0, 1): p.write(SEATS+0x30*seat+0x10, 0, 4)   # +0x10 == 0 mutes the per-second sound request
        assert o.run(0x127f68) == r
        s.begin(colour=rng.getrandbits(32), blend=rng.randrange(2))
        o.run(0x137d20, [index]); s.send('cont', index, r, index & 1, 7, 3)
        phase = r % 60
        prims, state = s.flush(('continue', r), paint_frame=phase < 0x16 or phase % 13 == 0 or r < 3)
        assert state[5:11] == (1, index & 1, 7, 3, 0x700, 0), state
        assert len(prims) == 1+(r > 0)+(r >= 600)
        n += 1; animated += r > 0 and phase < 0x15
    stats['continue_whole_137d20'] = n; stats['continue_animated_frames'] = animated

    # 138af0(frame) for the whole scene length, with and without the level-ending backdrop.
    n = 0
    for level in (0, 1):
        for frame in range(0, 0x12e if not quick else 0xb0):
            if frame % 61 == 0: s.fade(*FADES[(frame//61+level) % len(FADES)])
            p.write(G+0x34, level, 4)
            s.begin(colour=rng.getrandbits(32), blend=rng.randrange(2))
            fades = []
            o.run(0x138af0, [frame], observe=lambda pc: fades.append(pc) if pc in (0x1170d8, 0x117170) else None)
            assert bool(fades) == (frame == 0x50)
            if fades:
                # 1170d8(-1) / 117170(1) started a fade; restore the case's fade state for the comparison.
                s.fade(*s.o.fade)
            s.send('over', frame, level, 1, 9)
            prims, state = s.flush(('game over', level, frame))
            assert state[5:11] == (1, 1, 9, 0, 0x701, level), state
            assert len(prims) == level+(frame >= 0x88)+(frame >= 0x1e)+(frame > 0x50)
            n += 1
    stats['game_over_whole_138af0'] = n
    s.close()
    return stats, s.counts()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--quick', action='store_true')
    ap.add_argument('--scenarios', type=int, default=48)
    args = ap.parse_args()
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ORIGINAL
    asset = (ASSETS/extract_arcade_art.NAME).read_bytes(); assert asset == extract_arcade_art.build(raw)[0], 'run extract_arcade_art.py first'
    scenarios = 6 if args.quick else args.scenarios
    workers = min(os.cpu_count() or 2, 8)
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp)/'driver.cpp'; cpp.write_text(DRIVER); exe = cpp.with_suffix('')
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp, ROOT/'src/arcade_art.cpp',
                        ROOT/'src/arcade_tally.cpp', ROOT/'src/menu_canvas.cpp', ROOT/'src/console_menu.cpp',
                        ROOT/'src/game_random.cpp', ROOT/'src/scalar_float.cpp', '-o', exe], check=True)
        per = -(-scenarios//max(1, workers-1))
        jobs = [(str(exe), 0x1c7f08+i, i*per, min(per, scenarios-i*per), args.quick) for i in range(workers) if i*per < scenarios]
        with ProcessPoolExecutor(workers) as pool:
            scene = pool.submit(scene_job, (str(exe), args.quick))
            parts = list(pool.map(tally_job, jobs))
            scene_stats, scene_counts = scene.result()
    tally = {k: sum(part[0][k] for part in parts) for k in ('scenarios', 'ticks', 'texts', 'straight_rows', 'perfect', 'paused')}
    phases = [sum(part[0]['phases'][i] for part in parts) for i in range(7)]
    total = merge([part[1] for part in parts]+[scene_counts])
    assert tally['scenarios'] == scenarios and (args.quick or all(phases)) and total['slots'] == [1, 10, 0x28, SCENE, SCENE+1]
    assets = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
    report = dict(status='passed', quick=args.quick, elf_sha256=ORIGINAL, asset=extract_arcade_art.NAME,
                  asset_sha256=hashlib.sha256(asset).hexdigest(),
                  cases=total['cases'], identical_primitive_lists=total['cases'], identical_640x480_frames=total['frames'],
                  original_queue_entries=total['primitives'], entries_by_kind=total['kinds'],
                  sheet_slots=[hex(v) for v in total['slots']], original_instructions=total['instructions'],
                  tally_scenarios=tally['scenarios'], tally_ticks=tally['ticks'], tally_ticks_per_phase=phases,
                  tally_text_draws=tally['texts'], tally_ticks_with_straight_row=tally['straight_rows'],
                  tally_ticks_with_perfect_label=tally['perfect'], tally_paused_ticks=tally['paused'], **scene_stats,
                  fade_states=len(FADES),
                  resources={name: hashlib.sha256((assets/name).read_bytes()).hexdigest() for name in extract_arcade_art.TEXTURES},
                  scope='Whole original 1c7ce8 + handler 1c7f08 (panel 1c8a98 = 1c8bf8/1c8df0/1c9040/1c9258/1c95a0, 113028 texts through '
                        '1130f8/10a010) over the scenarios of validate_arcade_tally.py with native ArcadeTally logic feeding drawArcadeTally; '
                        'whole 1bc098 (1ba768); whole 1ba1b0 (1ba228 / 1ba448 / 1b9880 / 1b8e28 with the blink clock 1ba148); whole 137d20 '
                        '(137d40 + 137db8 with 127f68) for every remaining value 0..0x4eb; whole 138af0 (138b50, 138ba8, 138c70, 138e18) for '
                        'frames 0..0x12d with gameData+0x34 = 0 / 1; whole 1382a8 and 138eb0. No instruction is patched beyond the two disc '
                        'stubs of validate_menu_canvas.Oracle (1142d8 texture load by name, 1163c0 palette file read), which these routines '
                        'do not call. The 1bab38 score gate is a tail slice 1bac1c..1bac4c, not whole-function evidence. Sheets are '
                        'supplied as data fixtures: obj2_16 (slot 0xa, appended CLUT), font_otherscene16 (slot 0xc, 4-bit, banks 0/1 of the '
                        'obj0 CLUT uploaded through the unmodified 116478 and processed by 116588 for every fade state) and font_coin '
                        '(slot 0x28). Primitive lists are compared entry by entry in submission order with exact float bits together '
                        'with 3db900 / 3db8fc / 3db8f4 after the routine; frames are the queue painted in ascending depth by the '
                        'reference painter of validate_menu_canvas.py over a patterned background (queue-to-GS translation and GS '
                        'rasterisation are not executed; the turned panel edges of 114118 use its inverse-affine pixel-centre model on '
                        'both sides). The loser object of Continue / Game Over (object queue 479250, actions 0x700 / 0x701) and the '
                        'stage background are not drawn by either side; only the returned request words are compared with the case. '
                        '1ba448 reads two status bytes that the empty hooks 110ae8 / 110af0 leave unwritten; Probe supplies a zeroed '
                        'stack, which selects the drawn branch.')
    REPORT.write_text(json.dumps(report, indent=2)+'\n'); print(report)

if __name__ == '__main__':main()
