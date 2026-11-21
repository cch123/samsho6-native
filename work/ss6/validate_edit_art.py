#!/usr/bin/env python3
"""Compare the SPIRITS EDIT / COLOR EDIT drawing (src/edit_art.cpp) with the original tasks.

Each case runs the ORIGINAL task (13ada0 or 13b1c8) visit by visit with its draw routines
executing, decodes the 128-byte submission queue 68c3c0 of every visit, and requires from the
native logic module + EditFrame + drawSpiritsEdit / drawColorEdit fed with the same pads:
(a) the same ordered primitive list (exact float bits, texel blocks of glyphs) and renderer
globals, (b) on sampled visits the same 640x480 frame (reference painter of this script against
EditArt::rasterise), (c) for COLOR EDIT the three preview object descriptions against the
objects 13bf00 / 13bfd0 / 13c4f8 wrote. EditPaletteBank is compared with whole 115d40 runs.
"""
import argparse
import hashlib
import json
import random
import struct
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from mips_probe import signed
from character_tiles_oracle import ROOT, ASSETS
from extract_console_versus_art import PACKETS, GLYPH, ORIGINAL
from validate_menu_canvas import Oracle as CanvasOracle, native_keys, paint, bits, real, STUB
import extract_edit_art

PACKAGE = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
REPORT = ROOT/'outputs/ss6-feasibility/edit_art_validation.json'
YIELD = 0x112a28
SOURCES = ('edit_art.cpp', 'spirits_edit.cpp', 'color_edit.cpp', 'edit_widgets.cpp', 'menu_canvas.cpp', 'console_menu.cpp',
           'system_data.cpp', 'game_random.cpp', 'scalar_float.cpp')
# Callees replaced by `jr ra; move v0,zero` in both tasks.
COMMON_STUBS = {
    'disc: texture and palette by name': (0x17eab0, 0x1142d8, 0x1163c0),
    'sound driver': (0x1e7b70, 0x1e7b40),
    'scene switch': (0x1252f0,),
    'memory card': (0x10f158,),
    'debug print': (0x316140,),
}
# COLOR EDIT only: the battle camera, resource slots and the fighter objects. The per-visit object
# updates 13bf00/13bfd0/13c4f8 run; only their object-engine callees are replaced.
COLOR_STUBS = {
    'preview camera and resources': (0x13f8a8, 0x11d448, 0x11d4f8, 0x11d488, 0x11d528),
    'fighter object engine': (0x11d668, 0x11d570, 0x11d908, 0x11dff8, 0x11d6c8, 0x11d868, 0x11d730),
}
OBJECTS = 0x1e00000

DRIVER = r'''
#include "edit_art.hpp"
#include <bit>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <sstream>
using namespace ss6;
template<class T> static void put(const T& v){std::cout.write(reinterpret_cast<const char*>(&v),sizeof v);}
int main(int,char** argv){
 MenuCanvas canvas(argv[1]);EditArt art(argv[1],canvas);
 EditWidgetAssets widgets(argv[1]);SpiritsEditAssets spiritAssets(argv[1]);ColorEditTables tables(argv[1]);
 SystemData data(argv[1]);GameRandom random;
 std::ifstream palFile(std::string(argv[1])+"/pal_all.bin",std::ios::binary);
 std::vector<uint8_t> pal((std::istreambuf_iterator<char>(palFile)),std::istreambuf_iterator<char>());
 std::unique_ptr<EditPaletteBank> bank;std::array<std::vector<uint8_t>,2> runtime,network;
 std::unique_ptr<SpiritsEdit> spirits;std::unique_ptr<ColorEdit> color;std::unique_ptr<EditFrame> frame;
 MenuDrawList list;EditPen pen;MenuPadRepeat repeat;std::array<uint32_t,2> last{};unsigned seat=0;
 std::vector<uint8_t> pixels(640*480*4),base(pixels.size());
 for(int y=0;y<480;++y)for(int x=0;x<640;++x){auto* p=base.data()+4*(640*y+x);p[0]=x+3*y;p[1]=x^y;p[2]=4*x+y;p[3]=255;}
 const auto fresh=[&]{list=MenuDrawList();list.asciiDepth=-200.f;pen=EditPen();pen.colour=art.assets().initialTextColour;repeat=MenuPadRepeat();last={};};
 const auto flush=[&](int paint){
  uint32_t n=uint32_t(list.records.size());put(n);
  for(auto& r:list.records){uint8_t head[6]={uint8_t(r.kind),uint8_t(r.font),r.slot,r.blend,uint8_t(r.additive),0};put(head);put(r.glyph);put(r.colour);put(r.z);
   float g[8]={r.x,r.y,r.w,r.h,r.u,r.v,r.uw,r.vh};put(g);put(r.corner);}
  uint32_t st[7]={list.colour,uint32_t(list.blend),uint32_t(list.depth),uint32_t(list.glyphs),uint32_t(list.textDepth),
   std::bit_cast<uint32_t>(list.cursor),pen.colour};put(st);
  if(paint){pixels=base;art.rasterise(list,pixels);std::cout.write(reinterpret_cast<const char*>(pixels.data()),pixels.size());}
 };
 std::string line;
 while(std::getline(std::cin,line)){
  std::istringstream in(line);std::string op;in>>op;
  auto num=[&]{long long v=0;in>>v;return v;};
  if(op=="fade"){int en=int(num()),level=int(num());uint32_t c=uint32_t(num());canvas.setFade(en,level,c);art.setFade(en,level,c);}
  else if(op=="bright")canvas.setBrightness(int(num()));
  else if(op=="SI"){
   seat=unsigned(num());data.option(0x95)=uint8_t(num());unsigned long long seed;in>>seed;random.librarySeed=seed;
   for(unsigned i=0;i<128;++i)data.image()[SystemData::records4d7068+i]=uint8_t(num());
   fresh();spirits=std::make_unique<SpiritsEdit>(data,spiritAssets,widgets,random);
   frame=std::make_unique<EditFrame>(art.assets(),widgets,seat);
  } else if(op=="ST"){
   const std::array<uint32_t,2> held{uint32_t(num()),uint32_t(num())};const int paint=int(num());
   const auto pads=repeat.sample(held,{held[0]&~last[0],held[1]&~last[1]});last=held;
   frame->tick();spirits->tick(pads[seat]);frame->follow(*spirits);
   list.beginFrame();
   drawSpiritsEdit(art,list,pen,*spirits,*frame,seat,data.option(0x7e)!=0);
   flush(paint);
  } else if(op=="CI"){
   seat=unsigned(num());const int locks=int(num());
   data=SystemData(argv[1]);
   for(int i=0;i<locks;++i){const int c=int(num());data.option(0x16+size_t(c))=uint8_t(num());}
   fresh();bank=std::make_unique<EditPaletteBank>(tables,data,pal);
   color=std::make_unique<ColorEdit>(tables,data,pal,*bank);
   frame=std::make_unique<EditFrame>(art.assets(),widgets,seat);
  } else if(op=="CT"){
   const std::array<uint32_t,2> held{uint32_t(num()),uint32_t(num())};const int paint=int(num());
   const auto pads=repeat.sample(held,{held[0]&~last[0],held[1]&~last[1]});last=held;
   frame->tick();
   for(const auto& e:color->tick({held[seat],pads[seat].pressed,pads[seat].repeat}))frame->apply(e);
   list.beginFrame();
   const auto preview=drawColorEdit(art,list,pen,*color,tables,*frame,widgets,seat,data.option(0x7e)!=0);
   flush(0);
   for(const auto& o:preview){
    uint32_t w[9]={uint32_t(o.hidden),uint32_t(o.flip),uint32_t(o.character),uint32_t(o.action),uint32_t(o.record),
     std::bit_cast<uint32_t>(o.x),std::bit_cast<uint32_t>(o.y),std::bit_cast<uint32_t>(o.depth),o.paletteKey};put(w);}
   uint32_t cache[3]={0,0,0};
   for(auto v:bank->words()[0])cache[0]=cache[0]*131+v;
   for(auto v:bank->words()[1])cache[1]=cache[1]*131+v;
   for(unsigned i=0;i<512;++i)cache[2]=cache[2]*131+bank->store()[i];
   put(cache);
   if(paint){pixels=base;art.rasterise(list,pixels);std::cout.write(reinterpret_cast<const char*>(pixels.data()),pixels.size());}
  } else if(op=="PI"){
   data=SystemData(argv[1]);
   for(unsigned i=0;i<0x6180;++i)data.image()[4+i]=uint8_t(i*7+3+(i>>8)*5);
   for(unsigned s=0;s<2;++s){
    runtime[s].resize(0x6180);network[s].resize(0x60);
    for(unsigned i=0;i<0x6180;++i)runtime[s][i]=uint8_t(i*11+5+s*77+(i>>8)*3);
    for(unsigned i=0;i<0x60;++i)network[s][i]=uint8_t(i*13+9+s*31);
   }
   bank=std::make_unique<EditPaletteBank>(tables,data,pal);
   for(unsigned s=0;s<2;++s){bank->setRuntime(s,runtime[s]);bank->setNetwork(s,network[s]);}
  } else if(op=="PR"){bank->reset();uint32_t z=0;put(z);
  } else if(op=="PF"){bank->beginFrame();uint32_t z=0;put(z);
  } else if(op=="PK"){
   const uint32_t key=uint32_t(num());const int b=int(num());
   const int row=bank->resolve(key,b);
   uint32_t out[2+16]={uint32_t(row),0};
   if(row>=0){const auto c=bank->colours(row);for(unsigned i=0;i<16;++i)out[2+i]=c[i];}
   uint32_t h[3]={0,0,0};
   for(unsigned k=0;k<3;++k)for(auto v:bank->words()[k])h[k]=h[k]*131+v;
   put(out);put(h);
  } else return 3;
  std::cout.flush();
 }
}
'''


class Machine(CanvasOracle):
    """Probe with the menu sheets, texture slot 5 and one task on its own stack."""
    def __init__(self):
        self.gauge = None
        super().__init__()
        p = self.p
        # 12f050: "ps2_gage_1_2_3_all.pvr" on slot 5, its 32-bit CLUT at bank 0x300 (1163c0 + 116478 + 10add8).
        raw = (ASSETS/'ps2_gage_1_2_3_all.tex').read_bytes(); addr = 0x1f40000
        p.memory[addr:addr+len(raw)] = raw
        for o, v in [(0, addr), (4, 1024), (8, 1024), (12, 19), (20, 10), (24, 10), (36, 0)]: p.write(0x3a9680+5*40+o, v, 4)
        pal = (ASSETS/'ps2_gage_1_2_3_all.pal').read_bytes(); at = 0x1600000; dest = at+0x2000
        p.memory[at:at+len(pal)] = pal
        for a, v in [(0x439b68, 1), (0x43cc60, dest), (0x3ebf28, at)]: p.write(a, v, 4)
        p.run(0x116478, [0x300, 256, dest], limit=100000); p.run(0x10add8, [5, 0x30])
        self.gauge = np.frombuffer(raw, np.uint8).reshape(1024, 1024)
        self.refresh()
        self.reset(); self.sprite(5, 0, 0, 0, 8, 8, 0, 0, 8, 8)
        tex = p.read(PACKETS+16, 8); self.slots[tex & 0x3fff, (tex >> 37) & 0x3fff] = 5
        assert len(self.slots) == 4
        self.instructions = 0; self.packets = 0
        self.hooks = {}; self.context = None; self.started = False; self.last = [0, 0]

    def refresh(self):
        super().refresh()
        if self.gauge is not None:
            self.tex[5] = np.frombuffer(self.p.memory, np.uint8, 1024, 0x11e7980+4*0x300).reshape(256, 4)[self.gauge]

    def stub(self, groups):
        for group in groups.values():
            for pc in group: self.p.memory[pc:pc+8] = STUB

    # --- task ----------------------------------------------------------
    def task(self, entry, resume, stack_top):
        self.entry, self.resume, self.stack_top = entry, resume, stack_top
        self.p.write(0x443150, 1, 4)
        def palette(pc):
            # 1ce478 would upload the palette file 1163c0 did not read; the sheet CLUT is already resident.
            if 0x1ce478 <= (self.p.registers[31] & 0xffffffff) < 0x1ce570: self.p.registers[5] = 0
        self.hooks[0x116478] = palette

    def watch(self, pc):
        p = self.p
        if self.context is not None:
            # The EE kernel resumes the task thread with its saved context.
            if self.context == 'start': p.registers[29] = self.stack_top
            else: p.registers[:], p.registers_high[:], p.floats[:], p.lo, p.hi = self.context
            self.context = None
        hook = self.hooks.get(pc)
        if hook: hook(pc)

    def visit(self, held):
        p = self.p
        for s, h in enumerate(held):
            p.write(0x443568+4*s, h, 4); p.write(0x443570+4*s, self.last[s], 4)
            self.instructions += p.run(0x117fd8, [s], limit=100000)[1]
        self.last = list(held)
        # Per-frame reset of the queue as the scheduler performs it.
        for a in (0x345178, 0x345180, 0x378e08, 0x3db8f8, 0x348b10): p.write(a, 0, 4)
        p.run(0x114e80)
        self.context = self.saved if self.started else 'start'
        _, n = p.run(self.resume if self.started else self.entry, [], limit=40000000, observe=self.watch, stop_before=(YIELD,))
        self.instructions += n
        assert (p.registers[31] & 0xffffffff) == self.resume and self.context is None
        self.saved = (list(p.registers), list(p.registers_high), list(p.floats), p.lo, p.hi)
        self.started = True

    def globals(self):
        p = self.p
        return tuple(p.read(a, 4) for a in (0x3db900, 0x3db8fc, 0x3db8f4, 0x345180, 0x348a8c, 0x12d3850, 0x4ee548))

    def decode(self):
        """As the menu canvas decoder, with four-vertex flat strips of 1147d8 split into their two triangles."""
        p = self.p; out = []
        count = p.read(0x345178, 4); self.packets += count
        for i in range(count):
            a = PACKETS+i*128
            q = struct.unpack_from('<16Q', p.memory, a); tag = q[0]; kind = tag & 0xfff
            assert tag >> 12 in (1, 2), hex(tag)
            if kind == 0xff3:
                n = q[15]; assert n in (3, 4)
                pts = []; colours = set(); depths = set()
                for j in range(n):
                    colour, xyz = q[1+2*j] & 0xffffffff, q[2+2*j]
                    pts.append((signed(((xyz & 65535)-0x6c00) & 0xffffffff, 32)//16, signed((((xyz >> 16) & 65535)-0x7900) & 0xffffffff, 32)//8))
                    colours.add(colour); depths.add(xyz >> 32)
                    assert ((xyz & 65535)-0x6c00) % 16 == 0 and (((xyz >> 16) & 65535)-0x7900) % 8 == 0
                assert len(colours) == len(depths) == 1 and tag >> 12 == 1
                colour = colours.pop(); z = float(depths.pop())
                (x, y), (x1, y1) = pts[0], pts[-1]
                if n == 4 and pts == [(x, y), (x, y1), (x1, y), (x1, y1)]:
                    out.append(dict(kind='flat', key=('flat', colour, bits(z), x, y, x1-x, y1-y), z=z, colour=colour, rect=(x, y, x1, y1)))
                else:
                    for tri in ([pts[:3]] if n == 3 else [pts[:3], pts[1:]]):
                        out.append(dict(kind='tri', key=('tri', colour, bits(z), *sum(tri, ())), z=z, colour=colour, pts=list(tri)))
            elif kind == 0xff2:
                assert q[4] == 4
                v = [struct.unpack_from('<5fI', p.memory, q[3]+24*j) for j in range(4)]
                colour = q[1] & 0xffffffff
                assert len({w[5] for w in v}) == 1 and len({w[2] for w in v}) == 1
                slot = self.slots[q[2] & 0x3fff, (q[2] >> 37) & 0x3fff]; raw = tag >> 12 == 2
                out.append(dict(kind='quad', key=('quad', slot, raw, colour, bits(v[0][2]), *[bits(c) for w in v for c in (w[0], w[1], w[3], w[4])]),
                                z=v[0][2], colour=colour, slot=slot, raw=raw, verts=v))
            elif kind == 0xff1:
                assert tag >> 12 == 1
                tex, uv0, xy0, uv1, xy1 = q[2:7]
                xy = lambda w: (signed(((w & 65535)-0x6c00) & 0xffffffff, 32)//16, signed((((w >> 16) & 65535)-0x7900) & 0xffffffff, 32)//16)
                x, y = xy(xy0); r, b = xy(xy1); z = (xy0 >> 32) & 0x7fffffff; u, v = ((uv0 & 65535)-8)//16, ((uv0 >> 16 & 65535)-8)//16
                assert uv1-uv0 == 16*(r-x)+16*(b-y)*65536 and (xy1 >> 32) & 0x7fffffff == z and (tex >> 37) & 16383 == 0x3080
                base = tex & 16383; w, h = r-x, b-y
                if base == 0x3000:
                    font = 'half'; cols = np.arange(u, u+w)
                    cell = (self.half[v:v+h, cols//2] >> (4*(cols % 2))) & 15
                else:
                    assert base == 0x1a40 and w == h and w in (20, 24) and u % 24 == 0 and v % 24 == 0
                    font = w; page = np.frombuffer(p.memory, np.uint8, 512*256, GLYPH).reshape(512, 256)
                    cols = np.arange(u, u+w); cell = (page[v:v+h, cols//2] >> (4*(cols % 2))) & 15
                out.append(dict(kind='glyph', key=('glyph', font, q[1] & 0xffffffff, bits(float(z)), x, y, w, h, u, v, cell.tobytes()),
                                z=float(z), colour=q[1] & 0xffffffff, rect=(x, y, r, b), cell=cell.copy()))
            else: raise AssertionError(hex(tag))
        return out


def spirits_machine(seat, slots8, seed, table):
    m = Machine(); p = m.p
    m.stub(COMMON_STUBS)
    m.task(0x13ada0, 0x13af48, 0x124a1c0+0x6000)
    p.write(0x4c3808, 0xf+seat, 4); p.write(0x4c38a8, 0, 4); p.write(0x43d0ed, slots8, 1)
    p.write(p.read(0x5d1bf8, 4)+0xa8, seed, 8)
    p.memory[0x4d7068:0x4d7068+128] = bytes(table)
    m.state = lambda: (signed(p.registers[21], 32), signed(p.registers[16], 32))
    return m


def color_machine(seat, locks):
    m = Machine(); p = m.p
    m.stub(COMMON_STUBS); m.stub(COLOR_STUBS)
    m.task(0x13b1c8, 0x13b6ec, 0x12621c0+0x4000)
    image = bytearray((PACKAGE/'save_default.bin').read_bytes())
    for c, v in locks: image[0x618c+0x16+c] = v
    p.memory[0x5735c8:0x5735c8+len(image)] = image
    p.memory[0x43d058:0x43d058+0x98] = image[0x618c:0x6224]
    for i in range(24):
        for at, v in [(0x439a48, -1), (0x439aa8, 0), (0x439b08, 0)]: p.write(at+i*4, v, 4)
    # 11e2e8 allocates the three preview objects; hand out distinct zeroed blocks.
    p.memory[0x11e2e8:0x11e2e8+12] = struct.pack('<III', 0x3c0201f0, 0x03e00008, 0x8c420000)
    p.memory[OBJECTS:OBJECTS+0xc00] = bytes(0xc00)
    p.write(0x4c3808, 0x10 if seat else 0xf, 4); p.write(0x4c38a8, 0, 4)
    m.allocated = 0; m.loaded = 0; m.depth = {}; m.actions = {}
    r = p.registers
    obj = lambda: ((r[4] & 0xffffffff)-OBJECTS)//0x400
    def allocate(pc):
        p.write(0x1f00000, OBJECTS+0x400*m.allocated, 4); m.allocated += 1
    def load(pc): m.loaded = signed(r[4], 32)
    # Stores of the replaced object engine that the three update routines read back, written as
    # the originals write them: 11d570(obj, b, x, y, flags) -> 11fef8: +14 = fighter of resource
    # slot 1, +1c = fighter*5, +24 = 0, +40/+44 = float(x), float(y); 11d668(obj, id, x, y, flags)
    # -> 1202e8: +14 = id, +1c = id*5, +40/+44; 11d908(obj, action, ..) on a slot object: +24 = action.
    def place(pc):
        o = r[4] & 0xffffffff
        for at, v in ((0x14, m.loaded), (0x1c, m.loaded*5), (0x24, 0), (0x40, bits(float(signed(r[6], 32)))), (0x44, bits(float(signed(r[7], 32))))):
            p.write(o+at, v, 4)
    def portrait(pc):
        o = r[4] & 0xffffffff; ident = signed(r[5], 32)
        for at, v in ((0x14, ident), (0x1c, ident*5), (0x40, bits(float(signed(r[6], 32)))), (0x44, bits(float(signed(r[7], 32))))):
            p.write(o+at, v, 4)
    def action(pc):
        o = r[4] & 0xffffffff; m.actions[obj()] = signed(r[5], 32)
        if obj(): p.write(o+0x24, r[5] & 0xffffffff, 4)
    def depth(pc): m.depth[obj()] = p.floats[12] & 0xffffffff
    m.hooks.update({0x11e2e8: allocate, 0x13bed0: load, 0x11d570: place, 0x11d668: portrait, 0x11d908: action, 0x11dff8: depth})
    m.state = lambda: (signed(p.registers[19], 32), signed(p.registers[21], 32))
    return m


class Native:
    def __init__(self, exe):
        self.proc = subprocess.Popen([exe, PACKAGE], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    def send(self, *parts):
        self.proc.stdin.write((' '.join(str(int(v)) if isinstance(v, (bool, np.integer)) else str(v) for v in parts)+'\n').encode())
        self.proc.stdin.flush()
    def read(self, n):
        data = self.proc.stdout.read(n)
        if len(data) != n: raise RuntimeError('Native driver stopped')
        return data
    def records(self):
        count = struct.unpack('<I', self.read(4))[0]; blob = self.read(count*80); state = struct.unpack('<7I', self.read(28))
        return blob, state
    def close(self):
        self.proc.stdin.close(); assert self.proc.wait() == 0


BASE = None
def base_frame():
    global BASE
    if BASE is None:
        y, x = np.mgrid[:480, :640]; BASE = np.stack((x+3*y, x ^ y, 4*x+y, np.full_like(x, 255)), axis=-1).astype(np.uint8)
    return BASE


def compare(label, m, native, paint_frame, extra=None):
    prims = m.decode()
    blob, state = native.records()
    got = native_keys(blob, m); expected = [q['key'] for q in prims]
    if got != expected:
        for i, (a, b) in enumerate(zip(got, expected)):
            if a != b:
                show = lambda k: tuple(real(v) if isinstance(v, int) and v > 0xffff and j > 1 else v for j, v in enumerate(k[:-1] if k[0] == 'glyph' else k))
                raise AssertionError((label, 'primitive', i, len(got), len(expected), show(a), show(b),
                                      [show(k) for k in got[max(0, i-3):i]]))
        raise AssertionError((label, 'primitive count', len(got), len(expected), (got+expected)[min(len(got), len(expected))][:10]))
    if state != m.globals(): raise AssertionError((label, 'globals', state, m.globals()))
    if extra: extra()
    if paint_frame:
        want = paint(m, prims, base_frame().astype(np.int32)).astype(np.uint8)
        have = np.frombuffer(native.read(want.size), np.uint8).reshape(want.shape)
        if not np.array_equal(have, want):
            bad = np.any(have != want, axis=-1); y, x = map(int, np.argwhere(bad)[0])
            raise AssertionError((label, 'pixels', int(bad.sum()), x, y, have[y, x].tolist(), want[y, x].tolist()))
    return prims


def tally(counts, prims):
    for q in prims: counts[q['kind']] = counts.get(q['kind'], 0)+1


FADES = [(False, 0, 0), (True, 100, 0xffffffff), (True, 256, 0xffffffff), (True, 175, 0xff000000), (False, 0, 0)]


def spirits_case(spec):
    exe, name, seat, slots8, seed, table, inputs, every = spec
    from validate_spirits_edit import gesture
    rng = random.Random(seed)
    m = spirits_machine(seat, slots8, seed, table); native = Native(exe)
    native.send('SI', seat, slots8, seed, *table)
    queue = list(inputs) if isinstance(inputs, list) else []
    visits = frames = 0; state = focus = 0; tail = None; states = set(); kinds = {}; seen = set(); primitives = 0
    while True:
        if not queue:
            if isinstance(inputs, list) or visits >= inputs: break
            queue = gesture(rng, state, focus)
        if tail is not None:
            tail -= 1
            if tail < 0: break
        key = queue.pop(0); visits += 1
        if name.startswith('fade') and visits % 40 == 0:
            fade = FADES[(visits//40) % len(FADES)]
            m.fade = fade; m.refresh(); native.send('fade', int(fade[0]), fade[1], fade[2])
            bright = (0x100, 0xa0, 0x38)[(visits//40) % 3]
            m.p.write(0x43d064, bright, 4); native.send('bright', bright)
        held = [rng.choice((0, 0, 0x200, 0x400, 0x20, 0x10, 8)), key] if seat else [key, rng.choice((0, 0, 0x200, 0x400, 0x20, 0x10, 8))]
        m.visit(held)
        state, nxt = m.state(); focus = m.p.read(m.p.registers[29]+0xa00+0x3f4, 4) if False else focus
        # Paint every state change, every slide step after it, and a regular sample.
        signature = (state, nxt)
        painted = visits % every == 0 or signature not in seen or visits < 24 or (queue == [] and visits % 3 == 0)
        seen.add(signature)
        native.send('ST', held[0], held[1], int(painted))
        prims = compare((name, visits, state, nxt, held), m, native, painted)
        tally(kinds, prims); primitives += len(prims); frames += painted; states.add(state)
        if state == -2 and tail is None and not isinstance(inputs, list): tail = 6
    native.close()
    return dict(case=name, scene='spirits', seat=seat, slots=8 if slots8 else 6, visits=visits, frames=frames, states=sorted(states),
                primitives=primitives, kinds=kinds, instructions=m.instructions)


def color_case(spec):
    exe, kind, seat, seed, argument, every = spec
    from validate_color_edit import scripted, wander, SP, Oracle as LogicOracle
    rng = random.Random(seed)
    locks = [(c, rng.randrange(2)) for c in rng.sample(range(49), 12)] if kind == 'wander' and seed & 1 else []
    locks = [(c, v) for c, v in locks if c]
    if kind == 'walk': locks = [(argument[0], 0)]
    m = color_machine(seat, locks); native = Native(exe); p = m.p
    native.send('CI', seat, len(locks), *[v for pair in locks for v in pair])
    counters = dict(visits=0, frames=0, primitives=0, previews=0, shown=[0, 0, 0])
    states = set(); kinds = {}; seen = set()
    name = (kind, seat, seed, argument)
    def step(key):
        other = rng.choice((0, 0, 0x200, 0x20, 0x400, 0x80, 0x80000))
        held = (other, key) if seat else (key, other)
        m.depth = {}; m.actions = {}
        m.visit(held)
        counters['visits'] += 1; visits = counters['visits']
        state, nxt = m.state()
        signature = (state, nxt, p.read(SP+0x1ae0+0x64, 4) if state >= 2 else 0)
        painted = visits % every == 0 or signature not in seen or visits < 24
        seen.add(signature)
        native.send('CT', held[0], held[1], int(painted))
        def preview():
            words = struct.unpack('<27I', native.read(108)); cache = struct.unpack('<3I', native.read(12))
            for i in range(3):
                hidden, flip, character, action, record, x, y, depth, key = words[9*i:9*i+9]
                o = OBJECTS+0x400*i
                flags = p.read(o+0x104, 4)
                expected = [flags >> 1 & 1, m.depth[i], p.read(o+0x20, 4)]
                actual = [hidden, depth, key]
                assert flags & 0x200
                if not hidden and i:
                    expected += [p.read(o+0x40, 4), p.read(o+0x44, 4), p.read(o+0x24, 4), p.read(o+0x14, 4)]
                    actual += [x, y, action & 0xffffffff, character]
                    if i == 1:
                        expected.append(p.read(o+0x38, 4) >> 31); actual.append(flip)
                    if i in m.actions:
                        expected.append(p.read(o+0x28, 4)); actual.append(record)
                    counters['shown'][i] += 1
                elif not hidden:
                    expected += [p.read(o+0x40, 4), p.read(o+0x44, 4), p.read(o+0x14, 4)]
                    actual += [x, y, character]
                    counters['shown'][0] += 1
                if expected != actual: raise AssertionError((name, visits, 'preview', i, actual, expected))
            want = []
            for at, n, size in ((0x439a48, 24, 4), (0x439aa8, 24, 4), (0x43ab70, 512, 2)):
                h = 0
                for j in range(n): h = (h*131+p.read(at+size*j, size)) & 0xffffffff
                want.append(h)
            if list(cache) != want: raise AssertionError((name, visits, 'palette cache', cache, want))
            counters['previews'] += 3
        prims = compare((name, visits, state, nxt, held), m, native, painted, preview)
        tally(kinds, prims); counters['primitives'] += len(prims); counters['frames'] += painted; states.add(state)
    # The logic validator's sequences drive its own oracle object; give them this machine's view.
    class View: pass
    o = View(); o.p = p; o.locks = locks
    if kind == 'walk': scripted(o, step, argument[0], argument[1], rng)
    else: wander(o, step, rng, argument)
    native.close()
    return dict(case=kind, scene='color', seat=seat, seed=seed, argument=argument, visits=counters['visits'], frames=counters['frames'],
                states=sorted(states), primitives=counters['primitives'], kinds=kinds, preview_objects=counters['previews'],
                preview_visible=counters['shown'], instructions=m.instructions)


def palette_case(exe):
    """Whole 115d40 (lookup, allocation, 116478 upload) and 1159d0 against EditPaletteBank."""
    from validate_color_edit import machine
    p = machine(); native = Native(exe)
    rng = random.Random(0x115d40)
    seeded = bytes((i*7+3+(i >> 8)*5) & 255 for i in range(0x6180))
    p.memory[0x5735cc:0x5735cc+0x6180] = seeded
    for i in range(24):
        for at, v in [(0x439a48, -1), (0x439aa8, 0), (0x439b08, 0)]: p.write(at+i*4, v, 4)
    p.memory[0x316140:0x316148] = STUB
    for s, (run, net) in enumerate(((0x3ec740, 0x1232c80), (0x3f28c0, 0x1232ce0))):
        p.memory[run:run+0x6180] = bytes((i*11+5+s*77+(i >> 8)*3) & 255 for i in range(0x6180))
        p.memory[net:net+0x60] = bytes((i*13+9+s*31) & 255 for i in range(0x60))
    native.send('PI')
    instructions = calls = resets = full = frames = 0
    def hashes():
        out = []
        for at in (0x439a48, 0x439aa8, 0x439b08):
            h = 0
            for j in range(24): h = (h*131+p.read(at+4*j, 4)) & 0xffffffff
            out.append(h)
        return out
    for n in range(6000):
        if rng.random() < 0.02:
            instructions += p.run(0x1159d0, [], limit=100000)[1]; native.send('PR'); native.read(4); resets += 1
        if rng.random() < 0.1:
            # 113aa8, the per-frame entry that ages the reference words.
            instructions += p.run(0x113aa8, [], limit=1000)[1]; native.send('PF'); native.read(4); frames += 1
        character = rng.choice((0, 1, 2, 11, 16, 25, 33, 33, 34, 48, rng.randrange(51)))
        colour = rng.randrange(5)
        owner = rng.choice((0, 0, 1, 1, 1, 2))
        aux = p.memory[0x4ca9a8+character]
        bank = rng.choice((0, 1, 2, aux if aux != 0xff else 2, (aux+1) & 31 if aux != 0xff else 3, rng.randrange(32)))
        key = (character*5+colour) | owner << 16 | (rng.choice((0, 0, 0x40000, 0x80000, 0xc0000)) if owner else 0)
        value, count = p.run(0x115d40, [key, bank], limit=200000); instructions += count; calls += 1
        row = signed(value, 32)
        native.send('PK', key, bank)
        out = struct.unpack('<18I', native.read(72)); h = struct.unpack('<3I', native.read(12))
        slot = None
        if row >= 0:
            assert row in [p.read(0x5dd5c8+4*i, 4) for i in range(24)]
            colours = [p.read(0x43ab70+2*(row*16+i), 2) for i in range(16)]
        else: colours = [0]*16; full += 1
        if out[0] != row & 0xffffffff or (row >= 0 and list(out[2:]) != colours) or list(h) != hashes():
            raise AssertionError(('palette', n, hex(key), bank, signed(out[0], 32), row, out[2:], colours, h, hashes()))
    native.close()
    return dict(resolves=calls, cache_resets=resets, frame_ageings=frames, cache_full=full, instructions=instructions)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--quick', action='store_true'); ap.add_argument('--only', default='')
    ap.add_argument('--jobs', type=int, default=8)
    args = ap.parse_args()
    blob, _ = extract_edit_art.extract()
    assert extract_edit_art.OUT.read_bytes() == blob == (PACKAGE/'edit_art.bin').read_bytes(), 'run extract_edit_art.py first'
    from validate_spirits_edit import scripted as spirit_script, random_table
    from extract_spirits_edit import Source as Tables, OPTIONS
    from extract_save_default import factory_image
    tables = Tables()
    options = [struct.unpack('<Bb', tables.bytes(OPTIONS+12*i, 2)) for i in range(47)]
    default = list(factory_image()[0x633c:0x633c+128])
    rng = random.Random(0x17e428)
    start = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp)/'driver.cpp'; exe = Path(tmp)/'driver'; cpp.write_text(DRIVER)
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp, *[ROOT/'src'/s for s in SOURCES], '-o', exe], check=True)
        spirit_specs = []
        plan = (('leave', 0), ('hold', 1)) if args.quick else (('leave', 0), ('leave', 1), ('hold', 0), ('hold', 1), ('first', 0), ('last', 1))
        for kind, slots8 in plan:
            seat = len(spirit_specs) % 2
            spirit_specs.append((exe, f'{kind}-{8 if slots8 else 6}', seat, slots8, 1+len(spirit_specs), default,
                                 spirit_script(kind, 8 if slots8 else 6), 5))
        for n in range(2 if args.quick else 8):
            table = default if n % 4 == 0 else random_table(rng, options, valid=n % 4 != 3)
            spirit_specs.append((exe, ('fade-' if n % 2 else 'random-')+str(n), n % 2, int(n % 3 != 0), rng.getrandbits(40), table,
                                 150 if args.quick else 600, 9))
        walks = [((33, 0), 0), ((11, 3), 1), ((25, 2), 0), ((48, 4), 1)]
        if args.quick: walks = walks[:1]
        color_specs = [(exe, 'walk', seat, 0x13b160+i, argument, 6) for i, (argument, seat) in enumerate(walks)]
        color_specs += [(exe, 'wander', seed & 1, 0x13b1c8+seed, 200 if args.quick else 700, 9) for seed in range(2 if args.quick else 6)]
        if args.only == 'spirits': color_specs = []
        if args.only == 'color': spirit_specs = []
        if args.only == 'palette': color_specs = spirit_specs = []
        with ProcessPoolExecutor(args.jobs) as pool:
            static = pool.submit(palette_case, exe)
            futures = [pool.submit(spirits_case, s) for s in spirit_specs]+[pool.submit(color_case, s) for s in color_specs]
            cases = []
            for f in futures:
                cases.append(f.result())
                c = cases[-1]
                print(f"{c['scene']} {c['case']}: {c['visits']} visits, {c['frames']} frames, {time.time()-start:.0f}s", file=sys.stderr, flush=True)
            static = static.result()
    kinds = {}
    for c in cases:
        for k, v in c['kinds'].items(): kinds[k] = kinds.get(k, 0)+v
    scenes = {s: [c for c in cases if c['scene'] == s] for s in ('spirits', 'color')}
    total = lambda s, k: sum(c[k] for c in scenes[s])
    report = dict(status='passed', quick=args.quick, only=args.only, elf_sha256=ORIGINAL,
                  native_sha256={n: hashlib.sha256((ROOT/'src'/n).read_bytes()).hexdigest() for n in ('edit_art.cpp', 'edit_art.hpp')},
                  asset_sha256=hashlib.sha256(blob).hexdigest(),
                  spirits=dict(cases=len(scenes['spirits']), visits=total('spirits', 'visits'), identical_primitive_lists=total('spirits', 'visits'),
                               identical_640x480_frames=total('spirits', 'frames'), queue_entries=total('spirits', 'primitives'),
                               states=sorted({s for c in scenes['spirits'] for s in c['states']})),
                  color=dict(cases=len(scenes['color']), visits=total('color', 'visits'), identical_primitive_lists=total('color', 'visits'),
                             identical_640x480_frames=total('color', 'frames'), queue_entries=total('color', 'primitives'),
                             preview_objects=total('color', 'preview_objects'),
                             preview_visible=[sum(c['preview_visible'][i] for c in scenes['color']) for i in range(3)],
                             states=sorted({s for c in scenes['color'] for s in c['states']})),
                  entries_by_kind=kinds, palette_bank=static,
                  original_instructions=sum(c['instructions'] for c in cases)+static['instructions'],
                  stubbed={k: [hex(a) for a in v] for k, v in {**COMMON_STUBS, **COLOR_STUBS}.items()},
                  scope='Original tasks 13ada0 and 13b1c8 executed visit by visit on their own stacks (the 112a28 context switch is the '
                        'harness, as in the logic validators) with every draw routine running: 182600 (1817f0, 181e88, 182118, 181c30), '
                        '20d9f8/20d2e8, 20ef38/20f1c8, 20f360, 20c038/20c1a0, 20f680, 20fb58, 2129d0, 17eac8 and the primitives 17c228..'
                        '17f090, 17e228, 17e428, 17e038, 17df90 down to the queue builders. Compared every visit: the ordered queue '
                        '(exact float bits, glyph texel blocks, sheet slot, additive tag), the renderer globals 3db900, 3db8fc, 3db8f4, '
                        '345180, 348a8c, the depth cursor 12d3850 and the text colour 4ee548. Frames are painted from the original queue '
                        'by the reference painter of validate_menu_canvas.py (ascending depth; the queue-to-GS translation and GS '
                        'rasterisation are not executed) and compared with EditArt::rasterise on sampled visits (every state change, '
                        'the first 24 visits and a fixed stride). Four-vertex flat strips of 1147d8 are compared and painted as their '
                        'two triangles. The native side runs the validated logic modules (SpiritsEdit, ColorEdit) from the same pads; '
                        'the screen frame state is the new EditFrame. Stubbed callees are listed in "stubbed"; texture slot 5 and its '
                        'CLUT are supplied through the unmodified 116478/10add8, and the 116478 call inside 1ce478 is given length 0 '
                        'because its palette file read 1163c0 is stubbed. COLOR EDIT preview: 13bf00, 13bfd0 and 13c4f8 run whole on '
                        'zeroed objects; their object-engine callees are replaced, and the harness writes +14, +1c, +24, +40 and +44 '
                        'as 11fef8 (behind 11d570), 1202e8 (behind 11d668) and 11d908 store them. Compared per visit and object: '
                        'hidden flag, 11dff8 depth, palette word +20; for a shown sprite position, action, fighter, flip and the '
                        'start record on visits that request an action; for the shown portrait fighter and position. The fighter sprites themselves (character draw queue) and the portrait object are NOT rendered or '
                        'compared: no fighter pixels are part of the frame comparison on either side. EditPaletteBank is compared '
                        'with whole 115d40/1159d0 runs (returned row, sixteen colours, identity/reference/busy words) and inside the '
                        'COLOR EDIT task after every visit (identity, reference, 384 colours).',
                  cases=cases)
    if not args.only: REPORT.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('cases', 'scope')}, indent=1))
    print(f'{time.time()-start:.0f}s')


if __name__ == '__main__': main()
