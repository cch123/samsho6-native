#!/usr/bin/env python3
"""Compare the arcade MAP scene 1c1b20 and the WALK-IN scene 1c4428 with the original tasks.

Every scenario runs the ORIGINAL entry and task code in Probe one frame at a time (map task
1c25e0; walk-in redraw task 1c43f0 followed by the coroutine 1c4568 from its yield return
address to the next 112a28 call on the task's own stack) and requires from src/arcade_map.cpp,
on every visit: the same scene / run / generator state, the same sound and exit requests, the
same fighter object calls, the same ordered primitive list (exact float bits) and, on the
painted visits, the same 640x480 frame.
"""
import argparse
import hashlib
import json
import os
import random
import struct
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import validate_menu_canvas as base
from validate_menu_canvas import bits
from character_tiles_oracle import ROOT, ASSETS
from extract_console_versus_art import ORIGINAL, PACKETS, GLYPH
from mips_probe import signed
import extract_arcade_map

REPORT = ROOT/'outputs/ss6-feasibility/arcade_map_validation.json'
RES = ROOT/'work/ss6/extracted/resources'
G, P, S, O, PADS = 0x4c3808, 0x456890, 0x12d3668, 0x43d058, 0x1237cc8
STUB = base.STUB
# Rendering-side, sound, task-kernel and disc callees replaced by `jr ra; move v0, zero`.
STUBS = dict(sound=(0x1e7c00, 0x1e7d60, 0x1e7ad0, 0x1e7b40),
             tasks=(0x118320, 0x11e3a0, 0x112a70, 0x1252f0),
             objects=(0x11fed0, 0x11d488, 0x10b640),
             camera=(0x114cb8, 0x122e98, 0x122eb8))
SCRIPT, OBJECTS, HANDLE = 0x1f40000, 0x1f50000, 0x1f48000
YIELD, STACK_TOP = 0x112a28, 0x132f780+0x1000
FADES = [(False, 0, 0), (True, 0, 0xff000000), (True, 100, 0xffffffff), (True, 175, 0xff000000), (True, 75, 0xff204080)]
OWN = (0x1e, 0x1f, 0x20, 0x22, 0x29, 0x2a, 0x2b)
CLOUDS = ((0, 5), (0x18, 4), (0x28, 3), (0x38, 5))   # offsets of the four layers inside each cloud block

DRIVER = r'''
#include "arcade_map.hpp"
#include "system_data.hpp"
#include <bit>
#include <fstream>
#include <iostream>
#include <iterator>
#include <sstream>
using namespace ss6;
template<class T> static void put(const T& v){std::cout.write(reinterpret_cast<const char*>(&v),sizeof v);}
struct Host:ArcadeObjectHost{
 std::vector<uint8_t> script;size_t at=0;std::vector<int> flags;std::vector<std::array<int32_t,7>> log;
 int create(int tag,int seat,int action,int x,int f,int colour) override{log.push_back({0,tag,seat,action,x,f,colour});flags.push_back(0);return int(flags.size())-1;}
 bool finished(int o) override{return flags.at(size_t(o))==1;}
 void restart(int o,int action) override{log.push_back({1,o,action,0,0,0,0});flags.at(size_t(o))=0;}
 void step(int o) override{log.push_back({2,o,0,0,0,0,0});flags.at(size_t(o))=script.at(at++);}
};
int main(int argc,char** argv){
 if(argc!=2)return 2;
 std::ifstream file(std::string(argv[1])+"/arcade_run.bin",std::ios::binary);
 const std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(file)),{});
 const ArcadeTables tables(bytes);
 SystemData system(argv[1]);GameRandom rng;ArcadeRun run(tables,system,rng);
 MenuCanvas canvas(argv[1]);ArcadeMapArt art(argv[1]);MenuDrawList list;
 ArcadeMapState state;ArcadeMapScene map;ArcadeWalkInScene walk;Host host;ArcadeSceneEvents ev;
 std::vector<uint8_t> pixels(640*480*4),base(pixels.size());
 for(int y=0;y<480;++y)for(int x=0;x<640;++x){auto* p=base.data()+4*(640*y+x);p[0]=x+3*y;p[1]=x^y;p[2]=4*x+y;p[3]=255;}
 std::string line;
 while(std::getline(std::cin,line)){
  std::istringstream in(line);std::string op;in>>op;
  auto u=[&]{uint32_t v;in>>v;return v;};auto i=[&]{int v;in>>v;return v;};
  if(op=="fade"){int en=i(),level=i();uint32_t c=u();canvas.setFade(en,level,c);art.setFade(en,level,c);}
  else if(op=="seed"){rng.mode=i();rng.gameSeed=u();uint64_t lo=u();rng.librarySeed=lo|uint64_t(u())<<32;}
  else if(op=="run"){
   run.game.clear();run.game.mode=i();run.game.submode=i();run.game.stage=i();run.game.transitionLock=i();
   for(auto& p:run.players){p=ArcadePlayer{};p.character=i();p.colour=i();p.stageIndex=i();p.progress=i();}
   for(auto& v:run.schedule.stages)v=int16_t(i());for(auto& v:run.schedule.opponents)v=int16_t(i());
   for(auto& v:run.schedule.rolls)v=uint8_t(i());for(auto& v:run.schedule.bonus)v=uint8_t(i());
   run.schedule.intruderDisabled=i();run.intruderFight=i();run.mapStageIndex=i();run.startHoldCounter=i();run.startHoldFlag=i();
   system.option(3)=uint8_t(i());
   host=Host{};}
  else if(op=="script"){int n=i();host.script.clear();host.at=0;for(int k=0;k<n;++k)host.script.push_back(uint8_t(i()));}
  else if(op=="freeze")run.game.challengerFreeze=i();
  else if(op=="begin"){list.beginFrame();list.colour=u();list.blend=i();list.additive=false;host.log.clear();ev={};}
  else if(op=="opening"){state.reset(art.tables(),rng);run.prepareFight();art.bindIcon(run.game.stage);}       // 1c6af8, 1c2420, 1c1ec8
  else if(op=="idle"){state.moveClouds(art.tables(),rng);}                                               // update half of 1c6b10
  else if(op=="mleave"){ArcadeMapScene::leave(run);}
  else if(op=="menter"){ev=map.enter(run,state,art,host);}
  else if(op=="mtick"){ev=map.tick(run,state,art,host);map.draw(art,canvas,list);}
  else if(op=="wenter"){walk.enter(run,art);}
  else if(op=="wtick"){uint32_t held=u(),pressed=u();int language=i(),complete=i();
   ev=walk.tick(run,state,art,host,held,pressed,language,complete);walk.draw(art,canvas,list);}
  else if(op=="flush"){
   int paint=i();
   uint32_t n=uint32_t(list.records.size());put(n);
   for(auto& r:list.records){uint8_t head[6]={uint8_t(r.kind),uint8_t(r.font),r.slot,r.blend,uint8_t(r.additive),0};put(head);put(r.glyph);put(r.colour);put(r.z);
    float g[8]={r.x,r.y,r.w,r.h,r.u,r.v,r.uw,r.vh};put(g);put(r.corner);}
   int32_t st[]={state.frame,state.pathStep,state.pathDone,state.arrivalStep,state.arrived,state.postArrival,state.exitState,state.cloudsOpened};put(st);
   put(state.layerStep);put(state.cloudStep);
   float fs[]={state.viewA,state.viewB,state.viewC,state.viewD,state.viewE,state.offsetX,state.offsetY};put(fs);
   put(state.layerY);put(state.word648);put(state.cloudX);put(state.cloudSpeed);put(state.cloudH);
   int32_t rs[]={run.game.stage,run.game.transitionLock,run.players[0].character,run.players[0].colour,run.players[0].stageIndex,run.players[0].progress,
    run.players[1].character,run.players[1].colour,run.players[1].stageIndex,run.players[1].progress,run.intruderFight,run.mapStageIndex,
    run.startHoldCounter,run.startHoldFlag,walk.exitLatch,walk.wait,rng.mode,int32_t(rng.gameSeed),int32_t(uint32_t(rng.librarySeed)),int32_t(uint32_t(rng.librarySeed>>32)),
    int32_t(list.colour),list.blend,list.depth,list.glyphs,
    ev.music,ev.voice,ev.exit.requested,ev.exit.handOff,ev.exit.kind,ev.exit.speed,int32_t(ev.exit.destructor),int32_t(uint32_t(ev.exit.next)),art.boundIcon()};put(rs);
   put(map.camera);put(walk.redrawCamera);put(walk.camera);
   uint32_t m=uint32_t(host.log.size());put(m);for(auto& e:host.log)put(e);
   if(paint){pixels=base;art.rasterise(canvas,list,pixels);std::cout.write(reinterpret_cast<const char*>(pixels.data()),pixels.size());}
   std::cout.flush();
  }
  else return 3;
 }
}
'''


def unpack4(raw):
    blob = np.frombuffer(raw, np.uint8).reshape(512, 256); out = np.empty((512, 512), np.uint8)
    out[:, ::2] = blob & 15; out[:, 1::2] = blob >> 4
    return out


class Oracle(base.Oracle):
    """validate_menu_canvas.Oracle plus the sheets, stubs and fixtures of the two scenes."""
    def __init__(self):
        self.ready = False
        super().__init__()
        p = self.p
        for group in STUBS.values():
            for pc in group: p.memory[pc:pc+8] = STUB
        word = lambda *w: struct.pack(f'<{len(w)}I', *w)
        hi = SCRIPT >> 16
        # 112670 / 1126f0 (task creation): return a scratch task record.
        for pc in (0x112670, 0x1126f0): p.memory[pc:pc+12] = word(0x3c020000 | HANDLE >> 16, 0x03e00008, 0x34420000 | HANDLE & 0xffff)
        # 11e2e8 (object allocation): bump allocator over zeroed scratch records.
        p.memory[0x11e2e8:0x11e2e8+20] = word(0x3c0f0000 | hi, 0x8de20004, 0x244e0200, 0x03e00008, 0xadee0004)
        # 120390 (action start): clears the finished flag. 120ce0 (object step): loads the flag
        # from the scenario's script, one byte per call.
        p.memory[0x120390:0x120390+8] = word(0x03e00008, 0xac8000c0)
        p.memory[0x120ce0:0x120ce0+28] = word(0x3c0f0000 | hi, 0x8dee0000, 0x91cd0000, 0x25ce0001, 0xadee0000, 0x03e00008, 0xac8d00c0)
        # Resident CLUT bank 0 as 113890 leaves it (entry 0 of every bank cleared).
        palette = bytearray((ASSETS/'obj0.pal').read_bytes())
        for i in range(0, len(palette), 32): palette[i:i+2] = bytes(2)
        p.memory[0x1e80000:0x1e80000+512] = palette; p.write(0x439b68, 0, 4)
        p.run(0x116478, [0, 128, 0x1e80000], limit=150000)
        # 113980..1139ec: the original conversion of map_main.pal into CLUT 3101.
        raw = (RES/'map_main.pal').read_bytes(); p.memory[0x1fff210:0x1fff410] = raw; p.put(2, 512)
        p.run(0x113980, stop_before=(0x1139ec,))
        # 10aa28 assigns the buffers of slots 0x29 / 0x2a.
        p.write(0x3a9680+40*0x29, 0xb24c40, 4); p.write(0x3a9680+40*0x2a, 0xc24c40, 4)
        self.indices = {}
        for slot, name in ((0x29, 'map_main'), (0x2a, 'map_cloud')):
            self.load(slot, name+'.tex')
        self.reent = p.read(0x5d1bf8, 4)
        self.icon = None; self.calls = []; self.slot_log = []; self.context = None
        self.ready = True; self.refresh()
        self.instructions = 0; self.packets = 0

    def load(self, slot, name):
        p = self.p; raw = (RES/name).read_bytes(); at = p.read(0x3a9680+40*slot, 4)
        size = p.read(0x3a9680+40*slot+4, 4); kind = p.read(0x3a9680+40*slot+12, 4)
        assert len(raw) == size*size//(1 if kind == 0x13 else 2), (hex(slot), name)
        p.memory[at:at+len(raw)] = raw
        self.indices[slot] = np.frombuffer(raw, np.uint8).reshape(size, size) if kind == 0x13 else unpack4(raw)

    def refresh(self):
        super().refresh()
        if not self.ready: return
        p = self.p
        colours = lambda at, n: np.frombuffer(p.memory, np.uint8, 4*n, at).reshape(n, 4).copy()
        chart = colours(0x1232880, 256)
        for slot, index in self.indices.items():
            if slot in (0x29, 0x2a): self.tex[slot] = chart[index]
            elif slot == 0x22: self.tex[slot] = colours(0x11e7980+64*0x30, 256)[index]
            else: self.tex[slot] = colours(0x11e7980, 16)[index]

    def watch(self, pc):
        p = self.p; r = p.registers
        if self.context is not None:
            if self.context == 'start': r[29] = STACK_TOP
            else: p.registers[:], p.registers_high[:], p.floats[:], p.lo, p.hi = self.context
            self.context = None
        if pc == 0x1149d0: self.slot_log.append((p.read(0x345178, 4), r[6] & 0xff))
        elif pc == 0x1142d8:
            # Disc read of 10aa28 supplied by the harness.
            name = bytes(p.memory[r[5]:p.memory.index(0, r[5])]).decode(); self.load(r[4] & 0xff, name.replace('.pvr', '.tex'))
            if name.startswith('map_icon'): self.icon = int(name[9:11])
        elif pc == 0x1163c0:
            name = bytes(p.memory[r[4]:p.memory.index(0, r[4])]).decode()
            # 1c1ec8 passes a record whose first word is the destination buffer.
            raw = (RES/name.replace('.pvp', '.pal')).read_bytes(); at = p.read(r[5], 4); p.memory[at:at+len(raw)] = raw
        elif pc == 0x1e7c00: self.calls.append(('music', signed(r[4], 32), signed(r[5], 32)))
        elif pc == 0x1e7d60: self.calls.append(('voice', signed(r[4], 32), signed(r[5], 32)))
        elif pc in (0x1e7ad0, 0x1e7b40, 0x112f08, 0x112f30, 0x11d488, 0x10b640, 0x118320, 0x112670, 0x1126f0):
            self.calls.append((hex(pc), *[signed(v, 32) for v in r[4:8]]))
        elif pc in (0x122e98, 0x122eb8): self.calls.append(('camera', *p.floats[12:15]))
        elif pc == 0x1c1ac0: self.calls.append(('handoff', r[4] & 0xffffffff, r[5] & 0xffffffff))
        elif pc == 0x1252f0: self.calls.append(('switch', *[v & 0xffffffff for v in r[4:8]]))
        elif pc == 0x11e2e8: self.calls.append(('alloc', signed(r[4], 32), p.read(SCRIPT+4, 4)))
        elif pc == 0x11fed0: self.calls.append(('init', r[4] & 0xffffffff, *[signed(v, 32) for v in r[5:10]]))
        elif pc == 0x120390: self.calls.append(('restart', r[4] & 0xffffffff, signed(r[5], 32)))
        elif pc == 0x120ce0: self.calls.append(('step', r[4] & 0xffffffff))

    def run(self, pc, args=(), limit=6000000, stop=()):
        value, count = self.p.run(pc, list(args), limit=limit, observe=self.watch, stop_before=stop); self.instructions += count; return value

    def word(self, at): return signed(self.p.read(at, 4), 32)
    def words(self, at, n): return [self.word(at+4*i) for i in range(n)]
    def raw(self, at, n): return [self.p.read(at+4*i, 4) for i in range(n)]

    def begin(self, colour, blend):
        self.reset(colour, blend, ascii_depth=-200.0); self.calls = []; self.slot_log = []; self.context = None

    def decode(self):
        """Queue entries in submission order: quads, 18-vertex strips and glyphs."""
        p = self.p; out = []; count = p.read(0x345178, 4); self.packets += count
        slots = {}
        for index, slot in self.slot_log: slots[index] = slot
        for i in range(count):
            a = PACKETS+i*128; q = struct.unpack_from('<16Q', p.memory, a); tag = q[0]; kind = tag & 0xfff
            assert tag >> 12 in (1, 2), hex(tag)
            if kind == 0xff2:
                n = q[4]; assert n in (4, 18), n
                v = [struct.unpack_from('<5fI', p.memory, q[3]+24*j) for j in range(n)]
                colour = q[1] & 0xffffffff; slot = slots[i]; raw = tag >> 12 == 2
                assert len({w[5] for w in v}) == 1 and len({w[2] for w in v}) == 1 and slot in OWN, (hex(slot), n)
                cbp = (q[2] >> 37) & 0x3fff
                assert cbp == (0x3101 if slot in (0x29, 0x2a) else 0x30cd if slot == 0x22 else 0x3081), (hex(slot), hex(cbp))
                key = ('quad' if n == 4 else 'strip', slot, raw, colour, bits(v[0][2]), *[bits(c) for w in v for c in (w[0], w[1], w[3], w[4])])
                out.append(dict(kind='quad' if n == 4 else 'strip', key=key, z=v[0][2], colour=colour, slot=slot, raw=raw, verts=v))
            elif kind == 0xff1:
                assert tag >> 12 == 1
                tex, uv0, xy0, uv1, xy1 = q[2:7]
                xy = lambda w: (((w & 65535)-0x6c00)//16, (((w >> 16) & 65535)-0x7900)//16)
                x, y = xy(xy0); r, b = xy(xy1); z = (xy0 >> 32) & 0x7fffffff; u, v = ((uv0 & 65535)-8)//16, ((uv0 >> 16 & 65535)-8)//16
                assert uv1-uv0 == 16*(r-x)+16*(b-y)*65536 and (xy1 >> 32) & 0x7fffffff == z and (tex >> 37) & 16383 == 0x3080
                tbp = tex & 16383; w, h = r-x, b-y
                if tbp == 0x3000:
                    font = 'half'; cols = np.arange(u, u+w); cell = (self.half[v:v+h, cols//2] >> (4*(cols % 2))) & 15
                else:
                    assert tbp == 0x1a40 and w == h == 24 and u % 24 == 0 and v % 24 == 0
                    font = 24; page = np.frombuffer(p.memory, np.uint8, 512*256, GLYPH).reshape(512, 256)
                    cols = np.arange(u, u+w); cell = (page[v:v+h, cols//2] >> (4*(cols % 2))) & 15
                out.append(dict(kind='glyph', key=('glyph', font, q[1] & 0xffffffff, bits(float(z)), x, y, w, h, u, v, cell.tobytes()),
                                z=float(z), colour=q[1] & 0xffffffff, rect=(x, y, r, b), cell=cell.copy()))
            else: raise AssertionError(hex(tag))
        return out


def native_keys(blob, oracle):
    keys = []; rows = list(struct.iter_unpack('<6BHIf16f', blob)); i = 0
    while i < len(rows):
        kind, font, slot, blend, raw, _, glyph, colour, z, *g = rows[i]
        x, y, w, h, u, v, uw, vh = g[:8]; c = g[8:]
        f32 = lambda t: bits(np.float32(t))
        if kind == 2:
            assert slot in OWN
            x1, y1, u1, v1 = c[0], c[1], np.float32(u)+np.float32(uw), np.float32(v)+np.float32(vh)
            corners = [(x, y, u, v), (x, y1, u, v1), (x1, y, u1, v), (x1, y1, u1, v1)]
            keys.append(('quad', slot, bool(raw), colour, bits(z), *[f32(t) for q in corners for t in q])); i += 1
        elif kind == 3:
            # Eight mesh cells of slot 0x29 form one 18-vertex strip of 1c32c8.
            assert slot == 0x29
            cells = rows[i:i+8]; verts = []
            for k, cell in enumerate(cells):
                assert cell[0] == 3 and cell[2] == 0x29 and cell[7] == colour and cell[8] == z
                cx, cy, cw, ch, cu, cv, cuw, cvh = cell[9:17]; cc = cell[17:]
                u1, v1 = np.float32(cu)+np.float32(cuw), np.float32(cv)+np.float32(cvh)
                verts += [(cc[0], cc[1], cu, cv), (cc[4], cc[5], u1, cv)]
                if k == 7: verts += [(cc[2], cc[3], cu, v1), (cc[6], cc[7], u1, v1)]
                else:
                    nxt = cells[k+1]
                    assert (cc[2], cc[3], cc[6], cc[7]) == (nxt[17], nxt[18], nxt[21], nxt[22]) and bits(v1) == bits(nxt[14])
            keys.append(('strip', slot, bool(raw), colour, bits(z), *[f32(t) for q in verts for t in q])); i += 8
        elif kind == 4:
            if font == 1:
                cols = np.arange(int(u), int(u+w)); cell = (oracle.half[int(v):int(v+h), cols//2] >> (4*(cols % 2))) & 15; name = 'half'
            else:
                assert font == 3
                rows24 = np.frombuffer(oracle.fonts[24], np.uint8, 12*24, glyph*312+12).reshape(24, 12)
                cols = np.arange(24); cell = (rows24[:, cols//2] >> (4*(cols % 2))) & 15; name = 24
            keys.append(('glyph', name, colour, bits(z), int(x), int(y), int(w), int(h), int(u), int(v), cell.tobytes())); i += 1
        else: raise AssertionError(kind)
    return keys


def paint_strip(oracle, q, frame):
    """Triangle-strip reference: pixel centres, affine texels, half-open edge rule (see ArcadeMapArt::rasterise)."""
    tex = oracle.tex[q['slot']]; v = q['verts']; colour = q['colour']; size = tex.shape[0]
    mod = np.array([(colour >> k) & 255 for k in (0, 8, 16, 24)], np.int32)
    f = np.float64
    for k in range(8):
        cell = v[2*k:2*k+4]
        for tri in ((0, 1, 2), (1, 2, 3)):
            (ax, ay, _, au, av, _), (bx, by, _, bu, bv, _), (cx, cy, _, cu, cv, _) = [tuple(map(f, cell[j])) for j in tri]
            area = (bx-ax)*(cy-ay)-(by-ay)*(cx-ax)
            if area == 0: continue
            if area < 0: (bx, by, bu, bv), (cx, cy, cu, cv) = (cx, cy, cu, cv), (bx, by, bu, bv); area = -area
            left, right = max(0, int(np.floor(min(ax, bx, cx)))), min(639, int(np.ceil(max(ax, bx, cx))))
            top, bottom = max(0, int(np.floor(min(ay, by, cy)))), min(479, int(np.ceil(max(ay, by, cy))))
            if right < left or bottom < top: continue
            tie = lambda dx, dy: dy > 0 or (dy == 0 and dx < 0)
            gy, gx = np.mgrid[top:bottom+1, left:right+1]
            sx = gx+0.5; sy = gy+0.5
            w0 = (cx-bx)*(sy-by)-(cy-by)*(sx-bx)
            w1 = (ax-cx)*(sy-cy)-(ay-cy)*(sx-cx)
            w2 = (bx-ax)*(sy-ay)-(by-ay)*(sx-ax)
            inside = np.ones(w0.shape, bool)
            for w, t in ((w0, tie(cx-bx, cy-by)), (w1, tie(ax-cx, ay-cy)), (w2, tie(bx-ax, by-ay))):
                inside &= (w > 0) | ((w == 0) & t)
            tu = np.floor(((w0*au+w1*bu)+w2*cu)/area).astype(int); tv = np.floor(((w0*av+w1*bv)+w2*cv)/area).astype(int)
            inside &= (tu >= 0) & (tv >= 0) & (tu < size) & (tv < size)
            if not inside.any(): continue
            view = frame[top:bottom+1, left:right+1, :3]; pixels = view[inside]
            source = np.minimum(255, tex[tv[inside], tu[inside]].astype(np.int32)*mod//128)
            if q['raw']: pixels[:] = np.minimum(255, pixels+source[..., :3])
            else: base.blend(pixels, source[..., :3], source[..., 3:])
            view[inside] = pixels


def paint(oracle, prims, frame):
    for q in sorted(prims, key=lambda item: item['z']):
        if q['kind'] == 'strip': paint_strip(oracle, q, frame)
        else: base.paint(oracle, [q], frame)
    return frame


class Session:
    def __init__(self, exe):
        self.o = Oracle()
        self.proc = subprocess.Popen([exe, ASSETS], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.lines = []
        y, x = np.mgrid[:480, :640]; self.base = np.stack((x+3*y, x ^ y, 4*x+y, np.full_like(x, 255)), axis=-1).astype(np.uint8)
        self.frames = self.primitives = self.cases = self.lists = 0; self.kinds = {}; self.slots = set()
        self.objects = {}
    def close(self):
        self.proc.stdin.close(); assert self.proc.wait() == 0
    def send(self, *parts): self.lines.append(' '.join(str(int(v)) if isinstance(v, (bool, np.integer)) else str(v) for v in parts))
    def read(self, n):
        data = self.proc.stdout.read(n)
        if len(data) != n: raise RuntimeError('Native driver stopped')
        return data
    def fade(self, enabled, level, colour):
        self.o.fade = (enabled, level, colour); self.o.refresh(); self.send('fade', int(enabled), level, colour)
    def seed(self, mode, game, library):
        p = self.o.p; p.write(0x443150, mode, 4); p.write(0x3d2e80, game, 4); p.write(self.o.reent+0xa8, library, 8)
        self.send('seed', mode, game, library & 0xffffffff, library >> 32)

    def setup(self, w):
        """Writes one run fixture to both sides and clears the object scratch."""
        p = self.o.p
        for at in range(G, G+0xa8, 4): p.write(at, 0, 4)
        p.write(G, w['mode'], 4); p.write(G+0xa0, w['submode'], 4); p.write(G+4, w['stage'], 4); p.write(G+0x2c, w['lock'], 4)
        for off in (8, 0xc, 0x10, 0x14, 0x9c): p.write(G+off, -1, 4)
        line = ['run', w['mode'], w['submode'], w['stage'], w['lock']]
        for seat, pl in enumerate(w['players']):
            for at in range(0, 0x30, 4): p.write(P+0x30*seat+at, 0, 4)
            for off, key in ((0, 'character'), (4, 'colour'), (0x14, 'index'), (0x18, 'progress')): p.write(P+0x30*seat+off, pl[key], 4)
            line += [pl['character'], pl['colour'], pl['index'], pl['progress']]
        for i in range(7):
            p.write(S+2*i, w['stages'][i], 2); p.write(S+0xe+2*i, w['opponents'][i], 2)
            p.write(S+0x1c+i, w['rolls'][i], 1); p.write(S+0x23+i, w['bonus'][i], 1)
        p.write(S+0x34, w['intruder_disabled'], 4)
        line += [*w['stages'], *w['opponents'], *w['rolls'], *w['bonus'], w['intruder_disabled']]
        for at, key in ((0x5823ac, 'intruder'), (0x582398, 'map_index'), (0x582444, 'hold_counter'), (0x582448, 'hold_flag')): p.write(at, w[key], 4)
        p.write(O+3, w['option3'], 1); p.write(0x43d052, w['language'], 1)
        line += [w['intruder'], w['map_index'], w['hold_counter'], w['hold_flag'], w['option3']]
        self.send(*line)
        p.memory[OBJECTS:OBJECTS+0x1000] = bytes(0x1000); p.write(SCRIPT+4, OBJECTS, 4); self.objects = {}
        p.write(0x58243c, 0, 4)
    def script(self, flags):
        p = self.o.p; p.memory[SCRIPT+0x10:SCRIPT+0x10+len(flags)] = bytes(flags); p.write(SCRIPT, SCRIPT+0x10, 4)
        self.send('script', len(flags), *flags)
    def freeze(self, value):
        self.o.p.write(G+0x18, value, 4); self.send('freeze', value)
    def begin(self, rng):
        colour, blend = rng.getrandbits(32), rng.randrange(2)
        self.o.begin(colour, blend); self.send('begin', colour, blend)

    def expected_state(self):
        o = self.o; p = o.p
        cloud_ints = lambda at: [v for off, n in CLOUDS for v in o.words(at+off, n)]
        cloud_raw = lambda at: [v for off, n in CLOUDS for v in o.raw(at+off, n)]
        ints = [o.word(a) for a in (0x582380, 0x582384, 0x582388, 0x58238c, 0x582390, 0x582394, 0x5823a8, 0x132f6fc)]
        ints += o.words(0x132f6a0, 4)+cloud_ints(0x132f6b0)
        floats = o.raw(0x132f5c8, 7)+o.raw(0x132f638, 5)+cloud_raw(0x132f5e8)+cloud_raw(0x132f700)+cloud_raw(0x132f650)
        run = [o.word(G+4), o.word(G+0x2c)]
        for seat in (0, 1): run += [o.word(P+0x30*seat+off) for off in (0, 4, 0x14, 0x18)]
        run += [o.word(a) for a in (0x5823ac, 0x582398, 0x582444, 0x582448, 0x582440, 0x58244c, 0x443150, 0x3d2e80)]
        seed = p.read(o.reent+0xa8, 8); run += [signed(seed & 0xffffffff, 32), signed(seed >> 32, 32)]
        return ints, floats, run

    def object_log(self):
        """Folds the observed 11e2e8 / 11fed0 / 120390 / 120ce0 calls into the native host's log format."""
        o = self.o; p = o.p; log = []; pending = None
        for call in o.calls:
            if call[0] == 'alloc': pending = call
            elif call[0] == 'init':
                at = call[1]; assert at == pending[2] and call[5] == 0, call
                self.objects[at] = len(self.objects)
                log.append([0, pending[1], call[2], call[3], call[4], call[6], ('colour', at)])
            elif call[0] == 'restart': log.append([1, self.objects[call[1]], call[2], 0, 0, 0, 0])
            elif call[0] == 'step': log.append([2, self.objects[call[1]], 0, 0, 0, 0, 0])
        for row in log:
            if isinstance(row[6], tuple): row[6] = signed(p.read(row[6][1]+0x20, 4), 32)
        return log

    def flush(self, label, paint_frame, events, draws=True, renderer=True):
        """Compares one visit. `events` = (music, voice, exit tuple of 6) expected from the observed calls."""
        o = self.o; p = o.p; prims = o.decode() if draws else []
        self.send('flush', int(paint_frame)); self.proc.stdin.write(('\n'.join(self.lines)+'\n').encode()); self.proc.stdin.flush(); self.lines = []
        count = struct.unpack('<I', self.read(4))[0]; blob = self.read(count*80)
        ints = list(struct.unpack('<29i', self.read(116))); floats = list(struct.unpack('<63I', self.read(252)))
        run = list(struct.unpack('<33i', self.read(132))); cameras = struct.unpack('<15I', self.read(60))
        entries = struct.unpack('<I', self.read(4))[0]; log = [list(struct.unpack('<7i', self.read(28))) for _ in range(entries)]
        want_ints, want_floats, want_run = self.expected_state()
        if ints != want_ints: raise AssertionError((label, 'scene words', ints, want_ints))
        if floats != want_floats: raise AssertionError((label, 'scene floats', [i for i, (a, b) in enumerate(zip(floats, want_floats)) if a != b], floats, want_floats))
        if run[:20] != want_run: raise AssertionError((label, 'run state', run[:20], want_run))
        if renderer:
            original = [signed(p.read(a, 4), 32) for a in (0x3db900, 0x3db8fc, 0x3db8f4, 0x345180)]
            if run[20:24] != original: raise AssertionError((label, 'renderer state', run[20:24], original))
        if tuple(run[24:32]) != tuple(events): raise AssertionError((label, 'events', run[24:32], events, o.calls))
        want_log = self.object_log()
        if log != want_log: raise AssertionError((label, 'object calls', log, want_log))
        if draws:
            native = native_keys(blob, o); expected = [q['key'] for q in prims]
            if native != expected:
                for i, (a, b) in enumerate(zip(native, expected)):
                    if a != b:
                        cut = lambda k: k[:-1] if k[0] == 'glyph' else k[:5]+tuple(j for j in range(5, len(k)) if j >= len(b) or j >= len(a) or a[j] != b[j])
                        raise AssertionError((label, 'primitive', i, cut(a), cut(b), a[:30], b[:30]))
                raise AssertionError((label, 'primitive count', len(native), len(expected)))
            for q in prims:
                self.kinds[q['kind']] = self.kinds.get(q['kind'], 0)+1
                if q['kind'] != 'glyph': self.slots.add(q['slot'])
            self.primitives += len(prims); self.lists += 1
        self.cases += 1
        if paint_frame:
            o.refresh()
            expected_frame = paint(o, prims, self.base.astype(np.int32)).astype(np.uint8)
            got = np.frombuffer(self.read(self.base.size), np.uint8).reshape(self.base.shape)
            if not np.array_equal(got, expected_frame):
                bad = np.any(got != expected_frame, axis=-1); y, x = map(int, np.argwhere(bad)[0])
                raise AssertionError((label, 'pixels', int(bad.sum()), x, y, got[y, x].tolist(), expected_frame[y, x].tolist()))
            self.frames += 1
        return prims, run, cameras
    def counts(self):
        return dict(cases=self.cases, lists=self.lists, frames=self.frames, primitives=self.primitives, kinds=self.kinds, slots=sorted(self.slots),
                    instructions=self.o.instructions)


# ---------------------------------------------------------------------------
def messages():
    """Speakers and pair entries of the extracted message tables (for scenario selection)."""
    raw = (ASSETS/extract_arcade_map.NAME).read_bytes(); at = len(raw)
    languages = []
    for count in (43, 49):
        size = 4+count*4*(2+extract_arcade_map.PAIRS); at -= size
        assert struct.unpack_from('<I', raw, at)[0] == count
        rows = [struct.unpack_from(f'<{2+extract_arcade_map.PAIRS}i', raw, at+4+i*4*(2+extract_arcade_map.PAIRS)) for i in range(count)]
        languages.insert(0, rows)
    return languages


def scenario(rng, index, tables):
    mode = 1+index % 2; human = mode-1
    stage_index = (0, 1, 3, 5, 2, 6, 4, 3, 5, 0, 6, 1)[index % 12]
    language = int(index % 5 == 3)
    rows = tables[language]
    speakers = [c for c in range(len(rows)) if rows[c][0] >= 0 and rows[c][1] >= 0 and c != 43]
    own = rng.choice([c for c in range(43) if c not in (11, 13, 26, 27, 33)])
    opponents = [rng.choice(speakers) for _ in range(7)]
    if index % 3 == 1:
        # A pair entry of the tables, when one exists for this listener.
        pairs = [c for c in speakers if rows[c][2+own] >= 0]
        if pairs: opponents[stage_index] = rng.choice(pairs)
    if index % 7 == 5: opponents[stage_index] = own          # mirror match: colour rule
    stages = [rng.randrange(0, 11) for _ in range(7)]
    intruder = index % 4 == 2 and stage_index in (3, 5)
    rolls = [rng.randrange(1, 101) for _ in range(7)]; bonus = [rng.randrange(0, 40) for _ in range(7)]
    if stage_index in (3, 5): rolls[stage_index] = 1 if intruder else 100; bonus[stage_index-1] = 0
    players = [dict(character=0, colour=0, index=0, progress=0), dict(character=0, colour=0, index=0, progress=0)]
    players[human] = dict(character=own, colour=rng.randrange(0, 3), index=stage_index, progress=1 if index % 3 == 0 else rng.choice((0, 2)))
    players[human ^ 1]['colour'] = rng.randrange(0, 3) if index % 7 != 5 else players[human]['colour']
    return dict(mode=mode, submode=1, stage=rng.randrange(0, 11), lock=0, players=players, stages=stages, opponents=opponents,
                rolls=rolls, bonus=bonus, intruder_disabled=0, intruder=rng.randrange(2), map_index=rng.randrange(7),
                hold_counter=0, hold_flag=int(index % 6 == 4), option3=int(index % 4 == 1), language=language, expect_intruder=intruder,
                from_opening=index % 3 == 0, seed=(rng.randrange(2), rng.randrange(1, 1 << 31), rng.getrandbits(64)))


def events_of(calls):
    music = [c[1] for c in calls if c[0] == 'music']; voice = [c for c in calls if c[0] == 'voice']
    assert len(music) <= 1 and len(voice) <= 1 and all(c[1] == 0x31 for c in voice) and all(c[2] == 0 for c in calls if c[0] == 'music')
    exits = [c for c in calls if c[0] in ('handoff', 'switch')]; assert len(exits) <= 1, calls
    if not exits: exit_words = (0, 0, 0, 0, 0, 0)
    elif exits[0][0] == 'handoff': exit_words = (1, 1, 0, 0, signed(exits[0][1], 32), signed(exits[0][2], 32))
    else: exit_words = (1, 0, signed(exits[0][1], 32), signed(exits[0][2], 32), signed(exits[0][3], 32), signed(exits[0][4], 32))
    return (music[0] if music else -1, voice[0][2] if voice else -1, *exit_words)


def scene_job(job):
    exe, seed, first, count, quick = job
    rng = random.Random(seed); s = Session(exe); o = s.o; p = o.p; tables = messages()
    stats = dict(scenarios=0, map_visits=0, walk_visits=0, frozen_visits=0, intruder_maps=0, from_opening=0, first_stage=0,
                 dialogue_exits=0, battle_exits=0, pair_messages=0, generic_messages=0, mirrored_balloons=0, fast_forwards=0,
                 start_toggles=0, fade_complete_visits=0, cloud_respawns=0, glyph_visits=0, colour_rule_changes=0)
    for index in range(first, first+count):
        w = scenario(rng, index, tables)
        s.fade(*FADES[index % len(FADES)])
        s.setup(w); s.seed(*w['seed'])
        flags = [int(rng.random() < 0.02) for _ in range(4000)]; s.script(flags)
        human = w['mode']-1
        if w['from_opening']:
            # The opening scene has run 1c6af8 (-> 1c1e30), 1c2420 and 1c1ec8, its task 1c6b10 has drawn
            # the map for some frames and its coroutine has stored progress = 1.
            o.begin(0xffffffff, 1); o.run(0x1c1e30); o.run(0x1c2420); o.run(0x1c1ec8); s.send('opening')
            for _ in range(rng.randrange(1, 40)): o.begin(0xffffffff, 1); o.run(0x1c6b10); s.send('idle')
            stats['from_opening'] += 1
        # ---- map ----------------------------------------------------------
        s.freeze(0); s.begin(rng)
        p.write(0x58243c, 0, 4); o.run(0x1c1b20); s.send('menter')
        calls = o.calls
        assert [c for c in calls if c[0] == '0x112670'] == [('0x112670', 0x14, 0x1c25e0, 0x10, 0x1770), ('0x112670', 0x1e, 0x1c1ae8, 0x11, 0x1770)]
        assert [c for c in calls if c[0] == '0x118320'][0][1] == 0x1c1de8 and p.read(0x58243c, 4) == HANDLE
        cams = [c[1:] for c in calls if c[0] == 'camera']
        assert bool([c for c in calls if c[0] == 'music']) == (not w['from_opening'])
        _, run, cameras = s.flush(('map enter', index), False, events_of(calls), draws=False, renderer=False)
        assert cameras[:5] == (*cams[0], *cams[1][:2]) and run[32] == o.icon
        intruder = o.word(0x5823ac)
        if not w['from_opening']: assert bool(intruder) == w['expect_intruder'] and (not intruder or (o.word(G+4), o.word(P+0x30*(human ^ 1))) == (3, 33))
        stats['intruder_maps'] += intruder == 1; stats['first_stage'] += w['players'][human]['index'] == 0
        frame = 0; done = False
        while not done:
            frozen = int(rng.random() < 0.04 or (frame in range(0x1c, 0x21) and index % 5 == 0 and rng.random() < 0.5))
            if frame == 97 and index % 2: s.fade(*FADES[(index+1) % len(FADES)])
            before = p.read(o.reent+0xa8, 8)
            s.freeze(frozen); s.begin(rng); o.run(0x1c25e0); s.send('mtick')
            ev = events_of(o.calls); done = bool(ev[2])
            visit = o.word(0x582380)
            shown = frame < 2 or done or visit in (0x1e, 0x1f, 0x5b, 0x5c, 0x78, 0x96, 0x97, 0x98, 0xb4, 0xd3) or frame % (11 if not quick else 37) == 0
            prims, _, _ = s.flush(('map', index, frame, visit), shown, ev)
            assert sum(q['kind'] == 'strip' for q in prims) == 8 and sum(q['kind'] == 'quad' and q['slot'] == 0x2a and q['z'] < 100 for q in prims) == 24
            stats['map_visits'] += 1; stats['frozen_visits'] += frozen; stats['cloud_respawns'] += before != p.read(o.reent+0xa8, 8)
            frame += 1; assert frame < 600
        assert o.word(0x582390) == 1 and o.word(G+0x2c) == 1 and o.word(0x5823a8) == 2
        # ---- hand-off: 1c1de8 then 1c4428 ----------------------------------
        o.begin(0xffffffff, 1); o.run(0x1c1de8); assert o.word(G+0x2c) == 0
        o.calls = []; o.run(0x1c4428)
        calls = o.calls
        assert [c[1:] for c in calls if c[0] == '0x1126f0'] == [(0x14, 0x1c4568, 0x132f780, 0x1000)]
        assert [c[1:] for c in calls if c[0] == '0x112670'] == [(0xa, 0x1c43f0, 0x10, 0x1771)]
        cams = [c[1:] for c in calls if c[0] == 'camera']
        s.send('mleave'); s.send('wenter')
        colours_before = [o.word(P+0x30*seat+4) for seat in (0, 1)]
        started = False; context = None; resume = None; frame = 0; exited = None; after = 0; presses = 0
        p.write(G+0x2c, 0, 4)
        fast = index % 4 == 0
        while True:
            frozen = int(rng.random() < 0.03)
            pressed = 0
            if rng.random() < (0.05 if fast else 0.004): pressed = rng.choice((0x1, 0x2, 0x4, 0x8, 0x200, 0x400))
            if rng.random() < 0.01: pressed |= 0x10   # a direction: not in mask 0x60f
            # After the exit request the scene keeps running under the fade; holding START there
            # reaches the 0xf toggle of 582444 / 582448.
            held = pressed | (8 if (frame//40+index) % 3 == 0 or (exited is not None and index % 2 == 0) else 0)
            complete = int(index % 6 == 1 and rng.random() < 0.02)
            for seat in (0, 1):
                p.write(PADS+0xc*seat, held if seat == human else 0, 4); p.write(PADS+0xc*seat+4, pressed if seat == human else 0, 4)
            p.write(0x3ec73c, complete, 4)
            hold = (o.word(0x582444), o.word(0x582448)); seed_before = p.read(o.reent+0xa8, 8)
            s.freeze(frozen); s.begin(rng)
            o.run(0x1c43f0)
            o.context = context if started else 'start'
            o.run(resume if started else 0x1c4568, stop=(YIELD,))
            assert o.context is None
            resume = p.registers[31] & 0xffffffff
            context = (list(p.registers), list(p.registers_high), list(p.floats), p.lo, p.hi); started = True
            s.send('wtick', held, pressed, w['language'], complete)
            ev = events_of(o.calls)
            if ev[2]:
                # 1252f0 is not executed; the harness applies its gameData+0x2c = 1 (kinds 1..3).
                p.write(G+0x2c, 1, 4); exited = ev[7]; assert ev[3:7] == (0, 2, 0, 0x1c44f0)
            glyphs = 0
            shown = (not complete) and (frame < 2 or bool(ev[2]) or frame % (13 if not quick else 41) == 0 or (o.word(0x3d3aa0) in (1, 3, 9) and frame % 4 == 0))
            prims, run, cameras = s.flush(('walk', index, frame), shown, ev, draws=not complete, renderer=not complete)
            if frame == 0:
                assert cameras[5:10] == (*cams[0], *cams[1][:2]) and cameras[10:15] == (*cams[2], *cams[3][:2])
                voice = [c for c in o.calls if c[0] == 'voice']; assert len(voice) == 1
                stats['colour_rule_changes'] += colours_before != [o.word(P+0x30*seat+4) for seat in (0, 1)]
            glyphs = sum(q['kind'] == 'glyph' for q in prims)
            balloons = [q for q in prims if q['kind'] == 'quad' and q['slot'] in (0x1f, 0x20)]
            if balloons and not after and exited is None:
                stats['mirrored_balloons'] += balloons[0]['verts'][0][3] > balloons[0]['verts'][2][3]
            stats['glyph_visits'] += glyphs > 0; stats['walk_visits'] += 1; stats['frozen_visits'] += frozen
            stats['fade_complete_visits'] += complete; stats['start_toggles'] += hold[1] != o.word(0x582448)
            stats['cloud_respawns'] += seed_before != p.read(o.reent+0xa8, 8)
            if o.word(0x3d3aa0) >= 0x9c4 and glyphs: presses += 1
            frame += 1
            if exited is not None:
                after += 1
                if after == (20 if index % 2 == 0 else 6): break
            assert frame < 2500, (index, frame, o.word(0x58244c))
        stats['fast_forwards'] += presses > 0
        dialogue = exited == 0x1c5290
        assert exited in (0x1c5290, 0x139760)
        want_dialogue = w['players'][human]['index'] in (3, 5, 6) and o.word(0x5823ac) != 1
        assert dialogue == want_dialogue, (index, hex(exited))
        stats['dialogue_exits'] += dialogue; stats['battle_exits'] += not dialogue
        if not dialogue:
            cpu = o.word(P+0x30*(human ^ 1)); own = o.word(P+0x30*human)
            pair = tables[w['language']][cpu][2+own] >= 0
            stats['pair_messages'] += pair; stats['generic_messages'] += not pair
        p.write(0x3ec73c, 0, 4)
        # Destructor 1c44f0: tag frees and the two sound stops.
        o.calls = []; o.run(0x1c44f0); assert [c[0] for c in o.calls] == ['0x1e7ad0', '0x1e7b40']
        stats['scenarios'] += 1
    s.close()
    return stats, s.counts()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--quick', action='store_true'); ap.add_argument('--scenarios', type=int, default=36)
    ap.add_argument('--only', type=int, default=None)
    args = ap.parse_args()
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ORIGINAL
    asset = (ASSETS/extract_arcade_map.NAME).read_bytes()
    assert asset == (RES/extract_arcade_map.NAME).read_bytes() and asset == extract_arcade_map.build(raw)[0], 'run extract_arcade_map.py first'
    scenarios = 6 if args.quick else args.scenarios
    workers = min(os.cpu_count() or 2, 10)
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp)/'driver.cpp'; cpp.write_text(DRIVER); exe = cpp.with_suffix('')
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp, ROOT/'src/arcade_map.cpp', ROOT/'src/arcade_run.cpp',
                        ROOT/'src/system_data.cpp', ROOT/'src/menu_canvas.cpp', ROOT/'src/console_menu.cpp', ROOT/'src/game_random.cpp',
                        ROOT/'src/scalar_float.cpp', ROOT/'src/soft_double.cpp', '-o', exe], check=True)
        if args.only is not None:
            print(scene_job((str(exe), 0x1c1b20+args.only, args.only, 1, args.quick))); return
        jobs = [(str(exe), 0x1c1b20+i, i, 1, args.quick) for i in range(scenarios)]
        with ProcessPoolExecutor(workers) as pool: parts = list(pool.map(scene_job, jobs))
    stats = {k: sum(part[0][k] for part in parts) for k in parts[0][0]}
    total = dict(cases=0, lists=0, frames=0, primitives=0, instructions=0, kinds={}, slots=set())
    for _, part in parts:
        for k in ('cases', 'lists', 'frames', 'primitives', 'instructions'): total[k] += part[k]
        for k, v in part['kinds'].items(): total['kinds'][k] = total['kinds'].get(k, 0)+v
        total['slots'] |= set(part['slots'])
    report = dict(status='passed', quick=args.quick, elf_sha256=ORIGINAL, asset=extract_arcade_map.NAME,
                  asset_sha256=hashlib.sha256(asset).hexdigest(), visits=total['cases'], identical_primitive_lists=total['lists'],
                  identical_640x480_frames=total['frames'], original_queue_entries=total['primitives'], entries_by_kind=total['kinds'],
                  sheet_slots=[hex(v) for v in sorted(total['slots'])], original_instructions=total['instructions'], **stats,
                  fade_states=len(FADES),
                  scope='Whole original 1c1b20 and, per frame, whole task 1c25e0 (1c3608, 1c3888, 1c3b78, 1c3ec8, 1c4118, 1c4230, 1c2860, '
                        '1c2920 / 1c32c8, 1c2a38, 1c2fe8, 1c31f0, 1c3260, 1c2420 with 17a548 / 17a350 / 17a410, 1c1ec8, the C library sine 30bd00 '
                        'and the libgcc double routines) until its 1c1ac0 hand-off; whole 1c1de8, 1c4428, 1c4530 and 1c44f0; per frame whole '
                        'redraw task 1c43f0 and the coroutine 1c4568 from its 112a28 return address to the next 112a28 call on the task stack '
                        '(1c6068, 1a3168 with 316b90, 1a26b0 with 113f98 / 113028 / 1130f8 / 1131d8). Runs that start from the opening use '
                        'whole 1c1e30 / 1c2420 / 1c1ec8 and the opening draw task 1c6b10 as the preceding scene. Replaced by `jr ra`: sound '
                        '(1e7c00, 1e7d60, 1e7ad0, 1e7b40; arguments observed), task kernel and scene switch (118320, 11e3a0, 112a70, 1252f0; '
                        '112670 / 1126f0 return a scratch record; the harness applies the gameData+0x2c write of 1252f0), character object '
                        'system (11fed0, 11d488, 10b640; 11e2e8 is a bump allocator, 120390 clears object+0xc0 and 120ce0 loads object+0xc0 from '
                        'a scripted byte stream, mirrored by the native ArcadeObjectHost of the driver), camera (114cb8, 122e98, 122eb8; float '
                        'arguments compared) and the two disc stubs of validate_menu_canvas.Oracle (1142d8, 1163c0), whose file contents the '
                        'harness copies into the slot buffer / palette buffer at the call. The fighters are therefore not drawn by either '
                        'side; only their object calls are compared. Primitive lists are compared entry by entry with exact float bits, with '
                        '3db900 / 3db8fc / 3db8f4 / 345180 after the visit; frames are the queue painted in ascending depth over a patterned '
                        'background: quads and glyphs by the reference painter of validate_menu_canvas.py, the 18-vertex strips of 1c32c8 by a '
                        'triangle-strip model (pixel centres, affine texels, half-open edges) implemented on both sides; queue-to-GS '
                        'translation and GS rasterisation are not executed. Visits with word 3ec73c set compare state and requests only '
                        '(1149d0 then submits nothing; the native draw is the caller\'s to suppress).')
    REPORT.write_text(json.dumps(report, indent=2)+'\n'); print(report)


if __name__ == '__main__': main()
