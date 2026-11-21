#!/usr/bin/env python3
"""Compare the arcade result scenes with the original tasks, tick by tick.

Win quote 135e30 / 136000, VS result 136a60 / 136c58, challenger banner (1252f0 kind 4, task
1251d0), name entry overlay 1c9928, unlock notice 1e5d88 / 1e5e90 and the unlock predicates
584f78 / 584fb8 (1e3640, 1e6180, 1e62b8). Every visit runs the ORIGINAL handler in Probe, decodes
the submission queue 68c3c0 and requires the same state words, sound / scene requests, ordered
primitive list and (on the painted visits) the same 640x480 frame from src/arcade_results.cpp.
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
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import validate_menu_canvas as base
import validate_arcade_art as arcade
from validate_menu_canvas import bits, real, paint, PACKETS
from character_tiles_oracle import ROOT, ASSETS
from extract_console_versus_art import ORIGINAL
from mips_probe import signed
import extract_arcade_results

REPORT = ROOT/'outputs/ss6-feasibility/arcade_results_validation.json'
G, SEATS, PADS, SCHEDULE, OPTION, SESSION = 0x4c3808, 0x456890, 0x1237cc8, 0x12d3668, 0x43d058, 0x13430b0
STUB = struct.pack('<II', 0x03e00008, 0x0000102d)
SCENE = arcade.SCENE
TEX = dict(board=0x1400000, picture=0x1510000, faces=0x1620000, win=0x1730000, digits=0x1780000, curtain=0x17b0000)
PAL, OBJECT, TASK = 0x17f4000, 0x17fc000, 0x1c50000
OLD, NEW = 0x1c40000, 0x1c40010
SOUND, MUSIC, VOICE, JINGLE, SWITCH, SAVE, ACTION = 0x1e7b70, 0x1e7c00, 0x1e7d60, 0x1e79c8, 0x1252f0, 0x10f158, 0x11d908
FADES = [(False, 0, 0), (True, 100, 0xffffffff), (True, 175, 0xff000000), (True, 75, 0xff204080)]
DRIVER = r'''
#include "arcade_results.hpp"
#include "game_random.hpp"
#include "system_data.hpp"
#include <bit>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <sstream>
using namespace ss6;
template<class T> static void put(const T& v){std::cout.write(reinterpret_cast<const char*>(&v),sizeof v);}
int main(int argc,char** argv){
 if(argc!=2)return 2;
 const std::filesystem::path assets=argv[1];
 MenuCanvas canvas(assets);ArcadeResultsArt art(assets);ArcadeResultsTables tables(assets);
 std::ifstream in0(assets/"arcade_run.bin",std::ios::binary);
 std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(in0)),std::istreambuf_iterator<char>());
 ArcadeTables arcadeTables(bytes);SystemData system(assets);GameRandom random;ArcadeRun run(arcadeTables,system,random);
 UnlockSessionFlags session{};
 ArcadeWinQuote quote;ArcadeVersusResult result;ArcadeChallengerBanner banner;ArcadeNameEntry entry;ArcadeUnlockNotice notice;
 ArcadeEdgePulse pulse;
 MenuDrawList list;std::vector<int32_t> st;
 std::vector<uint8_t> pixels(640*480*4),base(pixels.size());
 for(int y=0;y<480;++y)for(int x=0;x<640;++x){auto* p=base.data()+4*(640*y+x);p[0]=x+3*y;p[1]=x^y;p[2]=4*x+y;p[3]=255;}
 const auto events=[&](const ArcadeResultEvents& e){
  for(int v:{e.music,int(e.sound),e.soundA,e.soundB,int(e.voice),e.voiceA,e.voiceB,int(e.exit),int(e.autosave),int(e.objectAction),e.action,
             run.transition.kind,run.transition.speed,int(run.transition.destructor),int(run.transition.next),
             run.game.transitionLock,run.game.challengerInhibit,run.game.versusInterrupted,run.game.mode})st.push_back(v);};
 std::string line;
 while(std::getline(std::cin,line)){
  std::istringstream in(line);std::string op;in>>op;
  auto u=[&]{uint32_t v;in>>v;return v;};auto i=[&]{int v;in>>v;return v;};
  if(op=="fade"){int en=i(),level=i();uint32_t c=u();canvas.setFade(en,level,c);art.setFade(en,level,c);}
  else if(op=="begin"){list.beginFrame();list.colour=u();list.blend=i();list.additive=false;st.clear();}
  else if(op=="g"){int k=i();int32_t v=i();std::memcpy(reinterpret_cast<char*>(&run.game)+4*k,&v,4);}
  else if(op=="p"){int seat=i(),k=i();int32_t v=i();std::memcpy(reinterpret_cast<char*>(&run.players[seat])+4*k,&v,4);}
  else if(op=="nointruder")run.schedule.intruderDisabled=i();
  else if(op=="clear"){run.transition={};}
  else if(op=="opt"){int off=i();system.option(off)=uint8_t(i());}
  else if(op=="set"){int off=i();system.setting(off)=uint8_t(i());}
  else if(op=="sess"){int k=i();session[k]=i();}
  else if(op=="pred"){int force=i();int ec=unlockEndingCount(system),sc=unlockSpiritCount(system);put(ec);put(sc);
   for(unsigned k=0;k<16;++k){uint8_t v=unlockPredicate(k,system,session,ec,sc,force);put(v);}std::cout.flush();}
  else if(op=="setter"){int k=i();unlockSetter(k,system,i());}
  else if(op=="recompute")unlockRecompute(system,session);
  else if(op=="pending"){uint8_t v=unlockPending(system,session);put(v);std::cout.flush();}
  else if(op=="collect"){auto v=unlockCollect(system,session);uint32_t n=uint32_t(v.size());put(n);for(int k:v)put(k);std::cout.flush();}
  else if(op=="options"){for(int k=0;k<0x98;++k)put(system.option(k));std::cout.flush();}
  else if(op=="bg"){int variant=i();art.bindBackground(variant);drawResultBackground(canvas,list,tables,variant,i());}
  else if(op=="wq_enter"){auto e=quote.enter(run,tables);art.bindBackground(0);art.bindPortrait(quote.draw.character);events(e);
   st.push_back(quote.revealLimit);}
  else if(op=="wq_tick"){std::array<uint32_t,2> pad;pad[0]=u();pad[1]=u();auto e=quote.tick(run,pad,u());
   drawArcadeWinQuote(canvas,list,tables,quote.draw);events(e);
   for(int v:{quote.frame,quote.backgroundFrame,quote.messageFrame,quote.endFrame,quote.messageDone,quote.latch,quote.revealLimit})st.push_back(v);}
  else if(op=="wq_leave"){ArcadeWinQuote::leave(run);st.push_back(run.game.versusInterrupted);}
  else if(op=="wq_draw"){ArcadeWinQuoteDraw d;d.frame=i();d.backgroundFrame=i();d.revealLimit=i();d.winner=i();d.character=i();
   d.quote=tables.quote(system,d.character,i());art.bindBackground(0);art.bindPortrait(d.character);
   drawArcadeWinQuote(canvas,list,tables,d);st.push_back(d.quote?ArcadeWinQuote::glyphCount(*d.quote):-1);}
  else if(op=="vr_enter"){auto e=result.enter(run,tables);art.bindBackground(1);events(e);
   for(int v:{result.fighter.seat,result.fighter.character,result.fighter.colour,result.fighter.x,result.fighter.flags,result.fighter.action})st.push_back(v);}
  else if(op=="vr_tick"){std::array<uint32_t,2> pad;pad[0]=u();pad[1]=u();uint32_t held=u();auto e=result.tick(run,pad,held,i());
   drawArcadeVersusResult(canvas,list,tables,result.draw);events(e);
   for(int v:{result.frame,result.endFrame,result.latch,result.fighter.action})st.push_back(v);}
  else if(op=="vr_draw"){ArcadeVersusResultDraw d;d.frame=i();d.streak=i();for(auto& v:d.defeated)v=i();art.bindBackground(1);
   drawArcadeVersusResult(canvas,list,tables,d);}
  else if(op=="bn_begin")banner.begin();
  else if(op=="bn_tick"){auto f=banner.tick(i());if(f.banner)drawArcadeBanner(canvas,list,tables);
   for(int v:{int(f.banner),f.curtain,int(f.voice),int(f.stopSound),int(f.swap),int(f.finished),banner.state,banner.age})st.push_back(v);}
  else if(op=="ne_begin"){entry={};entry.active=true;}
  else if(op=="ne_tick"){drawArcadeNameCountdown(canvas,list,tables,entry,run.game.mode);
   // Stop before the commit visit: 1c5150 belongs to the logic validator.
   entry.tick(run,u());drawArcadeNameEntry(canvas,list,tables,arcadeTables,entry,run.game.mode);
   for(int v:{int(entry.name[0]),int(entry.name[1]),int(entry.name[2]),int(entry.name[3]),entry.glyph,entry.cursor,entry.seconds,
              entry.secondFrame,entry.blinkShown,entry.blinkOn,entry.blinkCounter,entry.finished,entry.commitFrames})st.push_back(v);}
  else if(op=="pulse"){pulse.counter=i();pulse.reverse=i();}
  else if(op=="un_enter"){auto e=notice.enter(run,session);events(e);st.push_back(int(notice.items.size()));for(int v:notice.items)st.push_back(v);}
  else if(op=="un_tick"){std::array<uint32_t,2> pad;pad[0]=u();pad[1]=u();auto e=notice.tick(run,pad);
   drawArcadeUnlockNotice(canvas,list,tables,notice.draw,pulse);events(e);
   for(int v:{notice.index,notice.latch,notice.frame,notice.fading,pulse.counter,pulse.reverse})st.push_back(v);}
  else if(op=="un_leave"){ArcadeUnlockNotice::leave(run);for(int k=0;k<0x2a;++k){int32_t v;std::memcpy(&v,reinterpret_cast<char*>(&run.game)+4*k,4);st.push_back(v);}}
  else if(op=="un_draw"){ArcadeUnlockDraw d;d.item=i();d.alpha=i();drawArcadeUnlockNotice(canvas,list,tables,d,pulse);
   st.push_back(pulse.counter);st.push_back(pulse.reverse);}
  else if(op=="flush"){
   int paint=i();
   uint32_t n=uint32_t(list.records.size());put(n);
   for(auto& r:list.records){uint8_t head[6]={uint8_t(r.kind),uint8_t(r.font),r.slot,r.blend,uint8_t(r.additive),0};put(head);put(r.glyph);put(r.colour);put(r.z);
    float g[8]={r.x,r.y,r.w,r.h,r.u,r.v,r.uw,r.vh};put(g);put(r.corner);}
   uint32_t rs[4]={list.colour,uint32_t(list.blend),uint32_t(list.depth),uint32_t(st.size())};put(rs);
   for(int32_t v:st)put(v);
   if(paint){pixels=base;art.rasterise(canvas,list,pixels);std::cout.write(reinterpret_cast<const char*>(pixels.data()),pixels.size());}
   std::cout.flush();
  }
  else return 3;
 }
}
'''


def log(*parts):
    if os.environ.get('ARCADE_RESULTS_LOG'): print(time.strftime('%H:%M:%S'), *parts, file=sys.stderr, flush=True)


class Slots(dict):
    def __missing__(self, key): return -1


class Oracle(arcade.Oracle):
    """validate_arcade_art.Oracle with the sheets of the result scenes and disc hooks.

    The two disc stubs of the base oracle (1142d8 texture by name, 1163c0 palette file) become
    hooks that place the named resource exactly where the caller's unmodified code expects it.
    """
    def __init__(self):
        self.files = {}; self.stq = 0; self.variant = 0; self.portrait = None; self.extra = None; self.curtain_tex = None; self.emulate_switch = True
        super().__init__()
        p = self.p
        self.switch_code = bytes(p.memory[SWITCH:SWITCH+8])
        # libc strcmp 31806c: Probe lacks the MMI quadword compare of its 16-byte-aligned path
        # (PSUBW at 3180c8). Route every call to the function's own byte loop 31817c, which it
        # uses for unaligned operands: andi v0, t0, 7 -> ori v0, zero, 1. Results are identical.
        assert p.read(0x318070, 4) == 0x31020007
        p.write(0x318070, 0x34020001, 4)
        for fn in (SOUND, MUSIC, VOICE, JINGLE, 0x1e7ad0, 0x1e7b40, 0x1e7af8, SWITCH, SAVE, OLD, NEW, 0x316140, 0x316218):
            p.memory[fn:fn+8] = STUB
        # Bank keys of the 4-bit sheet (slot 0xc) as the base oracle learnt them.
        self.banks = {key: slot-SCENE for key, slot in self.slots.items() if slot in (SCENE, SCENE+1)}
        self.learnt = dict(self.slots); self.slots = Slots()
        self.digits = None
        self.events = []; self.quads = []
        self.texture(3, 'change_base16'); self.curtain_tex = self.embedded('change_base16', 512)

    def file(self, name):
        if name not in self.files: self.files[name] = (ASSETS/name).read_bytes()
        return self.files[name]

    def embedded(self, name, size):
        raw = np.frombuffer(self.file(name+'.tex'), np.uint8)
        clut = raw[size*size:].reshape(8, 4, 8, 4)[:, [0, 2, 1, 3]].reshape(256, 4)
        return clut[raw[:size*size]].reshape(size, size, 4)

    def texture(self, slot, name):
        """1142d8(slot, name): the record fields 10aa28 derives from the file."""
        p = self.p; data = self.file(name+'.tex')
        kind = {3: 'curtain', 5: 'faces', 8: 'win', 12: 'digits'}.get(slot) or ('board' if name == 'menu_bg00_00' else 'picture')
        at = TEX[kind]; p.memory[at:at+len(data)] = data
        four = len(data) == 512*512//2
        size = 512 if four or len(data) < 1024*1024 else 1024
        log = 9 if size == 512 else 10
        for off, value in ((0, at), (4, size), (8, size), (12, 20 if four else 19), (20, log), (24, log), (36, int(len(data) % 4096 == 1024))):
            p.write(0x3a9680+slot*40+off, value, 4)
        if slot == 4: self.variant = 0 if name == 'menu_bg00_00' else 1
        if slot == 8: self.portrait = name
        if slot == 12: self.digits = name

    def palette_file(self, name, header):
        """1163c0(name, header): the caller's buffer and the entry count; 32-bit files use the
        parallel buffer that 116478 reads through 43cc60 / 3ebf28 when 439b68 is set."""
        p = self.p; data = self.file(name+'.pal'); buffer = p.read(header, 4)
        if len(data) == 512:
            p.memory[buffer:buffer+512] = data; p.write(0x439b68, 0, 4)
        else:
            assert len(data) == 1024
            p.memory[PAL:PAL+1024] = data
            p.write(0x439b68, 1, 4); p.write(0x43cc60, buffer, 4); p.write(0x3ebf28, PAL, 4)
        p.write(header+0xa, 256, 2)

    def observe(self, pc):
        p = self.p; r = p.registers
        if pc == 0x1149d0: self.quads.append(r[6] & 255)
        elif pc == 0x1142d8:
            at = r[5] & 0xffffffff; self.texture(r[4] & 255, bytes(p.memory[at:at+40]).split(b'\0')[0].decode().removesuffix('.pvr'))
        elif pc == 0x1163c0:
            at = r[4] & 0xffffffff; self.palette_file(bytes(p.memory[at:at+40]).split(b'\0')[0].decode().removesuffix('.pvp'), r[5] & 0xffffffff)
        elif pc in (SOUND, MUSIC, VOICE, JINGLE, SWITCH, SAVE, ACTION, OLD, NEW):
            self.events.append((pc, *[signed(r[i] & 0xffffffff, 32) for i in (4, 5, 6, 7)]))
            if pc == ACTION and (r[4] & 0xffffffff) == OBJECT: p.write(OBJECT+0x24, r[5] & 0xffffffff, 4)
            # The stubbed 1252f0 would raise the transition lock g+2c for kinds 1..3.
            if pc == SWITCH and self.emulate_switch and 1 <= (r[4] & 0xffffffff) <= 3: p.write(G+0x2c, 1, 4)
        if self.extra: self.extra(pc)

    def go(self, pc, args=(), limit=6000000, extra=None):
        self.extra = extra
        value, count = self.p.run(pc, list(args), limit=limit, observe=self.observe); self.instructions += count
        return value

    def begin(self, colour=0xffffffff, blend=1):
        self.reset(colour, blend, ascii_depth=-200.0); self.events = []; self.quads = []

    def refresh(self):
        super().refresh()
        if getattr(self, 'curtain_tex', None) is None: return
        p = self.p
        entries = lambda first, count: np.frombuffer(p.memory, np.uint8, 4*count, 0x11e7980+4*first).reshape(count, 4)
        self.tex[3] = self.curtain_tex
        if self.variant == 0: self.tex[4] = self.embedded('menu_bg00_00', 1024)
        else: self.tex[4] = entries(0, 256)[np.frombuffer(self.file('menu_bg01_00.tex'), np.uint8).reshape(1024, 1024)]
        if 'char_face_1024.tex' in self.files:
            self.tex[5] = entries(0x200, 256)[np.frombuffer(self.file('char_face_1024.tex'), np.uint8).reshape(1024, 1024)]
        if self.portrait: self.tex[8] = entries(0x100, 256)[np.frombuffer(self.file(self.portrait+'.tex'), np.uint8).reshape(512, 512)]
        if self.digits:
            blob = np.frombuffer(self.file(self.digits+'.tex'), np.uint8).reshape(512, 256)
            sheet = np.empty((512, 512), np.uint8); sheet[:, ::2] = blob & 15; sheet[:, 1::2] = blob >> 4
            for bank in (0, 1): self.tex[SCENE+bank] = entries(16*bank, 16)[sheet]

    def decode(self):
        p = self.p
        # With word 3db908 = 1 (transition kinds 3 / 4) 108118 emits tag ff4: the ff2 layout with
        # normalised STQ texel coordinates (u + 0.5) / size .. (u + w - 0.5) / size and Q = 1.
        # Rewrite them in place as ff2 entries in texel units (exact: the sizes are powers of two).
        for i in range(p.read(0x345178, 4)):
            at = PACKETS+i*128; tag = p.read(at, 8)
            if tag & 0xfff != 0xff4: continue
            tex, ptr, n = p.read(at+16, 8), p.read(at+24, 8), p.read(at+32, 8)
            assert n == 4 and p.read(at+12, 4) == 0x3f800000, hex(tag)
            tw, th = 1 << ((tex >> 26) & 15), 1 << ((tex >> 30) & 15)
            for k in range(4):
                u, v = struct.unpack_from('<2f', p.memory, ptr+24*k+12)
                tu, tv = np.float32(u)*np.float32(tw), np.float32(v)*np.float32(th)
                assert np.float32(tu/np.float32(tw)) == np.float32(u) and np.float32(tv/np.float32(th)) == np.float32(v)
                struct.pack_into('<2f', p.memory, ptr+24*k+12, tu, tv)
            p.write(at, (tag & ~0xfff) | 0xff2, 8); p.write(at+12, 0, 4)
            self.stq += 1
        prims = super().decode()
        quads = [q for q in prims if q['kind'] == 'quad']
        assert len(quads) == len(self.quads), (len(quads), len(self.quads))
        cursor = 0
        for index, q in enumerate(prims):
            if q['kind'] != 'quad': continue
            slot = self.quads[cursor]; cursor += 1
            if slot == 12:
                tex = p.read(PACKETS+index*128+16, 8); slot = SCENE+self.banks[tex & 0x3fff, (tex >> 37) & 0x3fff]
            q['slot'] = slot; q['key'] = ('quad', slot, *q['key'][2:])
        return prims

    def word(self, at): return signed(self.p.read(at, 4), 32)
    def pads(self, values):
        for seat in (0, 1): self.p.write(PADS+0xc*seat+4, values[seat], 4)


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
            if font == 1:
                cols = np.arange(int(u), int(u+w)); cell = (oracle.half[int(v):int(v+h), cols//2] >> (4*(cols % 2))) & 15; name = 'half'
            else:
                size = 20 if font == 2 else 24
                step = 220 if size == 20 else 312; head = 10 if size == 20 else 12; pitch = size//2
                rows = np.frombuffer(oracle.fonts[size], np.uint8, pitch*size, glyph*step+head).reshape(size, pitch)
                cols = np.arange(size); cell = (rows[:, cols//2] >> (4*(cols % 2))) & 15; name = size
            keys.append(('glyph', name, colour, bits(z), int(x), int(y), int(w), int(h), int(u), int(v), cell.tobytes()))
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
        self.o.begin(colour, blend); self.send('begin', colour, blend)
    def g(self, offset, value):
        self.o.p.write(G+offset, value & 0xffffffff, 4); self.send('g', offset//4, signed(value & 0xffffffff, 32))
    def player(self, seat, offset, value):
        self.o.p.write(SEATS+0x30*seat+offset, value & 0xffffffff, 4); self.send('p', seat, offset//4, value)
    def option(self, offset, value):
        self.o.p.write(OPTION+offset, value, 1); self.send('opt', offset, value)
    def flush(self, label, paint_frame=True, prims=None, compare=True):
        """Compares primitives, renderer globals and the frame; returns the native state words."""
        o = self.o; p = o.p
        if prims is None: prims = o.decode()
        self.send('flush', int(paint_frame)); self.push()
        count = struct.unpack('<I', self.read(4))[0]; blob = self.read(count*80); rs = struct.unpack('<4I', self.read(16))
        state = struct.unpack(f'<{rs[3]}i', self.read(4*rs[3]))
        native = native_keys(blob, o); expected = [q['key'] for q in prims]
        if compare and native != expected:
            for i, (a, b) in enumerate(zip(native, expected)):
                if a != b:
                    show = lambda k: k[:-1] if k[0] == 'glyph' else (k[:3]+(hex(k[3]),)+tuple(real(v) for v in k[4:]) if k[0] == 'quad' else k)
                    raise AssertionError((label, 'primitive', i, show(a), show(b)))
            raise AssertionError((label, 'primitive count', len(native), len(expected)))
        if compare:
            original = (p.read(0x3db900, 4), p.read(0x3db8fc, 4), p.read(0x3db8f4, 4))
            if rs[:3] != original: raise AssertionError((label, 'renderer state', [hex(v) for v in rs[:3]], [hex(v) for v in original]))
        for q in prims:
            self.kinds[q['kind']] = self.kinds.get(q['kind'], 0)+1
            if q['kind'] == 'quad': self.slots.add(q['slot'])
        self.primitives += len(prims); self.cases += 1
        if paint_frame:
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


def events_of(o):
    """The native ArcadeResultEvents words for the calls the original made on this visit."""
    out = dict(music=-1, sound=(0, 0, 0), voice=(0, 0, 0), exit=0, save=0, action=(0, 0), switch=None)
    for pc, a0, a1, a2, a3 in o.events:
        if pc in (MUSIC, JINGLE): out['music'] = a0 if pc == MUSIC else a1
        elif pc == SOUND: out['sound'] = (1, a0, a1)
        elif pc == VOICE: out['voice'] = (1, a0, a1)
        elif pc == SWITCH: out['exit'] = 1; out['switch'] = (a0, a1, a2 & 0xffffffff, a3 & 0xffffffff)
        elif pc == SAVE: out['save'] = 1
        elif pc == ACTION: out['action'] = (1, a1)
    return out

def check_events(label, o, state, transition=None):
    e = events_of(o)
    want = (e['music'], *e['sound'], *e['voice'], e['exit'], e['save'], *e['action'])
    if tuple(state[:11]) != want: raise AssertionError((label, 'events', state[:11], want, [(hex(v[0]), *v[1:]) for v in o.events]))
    if e['switch']:
        got = (state[11], state[12], state[13] & 0xffffffff, state[14] & 0xffffffff)
        if got != e['switch']: raise AssertionError((label, 'transition', [hex(v) for v in got], [hex(v) for v in e['switch']]))
    live = (o.word(G+0x2c), o.word(G+0x30), o.word(G+0x1c), o.word(G))
    if tuple(state[15:19]) != live: raise AssertionError((label, 'game words', state[15:19], live))
    return e


# ---------------------------------------------------------------------------
def unlock_logic(s, rng, quick):
    """Whole predicates 584f78[i], setters 584fb8[i], 1e3640, 1e6180 and 1e62b8."""
    o = s.o; p = o.p; stats = dict(predicate_calls=0, setter_calls=0, recompute=0, pending=0, collect=0, true_predicates=[0]*16)
    for off in range(0x98): s.send('opt', off, p.memory[OPTION+off])   # the native image starts from the factory defaults
    s.send('set', 2, p.memory[0x43d052])
    table = struct.unpack('<16I', p.memory[0x584f78:0x584f78+64]); setters = struct.unpack('<16I', p.memory[0x584fb8:0x584fb8+64])
    interesting = sorted(set(range(0x3e, 0x47)) | set(range(0x47, 0x78)) | set(range(0x7e, 0x8d)) | {0x73, 0x74, 0x75, 0x76, 0x94, 0x95})
    def options():
        s.send('options'); s.push(); got = s.read(0x98); want = bytes(p.memory[OPTION:OPTION+0x98])
        assert got == want, ('options', [hex(i) for i in range(0x98) if got[i] != want[i]])
    def randomise(index):
        style = index % 6
        for off in interesting:
            if 0x47 <= off < 0x78: value = int(rng.random() < (0.05, 0.3, 0.6, 0.9, 0.5, 1.0)[style])
            elif 0x3e <= off < 0x47: value = int(rng.random() < (0.9, 0.5, 0.2, 0.7, 0.5, 0.5)[style])
            else: value = rng.choice((0, 0, 1, 1, 1, 2)) if rng.random() < 0.9 else rng.randrange(256)
            s.option(off, value)
        for off in range(0x81, 0x8a): s.option(off, int(rng.random() < (0.2, 0.5, 0.95, 0.5, 1.0, 0.9)[style]))
        total = rng.choice((0, 0, 0, 0x2bf1f, 0x2bf20, rng.getrandbits(32)))
        for k in range(4): s.option(0x90+k, (total >> (8*k)) & 255)
        for k in range(8):
            v = int(rng.random() < 0.15); p.write(SESSION+4*k, v, 4); s.send('sess', k, v)
    for index in range(60 if quick else 600):
        randomise(index)
        ec = o.go(0x1e3f70, [OPTION+0x47]); sc = o.go(0x1e3fa0, [OPTION+0x81])
        for force in (0, 1):
            want = [int(o.go(fn, [ec, sc, force]) != 0) for fn in table]
            s.send('pred', force); s.push(); got_ec, got_sc = struct.unpack('<2i', s.read(8)); got = list(s.read(16))
            assert (got_ec, got_sc) == (ec, sc) and got == want, (index, force, ec, sc, got, want)
            stats['predicate_calls'] += 16
            if not force:
                for k in range(16): stats['true_predicates'][k] += want[k]
        which = index % 4
        if which == 0:
            for k in rng.sample(range(16), 6):
                v = rng.choice((0, 1, 1, 2)); o.go(setters[k], [v]); s.send('setter', k, v); stats['setter_calls'] += 1
        elif which == 1:
            o.go(0x1e3640); s.send('recompute'); stats['recompute'] += 1
        elif which == 2:
            want = o.go(0x1e6180); s.send('pending'); s.push(); assert s.read(1)[0] == want, (index, want); stats['pending'] += 1
        else:
            out, count = PAL, PAL+0x100
            p.memory[out:out+0x104] = bytes(0x104); o.go(0x1e62b8, [out, count])
            n = p.read(count, 4); want = list(struct.unpack(f'<{n}i', p.memory[out:out+4*n]))
            s.send('collect'); s.push(); m = struct.unpack('<I', s.read(4))[0]; got = list(struct.unpack(f'<{m}i', s.read(4*m)))
            assert got == want, (index, got, want); stats['collect'] += 1
        options()
    assert quick or all(stats['true_predicates']), stats
    log('unlock logic', stats)
    return stats


def enter_scene(s, rng, winner, mode, characters, quote, interrupted, progress, streak=0, defeated=()):
    o = s.o; p = o.p
    p.memory[G:G+0xa8] = bytes(0xa8)
    for k in range(0x2a): s.send('g', k, 0)
    for seat in (0, 1):
        p.memory[SEATS+0x30*seat:SEATS+0x30*seat+0x30] = bytes(0x30)
        for k in range(12): s.send('p', seat, k, 0)
    s.g(0, mode); s.g(8, winner); s.g(0x8c, quote); s.g(0x1c, interrupted); s.g(0xa0, 1); s.g(0x38, streak); s.g(0x98, 1)
    for i, c in enumerate(defeated): s.g(0x3c+4*i, c)
    for seat in (0, 1):
        s.player(seat, 0, characters[seat]); s.player(seat, 4, rng.randrange(5)); s.player(seat, 0x18, progress[seat])
        s.player(seat, 0x14, rng.randrange(1, 6))
    p.write(SCHEDULE+0x34, 1, 4); s.send('nointruder', 1); s.send('clear')


def win_quote(job):
    exe, seed, runs, draws, quick = job
    rng = random.Random(seed); s = Session(exe); o = s.o; p = o.p
    stats = dict(runs=0, ticks=0, exits_start=0, exits_timeout=0, fast_forward=0, frozen_ticks=0, draw_cases=0, quotes=set(), next=set())
    characters = [c for c in range(49) if c != 43]
    for index in range(runs):
        winner = index & 1; mode = winner+1
        chars = [rng.choice(characters), rng.choice(characters)]
        if index < 4: chars[winner] = (0, 5, 24, 48)[index]
        quote = rng.randrange(16)
        while not p.read(p.read(p.read(0x50d550+4*chars[winner], 4)+0xd8+4*quote, 4)+8, 4): quote = rng.randrange(16)
        interrupted = int(index % 3 == 1); progress = [rng.choice((0, 2)), rng.choice((0, 2))]
        s.fade(*FADES[index % len(FADES)] if index % 3 == 2 else FADES[0])
        enter_scene(s, rng, winner, mode, chars, quote, interrupted, progress)
        o.begin(); s.send('begin', 0xffffffff, 1)
        o.go(0x135e30); s.send('wq_enter'); o.refresh()
        _, state = s.flush(('quote enter', index), paint_frame=False, prims=[], compare=False)
        check_events(('quote enter', index), o, state); assert state[19] == o.word(0x3d3aa0)
        assert o.portrait == f'win_{chars[winner]:02d}' and o.variant == 0
        style = index % 4; left = None; frozen = 0; last = None
        for frame in range(1400):
            pads = [0, 0]
            f = o.word(0x4ca1b4)
            if style == 0:
                if rng.random() < 0.02: pads[winner] = rng.choice((1, 2, 4, 0x200, 0x400, 0x10, 0x40))
            elif style == 1:
                if f == 0x10+index % 9: pads[winner] = 8 | rng.choice((0, 2))
            elif style == 2:
                if rng.random() < 0.08: pads[rng.randrange(2)] = rng.choice((1, 2, 4, 8, 0x200, 0x400, 0x607, 0x60f))
            elif f > 0x3c and rng.random() < 0.01: pads[winner] = 4
            if frozen == 0 and rng.random() < 0.004: frozen = rng.randrange(1, 12)
            freeze = int(frozen > 0); frozen = max(0, frozen-1)
            if o.word(G+0x18) != freeze: s.g(0x18, freeze)
            o.pads(pads); s.begin(colour=rng.getrandbits(32), blend=rng.randrange(2))
            o.go(0x136000, [TASK]); s.send('wq_tick', pads[0], pads[1], 0)
            shown = f in (0, 5, 9, 25, 44, 52, 59, 60, 61, 63, 64) or (f > 64 and frame % 97 == 0) or o.events and frame % 3 == 0
            _, state = s.flush(('quote', index, frame, f), paint_frame=bool(shown) and (not quick or index < 3))
            e = check_events(('quote', index, frame), o, state)
            want = tuple(o.word(a) for a in (0x4ca1b4, 0x4ca1b8, 0x4ca1bc, 0x4ca1c0, 0x4ca1b0, 0x4ca1c4, 0x3d3aa0))
            if tuple(state[19:26]) != want: raise AssertionError(('quote', index, frame, 'state', state[19:26], want))
            stats['ticks'] += 1; stats['frozen_ticks'] += freeze
            if e['exit']:
                stats['next'].add(hex(e['switch'][3]))
                if pads[winner] & 8: stats['exits_start'] += 1
                else: stats['exits_timeout'] += 1
                left = frame
            if any(v & 0x607 for v in pads) and f >= 0x3c: stats['fast_forward'] += 1
            if left is not None and frame > left+20: break
        assert left is not None, ('quote never left', index)
        # Destructor 136288: clears g+1c unless the mode word is 3.
        for final_mode in (mode, 3):
            s.g(0, final_mode); s.g(0x1c, 1); o.begin(); s.send('begin', 0xffffffff, 1)
            o.go(0x136288); s.send('wq_leave')
            _, state = s.flush(('quote leave', index), paint_frame=False, prims=[], compare=False)
            assert state[0] == o.word(G+0x1c) == int(final_mode == 3)
        stats['runs'] += 1; stats['quotes'].add((chars[winner], quote))
        log('quote run', index, chars, quote, frame, o.instructions)
    # 136400(frame, background frame, quote) at arbitrary draw states: every character, every record.
    cases = [(c, q) for c in characters for q in range(16)]
    rng.shuffle(cases)
    for index, (c, q) in enumerate(cases[:draws]):
        record = o.go(0x1a3070, [c, 2, q])
        if not record: continue
        winner = index & 1; p.write(G+8, winner, 4)
        s.fade(*FADES[index % len(FADES)] if index % 5 == 0 else FADES[0])
        o.texture(8, f'win_{c:02d}')
        pal = bytearray(o.file(f'win_{c:02d}.pal')); pal[0:2] = bytes(2); p.memory[PAL:PAL+512] = pal; p.write(0x439b68, 0, 4)
        o.go(0x116478, [0x100, 256, PAL]); o.texture(4, 'menu_bg00_00'); o.refresh()
        total = None
        for step in range(3):
            frame = rng.choice((0, 3, 9, 21, 29, 40, 47, 59, 60, 62, 64, 200, 4000)) if step else 60+step
            limit = rng.choice((-1, 0, 1, 5, 17, 40, 0x100, 0x400)) if step else 0x400
            bg = rng.randrange(0, 5000)
            p.write(0x3d3aa0, limit & 0xffffffff, 4); p.write(0x4ca1b0, 0, 4)
            s.begin(colour=rng.getrandbits(32), blend=rng.randrange(2))
            o.go(0x136400, [frame, bg, record]); s.send('wq_draw', frame, bg, limit, winner, c, q)
            prims, state = s.flush(('quote draw', c, q, frame, limit, bg), paint_frame=step == 0 and (not quick or index < 6))
            glyphs = sum(q_['kind'] == 'glyph' for q_ in prims)
            if frame >= 60:
                assert o.word(0x4ca1b0) == int(state[0] < limit) and glyphs == (state[0] if limit < 0 else min(state[0], limit)), (c, q, limit, glyphs, state)
            stats['draw_cases'] += 1
    s.close()
    stats['quotes'] = len(stats['quotes']); stats['next'] = sorted(stats['next'])
    return stats, s.counts()


def install_object(o):
    """The winner's fighter object belongs to the character pipeline: its allocation, set-up and
    per-frame update are replaced by a fixture whose words +24 / +c0 the script owns."""
    p = o.p
    for fn in (0x11d448, 0x11d488, 0x11d528, 0x11d570, 0x11d6c8, 0x11d868, 0x11d730, ACTION, 0x122e98, 0x122eb8, 0x11e3a0):
        p.memory[fn:fn+8] = STUB
    # 11e2e8 returns the fixture: lui v0, hi; jr ra; ori v0, v0, lo.
    p.memory[0x11e2e8:0x11e2e8+12] = struct.pack('<III', 0x3c020000 | (OBJECT >> 16), 0x03e00008, 0x34420000 | (OBJECT & 0xffff))
    p.memory[OBJECT:OBJECT+0x200] = bytes(0x200)


def versus_result(job):
    exe, seed, runs, draws, quick = job
    rng = random.Random(seed); s = Session(exe); o = s.o; p = o.p
    install_object(o)
    stats = dict(runs=0, ticks=0, exits_start=0, exits_timeout=0, pose_skips=0, draw_cases=0, next=set(), streaks=set())
    for index in range(runs):
        winner = index & 1
        chars = [rng.randrange(49), rng.randrange(49)]
        streak = (1, 2, 5, 6, 19, 20, 21, 37, 999, 1000, 3)[index % 11]
        defeated = [rng.randrange(52) for _ in range(20)]
        progress = [(0, 2, 2, 2)[index % 4]]*2
        s.fade(*FADES[index % len(FADES)] if index % 3 == 2 else FADES[0])
        enter_scene(s, rng, winner, winner+1, chars, 0, 1, progress, streak, defeated)
        s.player(winner, 0x14, (1, 7, 3, 7)[index % 4]); s.player(winner, 0x1c, index % 8 == 3)
        p.memory[OBJECT:OBJECT+0x200] = bytes(0x200)
        o.begin(); s.send('begin', 0xffffffff, 1)
        seen = {}
        o.go(0x136a60, extra=lambda pc: seen.setdefault(pc, [signed(p.registers[i] & 0xffffffff, 32) for i in (4, 5, 6, 7, 8)])
             if pc in (0x11d488, 0x11d570, ACTION) else None)
        s.send('vr_enter'); o.refresh()
        _, state = s.flush(('result enter', index), paint_frame=False, prims=[], compare=False)
        o.events = [v for v in o.events if v[0] != ACTION]   # 11d908(object, 0, 1, 0) of the set-up
        check_events(('result enter', index), o, state)
        colour = o.word(SEATS+0x30*winner+4)
        assert seen[0x11d488][:2] == [winner, chars[winner]] and seen[ACTION][1:4] == [0, 1, 0]
        want = (winner, chars[winner], colour, seen[0x11d570][2], seen[0x11d570][4], 0)
        assert seen[0x11d570][0] == OBJECT and seen[0x11d570][1] == winner and seen[0x11d570][3] == 0
        assert tuple(state[19:25]) == want and o.word(OBJECT+0x20) == colour, (state[19:25], want)
        assert o.variant == 1 and o.digits == 'font_otherscene2_16'
        style = index % 4; left = None; pose_after = rng.choice((0, 3, 40, 90)); pose_frames = 0
        for frame in range(900):
            f = o.word(0x4ca1e4); pads = [0, 0]
            if style == 0:
                if rng.random() < 0.02: pads[winner] = rng.choice((1, 2, 4, 0x200, 0x400))
            elif style == 1:
                if f == 0x1f+index % 7: pads[winner] = 8
            elif style == 2:
                if rng.random() < 0.1: pads[rng.randrange(2)] = rng.choice((1, 2, 4, 8, 0x200, 0x400, 0x60f))
            action = p.read(OBJECT+0x24, 4); hold = 0
            if action == 0x1fb:
                pose_frames += 1; hold = int(pose_frames > pose_after)
                if index % 9 == 4 and pose_frames % 50 == 49: hold = 2   # a value other than 1 does not advance the end counter
            p.write(OBJECT+0xc0, hold, 4)
            freeze = int(index % 6 == 5 and 30 <= frame < 37)
            if o.word(G+0x18) != freeze: s.g(0x18, freeze)
            o.pads(pads); s.begin(colour=rng.getrandbits(32), blend=rng.randrange(2))
            o.go(0x136c58, [TASK]); s.send('vr_tick', pads[0], pads[1], 0, hold if action == 0x1fb else 0)
            shown = f in (0, 1, 30, 59, 60, 99, 100, 101, 104, 111, 123, 124) or frame % 89 == 0
            _, state = s.flush(('result', index, frame, f), paint_frame=bool(shown) and (not quick or index < 3))
            e = check_events(('result', index, frame), o, state)
            want = (o.word(0x4ca1e4), o.word(0x4ca1e8), o.word(0x4ca1f0), o.word(OBJECT+0x24))
            if tuple(state[19:23]) != want: raise AssertionError(('result', index, frame, 'state', state[19:23], want))
            stats['ticks'] += 1
            if e['exit']:
                stats['next'].add(hex(e['switch'][3]))
                if pads[winner] & 8: stats['exits_start'] += 1
                else: stats['exits_timeout'] += 1
                left = frame
            if action == 0x1fb and hold and any(v & 0x607 for v in pads): stats['pose_skips'] += 1
            if left is not None and frame > left+12: break
        assert left is not None, ('result never left', index)
        stats['runs'] += 1; stats['streaks'].add(streak)
        log('result run', index, streak, frame, o.instructions)
    # 1370c8(frame) at arbitrary states, including the degenerate streak 0.
    for index in range(draws):
        streak = rng.choice((0, 1, 2, 4, 5, 6, 10, 11, 19, 20, 21, 25, 99, 100, 345, 999, 1000, 5000))
        frame = rng.choice((0, 1, 20, 59, 60, 61, 99, 100, 101, 102, 107, 108, 115, 123, 124, 300)) if index % 3 else rng.randrange(0, 200)
        defeated = [rng.randrange(52) for _ in range(20)]
        if index % 7 == 0: s.fade(*FADES[(index//7) % len(FADES)])
        p.write(G+0x38, streak, 4)
        for i, c in enumerate(defeated): p.write(G+0x3c+4*i, c, 4)
        s.begin(colour=rng.getrandbits(32), blend=rng.randrange(2))
        o.go(0x1370c8, [frame]); s.send('vr_draw', frame, streak, *defeated)
        s.flush(('result draw', streak, frame), paint_frame=not quick or index < 8)
        stats['draw_cases'] += 1
    s.close()
    stats['next'] = sorted(stats['next']); stats['streaks'] = sorted(stats['streaks'])
    return stats, s.counts()


def banner_timeline(o, kind, speed, submode, hidden):
    """Whole 1252f0(kind, speed, old, new) + task 1251d0 until the task ends."""
    p = o.p
    p.write(0x1239d98, TASK, 4); p.write(G+0xa0, submode, 4); p.write(0x443140, hidden, 4)
    p.write(G+0x94, 0, 4); p.write(G+0x2c, 0, 4); p.write(G, 1, 4)
    # 1253e0 (transition midpoint) is ArcadeRun::transitionMidpoint, validated by validate_arcade_run.py.
    p.memory[0x1253e0:0x1253e8] = STUB
    p.memory[SWITCH:SWITCH+8] = o.switch_code
    o.go(0x1252f0, [kind, speed, OLD, NEW])
    p.memory[SWITCH:SWITCH+8] = STUB
    out = []
    for tick in range(200):
        state, age = o.word(0x1239da4), o.word(0x1239da8)
        if state == 0: break
        o.begin(colour=0x12345678, blend=0)
        before = p.read(0x3db908, 4)
        o.go(0x1251d0, [TASK]); assert p.read(0x3db908, 4) == before
        out.append(dict(state=state, age=age, prims=o.decode(), events=list(o.events), flags=(o.word(G+0x94), o.word(G+0x2c)),
                        renderer=(p.read(0x3db900, 4), p.read(0x3db8fc, 4), p.read(0x3db8f4, 4))))
    else: raise AssertionError('transition did not end')
    return out


def banner(job):
    exe, quick = job
    s = Session(exe); o = s.o; p = o.p; stats = dict(visits=0, banner_visits=0, curtain_visits=0)
    o.emulate_switch = False
    # The shutter of kind 4 is compared with kind 3 at the same speed argument.
    references = {speed: banner_timeline(o, 3, speed, 1, 0) for speed in (0, 1)}
    assert all(len(r) == 33 and all(q['slot'] == 3 for v in r for q in v['prims']) for r in references.values())
    strip = lambda prims: [(q['key'][:4], q['key'][5:]) for q in prims]
    for speed, submode, hidden in ((0, 1, 0), (1, 1, 0), (0, 5, 1), (1, 5, 0), (0, 5, 0), (0, 1, 1)):
        # The timeline is captured whole, so it runs without a palette fade (as the reference);
        # the fade states are covered by the 125c68 cases below.
        s.fade(*FADES[0])
        timeline = banner_timeline(o, 4, speed, submode, hidden); reference = references[speed]
        concealed = submode == 5 and hidden != 0
        s.send('bn_begin')
        for tick, visit in enumerate(timeline):
            s.send('begin', 0x12345678, 0); s.send('bn_tick', int(concealed))
            own = [q for q in visit['prims'] if q['slot'] == 1]; curtain = [q for q in visit['prims'] if q['slot'] == 3]
            assert visit['prims'] == own+curtain
            label = ('banner', speed, submode, hidden, tick)
            s.send('flush', 0); s.push()
            count = struct.unpack('<I', s.read(4))[0]; blob = s.read(count*80); rs = struct.unpack('<4I', s.read(16))
            state = struct.unpack(f'<{rs[3]}i', s.read(4*rs[3]))
            flags = dict(zip(('banner', 'curtain', 'voice', 'stop', 'swap', 'finished', 'state', 'age'), state))
            events = [(pc, a0, a1) for pc, a0, a1, *_ in visit['events']]
            assert flags['banner'] == int(bool(own)) and len(own) in (0, 2), label
            assert flags['voice'] == int((VOICE, 0x31, 0x4d) in events), (label, events)
            assert flags['stop'] == int((SOUND, -1, 0xf) in events), (label, events)
            assert flags['swap'] == int(any(pc == OLD for pc, *_ in events)) == int(any(pc == NEW for pc, *_ in events)), label
            if curtain:
                assert flags['curtain'] >= 0 and strip(curtain) == strip(reference[flags['curtain']]['prims']), (label, flags, len(curtain), len(reference[flags['curtain']]['prims']) if flags['curtain'] >= 0 else None)
                stats['curtain_visits'] += 1
            else: assert flags['curtain'] == -1 or not reference[flags['curtain']]['prims'], label
            last = tick == len(timeline)-1
            assert flags['finished'] == int(last), label
            if last: assert visit['flags'] == (0, 0), (label, visit['flags'])
            nxt = (o.word(0x1239da4), o.word(0x1239da8)) if last else (timeline[tick+1]['state'], timeline[tick+1]['age'])
            assert (flags['state'], flags['age']) == nxt, (label, flags, nxt)
            stats['visits'] += 1; stats['banner_visits'] += bool(own)
        assert len(timeline) == 0x5a+0xf+3+0xf
    # 125c68(speed, n) before the shutter: the two banner sprites alone, with every fade state.
    for n in range(0, 0x5b, 1 if not quick else 9):
        for submode, hidden in ((1, 0), (5, 0), (5, 1)):
            if n % 4 == 0: s.fade(*FADES[(n//4) % len(FADES)])
            p.write(G+0xa0, submode, 4); p.write(0x443140, hidden, 4); p.write(0x3db908, 1, 4)
            s.begin(colour=0x00c0ffee+n, blend=n & 1)
            assert o.go(0x125c68, [n & 1, n]) == 1
            p.write(0x3db908, 0, 4)
            s.send('bn_begin'); s.send('bn_tick', int(submode == 5 and hidden))
            prims, state = s.flush(('banner sprites', n, submode, hidden))
            assert len(prims) == (0 if submode == 5 and hidden else 2)
    s.close()
    return stats, s.counts()


def name_entry(job):
    exe, seed, runs, quick = job
    rng = random.Random(seed); s = Session(exe); o = s.o; p = o.p
    stats = dict(runs=0, ticks=0, finished_by=dict(start=0, end=0, timeout=0), blink_hidden=0)
    for index in range(runs):
        mode = 1+index % 2; seat = mode-1
        p.memory[G:G+0xa8] = bytes(0xa8)
        for k in range(0x2a): s.send('g', k, 0)
        s.g(0, mode)
        s.fade(*FADES[index % len(FADES)] if index % 3 == 2 else FADES[0])
        o.go(0x1c98a0); s.send('ne_begin')
        style = index % 5; after = 0
        for frame in range(2200):
            pressed = 0
            if style == 0:
                if rng.random() < 0.25: pressed = rng.choice((0x40, 0x80, 0x80, 2, 4, 0x200, 0x400, 0x40 | 2, 0x80 | 0x400))
            elif style == 1:
                if rng.random() < 0.5: pressed = rng.choice((0x80, 0x80, 0x40, 2, 2, 0x200))
                if frame == 300+index: pressed = 8
            elif style == 2:
                if frame % 7 == 0: pressed = 0x40
                if frame % 31 == 5: pressed |= 4
            elif style == 3:
                if frame < 200 and rng.random() < 0.3: pressed = rng.choice((0x80, 2))
            pads = [0, 0]; pads[seat] = pressed; pads[seat ^ 1] = rng.choice((0, 8, 2, 0x40))
            finished = o.word(0x582a5c)
            o.pads(pads); s.begin(colour=rng.getrandbits(32), blend=rng.randrange(2))
            o.go(0x1c9928, [TASK]); s.send('ne_tick', pressed)
            _, state = s.flush(('name', index, frame), paint_frame=(frame % 37 == 0 or frame < 3) and (not quick or index < 2))
            name = bytes(p.memory[0x133f7d0:0x133f7d4])
            want = (*[signed(v, 8) for v in name], o.word(0x133f7c0), o.word(0x133f7c4), o.word(0x133f7c8), o.word(0x133f7cc),
                    o.word(0x582a4c), o.word(0x582a54), o.word(0x582a58), o.word(0x582a5c), o.word(0x582a60))
            if tuple(state) != want: raise AssertionError(('name', index, frame, state, want))
            stats['ticks'] += 1; stats['blink_hidden'] += o.word(0x582a4c) == 0
            if not finished and o.word(0x582a5c):
                stats['finished_by']['start' if pressed & 8 else 'timeout' if o.word(0x133f7c8) < 0 else 'end'] += 1
            if o.word(0x582a5c):
                after += 1
                if after >= 0xb0: break   # the commit visit (1c5150) is covered by validate_arcade_run.py
        stats['runs'] += 1
        log('name run', index, frame, o.instructions)
    s.close()
    return stats, s.counts()


def unlock_notice(job):
    exe, seed, runs, quick, first, step = job
    rng = random.Random(seed+first); s = Session(exe); o = s.o; p = o.p
    stats = dict(runs=0, ticks=0, items_shown=set(), empty_runs=0, skipped_waits=0, draw_cases=0)
    # The native image starts from the factory defaults; the oracle's option block may differ.
    for off in range(0x98): s.send('opt', off, p.memory[OPTION+off])
    s.send('set', 2, p.memory[0x43d052])
    if first == 0: stats.update(logic=unlock_logic(s, rng, quick))
    for index in range(first, runs, step):
        mode = 1+index % 2
        p.memory[G:G+0xa8] = bytes(0xa8)
        for k in range(0x2a): s.send('g', k, 0)
        s.g(0, mode); s.g(8, rng.randrange(2)); s.g(0x90, rng.randrange(100000))
        # Option bytes that leave between zero and several items pending.
        for off in range(0x3e, 0x47): s.option(off, int(rng.random() < 0.8))
        for off in range(0x47, 0x78): s.option(off, int(rng.random() < (0.02, 0.2, 0.5, 0.95)[index % 4]))
        for off in range(0x7e, 0x96): s.option(off, int(rng.random() < 0.3) if off < 0x90 or off > 0x93 else 0)
        for off in range(0x81, 0x8a): s.option(off, int(rng.random() < 0.5))
        if index == 3:
            for k, v in enumerate((0x20, 0xbf, 2, 0)): s.option(0x90+k, v)
        for k in range(8):
            v = int(rng.random() < 0.2); p.write(SESSION+4*k, v, 4); s.send('sess', k, v)
        s.fade(*FADES[index % len(FADES)] if index % 3 == 2 else FADES[0])
        s.send('pulse', o.word(0x584ff8), o.word(0x584ffc))
        o.begin(); s.send('begin', 0xffffffff, 1); s.send('clear')
        o.go(0x1e5d88); s.send('un_enter')
        _, state = s.flush(('unlock enter', index), paint_frame=False, prims=[], compare=False)
        check_events(('unlock enter', index), o, state)
        count = o.word(0x584f64); items = list(struct.unpack(f'<{count}i', p.memory[0x13430d0:0x13430d0+4*count]))
        assert list(state[19:20+count]) == [count]+items, (state[19:], items)
        assert bytes(p.memory[OPTION:OPTION+0x98]) == native_options(s)
        stats['empty_runs'] += count == 0; stats['items_shown'].update(items)
        left = None; patience = rng.choice((0, 0, 3, 25))
        for frame in range(4000):
            pads = [0, 0]; f = o.word(0x584f6c)
            if rng.random() < 0.02: pads[rng.randrange(2)] = rng.choice((1, 2, 4, 8, 0x200, 0x400, 0x10, 0x60e))
            if f >= 0x3c and o.word(0x584f70) == 0:
                patience -= 1
                if patience < 0: pads[mode-1] = rng.choice((2, 4, 8, 0x200, 0x400)); patience = rng.choice((0, 0, 3, 25))
            elif f == 20 and rng.random() < 0.2: pads[mode-1] = 4; stats['skipped_waits'] += 1
            o.pads(pads); s.begin(colour=rng.getrandbits(32), blend=rng.randrange(2))
            o.go(0x1e5e90, [TASK]); s.send('un_tick', pads[0], pads[1])
            _, state = s.flush(('unlock', index, frame), paint_frame=(f in (0, 1, 30, 59, 60) or frame % 53 == 0) and (not quick or index < 3))
            e = check_events(('unlock', index, frame), o, state)
            want = (o.word(0x584f60), o.word(0x584f68), o.word(0x584f6c), o.word(0x584f70), o.word(0x584ff8), o.word(0x584ffc))
            if tuple(state[19:25]) != want: raise AssertionError(('unlock', index, frame, state[19:25], want))
            stats['ticks'] += 1
            if e['exit']:
                assert e['save'] and e['switch'] == (1, 1, 0x1e6130, 0x1e8850); left = frame
            if left is not None and frame > left+5: break
        assert left is not None
        log('unlock run', index, count, frame, o.instructions)
        # Destructor 1e6130.
        o.begin(); s.send('begin', 0xffffffff, 1)
        o.go(0x1e6130); s.send('un_leave')
        _, state = s.flush(('unlock leave', index), paint_frame=False, prims=[], compare=False)
        assert list(state) == [o.word(G+4*k) for k in range(0x2a)], ('unlock leave', index)
        stats['runs'] += 1
    # 1e63c8 / 1e64a8 for every text and alpha.
    for item in range(16 if first == 0 else 0):
        text = p.read(0x584f20+4*item, 4)
        for alpha in (0, 1, 63, 128, 254, 255) if not quick else (128, 255):
            lines = o.go(0x1e2950, [text])
            s.send('pulse', o.word(0x584ff8), o.word(0x584ffc))
            if alpha == 128: s.fade(*FADES[item % len(FADES)])
            s.begin(colour=rng.getrandbits(32), blend=rng.randrange(2))
            o.go(0x1e63c8, [text, lines, alpha]); s.send('un_draw', item, alpha)
            _, state = s.flush(('unlock draw', item, alpha), paint_frame=alpha in (128, 255))
            assert tuple(state) == (o.word(0x584ff8), o.word(0x584ffc))
            stats['draw_cases'] += 1
    s.close()
    stats['items_shown'] = sorted(stats['items_shown'])
    return stats, s.counts()


def native_options(s):
    s.send('options'); s.push(); return s.read(0x98)


def run_job(job):
    return dict(quote=win_quote, result=versus_result, banner=banner, name=name_entry, unlock=unlock_notice)[job[0]](job[1:])


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--quick', action='store_true'); ap.add_argument('--only')
    args = ap.parse_args()
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ORIGINAL
    asset = (ASSETS/extract_arcade_results.NAME).read_bytes()
    assert asset == extract_arcade_results.build(raw)[0], 'run extract_arcade_results.py first'
    quick = args.quick
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp)/'driver.cpp'; cpp.write_text(DRIVER); exe = cpp.with_suffix('')
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp, ROOT/'src/arcade_results.cpp',
                        ROOT/'src/arcade_run.cpp', ROOT/'src/system_data.cpp', ROOT/'src/menu_canvas.cpp', ROOT/'src/console_menu.cpp',
                        ROOT/'src/game_random.cpp', ROOT/'src/scalar_float.cpp', '-o', exe], check=True)
        e = str(exe)
        jobs = [('quote', e, 0x135e30+i, 3 if quick else 9, 20 if quick else 196, quick) for i in range(1 if quick else 4)]
        jobs += [('result', e, 0x136a60+i, 3 if quick else 11, 20 if quick else 150, quick) for i in range(1 if quick else 2)]
        jobs += [('banner', e, quick), ('name', e, 0x1c9928, 3 if quick else 10, quick), ]
        jobs += [('unlock', e, 0x1e5d88, 4 if quick else 16, quick, i, 1 if quick else 8) for i in range(1 if quick else 8)]
        if args.only: jobs = [j for j in jobs if j[0] == args.only]
        with ProcessPoolExecutor(min(len(jobs), os.cpu_count() or 2)) as pool:
            futures = [pool.submit(run_job, job) for job in jobs]
            parts = []
            for job, future in zip(jobs, futures):
                try: parts.append(future.result())
                except Exception as error:
                    print('FAILED', job[0], repr(error)[:2000], file=sys.stderr, flush=True); raise
    total = arcade.merge([part[1] for part in parts])
    scenes = {}
    for job, (stats, counts) in zip(jobs, parts):
        entry = scenes.setdefault(job[0], dict(cases=0, frames=0, instructions=0))
        for k in ('cases', 'frames', 'instructions'): entry[k] += counts[k]
        for k, v in stats.items():
            if isinstance(v, (int, bool)) and not isinstance(v, bool): entry[k] = entry.get(k, 0)+v
            elif isinstance(v, list): entry[k] = sorted(set(entry.get(k, []))|set(map(str, v)))
            else: entry.setdefault(k, v)
    assets = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
    report = dict(status='passed', quick=quick, only=args.only, elf_sha256=ORIGINAL, asset=extract_arcade_results.NAME,
                  asset_sha256=hashlib.sha256(asset).hexdigest(),
                  visits=total['cases'], identical_primitive_lists=total['cases'], identical_640x480_frames=total['frames'],
                  original_queue_entries=total['primitives'], entries_by_kind=total['kinds'],
                  sheet_slots=[hex(v) for v in total['slots']], original_instructions=total['instructions'], scenes=scenes,
                  fade_states=len(FADES),
                  scope='Whole original entries and handlers: 135e30 + 136000 (136400 draw, 1353a0 / 135438 board, 1a3070 / 1a2870 / 113028 '
                        'quote text, exit 1362d8), 136a60 + 136c58 (1370c8 draw, exit 136fc8), 1252f0(4, speed) + task 1251d0 with 125c68 / '
                        '125778 / 125848 / 1258a8, 1c98a0 + 1c9928 (1ca248, 1c99c8, 1c9ec8) up to the visit before the score commit, '
                        '1e5d88 + 1e5e90 + 1e6130 (1e63c8, 1e64a8, 1c1528), and the unlock routines 584f78[0..15], 584fb8[0..15], '
                        '1e3640, 1e6180, 1e62b8, 1e3f70, 1e3fa0. Stubbed callees: sound driver 1e7b70 / 1e7c00 / 1e7d60 / 1e79c8 / '
                        '1e7ad0 / 1e7b40 / 1e7af8 (requests recorded at entry), scene switch 1252f0 inside the scene handlers '
                        '(arguments recorded; it runs unmodified in the banner job), memory-card autosave 10f158, debug print '
                        '316140 / 316218, and the two disc readers 1142d8 / 1163c0, which are replaced by hooks that place the named '
                        'file where the unmodified caller expects it. One instruction of libc strcmp 31806c (318070) is rewritten so every '
                        'call takes its own byte loop: Probe lacks the MMI quadword compare of the 16-byte-aligned path; results are '
                        'identical. Tag ff4 entries (STQ quads of 108118 while 3db908 = 1) are converted to texel units before '
                        'decoding (exact power-of-two scaling). VS result only: the winner object is a fixture - 11d448, '
                        '11d488, 11e2e8, 11d528, 11d570, 11d6c8, 11d868, 11d730, 11d908, 11e3a0 and the camera calls 122e98 / '
                        '122eb8 are stubbed, the script owns object words +24 / +c0 and the native tick receives the same +c0 '
                        'value. Banner job only: 1253e0 (ArcadeRun::transitionMidpoint) and the old / new scene callbacks are '
                        'stubbed. Exit dispatchers 1362d8 / 136fc8 run unmodified with the intruder disabled (schedule +34 = 1), '
                        'so 17a2c8 is not reached; validate_arcade_run.py covers the remaining branches. Primitive lists are '
                        'compared entry by entry with exact float bits and with 3db900 / 3db8fc / 3db8f4; the sheet slot of every '
                        'textured entry is taken from the 1149d0 call. Frames are the queue painted in ascending depth by the '
                        'reference painter of validate_menu_canvas.py over a patterned background (GS rasterisation is not '
                        'executed; the scaled portrait uses the painter\'s inverse-affine pixel-centre model on both sides). '
                        'The banner shutter is compared as original kind-4 queue entries against the original kind-3 timeline '
                        'at the frame index the native tick reports for VsCurtain, not as native pixels. Fighter objects are '
                        'not drawn by either side.')
    REPORT.write_text(json.dumps(report, indent=2)+'\n'); print(json.dumps({k: v for k, v in report.items() if k != 'scope'}, indent=1))

if __name__ == '__main__':main()
