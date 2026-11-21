#!/usr/bin/env python3
"""Compare the ending engine (182968 / 182a98 / 182d30, 19c1c8) with src/arcade_ending.cpp.

1. Script records. Each of the 50 ORIGINAL script functions behind 4eefe8 is executed with every
   script primitive replaced by a return stub; the primitive calls (register arguments) and the
   stores into the scene objects are recorded in execution order and must equal the records of
   arcade_ending.bin as the native EndingData loads them (strings by content).
2. Page renderers 1a2468 / 1a2540 / 1a26b0 / 1a2870 / 1a25f0 called directly: queue entries, the
   completion result and 3d3ab0 against layoutEndingPage + drawEnding.
3. Playback. The original coroutine body runs on its own stack from one 112a28 call to the next,
   framed by the original 113aa8 (fade latch), the picture task 1a4c20 and 113b28 (flash quad and
   the CLUT pass 116588). Every visit compares the submission queue, the 640x480 frame on the
   painted visits, the eight scene objects, the object queue 479250, the fade / camera / text
   registers and the sound, music, loader and scene-switch requests with the native engine.
"""
import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from validate_menu_canvas import Oracle as CanvasOracle, paint, native_keys, bits
from character_tiles_oracle import ROOT
from extract_console_versus_art import ORIGINAL, PACKETS
from mips_probe import Probe, signed
from validate_arcade_run import STRCMP
import extract_arcade_ending as ext

REPORT = ROOT/'outputs/ss6-feasibility/arcade_ending_validation.json'
ELF = ROOT/'work/ss6/extracted/SLPS_255.59'
PACKAGE = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
RETURN = struct.pack('<II', 0x03e00008, 0x0000102d)
# Return stubs. Sound driver, debug print, kernel thread creation, scene switch, the disc loader
# of resource "99a" (served as a memory fixture) and the memory-card autosave.
SOUND = (0x1e7b70, 0x1e7ba0, 0x1e79c8, 0x1e7d60, 0x1e7ad0, 0x1e7b40, 0x1e8298, 0x1e7c00, 0x1e7aa8, 0x213180, 0x213238)
PLATFORM = (0x316140, 0x316218, 0x100e58, 0x1252f0, 0x120110, 0x10f158)
TEXTURE, FILE, YIELD = 0x1142d8, 0x102810, 0x112a28
TRAMPOLINE, TRAP, STAGE = 0x1f90000, 0x1f90100, 0x1f90200
ACT, PORTRAIT, SCRATCH_FILE, TEXT = 0x1700000, 0x1740000, 0x1fa0000, 0x1760000
OPTION, G, SEATS = 0x43d058, 0x4c3808, 0x456890
OBJECTS, QUEUE, LIST = 0x4ef0d0, 0x479250, 0x4efa98
BSS_END = 0x1606d6c
STACK = (0x12d4f80, 0x1000)
EXIT = 0x1ffff00
KINDS = ('Music', 'MusicStop', 'Sound', 'ObjectSound', 'BackgroundClear', 'BackgroundStage', 'BackgroundPicture', 'Portrait',
         'TextColours', 'PaletteReset', 'PaletteBake', 'PaletteSave', 'Exit', 'MenuBackdrop')
K = {name: i for i, name in enumerate(KINDS)}

DRIVER = r'''
#include "arcade_ending.hpp"
#include "game_random.hpp"
#include "system_data.hpp"
#include <bit>
#include <fstream>
#include <iostream>
#include <iterator>
#include <sstream>
using namespace ss6;
template<class T> static void put(const T& v){std::cout.write(reinterpret_cast<const char*>(&v),sizeof v);}
int main(int argc,char** argv){
 if(argc!=2)return 2;
 MenuCanvas canvas(argv[1]);EndingData data(argv[1]);EndingArt art(argv[1]);MenuDrawList list;
 std::ifstream file(std::string(argv[1])+"/arcade_run.bin",std::ios::binary);
 const std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(file)),{});
 const ArcadeTables tables(bytes);SystemData system(argv[1]);GameRandom rng;ArcadeRun run(tables,system,rng);
 EndingPlayback playback(data);ArcadeEnding scene(data);StaffRoll roll(data);
 int owner=0;bool finished=false,done=false;std::vector<EndingEvent> events;EndingFrame page;
 std::vector<uint8_t> pixels(640*480*4),base(pixels.size());
 for(int y=0;y<480;++y)for(int x=0;x<640;++x){auto* p=base.data()+4*(640*y+x);p[0]=x+3*y;p[1]=x^y;p[2]=4*x+y;p[3]=255;}
 std::string line;
 while(std::getline(std::cin,line)) try {
  std::istringstream in(line);std::string op;in>>op;
  std::vector<long long> a;for(long long v;in>>v;)a.push_back(v);a.resize(12);
  if(op=="program"){
   const auto records=data.script(unsigned(a[0]));put(uint32_t(records.size()));
   for(const auto& r:records){
    put(uint32_t(r.op));put(r.a);
    uint32_t length=0,hash=2166136261u;
    if(r.op==EndingOp::MessageAdd||r.op==EndingOp::RollAdd){const auto t=data.text(r.a[0]);length=uint32_t(t.size());for(unsigned char c:t)hash=(hash^c)*16777619u;}
    put(length);put(hash);}
   std::cout.flush();
  } else if(op=="finish"){
   // Runs a whole playback with a page button held on alternate frames; reports the visits.
   EndingPlayback p(data);std::vector<EndingEvent> e;uint32_t n=0;
   p.begin(a[1]?EndingPlayback::Mode::StaffRoll:EndingPlayback::Mode::Playback,unsigned(a[0]),0,false,false);
   while(!p.tick(n&1?0x200:0,false,256,e)){e.clear();if(++n>400000)return 5;}
   put(n);put(uint32_t(p.position()));std::cout.flush();
  } else if(op=="lbegin"){list.beginFrame();list.colour=uint32_t(a[0]);list.blend=int(a[1]);}
  else if(op=="begin"){
   playback=EndingPlayback(data);owner=0;finished=false;
   playback.begin(a[0]?EndingPlayback::Mode::StaffRoll:EndingPlayback::Mode::Playback,unsigned(a[1]),int(a[2]),a[3]!=0,a[4]!=0);
  } else if(op=="tick"){
   events.clear();list.beginFrame();
   finished=playback.tick(uint32_t(a[0]),a[1]!=0,256,events);
   drawEnding(canvas,list,data,playback.frame);
  } else if(op=="aenter"){
   scene=ArcadeEnding(data);owner=1;finished=false;
   run.game.clear();run.game.mode=int(a[0]);run.game.score=int(a[4]);
   auto& p=run.players[a[0]==1?0:1];p.character=int(a[1]);p.colour=int(a[2]);p.spirit=int(a[3]);
   scene.enter(run,a[5]!=0);
  } else if(op=="atick"){
   list.beginFrame();
   scene.tick(run,{uint32_t(a[0]),uint32_t(a[1])},256);events=scene.events;
   drawEnding(canvas,list,data,scene.playback.frame);
  } else if(op=="rbegin"){roll=StaffRoll(data);roll.enter();owner=2;finished=false;}
  else if(op=="rtick"){
   list.beginFrame();roll.tick(uint32_t(a[0]),a[1]!=0,256);events=roll.events;finished=roll.finished;
   drawEnding(canvas,list,data,roll.playback.frame);
  } else if(op=="page"){
   // renderer balloon left reveal blank n offsets...
   list.beginFrame();page=EndingFrame{};page.blank=a[4]!=0;
   std::vector<uint32_t> message;for(int i=0;i<a[5];++i)message.push_back(uint32_t(a[6+i]));
   done=layoutEndingPage(data,int(a[0]),message,int(a[1]),int(a[2]),int(a[3]),a[4]!=0,page);
   drawEnding(canvas,list,data,page,false);owner=3;
  } else if(op=="flush"){
   const auto& p=owner==1?scene.playback:owner==2?roll.playback:playback;
   const auto& f=owner==3?page:p.frame;
   uint32_t n=uint32_t(list.records.size());put(n);
   for(auto& r:list.records){uint8_t head[6]={uint8_t(r.kind),uint8_t(r.font),r.slot,r.blend,uint8_t(r.additive),0};put(head);put(r.glyph);put(r.colour);put(r.z);
    float g[8]={r.x,r.y,r.w,r.h,r.u,r.v,r.uw,r.vh};put(g);put(r.corner);}
   uint32_t tones=0;for(unsigned i=0;i<1024;++i)tones=tones*31u+p.fade.tones[i]+i;
   const auto& human=run.players[run.game.mode==1?0:1];
   uint32_t st[40]={list.colour,uint32_t(list.blend),uint32_t(list.depth),uint32_t(list.glyphs),
    uint32_t(p.fade.mode),p.fade.colour,uint32_t(p.fade.level),uint32_t(p.fade.step),uint32_t(p.fade.ceiling),uint32_t(p.fade.floor),uint32_t(p.fade.flash),tones,
    uint32_t(p.portrait[0]),uint32_t(p.portrait[1]),uint32_t(p.cameraDelta[0]),uint32_t(p.cameraDelta[1]),
    std::bit_cast<uint32_t>(p.camera[0]),std::bit_cast<uint32_t>(p.camera[1]),std::bit_cast<uint32_t>(p.camera[2]),
    std::bit_cast<uint32_t>(p.cameraOffset[0]),std::bit_cast<uint32_t>(p.cameraOffset[1]),std::bit_cast<uint32_t>(p.cameraOffset[2]),
    uint32_t(p.balloon),uint32_t(p.message.size()),uint32_t(p.roll.size()),uint32_t(p.reveal),uint32_t(owner==3?f.glyphEnd:p.glyphs),
    uint32_t(owner==3?done:finished),uint32_t(p.skipped()),
    uint32_t(scene.phase),uint32_t(scene.nameEntry.active),uint32_t(run.game.levelEnding),uint32_t(run.game.challengerInhibit),
    system.option(size_t(0x81+human.spirit)),system.option(size_t(0x47+human.character)),uint32_t(run.transition.next),
    uint32_t(run.transition.kind),uint32_t(run.transition.speed),run.transition.destructor,uint32_t(scene.nameCommitted)};put(st);
   for(const auto& o:p.objects)for(unsigned i=0;i<78;++i)put(o[i]);
   put(uint32_t(f.objects.size()));for(const auto& o:f.objects)for(unsigned i=0;i<78;++i)put(o[i]);
   put(uint32_t(events.size()));for(const auto& e:events){put(uint32_t(e.kind));put(e.a);put(e.b);put(e.c);put(e.d);}
   if(a[0]){
    for(const auto& e:events)art.apply(e);
    art.setFade(f.fade);
    canvas.setFade((f.fade.mode&2)!=0,f.fade.level,f.fade.colour);
    pixels=base;art.rasterise(canvas,list,pixels);std::cout.write(reinterpret_cast<const char*>(pixels.data()),pixels.size());
   } else for(const auto& e:events)art.apply(e);
   std::cout.flush();
  } else return 3;
 } catch(const std::exception& e){std::cerr<<line<<": "<<e.what()<<std::endl;return 4;}
}
'''


# ---------------------------------------------------------------------------------------------
def asset_scripts():
    """arcade_ending.bin as (opcode, arguments) with strings resolved to bytes."""
    d = (PACKAGE/ext.NAME).read_bytes()
    _, n, count, pool_size = struct.unpack_from('<4I', d, 4)
    directory = [struct.unpack_from('<3I', d, 20+12*i) for i in range(n)]
    base = 20+12*n; pool = d[base+28*count:base+28*count+pool_size]
    text = lambda off: pool[off:pool.index(b'\0', off)]
    scripts = []
    for first, length, address in directory:
        rows = []
        for k in range(first, first+length):
            r = struct.unpack_from('<7I', d, base+28*k)
            sig = 'ooi' if r[0] == ext.STORE else ext.PRIMITIVES[r[0]][2]
            rows.append((r[0], [text(v) if s == 's' else v for s, v in zip(sig, r[1:])]))
        scripts.append((address, rows))
    return scripts, pool


def trace_scripts(exe):
    """Dynamic records of the 50 original script functions against the asset and the native loader."""
    raw = ELF.read_bytes(); p = Probe(raw, finite_model=True)
    for address, _, _ in ext.PRIMITIVES: p.memory[address:address+8] = RETURN
    table = [p.read(ext.TABLE+4*i, 4) for i in range(ext.SCRIPTS)]
    scripts, _ = asset_scripts()
    native = subprocess.Popen([exe, PACKAGE], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    def read(n):
        data = native.stdout.read(n); assert len(data) == n; return data
    totals = dict(scripts=0, records=0, primitive_calls=0, object_stores=0, strings=0, instructions=0, native_visits=0)
    for index, start in enumerate(table):
        end = table[index+1] if index+1 < len(table) else ext.END
        rows = []
        def observe(pc):
            r = p.registers
            if pc in ext.BY_ADDRESS:
                code, sig = ext.BY_ADDRESS[pc]; args, ints, floats = [], iter(ext.INT_ARGS), iter(ext.FLOAT_ARGS)
                for kind in sig:
                    if kind == 'f': args.append(p.floats[next(floats)]); continue
                    v = r[next(ints)] & 0xffffffff
                    if kind == 'o':
                        assert (v-OBJECTS) % 0x138 == 0 and 0 <= (v-OBJECTS)//0x138 < 8; v = (v-OBJECTS)//0x138
                    elif kind == 's': v = bytes(p.memory[v:p.memory.index(0, v)])
                    args.append(v)
                rows.append((code, args))
            elif start <= pc < end:
                w = p.read(pc, 4)
                if w >> 26 == 0x2b:
                    at = (r[(w >> 21) & 31]+signed(w, 16)) & 0xffffffff
                    if OBJECTS <= at < OBJECTS+8*0x138:
                        rows.append((ext.STORE, [(at-OBJECTS)//0x138, (at-OBJECTS) % 0x138, r[(w >> 16) & 31] & 0xffffffff]))
                # Straight-line code: nothing but the primitive calls and the return may leave the function.
                assert w >> 26 not in (1, 4, 5, 6, 7, 20, 21, 22, 23) and not (w >> 26 == 0x11 and (w >> 21) & 31 == 8), hex(pc)
            else: assert pc in (0x1ffff00,) or any(a <= pc < a+8 for a in ext.BY_ADDRESS), hex(pc)
        _, n = p.run(start, [], limit=400000, observe=observe); totals['instructions'] += n
        address, expected = scripts[index]
        assert address == start and rows == expected, (index, next((i, a, b) for i, (a, b) in enumerate(zip(rows, expected)) if a != b) if len(rows) == len(expected) else (len(rows), len(expected)))
        native.stdin.write(f'program {index}\n'.encode()); native.stdin.flush()
        count = struct.unpack('<I', read(4))[0]; assert count == len(rows)
        for code, args in rows:
            got = struct.unpack('<9I', read(36))
            assert got[0] == code
            if ext.NAMES[code] in ('messageAdd', 'rollAdd'):
                h = 2166136261
                for c in args[0]: h = ((h ^ c)*16777619) & 0xffffffff
                assert got[7:] == (len(args[0]), h), (index, args[0]); totals['strings'] += 1
            else: assert list(got[1:1+len(args)]) == args and not any(got[1+len(args):7]), (index, code, args, got)
        # The native engine executes exactly these records: a whole playback ends behind the last one
        # (plus the fadeOut / wait pair of 182a98 unless it is the staff roll).
        roll = index == 43
        native.stdin.write(f'finish {index} {int(roll)}\n'.encode()); native.stdin.flush()
        visits, position = struct.unpack('<2I', read(8)); assert position == len(rows)+(0 if roll else 2)
        totals['native_visits'] += visits
        totals['scripts'] += 1; totals['records'] += len(rows)
        totals['object_stores'] += sum(1 for c, _ in rows if c == ext.STORE)
        totals['primitive_calls'] += sum(1 for c, _ in rows if c != ext.STORE)
    native.stdin.close(); assert native.wait() == 0
    return totals


# ---------------------------------------------------------------------------------------------
class Oracle(CanvasOracle):
    """The original ending engine with its drawing; disc, sound and kernel boundaries are served here."""
    def __init__(self):
        self.playing = False
        super().__init__()
        self.last = [0, 0]; self.context = None; self.thread_pc = self.thread_sp = None; self.thread_ra = EXIT
        self.events = []; self.task = None; self.deltas = set(); self.argument = 0
        p = self.p; elf = ELF.read_bytes()
        p.memory[0x1300000:BSS_END] = bytes(BSS_END-0x1300000)
        # 1163c0 runs again: only its disc read 102810 is served.
        p.memory[0x1163c0:0x1163c8] = elf[0x1000+0x63c0+0x10000:0x1000+0x63c0+0x10000+8]
        assert p.read(0x1163c0, 4) == 0x27bdffe0
        for pc in SOUND+PLATFORM: p.memory[pc:pc+8] = RETURN
        p.memory[0x31806c:0x31806c+len(STRCMP)] = STRCMP
        for n, pc in enumerate((TEXTURE, FILE, YIELD), 1):
            p.memory[pc:pc+8] = struct.pack('<II', 0x08000000 | TRAP >> 2, 0x241b0000 | n)
        p.write(0x3ebf28, SCRATCH_FILE, 4)
        image = (PACKAGE/'save_default.bin').read_bytes()
        p.memory[OPTION:OPTION+0x98] = image[0x618c:0x618c+0x98]
        p.memory[0x43d050:0x43d057] = image[0x6184:0x6184+7]
        p.memory[0x43d0f0:0x43d0f0+0x118] = image[0x6224:0x6224+0x118]
        # Battle stage loaders 50e080[0..11]: a return stub; the stage is not part of this scene's drawing.
        p.memory[STAGE:STAGE+8] = RETURN
        for i in range(12): p.write(0x50e080+4*i, STAGE, 4)
        # 120110 (resource "99a" into both resource slots) as a memory fixture.
        aid = (PACKAGE/'aid_99a.bin').read_bytes(); act = (PACKAGE/'act_99a.bin').read_bytes()
        p.memory[0x46a9b0:0x46a9b0+len(aid)] = aid; p.memory[ACT:ACT+len(act)] = act
        p.write(0x4751b0, ACT, 4); p.write(0x46a9a0, 0x63, 4); p.write(0x46a9a4, 0x63, 4)
        self.act_records = len(act)//60
        # Portrait sheets 0x22 / 0x23 (256x256, 8-bit) and balloon sheets 0x1f / 0x20 as 1142d8 would register them.
        for slot in (0x22, 0x23):
            for o, v in [(0, PORTRAIT+0x10000*(slot-0x22)), (4, 256), (8, 256), (12, 19), (20, 8), (24, 8), (36, 0)]: p.write(0x3a9680+slot*40+o, v, 4)
        for slot in (0x1f, 0x20):
            for o, v in [(0, PORTRAIT+0x20000+0x20000*(slot-0x1f)), (4, 512), (8, 512), (12, 20), (20, 9), (24, 9), (36, 0)]: p.write(0x3a9680+slot*40+o, v, 4)
        self.go(0x112570)       # task pool
        p.write(0x443150, 1, 4)
        self.reent = p.read(0x5d1bf8, 4)
        self.go(0x1828c0)
        for slot, bank in ((0x22, 0), (0x23, 0x10), (0x1f, 0), (0x20, 0)):
            self.reset(); p.run(0x10add8, [slot, bank]); self.sprite(slot, 0, 0, 0, 8, 8, 0, 0, 8, 8)
            tex = p.read(PACKETS+16, 8); self.slots[tex & 0x3fff, (tex >> 37) & 0x3fff] = slot
        # Both balloon sheets are registered as 4-bit with CLUT bank 0 (the fixture's choice: the PVR header is not
        # served), so the queue cannot tell them apart; they are folded into one key.
        assert len(self.slots) == 6 and self.slots[tex & 0x3fff, (tex >> 37) & 0x3fff] == 0x20, self.slots
        for a, v in [(0x3db900, 0xffffffff), (0x3db8fc, 1), (0x348a8c, 0), (0x3d3aac, bits(-200.0)), (0x348b10, 0), (0x3d3aa0, 0xffffffff),
                     (0x3d3ab0, 0), (0x3ebf18, 0), (0x3ec730, 0), (0x3ec734, 0), (0x3ec738, 0), (0x3ebf1c, 0x100), (0x3ebf20, 0), (0x3ebf24, 0),
                     (0x3ec73c, 0), (0x582a68, 0)]: p.write(a, v, 4)
        p.memory[0x4a2a58:0x4a2a70] = bytes(24)
        p.memory[0x3ebf30:0x3ebf30+0x800] = bytes(0x800)
        self.instructions = 0; self.packets = 0; self.events = []; self.task = None
        self.playing = True
        self.textures()

    def refresh(self):
        # The base class integrates nothing between frames; during playback 113b28 runs 116588 itself.
        if not self.playing: super().refresh()

    def textures(self):
        p = self.p
        clut = lambda first: np.frombuffer(p.memory, np.uint8, 1024, 0x11e7980+4*first).reshape(256, 4)
        self.tex[4] = clut(0x200)[np.frombuffer(p.memory, np.uint8, 1024*1024, p.read(0x3a9680+4*40, 4))].reshape(1024, 1024, 4)
        for slot, first in ((0x22, 0), (0x23, 0x100)):
            self.tex[slot] = clut(first)[np.frombuffer(p.memory, np.uint8, 256*256, PORTRAIT+0x10000*(slot-0x22))].reshape(256, 256, 4)

    def watch(self, pc):
        p = self.p; r = p.registers; a = lambda n: signed(r[4+n], 32)
        if pc == 0x1e7c00: self.events.append((K['Music'], a(0), a(1), 0, 0))
        elif pc == 0x1e7ad0: self.events.append((K['MusicStop'], 0, 0, 0, 0))
        elif pc == 0x1e7b70: self.events.append((K['Sound'], a(0), a(1), 0, 0))
        elif pc == 0x1e8298: self.events.append((K['ObjectSound'], a(0), a(1), r[6] & 0xffffffff, 0))
        elif pc == 0x112a70 and a(0) == 0xfa1:
            self.events.append((K['BackgroundClear'], 0, 0, 0, 0)); self.task = None
        elif pc == STAGE: self.events.append((K['BackgroundStage'], signed(r[17], 32), 0, 0, 0))
        elif pc in (0x1a4b54, 0x1a4be0):
            assert self.task is None; self.task = r[2] & 0xffffffff
        elif pc == 0x112f30: self.events.append((K['TextColours'], a(0), a(1), 0, 0))
        elif pc == 0x1159d0: self.events.append((K['PaletteReset'], 0, 0, 0, 0))
        elif pc == 0x1174b8: self.events.append((K['PaletteBake'], a(0), a(1), p.read(0x3ec730, 4), p.read(0x3ec734, 4)))
        elif pc == 0x117438: self.events.append((K['PaletteSave'], 0, 0, 0, 0))
        elif pc == 0x182c78: self.events.append((K['MenuBackdrop'], p.read(0x4eefd4, 4), 0, 0, 0))   # behind 1ce478 and the 4eefd4 store
        elif pc == 0x1252f0: self.events.append((K['Exit'], a(0), a(1), r[6] & 0xffffffff, r[7] & 0xffffffff))
        elif pc == 0x11f4e4 or pc == 0x11f4dc: pass
        elif pc == 0x120af0: self.deltas.add(r[2] & 0xffffffff)     # 11f450 result inside 120ac8

    def serve(self, service):
        p = self.p; r = p.registers
        name = bytes(p.memory[r[5 if service == 1 else 4] & 0xffffffff:][:64]).split(b'\0')[0].decode('ascii')
        if service == 1:
            slot = r[4] & 0xffffffff
            data = (PACKAGE/(name[:-4]+'.tex')).read_bytes(); assert name.endswith('.pvr')
            if slot == 4:
                at = p.read(0x3a9680+4*40, 4); assert len(data) == 1024*1024
                if name.startswith('ed_bg'):
                    self.events.append((K['BackgroundPicture'], int(name[5:7]), p.read(self.task+0x1c, 4), 0, 0))
                else: assert name == 'PS2_menu_bg00_00.pvr'
                p.memory[at:at+len(data)] = data
            elif slot in (0x22, 0x23):
                assert name.startswith('demo_') and len(data) == 256*256
                indices = set(data); assert indices <= {0}|set(range(0xc0, 0x100)), sorted(indices)[:8]
                at = PORTRAIT+0x10000*(slot-0x22); p.memory[at:at+len(data)] = data
                self.events.append((K['Portrait'], slot-0x22, int(name[5:7]), 0, 0))
            else: assert slot in (0x1f, 0x20) and name.startswith('hukidasi'), (slot, name)
            return 0
        assert name.endswith('.pvp'), name
        data = (PACKAGE/(name[:-4]+'.pal')).read_bytes()
        assert len(data) <= (r[6] & 0xffffffff)
        at = r[5] & 0xffffffff; p.memory[at:at+len(data)] = data
        return len(data)

    def go(self, pc, *args, resume=False, sp=None, ra=None):
        """Run to the end or to the yield; serve the disc boundaries on the way. Returns 3 at a yield."""
        p = self.p
        while True:
            p.registers[27] = 0
            if resume:
                code = [0x3c1d0000 | sp >> 16, 0x37bd0000 | sp & 0xffff, 0x3c1f0000 | ra >> 16, 0x37ff0000 | ra & 0xffff,
                        0x3c1a0000 | pc >> 16, 0x375a0000 | pc & 0xffff, 0x03400008, 0]
                p.memory[TRAMPOLINE:TRAMPOLINE+32] = struct.pack('<8I', *code)
                _, n = p.run(TRAMPOLINE, (), limit=60000000, stop_before=(TRAP,), observe=self.watch)
            else:
                _, n = p.run(pc, args, limit=60000000, stop_before=(TRAP,), observe=self.watch)
            self.instructions += n
            service = p.registers[27] & 0xffffffff
            if service not in (1, 2): return service
            p.registers[2] = self.serve(service)
            pc = ra = p.registers[31] & 0xffffffff; sp = p.registers[29] & 0xffffffff; resume = True

    def sample(self, held):
        p = self.p
        for seat, word in enumerate(held):
            p.write(0x443568+4*seat, word, 4); p.write(0x443570+4*seat, self.last[seat], 4)
            self.go(0x117fd8, seat)
        self.last = list(held)

    def begin(self):
        p = self.p
        for a in (0x345178, 0x345180, 0x378e08, 0x3db8f8, 0x4a2250): p.write(a, 0, 4)
        p.run(0x114e80)

    def start(self, entry, argument=0):
        self.thread_pc = entry; self.thread_sp = STACK[0]+4*STACK[1]-0x40; self.thread_ra = EXIT; self.context = None
        self.argument = argument

    def visit(self):
        """One coroutine visit. Returns False when the body returned instead of yielding."""
        p = self.p
        if self.context:
            p.registers, p.registers_high, p.lo, p.hi, p.lo1, p.hi1, p.floats, p.float_acc, p.float_condition = self.context
            p.registers = list(p.registers); p.registers_high = list(p.registers_high); p.floats = list(p.floats)
            p.registers[2] = 0
        else: p.registers[4] = self.argument
        stopped = self.go(self.thread_pc, resume=True, sp=self.thread_sp, ra=self.thread_ra)
        if stopped != 3:
            self.context = None; return False
        self.thread_pc = self.thread_ra = p.registers[31] & 0xffffffff; self.thread_sp = p.registers[29] & 0xffffffff
        self.context = (list(p.registers), list(p.registers_high), p.lo, p.hi, p.lo1, p.hi1, list(p.floats), p.float_acc, p.float_condition)
        return True

    def frame(self, held, name_task=None):
        """113aa8, the picture task as the dispatcher listed it, one coroutine visit, 113b28."""
        p = self.p
        self.sample(held); self.begin(); self.events = []
        live = self.task
        self.go(0x113aa8)
        if name_task:
            # Task 1c9928 (same priority, created later): its own drawing belongs to the name
            # entry slice and is discarded together with what it leaves in 3db900 / 3db8fc.
            saved = (p.read(0x3db900, 4), p.read(0x3db8fc, 4))
            self.go(0x1c9928, name_task)
            p.write(0x3db900, saved[0], 4); p.write(0x3db8fc, saved[1], 4); self.begin()
        if live: self.go(0x1a4c20, live)
        yielded = self.visit()
        self.go(0x113b28)
        return yielded

    def state(self, finished, extra=()):
        p = self.p; w = lambda at: p.read(at, 4)
        tones = 0
        for i, t in enumerate(struct.unpack_from('<1024H', p.memory, 0x3ebf30)): tones = (tones*31+t+i) & 0xffffffff
        row = [w(0x3db900), w(0x3db8fc), w(0x3db8f4), w(0x345180),
               w(0x3ebf18), w(0x3ec730), w(0x3ec734), w(0x3ec738), w(0x3ebf1c), w(0x3ebf20), w(0x3ebf24), tones,
               w(0x4eeef0), w(0x4eeef4), w(0x4efa90), w(0x4efa94), *[w(0x4a2a58+4*i) for i in range(6)],
               w(LIST), w(LIST+4), w(0x4efb30), w(0x3d3aa0), w(0x3d3ab0), int(finished)]
        return row+list(extra)

    def objects(self):
        p = self.p
        scene = [struct.unpack_from('<78I', p.memory, OBJECTS+0x138*k) for k in range(8)]
        queue = []
        for i in range(p.read(0x4a2250, 4)):
            assert p.read(QUEUE+0x148*i+0x144, 4) == 0
            queue.append(struct.unpack_from('<78I', p.memory, QUEUE+0x148*i))
        return scene, queue


class Session:
    def __init__(self, exe, name):
        self.o = Oracle(); self.name = name
        self.proc = subprocess.Popen([exe, PACKAGE], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.lines = []
        y, x = np.mgrid[:480, :640]; self.base = np.stack((x+3*y, x ^ y, 4*x+y, np.full_like(x, 255)), axis=-1).astype(np.uint8)
        self.visits = self.frames = self.primitives = self.queued = self.event_count = 0; self.kinds = {}; self.slots = set(); self.seen = set()
        self.send('lbegin', 0xffffffff, 1)
    def send(self, *parts): self.lines.append(' '.join([parts[0]]+[str(int(v)) for v in parts[1:]]))
    def read(self, n):
        data = self.proc.stdout.read(n)
        if len(data) != n: raise RuntimeError(f'Native driver stopped ({self.name})')
        return data
    def compare(self, label, painted, state, state_words, objects=True):
        """`state` is the oracle row; `state_words` the native state indices it corresponds to."""
        o = self.o; prims = o.decode()
        self.send('flush', int(painted)); self.proc.stdin.write(('\n'.join(self.lines)+'\n').encode()); self.proc.stdin.flush(); self.lines = []
        count = struct.unpack('<I', self.read(4))[0]; blob = self.read(count*80); native_state = struct.unpack('<40I', self.read(160))
        scene = [struct.unpack('<78I', self.read(312)) for _ in range(8)]
        queue = [struct.unpack('<78I', self.read(312)) for _ in range(struct.unpack('<I', self.read(4))[0])]
        events = [struct.unpack('<IiiII', self.read(20)) for _ in range(struct.unpack('<I', self.read(4))[0])]
        label = (self.name, *label)
        native = [(k[0], 0x20, *k[2:]) if k[0] == 'quad' and k[1] == 0x1f else k for k in native_keys(blob, o)]; expected = [q['key'] for q in prims]
        if native != expected:
            for i, (a, b) in enumerate(zip(native, expected)):
                if a != b: raise AssertionError((label, 'primitive', i, a[:-1] if a[0] == 'glyph' else a, b[:-1] if b[0] == 'glyph' else b))
            raise AssertionError((label, 'primitive count', len(native), len(expected)))
        got = [native_state[i] for i in state_words]; want = [v & 0xffffffff for v in state]
        if got != want: raise AssertionError((label, 'state', [(state_words[i], hex(a), hex(b)) for i, (a, b) in enumerate(zip(got, want)) if a != b]))
        if objects:
            original_scene, original_queue = o.objects()
            for k in range(8):
                if scene[k] != original_scene[k]:
                    raise AssertionError((label, 'object', k, [(hex(4*i), hex(a), hex(b)) for i, (a, b) in enumerate(zip(scene[k], original_scene[k])) if a != b]))
            if queue != original_queue: raise AssertionError((label, 'object queue', len(queue), len(original_queue)))
            self.queued += len(queue)
            want_events = [(k, a, b, c & 0xffffffff, d & 0xffffffff) for k, a, b, c, d in o.events]
            if events != want_events: raise AssertionError((label, 'events', events, want_events))
            self.event_count += len(events)
            for e in events: self.seen.add(KINDS[e[0]])
        for q in prims:
            self.kinds[q['kind']] = self.kinds.get(q['kind'], 0)+1
            if q['kind'] == 'quad': self.slots.add(q['slot'])
        self.primitives += len(prims); self.visits += 1
        if painted:
            o.textures()
            expected_frame = paint(o, prims, self.base.astype(np.int32)).astype(np.uint8)
            got = np.frombuffer(self.read(self.base.size), np.uint8).reshape(self.base.shape)
            if not np.array_equal(got, expected_frame):
                bad = np.any(got != expected_frame, axis=-1); y, x = map(int, np.argwhere(bad)[0])
                raise AssertionError((label, 'pixels', int(bad.sum()), x, y, got[y, x].tolist(), expected_frame[y, x].tolist()))
            self.frames += 1
        return prims, native_state
    def close(self):
        self.proc.stdin.close(); assert self.proc.wait() == 0
    def result(self, **extra):
        return dict(name=self.name, visits=self.visits, frames=self.frames, primitives=self.primitives, kinds=self.kinds, slots=sorted(self.slots),
                    object_queue_records=self.queued, events=self.event_count, event_kinds=sorted(self.seen),
                    instructions=self.o.instructions, deltas=sorted(self.o.deltas), **extra)


PLAY = list(range(28))                 # native state words compared on a playback visit
ARCADE = PLAY+[30, 31, 32, 33, 34]     # + name entry lock, g+34, g+30, the two clear-record bytes


class Painter:
    def __init__(self, period): self.period = period; self.n = 0
    def __call__(self, force=False):
        self.n += 1
        return force or self.n <= 3 or self.n % self.period == 0


def playback_case(spec):
    """182a98(script) on the coroutine stack, with scripted pads."""
    exe, name, script, colour, gallery, alternate, plan, limit = spec
    plan = make_plan(plan)
    s = Session(exe, name); o = s.o; p = o.p; paint_now = Painter(11)
    seat = 1 if gallery else 0
    p.write(G, 0xd if gallery else 1, 4); p.write(0x4ef0c4, seat, 4); p.write(0x4ef0c8, colour, 4); p.write(0x43d052, alternate, 1)
    o.start(0x182a98, script); s.send('begin', 0, script, colour, int(gallery), alternate)
    stats = dict(script=script, blank_visits=0, text_visits=0, skipped=False, finished=False, portrait_visits=0)
    last_events = True
    for frame in range(limit):
        word, locked = plan(frame)
        p.write(0x582a68, locked, 4)
        held = (0, word) if seat else (word, 0)
        blank_before = None
        yielded = o.frame(held)
        s.send('tick', word, locked)
        # A gallery playback's return visit continues into 1ce478 (slot 4 becomes the menu backdrop) and the
        # selection UI 13f4a8, which finishes that frame: primitives and state only.
        painted = paint_now(bool(o.events) or last_events) and (yielded or not gallery)
        prims, state = s.compare(('visit', frame), painted, o.state(not yielded), PLAY)
        last_events = bool(o.events)
        stats['text_visits'] += any(q['kind'] == 'glyph' for q in prims)
        stats['portrait_visits'] += any(q['kind'] == 'quad' and q['slot'] in (0x22, 0x23) for q in prims)
        stats['blank_visits'] += len(prims) == 1 and prims[0]['kind'] == 'flat' and prims[0]['rect'] == (0, 0, 640, 480)
        if not yielded:
            stats['finished'] = True; stats['skipped'] = bool(state[28]); break
    assert stats['finished'] or limit < 100000, (name, 'did not finish')
    s.close()
    return s.result(scene='playback 182a98', **stats)


def arcade_case(spec):
    """Scene entry 182968 and the coroutine 182d30 with the name entry task 1c9928."""
    exe, name, mode, character, colour, spirit, score, alternate, plan, limit = spec
    plan = make_plan(plan)
    s = Session(exe, name); o = s.o; p = o.p; paint_now = Painter(11)
    seat = 0 if mode == 1 else 1
    p.write(G, mode, 4); p.write(G+0x90, score, 4); p.write(0x43d052, alternate, 1)
    for off, v in ((0, character), (4, colour), (8, spirit)): p.write(SEATS+0x30*seat+off, v, 4)
    # Scene entry up to its 1126f0 call names the coroutine; the rest of the entry runs unmodified.
    saved = bytes(p.memory[0x1126f0:0x1126f8])
    p.memory[0x1126f0:0x1126f8] = struct.pack('<II', 0x08000000 | TRAP >> 2, 0x241b0005)
    assert o.go(0x182968) == 5
    task = [p.registers[n] & 0xffffffff for n in (5, 6, 7)]; assert task == [0x182d30, *STACK], task
    p.memory[0x1126f0:0x1126f8] = saved
    assert o.go(0x1126f0, resume=True, sp=p.registers[29] & 0xffffffff, ra=p.registers[31] & 0xffffffff) == 0
    assert p.read(G+0x30, 4) == 1
    o.start(0x182d30); s.send('aenter', mode, character, colour, spirit, score, alternate)
    name_task = None; created = []
    watch = o.watch
    def spy(pc):
        if pc == 0x1c9864: created.append(p.registers[2] & 0xffffffff)     # behind 112670 in 1c9830
        watch(pc)
    o.watch = spy
    stats = dict(mode=mode, character=character, name_entry=False, locked_visits=0, exit_visit=None, committed_visit=None, roll_visits=0)
    last_events = True
    for frame in range(limit):
        word = plan(frame)
        held = (0, word) if seat else (word, 0)
        if name_task and (p.read(name_task+4, 4) & 6 or not p.read(name_task+4, 4)): name_task = None      # the task ended itself
        assert o.frame(held, name_task)
        if created: name_task = created.pop(); stats['name_entry'] = True
        s.send('atick', *held)
        extra = [p.read(0x582a68, 4), p.read(G+0x34, 4), p.read(G+0x30, 4), p.read(OPTION+0x81+spirit, 1), p.read(OPTION+0x47+character, 1)]
        prims, state = s.compare(('arcade', frame), paint_now(bool(o.events) or last_events), o.state(False, extra), ARCADE)
        last_events = bool(o.events)
        stats['locked_visits'] += extra[0]
        if state[39] and stats['committed_visit'] is None: stats['committed_visit'] = frame
        if state[29] == 2: stats['roll_visits'] += 1
        exits = [e for e in o.events if e[0] == K['Exit']]
        if exits:
            assert exits == [(K['Exit'], 1, 1, 0x182a48, 0x138340)] and state[35:39] == (0x138340, 1, 1, 0x182a48), (exits, state[35:39])
            stats['exit_visit'] = frame
        if stats['exit_visit'] is not None and frame >= stats['exit_visit']+3: break
    assert stats['exit_visit'] is not None, name
    # Destructor 182a48.
    o.go(0x182a48); assert p.read(G+0x30, 4) == 0 and p.read(G+0x90, 4) == 0
    s.close()
    return s.result(scene='arcade 182968 / 182d30', **stats)


def page_case(spec):
    """The five page renderers called directly."""
    exe, seed, count = spec
    import random
    rng = random.Random(seed); s = Session(exe, f'pages/{seed}'); o = s.o; p = o.p
    _, pool = asset_scripts()
    offsets = [0]+[i+1 for i, c in enumerate(pool[:-1]) if c == 0]
    functions = {1: 0x1a2468, 2: 0x1a2540, 3: 0x1a26b0, 4: 0x1a2870, 5: 0x1a25f0}
    done_count = 0
    for case in range(count):
        renderer = rng.choice((1, 1, 2, 2, 3, 4, 5)); n = rng.randrange(0, 5)
        chosen = [rng.choice(offsets) for _ in range(n)]
        left = rng.choice((-1, 0, 5, 0x30, 0x33, 0x34, 0x35)); balloon = rng.randrange(1, 11)
        total = sum(len(pool[c:pool.index(b'\0', c)]) for c in chosen)
        reveal = rng.choice((-1, 0, 1, rng.randrange(0, total+2), 0x9c4, total//2)); blank = rng.random() < .12
        at = TEXT
        p.write(LIST, balloon, 4); p.write(LIST+4, n, 4)
        for i in range(4):
            if i < n:
                text = pool[chosen[i]:pool.index(b'\0', chosen[i])+1]; p.memory[at:at+len(text)] = text; p.write(LIST+8+4*i, at, 4); at += len(text)
            else: p.write(LIST+8+4*i, 0, 4)
        colour, blend = rng.getrandbits(32), rng.randrange(2)
        for a, v in ((0x4eeef0, left), (0x3d3aa0, reveal), (0x3ec73c, int(blank)), (0x3d3ab0, rng.randrange(50)), (0x3db900, colour), (0x3db8fc, blend)): p.write(a, v, 4)
        o.begin(); s.send('lbegin', colour, blend)
        value, k = p.run(functions[renderer], [LIST], limit=3000000); o.instructions += k
        s.send('page', renderer, balloon, left, reveal, int(blank), n, *chosen)
        row = [p.read(0x3db900, 4), p.read(0x3db8fc, 4), p.read(0x3db8f4, 4), p.read(0x345180, 4), p.read(0x3d3ab0, 4), value & 1]
        # Balloon sheets are not painted by the native module: primitives only for renderer 3.
        s.compare(('page', case, renderer), renderer != 3 and case % 3 == 0, row, [0, 1, 2, 3, 26, 27], objects=False)
        done_count += value & 1
    p.write(0x3ec73c, 0, 4)
    s.close()
    return s.result(scene='page renderers', cases=count, complete_pages=done_count)


# Pad plans (picklable descriptions) --------------------------------------------------------------
def make_plan(spec):
    kind = spec[0]
    if kind == 'fast':
        # Natural typing for `natural` visits, then a page button on alternate visits; START at `start`.
        _, natural, start = spec
        def plan(frame):
            if start is not None and frame >= start: return (8 if frame == start else 0), 0
            return (0x200 if frame >= natural and frame % 2 else 0), 0
    elif kind == 'locked':
        # The lock 582a68 holds until visit 100: START and the page buttons are ignored under it.
        def plan(frame):
            locked = int(frame < 100)
            if frame in (30, 31, 60): return 8, locked
            if frame == 130: return 8, 0
            return (0x200 if frame % 2 else 0), locked
    elif kind == 'gallery':
        _, cancel = spec
        def plan(frame):
            if frame == cancel: return 0x400, 0
            if frame == 40: return 8, 0          # START does not leave a gallery playback
            return (0x2 if frame % 3 == 0 else 0), 0
    else:
        # finish: ends the name entry (the ending stays locked until the commit); skip: skips the
        # playback; leave: skips the staff roll.
        _, finish, skip, leave = spec
        def plan(frame):
            if frame in (finish, finish+20, finish+90, skip, leave): return 8
            return 0x200 if frame % 2 else 0
    return plan


def run_case(spec):
    kind = spec[0]; started = time.time()
    result = {'playback': playback_case, 'arcade': arcade_case, 'pages': page_case}[kind](spec[1:])
    result['seconds'] = round(time.time()-started, 1)
    print(result['name'], result['visits'], 'visits', result['frames'], 'frames', result['seconds'], 's', file=sys.stderr, flush=True)
    return result


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--quick', action='store_true'); ap.add_argument('--only')
    args = ap.parse_args()
    raw = ELF.read_bytes(); assert hashlib.sha256(raw).hexdigest() == ORIGINAL
    asset = (PACKAGE/ext.NAME).read_bytes(); assert asset == ext.build(raw)[0], 'run extract_arcade_ending.py first'
    quick = args.quick
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp)/'driver.cpp'; cpp.write_text(DRIVER); exe = str(cpp.with_suffix(''))
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp, ROOT/'src/arcade_ending.cpp',
                        ROOT/'src/arcade_run.cpp', ROOT/'src/system_data.cpp', ROOT/'src/motion.cpp', ROOT/'src/menu_canvas.cpp',
                        ROOT/'src/console_menu.cpp', ROOT/'src/game_random.cpp', ROOT/'src/scalar_float.cpp', '-o', exe], check=True)
        started = time.time()
        traces = trace_scripts(exe)
        print('script records', traces, round(time.time()-started, 1), 's', file=sys.stderr, flush=True)
        big = 10**6
        cases = [
            ('pages', exe, 0x1a2468, 60 if quick else 420),
            # A whole ending without a skip: natural typing first, then fast-forward to the return of 182a98.
            ('playback', exe, 'play/0', 0, 2, False, 0, ('fast', 150 if quick else 500, 400 if quick else None), 450 if quick else big),
            # Objects with colour steps, flashes and ACT sounds; skipped with START.
            ('playback', exe, 'play/10', 10, 4, False, 0, ('fast', 0, 260 if quick else 1500), big),
            ('playback', exe, 'play/21', 21, 1, False, 0, ('fast', 0, 200 if quick else 1300), big),
            ('playback', exe, 'play/39', 39, 0, False, 0, ('fast', 40, 200 if quick else 1300), big),
            ('playback', exe, 'stub/49', 49, 0, False, 0, ('fast', 0, 120 if quick else 320), big),
            ('playback', exe, 'locked/7', 7, 3, False, 0, ('locked',), big),
            ('playback', exe, 'gallery/30', 30, 0, True, 0, ('gallery', 150 if quick else 620), big),
            ('playback', exe, 'gallery/48', 48, 0, True, 0, ('gallery', 90), big),
            ('playback', exe, 'alternate/5', 5, 0, False, 1, ('fast', 0, None), big),
            ('arcade', exe, 'arcade/seat0', 1, 12, 3, 5, 250000, 0, ('arcade', 6, 240, 420 if quick else 1200), big),
            ('arcade', exe, 'arcade/seat1', 2, 33, 1, 0, 0, 0, ('arcade', -100, 70, 260 if quick else 700), big),
            ('arcade', exe, 'arcade/alternate', 1, 2, 0, 8, 0, 1, ('arcade', -100, -100, -100), big),
            # The playback skipped at visit 60, then the whole staff roll 19c1c8 to its natural exit.
            ('arcade', exe, 'arcade/roll', 1, 4, 2, 1, 0, 0, ('arcade', -100, 60, None), big),
        ]
        if args.only: cases = [c for c in cases if args.only in str(c[2])]
        with ProcessPoolExecutor(min(os.cpu_count() or 2, len(cases), 10)) as pool:
            results = list(pool.map(run_case, cases))
    total = dict(visits=sum(r['visits'] for r in results), frames=sum(r['frames'] for r in results),
                 primitives=sum(r['primitives'] for r in results), instructions=sum(r['instructions'] for r in results)+traces['instructions'],
                 object_queue_records=sum(r['object_queue_records'] for r in results), events=sum(r['events'] for r in results))
    kinds = {}
    for r in results:
        for k, v in r['kinds'].items(): kinds[k] = kinds.get(k, 0)+v
    seen = sorted({k for r in results for k in r['event_kinds']})
    deltas = sorted({d for r in results for d in r['deltas']})
    assert deltas in ([], [256]), deltas
    report = dict(status='passed', quick=quick, only=args.only, elf_sha256=ORIGINAL, asset=ext.NAME, asset_sha256=hashlib.sha256(asset).hexdigest(),
                  script_records=traces, identical_primitive_lists=total['visits'], identical_640x480_frames=total['frames'],
                  original_queue_entries=total['primitives'], entries_by_kind=kinds, object_queue_records=total['object_queue_records'],
                  requests_compared=total['events'], request_kinds_seen=seen, object_clock_deltas=deltas,
                  original_instructions=total['instructions'], cases=results,
                  scope='(1) All 50 script functions of table 4eefe8 executed whole with the 31 script primitives replaced by return stubs '
                        '(the comparison method: their register arguments and the inline object stores are the record stream). '
                        '(2) Whole 1a2468 / 1a2540 / 1a26b0 / 1a2870 / 1a25f0. (3) Whole 182a98 and whole 182968 + coroutine 182d30 '
                        '(with 19c1c8, setjmp 317598 / longjmp 3175f0, 1c9830 and the task handler 1c9928) as coroutine bodies on the '
                        'task stack from one 112a28 call to the next; per visit the harness runs the original 117fd8 pad sampling, '
                        '113aa8, the picture task handler 1a4c20 when the task existed before the visit, the visit, and 113b28 (with '
                        '116588). The task dispatcher 112838 itself and the kernel thread switch behind 1126f0 / 112a28 are not '
                        'executed; the order "picture task, name entry task, coroutine" is the harness\'s (priorities 0xa, 0x14, 0x14). '
                        'Return stubs: sound driver 1e7b70 1e7ba0 1e79c8 1e7d60 1e7ad0 1e7b40 1e8298 1e7c00 1e7aa8 213180 213238; '
                        'debug print 316140 316218; thread creation 100e58; scene switch 1252f0; resource loader 120110 (aid_99a / '
                        'act_99a supplied as a memory fixture with 46a9a0 = 46a9a4 = 0x63); autosave 10f158; the twelve battle stage '
                        'loaders of table 50e080 (background ids below 0xc: the stage is neither loaded nor drawn on either side). '
                        'Served boundaries: 1142d8 (texture by name: ed_bgNN into the slot-4 arena, demo_NN into the slot 0x22 / 0x23 '
                        'arenas, hukidasi ignored) and the disc read 102810 inside the unmodified 1163c0. strcmp 31806c is the '
                        'replacement of validate_arcade_run.py. The name entry task\'s own drawing (1c9ec8 / 1ca248) is discarded '
                        'before the comparison and its 3db900 / 3db8fc side effect undone. Scene objects are compared as their 78 '
                        'words and as object-queue records (479250); the character renderer 1208b0 / 121b80 is not executed and '
                        'objects are not part of the compared frames. Frames are the queue painted in ascending depth by the '
                        'reference painter of validate_menu_canvas.py over a patterned background (queue-to-GS translation and GS '
                        'rasterisation are not executed). Balloon sheets (renderer 3) are compared as queue entries only.')
    if not args.only: REPORT.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('cases', 'scope')}, indent=1))


if __name__ == '__main__':main()
