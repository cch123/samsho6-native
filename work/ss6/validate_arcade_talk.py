#!/usr/bin/env python3
"""Compare the arcade opening, stage dialogue and pre-final demo with SLPS-25559.

Every case runs the ORIGINAL scene entry, then the coroutine body visit by visit (from the
return address of the yield 112a28 to its next call, on the task's own stack) and finally the
destructor, and requires from src/arcade_talk.cpp on every visit:
  (a) the same ordered call list (sound, camera, stage / object / portrait requests, exits),
  (b) the same g_GameData, player records, schedule, scene words, transition record, random
      generators, fade registers 3ebf18.. with all 0x400 range flags, text colours and reveal words,
  (c) the same ordered submission queue 68c3c0 (exact float bits) and renderer globals, and
  (d) on the painted visits the same 640x480 frame.
"""
import argparse
import hashlib
import json
import os
import random
import struct
import subprocess
import tempfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from character_tiles_oracle import ROOT
from extract_console_versus_art import PACKETS, GLYPH, ORIGINAL
from validate_menu_canvas import Oracle as CanvasOracle, paint as paint_queue, native_keys, bits
from mips_probe import signed
import extract_arcade_talk

RES = ROOT/'work/ss6/extracted/resources'
PACKAGE = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
REPORT = ROOT/'outputs/ss6-feasibility/arcade_talk_validation.json'
ELF = ROOT/'work/ss6/extracted/SLPS_255.59'
RETURN = struct.pack('<II', 0x03e00008, 0x0000102d)
# `jr ra; move v0,zero` boundaries. Nothing here is scene logic.
SOUND = (0x1e7c00, 0x1e7ad0, 0x1e7b40, 0x1e7b70, 0x1e7d60, 0x1e79c8)            # sound driver requests
PRINT = (0x316140, 0x316218)                                                      # printf / puts
DISC = (0x11d488, 0x10b640, 0x1a4a98)                                             # fighter / system sheet / arena loaders
OBJECTS = (0x11e3a0,)                                                             # object pool release by tag
KERNEL = (0x100e58,)                                                              # EE CreateThread behind 1126f0
# Boundaries served by this script: entry replaced by `j TRAP; li k1, n`.
TEXTURE, FILE, YIELD, ALLOC, OBJINIT, OBJACT, OBJSTEP = 0x1142d8, 0x102810, 0x112a28, 0x11e2e8, 0x11fed0, 0x120390, 0x120ce0
TRAPS = (TEXTURE, FILE, YIELD, ALLOC, OBJINIT, OBJACT, OBJSTEP)
TRAP, TRAMPOLINE = 0x1f90100, 0x1f90000
TEXBASE, SCRATCH_FILE, OBJECT_BASE, HANDLE, PALETTE = 0x1700000, 0x1fa0000, 0x1fb0000, 0x1fc0000, 0x1e80000
G, P, S, T, PAD, O = 0x4c3808, 0x456890, 0x12d3668, 0x1239da0, 0x1237cc8, 0x43d058
BSS_END = 0x1606d6c
STOP = frozenset((TRAP,))
SIZES = {65536: (256, 256, 19), 1048576: (1024, 1024, 19), 131072: (512, 512, 20)}
OPENING, DIALOGUE, PREFINAL = (0x1c60c8, 0x1c6400, 0x1c61b8), (0x1c5290, 0x1c55d8, 0x1c53e0), (0x1c6cc0, 0x1c6e58, 0x1c6d70)
EVENTS = dict(Music=0, StopMusic=1, Voice=2, CameraPosition=3, CameraOffset=4, CameraLook=5, StageBackground=6, FreeStage=7,
              LoadCharacter=8, MapResources=9, MapIcon=10, LoadPortrait=11, ObjectCreate=12, ObjectAction=13, ObjectStep=14,
              HandOff=15, Exit=16)
NAMES = {v: k for k, v in EVENTS.items()}

DRIVER = r'''
#include "arcade_talk.hpp"
#include "game_random.hpp"
#include "system_data.hpp"
#include <bit>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <set>
#include <sstream>
using namespace ss6;
template<class T> static void put(const T& v){std::cout.write(reinterpret_cast<const char*>(&v),sizeof v);}
struct Host:ArcadeTalkObjects {
    std::array<int,2> steps{};std::array<bool,2> done{};std::array<std::set<int>,2> finishAt;
    void create(int k,int,int,int,int,uint32_t,int) override {done[k]=false;}
    void action(int k,int) override {done[k]=false;}
    void step(int k) override {if(finishAt[k].count(++steps[k]))done[k]=true;}
    bool finished(int k) override {return done[k];}
};
int main(int argc,char** argv){
 if(argc!=2)return 2;
 std::ifstream file(std::string(argv[1])+"/arcade_run.bin",std::ios::binary);
 const std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(file)),{});
 const ArcadeTables runTables(bytes);
 SystemData system(argv[1]);GameRandom rng;ArcadeRun run(runTables,system,rng);
 ArcadeTalkTables tables(argv[1]);ArcadeTalkArt art(argv[1],tables);MenuCanvas canvas(argv[1]);
 ArcadeFade fade;Host host;MenuDrawList list;
 std::unique_ptr<ArcadeOpening> opening;std::unique_ptr<ArcadeDialogue> dialogue;std::unique_ptr<ArcadePreFinal> prefinal;
 ArcadeTalkScene* scene=nullptr;
 std::vector<uint8_t> pixels(640*480*4),base(pixels.size());
 for(int y=0;y<480;++y)for(int x=0;x<640;++x){auto* p=base.data()+4*(640*y+x);p[0]=x+3*y;p[1]=x^y;p[2]=4*x+y;p[3]=255;}
 auto words=[](auto& object){return reinterpret_cast<int32_t*>(&object);};
 std::string line;
 while(std::getline(std::cin,line)){
  std::istringstream in(line);std::string op;in>>op;
  std::vector<long long> a;for(long long v;in>>v;)a.push_back(v);
  if(op=="g")words(run.game)[a[0]]=int32_t(a[1]);
  else if(op=="p")words(run.players[a[0]])[a[1]]=int32_t(a[2]);
  else if(op=="set")system.setting(size_t(a[0]))=uint8_t(a[1]);
  else if(op=="s")(a[0]==0?run.intruderFight:a[0]==1?run.mapStageIndex:run.dialoguePostFight)=int32_t(a[1]);
  else if(op=="r")rng={int32_t(a[0]),uint32_t(a[1]),uint64_t(a[2])};
  else if(op=="build")run.buildSchedule(int(a[0]),a[1]!=0,uint32_t(a[2]));
  else if(op=="roll"){run.schedule.rolls[a[0]]=uint8_t(a[1]);run.schedule.bonus[a[0]]=uint8_t(a[2]);}
  else if(op=="nointruder")run.schedule.intruderDisabled=int32_t(a[0]);
  else if(op=="finish")host.finishAt[a[0]].insert(int(a[1]));
  else if(op=="ramp")fade.ramp(uint32_t(a[0]),int32_t(a[1]));
  else if(op=="mode")fade.setMode(int32_t(a[0]));
  else if(op=="endframe")fade.endFrame();
  else if(op=="begin"){list.beginFrame();list.colour=uint32_t(a[0]);list.blend=int(a[1]);list.additive=false;}
  else if(op=="scene"){
   if(a[0]==0){opening=std::make_unique<ArcadeOpening>(tables);scene=opening.get();}
   else if(a[0]==1){dialogue=std::make_unique<ArcadeDialogue>(tables);scene=dialogue.get();}
   else {prefinal=std::make_unique<ArcadePreFinal>(tables);scene=prefinal.get();}
   scene->revealLimit=int32_t(a[1]);scene->revealCount=int32_t(a[2]);
   if(a[0]==0){
    opening->enter(run,fade,uint32_t(a[3]));
    // The map module's 1c1e30 (1c2010) makes 17 C library draws.
    for(auto& e:opening->events)if(e.kind==ArcadeTalkEvent::MapResources)for(int i=0;i<17;++i)rng.nextLibrary();
   }
   else if(a[0]==1)dialogue->enter(run,fade);
   else prefinal->enter(run,fade);
  }
  else if(op=="tick"){
   ArcadeTalkInput input;input.pressed={uint32_t(a[0]),uint32_t(a[1])};
   if(scene==opening.get())opening->tick(run,fade,host,input);
   else if(scene==dialogue.get())dialogue->tick(run,fade,host,input);
   else prefinal->tick(run,fade,input);
   scene->draw(canvas,list);
  }
  else if(op=="leave"){
   if(scene==opening.get())opening->leave(run,fade);
   else if(scene==dialogue.get())dialogue->leave(run,fade);
   else prefinal->leave(run,fade);
  }
  else if(op=="flush"){
   put(uint32_t(scene->events.size()));
   for(auto& e:scene->events){put(uint32_t(e.kind));put(e.a);put(e.f);}
   put(uint32_t(list.records.size()));
   for(auto& r:list.records){uint8_t head[6]={uint8_t(r.kind),uint8_t(r.font),r.slot,r.blend,uint8_t(r.additive),0};put(head);put(r.glyph);put(r.colour);put(r.z);
    float g[8]={r.x,r.y,r.w,r.h,r.u,r.v,r.uw,r.vh};put(g);put(r.corner);}
   std::vector<uint32_t> st;
   for(int i=0;i<42;++i)st.push_back(uint32_t(words(run.game)[i]));
   for(auto& p:run.players)for(int i=0;i<12;++i)st.push_back(uint32_t(words(p)[i]));
   const auto& s=run.schedule;
   for(auto v:s.stages)st.push_back(uint32_t(int32_t(v)));for(auto v:s.opponents)st.push_back(uint32_t(int32_t(v)));
   for(auto v:s.rolls)st.push_back(v);for(auto v:s.bonus)st.push_back(v);for(auto v:s.wins)st.push_back(v);
   st.push_back(uint32_t(s.intruderDisabled));st.push_back(uint32_t(s.substitutionDisabled));
   for(auto v:{run.intruderFight,run.mapStageIndex,run.dialoguePostFight})st.push_back(uint32_t(v));
   st.push_back(uint32_t(run.transition.kind));st.push_back(uint32_t(run.transition.speed));st.push_back(run.transition.destructor);st.push_back(uint32_t(run.transition.next));
   st.push_back(uint32_t(rng.mode));st.push_back(rng.gameSeed);st.push_back(uint32_t(rng.librarySeed));st.push_back(uint32_t(rng.librarySeed>>32));
   for(auto v:{uint32_t(fade.mode),fade.colour,uint32_t(fade.level),uint32_t(fade.speed),uint32_t(fade.maximum),uint32_t(fade.minimum),fade.textColour,fade.textShadow})st.push_back(v);
   st.push_back(uint32_t(scene->revealLimit));st.push_back(uint32_t(scene->revealCount));
   st.push_back(uint32_t(scene->portraits[0]));st.push_back(uint32_t(scene->portraits[1]));
   st.push_back(opening?uint32_t(opening->latch):0);
   for(auto v:{list.colour,uint32_t(list.blend),uint32_t(list.depth),uint32_t(list.glyphs),uint32_t(list.textDepth)})st.push_back(v);
   put(uint32_t(st.size()));std::cout.write(reinterpret_cast<const char*>(st.data()),4*st.size());put(fade.flags);
   if(a[0]){pixels=base;art.rasterise(canvas,list,pixels,fade,scene->portraits);std::cout.write(reinterpret_cast<const char*>(pixels.data()),pixels.size());}
   std::cout.flush();
  }
  else return 3;
 }
}
'''


class Oracle(CanvasOracle):
    """The original scenes; disc, sound, object-pipeline and kernel boundaries are served here."""
    def __init__(self, seed):
        super().__init__()
        p = self.p; elf = ELF.read_bytes()
        # The character-bank fixture of prepare() overlaps .bss; the scenes expect it clear.
        p.memory[0x1300000:BSS_END] = bytes(BSS_END-0x1300000)
        # 1163c0 runs again: only its disc read 102810 is served.
        p.memory[0x1163c0:0x1163c8] = elf[0x1000+0x63c0+0x10000:0x1000+0x63c0+0x10000+8]
        assert p.read(0x1163c0, 4) == 0x27bdffe0
        for pc in SOUND+PRINT+DISC+OBJECTS+KERNEL: p.memory[pc:pc+8] = RETURN
        for n, pc in enumerate(TRAPS, 1):
            p.memory[pc:pc+8] = struct.pack('<II', 0x08000000 | TRAP >> 2, 0x241b0000 | n)
        p.write(0x3ebf28, SCRATCH_FILE, 4); p.write(T-8, HANDLE, 4)
        image = (PACKAGE/'save_default.bin').read_bytes()
        p.memory[O:O+0x98] = image[0x618c:0x618c+0x98]
        p.memory[0x43d050:0x43d057] = image[0x6184:0x6184+7]
        # Resident CLUT 0..7f as 113890 uploads it: obj0.pal with entry 0 of every bank cleared.
        palette = bytearray((PACKAGE/'obj0.pal').read_bytes())
        for i in range(0, len(palette), 32): palette[i:i+2] = bytes(2)
        p.memory[PALETTE:PALETTE+512] = palette; p.write(0x439b68, 0, 4)
        p.run(0x116478, [0, 128, PALETTE], limit=150000)
        for a in (0x3ebf18, 0x3ec730, 0x3ec734, 0x3ec738, 0x3ebf20, 0x3ebf24): p.write(a, 0, 4)
        p.write(0x3ebf1c, 0x100, 4); p.write(0x3ebf2c, 1, 4)
        p.run(0x112f30, [0xffffff, 0x404040])
        p.write(0x3d3aa0, 0xffffffff, 4); p.write(0x3d3ab0, 0, 4)
        self.instructions = 0
        self.go(0x112570)   # task pool
        self.reent = p.read(0x5d1bf8, 4)
        p.write(0x443150, 1, 4); p.write(0x3d2e80, seed & 0x7fffffff | 1, 4); p.write(self.reent+0xa8, seed*2654435761 & 0xffffffffffff, 8)
        for a, v in [(0x3db900, 0xffffffff), (0x3db8fc, 1), (0x348a8c, 0), (0x3d3aac, bits(-200.0)), (0x348b10, 0)]: p.write(a, v, 4)
        self.context = None; self.thread_pc = self.thread_sp = None
        self.events = []; self.loads = []; self.objects = []; self.steps = [0, 0]; self.finish = [set(), set()]
        self.textures = {}; self.texture_top = TEXBASE; self.quads = {}; self.packets = 0
        self.tex = {}; self.unbound = 0

    def w(self, at): return signed(self.p.read(at, 4), 32)

    def observe(self, pc):
        p = self.p; r = p.registers
        a = lambda i: signed(r[4+i] & 0xffffffff, 32)
        f = lambda: tuple(p.floats[12:15])
        e = None
        if pc == 0x1149d0:
            slot = r[6] & 0xffffffff
            self.quads[p.read(0x345178, 4)] = (slot, p.read(0x3a9680+40*slot+0x10, 4))
        elif pc == 0x1e7c00: e = ('Music', a(0), a(1))
        elif pc == 0x1e7ad0: e = ('StopMusic',)
        elif pc == 0x1e7d60: e = ('Voice', a(0), a(1))
        elif pc == 0x122e98: e = ('CameraPosition', *f())
        elif pc == 0x122eb8: e = ('CameraOffset', *f())
        elif pc == 0x122ed8: e = ('CameraLook', *f())
        elif pc == 0x1a4a98: e = ('StageBackground', a(0))
        elif pc == 0x11e3a0 and a(0) == 0xfa1: e = ('FreeStage',)
        elif pc == 0x112a70 and a(0) == 0xfa1: assert self.events[-1] == ('FreeStage',)
        elif pc == 0x11d488: e = ('LoadCharacter', a(0), a(1))
        elif pc == 0x1c1e30: e = ('MapResources',)
        elif pc == 0x1c1ac0: e = ('HandOff', a(0), a(1))
        elif pc == 0x1252f0: e = ('Exit', a(0), a(1), a(2), a(3))
        elif pc in (0x1e7b40, 0x1e7b70, 0x1e79c8): raise AssertionError(hex(pc))
        if e: self.events.append(e)

    def serve(self, service):
        p = self.p; r = p.registers
        if service in (1, 2):
            name = bytes(p.memory[r[5 if service == 1 else 4] & 0xffffffff:][:64]).split(b'\0')[0].decode('ascii')
            self.loads.append(name)
            if service == 1:
                slot = r[4] & 0xffffffff
                data = (RES/(name[:-4]+'.tex')).read_bytes(); w, h, kind = SIZES[len(data)]
                at = self.texture_top; self.texture_top += len(data); assert self.texture_top <= 0x1d00000
                p.memory[at:at+len(data)] = data; self.textures[slot] = (at, w, h, kind)
                for o, v in [(0, at), (4, w), (8, h), (12, kind), (20, w.bit_length()-1), (24, h.bit_length()-1)]: p.write(0x3a9680+slot*40+o, v, 4)
                if name.startswith('map_icon_'): self.events.append(('MapIcon', int(name[9:11])))
                elif name.startswith('demo_') and name[5].isdigit(): self.events.append(('LoadPortrait', slot-0x21, int(name[5:7])))
                return 0
            data = (RES/(name[:-4]+'.pal')).read_bytes()
            assert len(data) <= (r[6] & 0xffffffff)
            at = r[5] & 0xffffffff; p.memory[at:at+len(data)] = data
            return len(data)
        if service == 4:
            k = len(self.objects); at = OBJECT_BASE+0x138*k; p.memory[at:at+0x138] = bytes(0x138); self.objects.append(at)
            p.write(at+0x20, 0xffffffff, 4)
            return at
        k = self.objects.index(r[4] & 0xffffffff); at = self.objects[k]
        if service == 5:
            # 11fed0(object, seat, action, x, y, flags); the scene stores the colour at +0x20 afterwards.
            self.events.append(['ObjectCreate', k, *[signed(r[i] & 0xffffffff, 32) for i in (5, 6, 7, 8, 9)], at]); p.write(at+0xc0, 0, 4)
        elif service == 6:
            self.events.append(('ObjectAction', k, signed(r[5] & 0xffffffff, 32))); p.write(at+0xc0, 0, 4)
        else:
            self.events.append(('ObjectStep', k)); self.steps[k] += 1
            if self.steps[k] in self.finish[k]: p.write(at+0xc0, 1, 4)
        return 0

    def go(self, pc, *args, resume=False, sp=None, ra=None):
        p = self.p
        if ra is None: ra = pc
        while True:
            p.registers[27] = 0
            if resume:
                # Probe.run presets sp and ra; the trampoline puts both back.
                code = [0x3c1d0000 | sp >> 16, 0x37bd0000 | sp & 0xffff, 0x3c1f0000 | ra >> 16, 0x37ff0000 | ra & 0xffff,
                        0x3c1a0000 | pc >> 16, 0x375a0000 | pc & 0xffff, 0x03400008, 0]
                p.memory[TRAMPOLINE:TRAMPOLINE+32] = struct.pack('<8I', *code)
                _, n = p.run(TRAMPOLINE, (), limit=40000000, stop_before=STOP, observe=self.observe)
            else:
                _, n = p.run(pc, args, limit=40000000, stop_before=STOP, observe=self.observe)
            self.instructions += n
            service = p.registers[27] & 0xffffffff
            if service not in (1, 2, 4, 5, 6, 7): return service
            p.registers[2] = self.serve(service)
            pc = ra = p.registers[31] & 0xffffffff; sp = p.registers[29] & 0xffffffff; resume = True

    def begin(self):
        p = self.p
        for a in (0x345178, 0x345180, 0x378e08, 0x3db8f8): p.write(a, 0, 4)
        p.run(0x114e80); self.quads = {}; self.events = []

    # A coroutine task is a PS2 kernel thread: its body runs on its own stack up to the
    # yield entry and is resumed at the saved return address with v0 = 0.
    def visit(self):
        p = self.p
        if self.context:
            p.registers, p.registers_high, p.lo, p.hi, p.lo1, p.hi1, p.floats, p.float_acc, p.float_condition = self.context
            p.registers = list(p.registers); p.registers_high = list(p.registers_high); p.floats = list(p.floats)
            p.registers[2] = 0
        stopped = self.go(self.thread_pc, resume=True, sp=self.thread_sp)
        assert stopped == 3, 'the coroutine returned'
        self.thread_pc = p.registers[31] & 0xffffffff; self.thread_sp = p.registers[29] & 0xffffffff
        self.context = (list(p.registers), list(p.registers_high), p.lo, p.hi, p.lo1, p.hi1, list(p.floats), p.float_acc, p.float_condition)

    def scene(self, entry, handler):
        """Scene entry; its 1126f0 call names the coroutine body and stack."""
        p = self.p; saved = bytes(p.memory[0x1126f0:0x1126f8])
        p.memory[0x1126f0:0x1126f8] = struct.pack('<II', 0x08000000 | TRAP >> 2, 0x241b0009)
        assert self.go(entry) == 9
        task = [p.registers[n] & 0xffffffff for n in (5, 6, 7)]
        assert task[0] == handler, hex(task[0])
        p.memory[0x1126f0:0x1126f8] = saved
        assert self.go(0x1126f0, resume=True, sp=p.registers[29] & 0xffffffff, ra=p.registers[31] & 0xffffffff) == 0
        self.thread_pc = handler; self.thread_sp = task[1]+4*task[2]-0x40; self.context = None

    def listed(self):
        """Calls of the visit as native event rows (kind, a[7], f[3])."""
        out = []
        for e in self.events:
            a = [0]*7; f = [0]*3
            if e[0] == 'ObjectCreate':
                a = [*e[1:7], self.w(e[7]+0x20)]
            elif e[0].startswith('Camera'): f = list(e[1:4])
            else: a[:len(e)-1] = e[1:]
            out.append((EVENTS[e[0]], *[v & 0xffffffff for v in a], *f))
        return out

    def state(self):
        p = self.p; h = lambda at: signed(p.read(at, 2), 16) & 0xffffffff
        row = [p.read(G+4*i, 4) for i in range(42)]+[p.read(P+4*i, 4) for i in range(24)]
        row += [h(S+2*i) for i in range(7)]+[h(S+0xe+2*i) for i in range(7)]
        row += [p.read(S+off+i, 1) for off in (0x1c, 0x23, 0x2a) for i in range(7)]
        row += [p.read(S+0x34, 4), p.read(S+0x38, 4), p.read(0x5823ac, 4), p.read(0x582398, 4), p.read(0x582528, 4)]
        row += [p.read(T, 4), p.read(T+0xc, 4), p.read(T+0x10, 4), p.read(T+0x14, 4)]
        row += [p.read(0x443150, 4), p.read(0x3d2e80, 4), p.read(self.reent+0xa8, 4), p.read(self.reent+0xac, 4)]
        row += [p.read(a, 4) for a in (0x3ebf18, 0x3ec730, 0x3ec734, 0x3ec738, 0x3ebf1c, 0x3ebf20, 0x3d3ae0, 0x3d3ae4)]
        row += [p.read(a, 4) for a in (0x3d3aa0, 0x3d3ab0, 0x4eeef0, 0x4eeef4, 0x58252c)]
        row += [p.read(a, 4) for a in (0x3db900, 0x3db8fc, 0x3db8f4, 0x345180, 0x348a8c)]
        return row

    def decode(self):
        """validate_menu_canvas.Oracle.decode with the sheet of a quad taken from the 1149d0 call."""
        p = self.p; out = []
        count = p.read(0x345178, 4); self.packets += count
        for i in range(count):
            a = PACKETS+i*128
            q = struct.unpack_from('<16Q', p.memory, a); tag = q[0]; kind = tag & 0xfff
            assert tag >> 12 in (1, 2), hex(tag)
            if kind == 0xff3:
                n = q[15]; assert n == 4
                pts = []; colours = set(); depths = set()
                for j in range(n):
                    colour, xyz = q[1+2*j] & 0xffffffff, q[2+2*j]
                    pts.append((((xyz & 65535)-0x6c00)//16, (((xyz >> 16) & 65535)-0x7900)//8)); colours.add(colour); depths.add(xyz >> 32)
                    assert ((xyz & 65535)-0x6c00) % 16 == 0 and (((xyz >> 16) & 65535)-0x7900) % 8 == 0
                assert len(colours) == len(depths) == 1 and tag >> 12 == 1
                colour = colours.pop(); z = float(depths.pop())
                (x, y), (x1, y1) = pts[0], pts[3]
                assert set(pts) == {(x, y), (x, y1), (x1, y), (x1, y1)}
                out.append(dict(kind='flat', key=('flat', colour, bits(z), x, y, x1-x, y1-y), z=z, colour=colour, rect=(x, y, x1, y1)))
            elif kind == 0xff2:
                assert q[4] == 4
                v = [struct.unpack_from('<5fI', p.memory, q[3]+24*j) for j in range(4)]
                colour = q[1] & 0xffffffff
                assert len({w[5] for w in v}) == 1 and len({w[2] for w in v}) == 1
                slot, bank = self.quads[i]; raw = tag >> 12 == 2
                out.append(dict(kind='quad', key=('quad', slot, raw, colour, bits(v[0][2]), *[bits(c) for w in v for c in (w[0], w[1], w[3], w[4])]),
                                z=v[0][2], colour=colour, slot=slot, bank=bank, raw=raw, verts=v))
            elif kind == 0xff1:
                assert tag >> 12 == 1
                tex, uv0, xy0, uv1, xy1 = q[2:7]
                xy = lambda w: (((w & 65535)-0x6c00)//16, (((w >> 16) & 65535)-0x7900)//16)
                x, y = xy(xy0); r, b = xy(xy1); z = (xy0 >> 32) & 0x7fffffff; u, v = ((uv0 & 65535)-8)//16, ((uv0 >> 16 & 65535)-8)//16
                assert uv1-uv0 == 16*(r-x)+16*(b-y)*65536 and (xy1 >> 32) & 0x7fffffff == z and (tex >> 37) & 16383 == 0x3080
                w, h = r-x, b-y
                assert tex & 16383 == 0x1a40 and w == h == 24 and u % 24 == 0 and v % 24 == 0
                page = np.frombuffer(p.memory, np.uint8, 512*256, GLYPH).reshape(512, 256)
                cols = np.arange(u, u+w); cell = (page[v:v+h, cols//2] >> (4*(cols % 2))) & 15
                out.append(dict(kind='glyph', key=('glyph', 24, q[1] & 0xffffffff, bits(float(z)), x, y, w, h, u, v, cell.tobytes()),
                                z=float(z), colour=q[1] & 0xffffffff, rect=(x, y, r, b), cell=cell.copy()))
            else: raise AssertionError(hex(tag))
        return out

    def paint(self, prims, base):
        """One 116588 pass (palette work of the frame, then the level step) and the reference painter.

        The GS CLUT of the glyph sheet (CBP 3080) is the 16-entry table 11e8980 that 116588
        derives from the 112f30 colours and 1091b8 uploads every frame; the reference painter
        reads it at 348a48, where the boot code keeps the equal-layout default.
        """
        p = self.p
        _, n = p.run(0x116588, limit=900000); self.instructions += n
        # A page-less dialogue (stage 7 before the fight) draws 1a22a8 with portrait -1: the
        # quad of slot 0x22 then samples a slot that 1828c0 unbound (10add8) and no load bound
        # again, i.e. stale VRAM. Neither side paints such a quad; they are counted.
        self.unbound += sum(q['kind'] == 'quad' and q['slot'] not in self.textures for q in prims)
        prims = [q for q in prims if q['kind'] != 'quad' or q['slot'] in self.textures]
        resident = np.frombuffer(p.memory, np.uint8, 0x1000, 0x11e7980).reshape(0x400, 4)
        tex = {}
        for q in prims:
            if q['kind'] != 'quad' or q['slot'] in tex: continue
            at, w, h, kind = self.textures[q['slot']]
            raw = np.frombuffer(p.memory, np.uint8, w*h//(2 if kind == 20 else 1), at)
            if kind == 20:
                index = np.empty((h, w), np.uint8); blob = raw.reshape(h, w//2); index[:, ::2] = blob & 15; index[:, 1::2] = blob >> 4
            else: index = raw.reshape(h, w)
            tex[q['slot']] = resident[16*q['bank']+index.astype(np.int32)]
        self.tex = tex
        saved = bytes(p.memory[0x348a48:0x348a88]); p.memory[0x348a48:0x348a88] = p.memory[0x11e8980:0x11e89c0]
        frame = paint_queue(self, prims, base.astype(np.int32)).astype(np.uint8)
        p.memory[0x348a48:0x348a88] = saved
        return frame


class Session:
    """One original scene and one native driver process, compared visit by visit."""
    def __init__(self, exe, name, seed):
        self.o = Oracle(seed); self.name = name
        self.proc = subprocess.Popen([exe, PACKAGE], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.lines = []
        y, x = np.mgrid[:480, :640]; self.base = np.stack((x+3*y, x ^ y, 4*x+y, np.full_like(x, 255)), axis=-1).astype(np.uint8)
        self.visits = self.frames = self.primitives = self.calls = 0; self.kinds = Counter(); self.slots = set(); self.seen = Counter()
        self.hashes = hashlib.sha256()
        p = self.o.p
        self.send('r', 1, p.read(0x3d2e80, 4), p.read(self.o.reent+0xa8, 8))
    def send(self, *parts): self.lines.append(' '.join(str(int(v)) for v in parts[1:]).join((parts[0]+' ', '')))
    def read(self, n):
        data = self.proc.stdout.read(n)
        if len(data) != n: raise RuntimeError(f'Native driver stopped in {self.name}')
        return data
    # --- fixtures applied to both sides ---
    def g(self, index, value): self.o.p.write(G+4*index, value, 4); self.send('g', index, value)
    def pl(self, seat, index, value): self.o.p.write(P+0x30*seat+4*index, value, 4); self.send('p', seat, index, value)
    def setting(self, offset, value): self.o.p.write(0x43d050+offset, value, 1); self.send('set', offset, value)
    def word(self, index, value): self.o.p.write((0x5823ac, 0x582398, 0x582528)[index], value, 4); self.send('s', index, value)
    def build(self, character, held):
        o = self.o; human = int(o.w(G) == 2)
        o.p.write(PAD+12*human, held, 4); o.go(0x17a2c8, character, 1); self.send('build', character, 1, held)
    def roll(self, index, roll, bonus):
        self.o.p.write(S+0x1c+index, roll, 1); self.o.p.write(S+0x23+index, bonus, 1); self.send('roll', index, roll, bonus)
    def finish(self, k, step): self.o.finish[k].add(step); self.send('finish', k, step)
    def pads(self, pressed):
        for seat in (0, 1): self.o.p.write(PAD+12*seat+4, pressed[seat], 4)
    def ramp(self, colour, speed):
        self.o.go(0x117158, colour, speed); self.send('ramp', colour, speed)
    # --- comparison ---
    def compare(self, label, painted, draws=True):
        o = self.o; prims = o.decode() if draws else []
        expected_events = o.listed(); expected_state = o.state(); flags = bytes(o.p.memory[0x3ebf30:0x3ebf30+0x800])
        self.send('flush', int(painted)); self.proc.stdin.write(('\n'.join(self.lines)+'\n').encode()); self.proc.stdin.flush(); self.lines = []
        count = struct.unpack('<I', self.read(4))[0]
        events = [struct.unpack('<11I', self.read(44)) for _ in range(count)]
        count = struct.unpack('<I', self.read(4))[0]; blob = self.read(count*80)
        count = struct.unpack('<I', self.read(4))[0]; state = list(struct.unpack(f'<{count}I', self.read(4*count))); native_flags = self.read(0x800)
        frame = np.frombuffer(self.read(self.base.size), np.uint8).reshape(self.base.shape) if painted else None
        if events != expected_events:
            show = lambda rows: [(NAMES[r[0]], *[hex(v) for v in r[1:]]) for r in rows]
            raise AssertionError((self.name, label, 'calls', show(events), show(expected_events)))
        if not draws: state[-5:] = expected_state[-5:]
        if state != expected_state:
            raise AssertionError((self.name, label, 'state', [(i, hex(a), hex(b)) for i, (a, b) in enumerate(zip(state, expected_state)) if a != b],
                                  len(state), len(expected_state)))
        if native_flags != flags:
            bad = [i for i in range(0x400) if native_flags[2*i:2*i+2] != flags[2*i:2*i+2]]
            raise AssertionError((self.name, label, 'fade flags', hex(bad[0]), hex(bad[-1]), len(bad)))
        native = native_keys(blob, o) if draws else []; expected = [q['key'] for q in prims]
        if native != expected:
            short = lambda k: k[:-1] if k[0] == 'glyph' else k
            for i, (a, b) in enumerate(zip(native, expected)):
                if a != b: raise AssertionError((self.name, label, 'primitive', i, len(native), len(expected), short(a), short(b)))
            raise AssertionError((self.name, label, 'primitive count', len(native), len(expected),
                                  [short(k) for k in (native if len(native) > len(expected) else expected)[min(len(native), len(expected)):][:3]]))
        for q in prims:
            self.kinds[q['kind']] += 1
            if q['kind'] == 'quad': self.slots.add(q['slot'])
        for e in expected_events: self.seen[NAMES[e[0]]] += 1
        self.primitives += len(prims); self.calls += len(expected_events)
        if painted:
            wanted = o.paint(prims, self.base)
            if not np.array_equal(frame, wanted):
                bad = np.any(frame != wanted, axis=-1); y, x = map(int, np.argwhere(bad)[0])
                raise AssertionError((self.name, label, 'pixels', int(bad.sum()), x, y, frame[y, x].tolist(), wanted[y, x].tolist()))
            self.frames += 1; self.hashes.update(wanted.tobytes())
        else:
            _, n = o.p.run(0x116588, limit=900000); o.instructions += n
        self.send('endframe')
        return prims, expected_events
    def enter(self, which, held=0):
        o = self.o; entry, handler, _ = (OPENING, DIALOGUE, PREFINAL)[which]
        human = int(o.w(G) == 2); o.p.write(PAD+12*human, held, 4)
        o.events = []; o.scene(entry, handler)
        self.send('scene', which, -1, 0, held); self.send('begin', 0xffffffff, 1)
        return self.compare('enter', False, draws=False)
    def tick(self, pressed, painted):
        o = self.o
        self.pads(pressed); o.begin(); o.visit()
        self.send('begin', 0xffffffff, 1) if False else None
        self.lines.append('begin %d %d' % (self.begin_colour, self.begin_blend)); self.send('tick', *pressed)
        self.begin_colour, self.begin_blend = o.p.read(0x3db900, 4), o.p.read(0x3db8fc, 4)
        self.visits += 1
        return self.compare(('visit', self.visits), painted)
    def leave(self, which):
        o = self.o; o.events = []
        assert o.go((OPENING, DIALOGUE, PREFINAL)[which][2]) == 0
        self.send('leave')
        return self.compare('leave', False, draws=False)
    def close(self):
        self.proc.stdin.close(); assert self.proc.wait() == 0
    def result(self, **extra):
        return dict(case=self.name, visits=self.visits, frames=self.frames, queue_entries=self.primitives, calls=self.calls,
                    kinds=dict(self.kinds), slots=sorted(self.slots), events=dict(self.seen), frames_sha256=self.hashes.hexdigest(),
                    instructions=self.o.instructions, unbound_slot_quads=self.o.unbound, **extra)


BUTTONS = (0, 0, 0, 0, 0, 0x200, 0x2, 0x400, 0x4, 0x1, 0x10, 0x8)

def start(spec, which):
    exe, name, seed, mode, character, opponent, alternate, quick = spec[:8]
    rng = random.Random(f'{which}{name}{seed}')
    s = Session(exe, f'{("opening", "dialogue", "prefinal")[which]}/{name}/{seed}', seed)
    s.begin_colour, s.begin_blend = 0xffffffff, 1
    s.g(0, mode); s.g(0x28, 1)
    for index in (2, 3, 4, 5, 0x27): s.g(index, -1)   # 124d50 defaults of the native record
    human = mode == 2
    if mode in (1, 2):
        s.pl(human, 0, character); s.pl(human ^ 1, 0, opponent)
    else:
        s.pl(0, 0, character); s.pl(1, 0, opponent)
    for seat in (0, 1): s.pl(seat, 1, rng.randrange(5))
    s.setting(2, alternate)
    return s, rng


def opening_case(spec):
    exe, name, seed, mode, character, opponent, alternate, quick = spec
    s, rng = start(spec, 0); o = s.o; p = o.p
    held = rng.choice((0, 0, 0x10, 0x20, 0x40, 0x80))
    _, events = s.enter(0, held)
    assert [NAMES[e[0]] for e in events] == ['MapIcon', 'LoadCharacter', 'LoadCharacter', 'CameraPosition', 'CameraOffset', 'MapResources',
                                              'CameraPosition', 'CameraOffset', 'Music'], events
    walk = rng.randrange(1, 90)
    s.finish(0, walk)
    for n in sorted(rng.sample(range(walk+2, walk+400), 6)): s.finish(0, n)
    handed = False; phases = Counter()
    script = dict(idle={}, skip_text={60: 8}, fast={50: 0x200, 52: 0x2, 300: 0x400, 302: 0x4}, skip_walk={}, skip_balloon={}, frozen={})[name] if name != 'random' else None
    for visit in range(1, 1500):
        word = 0
        if script is not None: word = script.get(visit, 0)
        elif rng.random() < .04: word = rng.choice(BUTTONS)
        text = p.read(0x3d3aa0, 4)
        if name == 'skip_walk' and visit == 0x2b+0xf0+40+3: word = 8
        if name == 'skip_balloon' and o.w(0x3d3ae0) == 0 and rng.random() < .05: word = 8
        if name == 'frozen':
            # The challenger freeze g+18 holds every counter and suppresses the hand-off.
            if visit in (55, 420, 700): s.g(6, 1)
            if visit in (58, 470, 760): s.g(6, 0)
            if visit == 56: word = 8
        if name == 'random' and rng.random() < .01: s.g(6, rng.randrange(2))
        pressed = (0, word) if mode == 2 else (word, 0)
        if mode not in (1, 2): pressed = (0, word)
        prims, events = s.tick(pressed, visit % (37 if quick else 9) == 0 or visit in (0x2b, 0x2c, 0x60) or (prims_changed := False))
        phases[len(prims) > 0] += 1
        if any(NAMES[e[0]] == 'HandOff' for e in events):
            handed = True
            # The task 1c1ae8 runs the destructor and the next entry on the same frame.
            assert p.read(0x132f754, 4) == OPENING[2] and p.read(0x132f758, 4) == 0x1c1b20 and p.read(p.read(0x58243c, 4)+4, 4) == 0x10
            assert o.w(P+0x30*(mode == 2)+0x18) == (1 if mode in (1, 2) else 0)
            break
    assert handed, (name, mode)
    s.leave(0)
    s.close()
    return s.result(scene='opening', mode=mode, script=name, alternate=alternate, hand_off_visit=s.visits)


def dialogue_case(spec):
    exe, name, seed, mode, character, opponent, alternate, quick, stage, post = spec
    s, rng = start(spec, 1); o = s.o; p = o.p
    human = int(mode == 2)
    s.build(character, 0)
    if mode in (1, 2): s.pl(human, 0, character); s.pl(human ^ 1, 0, opponent)
    s.pl(human, 5, stage); s.pl(human ^ 1, 5, rng.randrange(8)); s.word(2, post); s.g(1, rng.randrange(12))
    # 17a548: both outcomes of the intruder roll on the map exit.
    if 0 < stage < 7: s.roll(stage, rng.choice((1, 100)), rng.randrange(3))
    _, events = s.enter(1)
    music = {3: 0x11, 4: 0x11, 5: 0x12, 6: 0x12 if post == 1 else 0x13, 7: 0x13}.get(stage if mode in (1, 2) else 0)
    assert ([e[1:3] for e in events if NAMES[e[0]] == 'Music'] == ([(music, 1)] if music else [])), events
    for k in (0, 1):
        for n in sorted(rng.sample(range(2, 900), 12)): s.finish(k, n)
    exits = []; after = 0; white = 0
    for visit in range(1, 3000):
        word = 0
        if name == 'idle': pass
        elif name == 'fast':
            if visit % 7 == 3: word = rng.choice((0x200, 0x2, 0x400, 0x4, 0x1))
        elif name == 'skip':
            if visit == spec[10 if len(spec) > 10 else 2] % 200+5: word = 8
        elif rng.random() < .05: word = rng.choice(BUTTONS)
        if name == 'frozen':
            if visit % 150 == 20: s.g(6, 1)
            if visit % 150 == 60: s.g(6, 0)
            if visit % 50 == 25: word = 8
        pressed = (0, word) if mode != 1 else (word, 0)
        level = p.read(0x3ec734, 4)
        prims, events = s.tick(pressed, visit % (41 if quick else 11) == 0 or visit < 3 or (level and visit % 3 == 0))
        white += p.read(0x3ec734, 4) != 0
        exits += [e[1:5] for e in events if NAMES[e[0]] == 'Exit']
        if exits:
            after += 1
            if after == 4: break
    assert len(exits) == 1, (name, stage, post, exits)
    s.leave(1)
    assert o.w(0x582528) == 0
    s.close()
    return s.result(scene='dialogue', mode=mode, stage=stage, post=post, script=name, alternate=alternate, exit=[hex(v) for v in exits[0]],
                    opponent=opponent, white_visits=white)


def prefinal_case(spec):
    exe, name, seed, mode, character, opponent, alternate, quick, skip_at = spec
    s, rng = start(spec, 2); o = s.o; p = o.p
    human = int(mode == 2)
    s.build(character, 0)
    if mode in (1, 2): s.pl(human, 0, character); s.pl(human ^ 1, 0, opponent)
    s.pl(human, 5, 7); s.pl(human, 7, 1)
    _, events = s.enter(2)
    assert [NAMES[e[0]] for e in events] == ['CameraPosition', 'CameraOffset', 'Music'] and o.w(P+0x30*human+0x1c) == (0 if mode in (1, 2) else 1)
    exits = []; after = 0; frozen = False
    for visit in range(1, 4000):
        word = 0
        if visit == skip_at: word = 8
        if name == 'random' and rng.random() < .01: word = rng.choice(BUTTONS)
        if name == 'frozen':
            if visit == skip_at-3: s.g(6, 1)
            if visit == skip_at+3: s.g(6, 0)
            if visit == skip_at+9: word = 8
        if name == 'revealed' and visit > 60 and p.read(0x3ec734, 4) > 0 and not exits:
            # Fixture for the incoming transition of 1252f0: its task lowers the level through
            # 117158 once the scene stops rewriting it, which brings the picture out of white.
            s.ramp(0xffffffff, -8)
        pressed = (0, word) if mode != 1 else (word, 0)
        prims, events = s.tick(pressed, visit % (53 if quick else 13) == 0 or visit in (1, 60, 61, 90, 121, 165, 175, 200))
        exits += [e[1:5] for e in events if NAMES[e[0]] == 'Exit']
        if exits:
            after += 1
            if after == (70 if name != 'late' else 8): break
    assert exits and all(e == (1, 2, PREFINAL[2], 0x139760) for e in exits), exits
    assert o.w(P+0x30*human+0x1c) == 1 or mode not in (1, 2)
    s.leave(2)
    s.close()
    return s.result(scene='prefinal', mode=mode, script=name, alternate=alternate, exit_visit=s.visits-after+1, exits=len(exits))


def run(spec):
    kind, *rest = spec
    try:
        return dict(opening=opening_case, dialogue=dialogue_case, prefinal=prefinal_case)[kind](tuple(rest))
    except Exception as error:
        raise RuntimeError(f'{kind} {tuple(rest[1:])}: {error!r}'[:4000]) from None


def toward_zero(exact):
    """The double nearest to `exact` in the direction of zero (fp-bit result)."""
    from fractions import Fraction
    value = float(exact)
    if abs(Fraction(value)) > abs(exact): value = np.nextafter(value, 0.0)
    return float(value)


def ease_checks(exe):
    """The libgcc fp-bit identities ArcadePreFinal::ease relies on (soft_double.hpp): 310fa0
    product and 310f38 difference truncated toward zero to 53 bits, 311510 narrowing toward zero."""
    from fractions import Fraction
    o = Oracle(1); p = o.p
    d = lambda x: struct.unpack('<Q', struct.pack('<d', x))[0]
    f = lambda q: struct.unpack('<d', struct.pack('<Q', q & 0xffffffffffffffff))[0]
    rng = random.Random(0x1c7a30); n = 0
    for _ in range(200):
        a, b = rng.uniform(-3000, 3000), rng.uniform(-1, 1)
        assert f(p.run(0x310fa0, [d(a), d(b)], limit=100000)[0]) == toward_zero(Fraction(a)*Fraction(b))
        assert f(p.run(0x310f38, [d(a), d(b)], limit=100000)[0]) == toward_zero(Fraction(a)-Fraction(b))
        p.run(0x311510, [d(a)], limit=100000)
        narrow = np.float32(a)
        if abs(Fraction(float(narrow))) > abs(Fraction(a)): narrow = np.nextafter(narrow, np.float32(0))
        assert p.floats[0] == bits(narrow)
        n += 3
    return n


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--quick', action='store_true'); ap.add_argument('--only')
    args = ap.parse_args(); quick = args.quick
    raw = ELF.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ORIGINAL
    asset = (PACKAGE/extract_arcade_talk.NAME).read_bytes()
    assert asset == extract_arcade_talk.build(raw)[0], 'run extract_arcade_talk.py first'
    rng = random.Random(0x1c60c8)
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp)/'driver.cpp'; cpp.write_text(DRIVER); exe = str(cpp.with_suffix(''))
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp, ROOT/'src/arcade_talk.cpp', ROOT/'src/arcade_run.cpp',
                        ROOT/'src/menu_canvas.cpp', ROOT/'src/console_menu.cpp', ROOT/'src/system_data.cpp', ROOT/'src/game_random.cpp',
                        ROOT/'src/scalar_float.cpp', ROOT/'src/soft_double.cpp', '-o', exe], check=True)
        fighters = [c for c in range(49) if c != 43]
        specs = []
        for i, name in enumerate(('idle', 'skip_text', 'fast', 'skip_walk', 'skip_balloon', 'frozen', 'random', 'random', 'random', 'random')):
            for mode in (1, 2):
                alternate = int(i % 4 == 3)
                specs.append(('opening', exe, name, 100+i, mode, rng.choice(fighters[:42] if alternate else fighters), rng.choice(fighters), alternate, quick))
        specs.append(('opening', exe, 'skip_text', 150, 3, 4, 9, 0, quick))   # no fighter object outside modes 1 / 2
        bosses = (0xd, 0x1a, 0x1b, 5)
        for index, (stage, post) in enumerate(((3, 0), (4, 1), (5, 0), (6, 1), (6, 0), (7, 1), (2, 0), (4, 0), (7, 0), (8, 1))):
            for j, name in enumerate(('idle', 'fast', 'skip', 'random', 'frozen')):
                mode = 1+(index+j) % 2
                alternate = int((index+j) % 5 == 4)
                opponent = bosses[(index+j) % 4] if stage >= 6 else rng.choice(fighters)
                specs.append(('dialogue', exe, name, 200+10*index+j, mode, rng.choice(fighters[:42] if alternate else fighters), opponent, alternate, quick, stage, post))
        for j, (name, skip_at) in enumerate((('idle', 0), ('revealed', 0), ('skip', 300), ('skip', 700), ('skip', 30), ('late', 1890), ('frozen', 420),
                                             ('random', 0), ('skip', 1700))):
            specs.append(('prefinal', exe, name, 300+j, 1+j % 2, rng.choice(fighters), 43, int(j == 3), quick, skip_at))
        if args.only: specs = [s for s in specs if s[0] == args.only]
        if quick: specs = specs[::3]
        identities = ease_checks(exe)
        with ProcessPoolExecutor(min(os.cpu_count() or 2, 10)) as pool: results = list(pool.map(run, specs))
    total = Counter(); kinds = Counter(); events = Counter(); slots = set(); scenes = Counter()
    for r in results:
        for k in ('visits', 'frames', 'queue_entries', 'calls', 'instructions'): total[k] += r[k]
        kinds.update(r['kinds']); events.update(r['events']); slots |= set(r['slots']); scenes[r['scene']] += 1
    exits = sorted({tuple(r['exit']) for r in results if r['scene'] == 'dialogue'})
    report = dict(status='passed', quick=quick, elf_sha256=ORIGINAL, asset=extract_arcade_talk.NAME, asset_sha256=hashlib.sha256(asset).hexdigest(),
                  cases=len(results), cases_by_scene=dict(scenes), coroutine_visits=total['visits'], identical_call_lists=total['visits']+2*len(results),
                  identical_state_rows=total['visits']+2*len(results), identical_primitive_lists=total['visits'],
                  identical_640x480_frames=total['frames'], original_queue_entries=total['queue_entries'], entries_by_kind=dict(kinds),
                  sheet_slots=[hex(v) for v in sorted(slots)], compared_calls=total['calls'], calls_by_kind=dict(events),
                  dialogue_exits=[list(e) for e in exits], soft_float_identities=identities, original_instructions=total['instructions'],
                  case_results=[{k: v for k, v in r.items() if k not in ('kinds', 'events')} for r in results],
                  scope='Whole original scene entries 1c60c8 / 1c5290 / 1c6cc0 (with 1c6328, 17a2c8, 1c2420, 1c1ec8, 1c6388, 1c6a68, 1c1e30, '
                        '1c5438, 1828c0, 1c6da8, 1c7cb0), the coroutine bodies 1c6400 / 1c55d8 / 1c6e58 run on their own stacks from the return '
                        'address of the yield 112a28 to its next call (with 1c6208, 1a3070, 1a31e0, 1a26b0, 1a2948, 1a18e0, 1a22a8, 1a2380, '
                        '1a2468, 1a2540, 1a2870, 1c5490, 1c5590, 1c5dc0, 1c5e58, 17a548, 1c7848, 1c7a30 and its C library double routines, '
                        '113028 / 1131d8 / 10a1c0, 113f98, 117de8, 114118, 1145c0, 1148f0, 1252f0, 1c1ac0, the fade setters 1170c8..117180) and '
                        'the destructors 1c61b8 / 1c53e0 / 1c6d70. Replaced by `jr ra`: sound driver requests 1e7c00, 1e7ad0, 1e7b40, 1e7b70, '
                        '1e7d60, 1e79c8; printf / puts 316140, 316218; disc loaders 11d488 (fighter), 10b640 (system sheets), 1a4a98 (arena '
                        'picture task); object pool release 11e3a0; EE CreateThread 100e58 inside 1126f0. Served by the harness: 1142d8 (texture by name: the unpacked .tex is '
                        'attached to the slot), 102810 (disc read inside the unmodified palette loader 1163c0), the yield 112a28, and the '
                        'fighter object pipeline 11e2e8 / 11fed0 / 120390 / 120ce0, whose calls are compared as requests while the action-end '
                        'flag +0xc0 is a scripted fixture given to both sides (no fighter sprite is drawn by either side). The map picture '
                        'task 1c6b10 of the opening and the arena picture task of the dialogue are separate tasks and are not run; the '
                        'transition task of 1252f0 is not run (its register writes inside 1252f0 are; one pre-final case replays its 117158 '
                        'ramp as a fixture). Frames: 116588 runs unmodified once per visit; the queue is painted in ascending depth by the '
                        'reference painter of validate_menu_canvas.py over a patterned background with sheet texels taken from the resident '
                        'CLUT 11e7980 and glyph texels from the per-frame glyph CLUT 11e8980 (queue-to-GS translation and GS rasterisation '
                        'are not executed; turned or fractional quads use its inverse-affine pixel-centre model on both sides). Resident '
                        'CLUT entries 0..7f are the obj0.pal fixture of 113890; entries 80..bf and 100..1bf are zero in the fixture.')
    REPORT.write_text(json.dumps(report, indent=2)+'\n')
    print({k: v for k, v in report.items() if k not in ('case_results', 'scope')})

if __name__ == '__main__': main()
