#!/usr/bin/env python3
"""Compare the drawing of the GALLERY MODE pages with SLPS-25559 frame by frame.

Each case drives the ORIGINAL scene (entry + task or coroutine body) and the native
logic modules with the same pad words.  After every visit the original 128-byte
submission queue 68c3c0 is decoded and must equal, entry by entry, the MenuDrawList
that src/gallery_art.cpp produces from the native logic state; the renderer globals
left behind are compared as well.  A subset of the visits is also painted on both
sides (reference painter of validate_menu_canvas.py against GalleryArt::rasterise)
and must give identical 640x480 frames.
"""
import argparse
import hashlib
import json
import random
import struct
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from character_tiles_oracle import ROOT
from extract_console_versus_art import PACKETS, ORIGINAL
from validate_menu_canvas import Oracle as CanvasOracle, paint, native_keys, bits
import extract_gallery_art

RESOURCES = ROOT/'work/ss6/extracted/resources'
PACKAGE = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
REPORT = ROOT/'outputs/ss6-feasibility/gallery_art_validation.json'
ELF = ROOT/'work/ss6/extracted/SLPS_255.59'
RETURN = struct.pack('<II', 0x03e00008, 0x0000102d)
# Plain `jr ra; move v0,zero` boundaries: sound driver, debug print, thread
# creation, scene switch and the ending object reset. Nothing here draws.
SOUND = (0x1e7b70, 0x1e7ba0, 0x1e79c8, 0x1e7d60, 0x1e7ad0, 0x1e7b40, 0x1e8298, 0x213180, 0x213238)
PLATFORM = (0x316140, 0x316218, 0x100e58, 0x1252f0, 0x182858, 0x1828c0, 0x120110)
# Boundaries served by this script: entry replaced by `j TRAP; li k1, n`.
TEXTURE, FILE, YIELD, PLAYBACK = 0x1142d8, 0x102810, 0x112a28, 0x182a98
TRAP, TRAMPOLINE = 0x1f90100, 0x1f90000
PICTURE, SCRATCH_FILE = 0x1700000, 0x1fa0000
OPTION, SETTING = 0x43d058, 0x43d050
BSS_END = 0x1606d6c

DRIVER = r'''
#include "gallery_art.hpp"
#include <bit>
#include <cstdio>
#include <iostream>
#include <sstream>
using namespace ss6;
template<class T> static void put(const T& v){std::cout.write(reinterpret_cast<const char*>(&v),sizeof v);}
int main(int,char** argv){
    SystemData system(argv[1]);MenuWidgetData widgets(argv[1]);GalleryData data(argv[1]);
    MenuCanvas canvas(argv[1]);GalleryArt art(canvas,argv[1]);MenuDrawList list;MenuBackdrop backdrop;
    MenuChrome chrome;GameRandom random;MenuPadRepeat repeat;
    GalleryTopMenu top;IllustrationViewer pictures;SoundTest sound;EndingViewer ending;
    GuideWindow window;ListWidget single;CharacterRows singleRows{};uint32_t returned=0;
    std::array<uint32_t,2> last{};
    auto unhex=[](const std::string& s){std::string o;for(size_t i=0;i+1<s.size();i+=2)o.push_back(char(std::stoi(s.substr(i,2),nullptr,16)));return o;};
    auto fb=[](long long v){return std::bit_cast<float>(uint32_t(v));};
    std::vector<uint8_t> pixels(640*480*4),base(pixels.size());
    for(int y=0;y<480;++y)for(int x=0;x<640;++x){auto* p=base.data()+4*(640*y+x);p[0]=x+3*y;p[1]=x^y;p[2]=4*x+y;p[3]=255;}
    std::string line,op;
    while(std::getline(std::cin,line)) try {
        std::istringstream in(line);in>>op;
        std::string text;
        if(op=="w_markup"||op=="w_label"){in>>text;text=text=="-"?std::string():unhex(text);}
        std::vector<long long> v;for(long long x;in>>x;)v.push_back(x);
        v.resize(12);
        const long long a=v[0],b=v[1],c=v[2];
        auto pads=[&](unsigned seat){
            std::array<uint32_t,2> held{uint32_t(a),uint32_t(b)};
            auto m=repeat.sample(held,{held[0]&~last[0],held[1]&~last[1]});last=held;
            return std::pair{m,WidgetPad{held[seat],m[seat].pressed,m[seat].repeat}};
        };
        // 1ce478: the logic modules draw one library number, the original 1802.
        auto entered=[&](uint64_t seed){enterGalleryBackdrop(backdrop,chrome,random,seed);};
        const uint64_t seed=random.librarySeed;
        if(op=="option")system.option(size_t(a))=uint8_t(b);
        else if(op=="setting")system.setting(size_t(a))=uint8_t(b);
        else if(op=="seed")random.librarySeed=uint64_t(a);
        else if(op=="help")chrome.setHelp(int(a));
        else if(op=="seat"){art.seat=unsigned(a);art.extraIcons=system.option(0x7e)!=0;}
        else if(op=="fade"){canvas.setFade(a!=0,int(b),uint32_t(c));art.setFade(a!=0,int(b),uint32_t(c));}
        else if(op=="top_reset")top.reset();
        else if(op=="top_enter"){top.enter(data,chrome,random);entered(seed);}
        else if(op=="top"){
            list.beginFrame();
            const MenuChrome before=chrome;
            top.tick(data,chrome,pads(0).first);
            art.seat=unsigned(top.operatingSeat);
            art.drawGalleryTop(list,backdrop,random,before,top,data);
        } else if(op=="pictures_enter"){art.forget();pictures.enter(unsigned(a),system,widgets,data,chrome,random);entered(seed);}
        else if(op=="pictures"){
            list.beginFrame();
            pictures.tick(pads(pictures.seat).second);
            art.drawIllustrationViewer(list,backdrop,random,chrome,pictures);
        } else if(op=="sound_enter"){sound.enter(unsigned(a),system,widgets,data,chrome,random);entered(seed);}
        else if(op=="sound_counter")sound.lyricCounter=int(a);
        else if(op=="sound"){
            list.beginFrame();
            sound.tick(pads(sound.seat).second,c!=0);
            art.drawSoundTest(list,backdrop,random,chrome,sound,data);
        } else if(op=="ending_scene"){ending.enterScene(data,chrome,random);entered(seed);}
        else if(op=="ending_begin"){ending.beginSelection(unsigned(a),system,widgets,chrome,random);entered(seed);}
        else if(op=="ending"){
            list.beginFrame();
            ending.tick(pads(ending.seat).second);
            art.drawEndingSelect(list,backdrop,random,chrome,ending);
        } else if(op[0]=='g'&&op[1]=='_'){
            if(op=="g_init"){window.init(widgets);chrome.enter(backdrop.enter(random));}
            else if(op=="g_layout")window.setLayout(int(a),unsigned(b));
            else if(op=="g_tick")window.tick();
            else if(op=="g_open")window.open();
            else if(op=="g_close")window.close();
            else if(op=="g_message")window.setMessage(int(a),int(b));
            else if(op=="g_extra")window.setExtraLayout(int(a),unsigned(b));
            else if(op=="g_extra_open")window.openExtra();
            else if(op=="g_extra_close")window.closeExtra();
        } else if(op[0]=='l'&&op[1]=='_'){
            std::vector<int> t;
            if(op=="l_init")single.init(widgets,singleRows);
            else if(op=="l_flag")single.selector.setFlag(unsigned(a),b!=0);
            else if(op=="l_resize")single.resize(int(a),int(b));
            else if(op=="l_item")single.setItem(unsigned(a),b<0?std::string_view():std::string_view(widgets.characterNames[size_t(b)]));
            else if(op=="l_chars")single.fillCharacters(system,int(v[0]),int(v[1]),v[2]!=0,v[3]!=0,v[4]!=0);
            else if(op=="l_select")single.select(int(a));
            else if(op=="l_panel")single.panel.reset(int(v[0]),int(v[1]),int(v[2]),int(v[3]),int(v[4]));
            else if(op=="l_open")single.panel.open();
            else if(op=="l_close")single.panel.close();
            else if(op=="l_state"){single.shown=int(a);single.active=int(b);}
            else if(op=="l_update")single.update({uint32_t(a),uint32_t(b),uint32_t(c)},t);
        } else if(op=="w_begin"){list.beginFrame();list.resetCursor();returned=0;}
        else if(op=="w_globals"){art.gameMode=int(v[0]);art.extraIcons=v[1]!=0;art.frontText=v[2]!=0;art.middleText=v[3]!=0;list.cursorBase=fb(v[4]);}
        else if(op=="w_guide")art.drawGuide(list,window,backdrop,random,chrome);
        else if(op=="w_list")art.drawList(list,single);
        else if(op=="w_frame"){
            GalleryArt::Frame f;art.tint(f,v[5]!=0);f.style=int(v[0]);f.w=fb(v[1]);f.h=fb(v[2]);f.x=fb(v[3]);f.y=fb(v[4]);
            art.frame(list,f,int(v[6]));
        } else if(op=="w_scroll"){
            GalleryArt::Frame f;art.tint(f,v[4]!=0);f.w=fb(v[0]);f.h=fb(v[1]);f.x=fb(v[2]);f.y=fb(v[3]);
            art.scrollBar(list,f,int(v[5]),int(v[6]),int(v[7]),int(v[8]));
        } else if(op=="w_bar")art.softBar(list,fb(v[0]),fb(v[1]),fb(v[2]),fb(v[3]),fb(v[4]));
        else if(op=="w_markup"||op=="w_message"){
            const std::string_view view=op=="w_message"?std::string_view(widgets.messages[size_t(v[5])]):std::string_view(text);
            art.textColour=uint32_t(v[4]);
            const size_t r=art.markup(list,view,int(v[0]),v[1]!=0,fb(v[2]),fb(v[3]));
            returned=r==GalleryArt::noBreak?0:uint32_t(r);
        } else if(op=="w_label"){art.textColour=uint32_t(v[3]);art.label(list,text,int(v[0]),int(v[1]),int(v[2]));}
        else if(op=="w_small"){art.textColour=uint32_t(v[3]);art.smallText(list,widgets.characterNames[size_t(v[2])],int(v[0]),int(v[1]));}
        else if(op=="flush"){
            uint32_t n=uint32_t(list.records.size());put(n);
            for(auto& r:list.records){uint8_t head[6]={uint8_t(r.kind),uint8_t(r.font),r.slot,r.blend,uint8_t(r.additive),0};put(head);put(r.glyph);put(r.colour);put(r.z);
                float g[8]={r.x,r.y,r.w,r.h,r.u,r.v,r.uw,r.vh};put(g);put(r.corner);}
            uint32_t st[18]={list.colour,uint32_t(list.blend),uint32_t(list.depth),uint32_t(list.glyphs),uint32_t(list.textDepth),std::bit_cast<uint32_t>(list.cursor),
                uint32_t(chrome.helpX[0]),uint32_t(chrome.helpX[1]),uint32_t(chrome.helpDelay),uint32_t(random.librarySeed),uint32_t(random.librarySeed>>32),
                uint32_t(backdrop.target),uint32_t(backdrop.shown),uint32_t(backdrop.clock),uint32_t(chrome.band),uint32_t(chrome.content),uint32_t(chrome.legend),
                uint32_t(ending.chosen)|returned};put(st);
            if(a){pixels=base;art.rasterise(list,pixels);std::cout.write(reinterpret_cast<const char*>(pixels.data()),pixels.size());}
            std::cout.flush();
        } else return 3;
    } catch(const std::exception& e){std::cerr<<line<<": "<<e.what()<<std::endl;return 4;}
}
'''


class Oracle(CanvasOracle):
    """Original gallery scenes with their drawing; disc, sound and kernel boundaries are served here."""
    def __init__(self, seat=0, options=(), settings=(), seed=1):
        super().__init__()
        p = self.p;elf = ELF.read_bytes()
        # The character-bank fixture of prepare() overlaps .bss; the menu scenes expect it clear.
        p.memory[0x1300000:BSS_END] = bytes(BSS_END-0x1300000)
        # 1163c0 runs again: only its disc read 102810 is served.
        p.memory[0x1163c0:0x1163c8] = elf[0x1000+0x63c0+0x10000:0x1000+0x63c0+0x10000+8]
        assert p.read(0x1163c0, 4) == 0x27bdffe0
        for pc in SOUND+PLATFORM:p.memory[pc:pc+8] = RETURN
        for n, pc in enumerate((TEXTURE, FILE, YIELD, PLAYBACK), 1):
            p.memory[pc:pc+8] = struct.pack('<II', 0x08000000 | TRAP >> 2, 0x241b0000 | n)
        p.write(0x3ebf28, SCRATCH_FILE, 4)
        image = (PACKAGE/'save_default.bin').read_bytes()
        p.memory[OPTION:OPTION+0x98] = image[0x618c:0x618c+0x98]
        p.memory[SETTING:SETTING+7] = image[0x6184:0x6184+7]
        for off, value in options:p.write(OPTION+off, value, 1)
        for off, value in settings:p.write(SETTING+off, value, 1)
        self.picture = None
        # Slot 5 as 17eda0 binds it, so that the queue key of its sprites is known.
        for o, v in [(0, PICTURE), (4, 1024), (8, 1024), (12, 19), (20, 10), (24, 10), (36, 0)]:p.write(0x3a9680+5*40+o, v, 4)
        p.run(0x10add8, [5, 0x30])
        self.reset();self.sprite(5, 0, 0, 0, 8, 8, 0, 0, 8, 8)
        tex = p.read(PACKETS+16, 8);self.slots[tex & 0x3fff, (tex >> 37) & 0x3fff] = 5
        assert len(self.slots) == 4
        self.go(0x112570)       # task pool
        self.go(0x1cebb0, 52)   # help ticker as a preceding menu leaves it
        p.write(0x443150, 1, 4);p.write(0x4c3808, 0xd, 4);p.write(0x12d35c4, seat, 4)
        p.write(0x582b3c, 0, 4)  # prepare() leaves the legend counter at 5; every scene entry clears it
        self.reent = p.read(0x5d1bf8, 4)
        p.write(self.reent+0xa8, seed, 8)
        for a, v in [(0x3db900, 0xffffffff), (0x3db8fc, 1), (0x348a8c, 0), (0x3d3aac, bits(-200.0)), (0x12d3850, 0), (0x4ee54c, 0), (0x348b10, 0)]:
            p.write(a, v, 4)
        self.seat = seat;self.last = [0, 0];self.context = None;self.thread_pc = self.thread_sp = None
        self.instructions = 0;self.packets = 0;self.loads = []

    def refresh(self):
        super().refresh()
        if getattr(self, 'picture', None) is not None:
            p = self.p
            self.tex[5] = np.frombuffer(p.memory, np.uint8, 1024, 0x11e7980+4*0x300).reshape(256, 4)[
                np.frombuffer(p.memory, np.uint8, 1024*1024, PICTURE)].reshape(1024, 1024, 4)

    def serve(self, service):
        """Disc boundaries. Returns v0."""
        p = self.p;r = p.registers
        name = bytes(p.memory[r[5 if service == 1 else 4] & 0xffffffff:][:64]).split(b'\0')[0].decode('ascii')
        self.loads.append(name)
        if service == 1:
            slot = r[4] & 0xffffffff
            if slot == 4:assert name == 'PS2_menu_bg00_00.pvr'
            else:
                assert slot == 5 and name.startswith('gl_') and name.endswith('.pvr'), (slot, name)
                data = (RESOURCES/(name[:-4]+'.tex')).read_bytes();assert len(data) == 1024*1024
                p.memory[PICTURE:PICTURE+len(data)] = data;self.picture = int(name[3:5])
            return 0
        assert name.endswith('.pvp'), name
        data = (RESOURCES/(name[:-4]+'.pal')).read_bytes()
        assert len(data) <= (r[6] & 0xffffffff)
        at = r[5] & 0xffffffff;p.memory[at:at+len(data)] = data
        return len(data)

    def go(self, pc, *args, resume=False, sp=None, ra=None):
        """Run to the end, to the yield or to the ending engine; serve the disc boundaries on the way."""
        p = self.p
        if ra is None:ra = pc
        while True:
            p.registers[27] = 0
            if resume:
                # Probe.run presets sp and ra; the trampoline puts both back.
                code = [0x3c1d0000 | sp >> 16, 0x37bd0000 | sp & 0xffff, 0x3c1f0000 | ra >> 16, 0x37ff0000 | ra & 0xffff,
                        0x3c1a0000 | pc >> 16, 0x375a0000 | pc & 0xffff, 0x03400008, 0]
                p.memory[TRAMPOLINE:TRAMPOLINE+32] = struct.pack('<8I', *code)
                _, n = p.run(TRAMPOLINE, (), limit=40000000, stop_before=STOP)
            else:
                _, n = p.run(pc, args, limit=40000000, stop_before=STOP)
            self.instructions += n
            service = p.registers[27] & 0xffffffff
            if service not in (1, 2):return service
            p.registers[2] = self.serve(service)
            pc = ra = p.registers[31] & 0xffffffff;sp = p.registers[29] & 0xffffffff;resume = True

    def sample(self, held):
        p = self.p
        for seat, word in enumerate(held):
            p.write(0x443568+4*seat, word, 4);p.write(0x443570+4*seat, self.last[seat], 4)
            self.go(0x117fd8, seat)
        self.last = list(held)

    def begin(self):
        p = self.p
        for a in (0x345178, 0x345180, 0x378e08, 0x3db8f8):p.write(a, 0, 4)
        p.run(0x114e80)

    # A coroutine task is a PS2 kernel thread; as in validate_console_gallery.py
    # its body runs on its own stack up to the yield entry and is resumed at
    # the saved return address with v0 = 0.
    def start(self, entry, stack, words):
        self.thread_pc = entry;self.thread_sp = stack+4*words-0x40;self.context = None
    def visit(self):
        p = self.p
        if self.context:
            p.registers, p.registers_high, p.lo, p.hi, p.lo1, p.hi1, p.floats, p.float_acc, p.float_condition = self.context
            p.registers = list(p.registers);p.registers_high = list(p.registers_high);p.floats = list(p.floats)
            p.registers[2] = 0
        stopped = self.go(self.thread_pc, resume=True, sp=self.thread_sp)
        assert stopped in (3, 4), 'the coroutine returned'
        self.thread_pc = p.registers[31] & 0xffffffff;self.thread_sp = p.registers[29] & 0xffffffff
        self.context = (list(p.registers), list(p.registers_high), p.lo, p.hi, p.lo1, p.hi1, list(p.floats), p.float_acc, p.float_condition)
        return stopped
    def scene(self, entry, handler):
        """Scene entry; its 1126f0 call names the coroutine body and stack."""
        p = self.p;saved = bytes(p.memory[0x1126f0:0x1126f8])
        p.memory[0x1126f0:0x1126f8] = struct.pack('<II', 0x08000000 | TRAP >> 2, 0x241b0005)
        assert self.go(entry) == 5
        task = [p.registers[n] & 0xffffffff for n in (5, 6, 7)]
        assert task[0] == handler, hex(task[0])
        p.memory[0x1126f0:0x1126f8] = saved
        # Continue with the unmodified 1126f0 and the rest of the entry.
        assert self.go(0x1126f0, resume=True, sp=p.registers[29] & 0xffffffff, ra=p.registers[31] & 0xffffffff) == 0
        self.start(handler, *task[1:])

    def state(self):
        p = self.p;r = self.reent
        return (p.read(0x3db900, 4), p.read(0x3db8fc, 4), p.read(0x3db8f4, 4), p.read(0x345180, 4), p.read(0x348a8c, 4), p.read(0x12d3850, 4),
                p.read(0x582b28, 4), p.read(0x582b2c, 4), p.read(0x582b30, 4), p.read(r+0xa8, 4), p.read(r+0xac, 4),
                p.read(0x584d60, 4), p.read(0x584d64, 4), p.read(0x584d68, 4), p.read(0x582b34, 4), p.read(0x582b38, 4), p.read(0x582b3c, 4))


STOP = frozenset((TRAP,))


class Session:
    """One original scene and one native driver process, compared visit by visit."""
    def __init__(self, exe, oracle, name):
        self.proc = subprocess.Popen([exe, PACKAGE], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.o = oracle;self.name = name;self.lines = []
        y, x = np.mgrid[:480, :640];self.base = np.stack((x+3*y, x ^ y, 4*x+y, np.full_like(x, 255)), axis=-1).astype(np.uint8)
        self.visits = self.frames = self.primitives = 0;self.kinds = {};self.pictures = set();self.hashes = hashlib.sha256()
    def send(self, *parts):self.lines.append(' '.join(str(v) for v in parts))
    def read(self, n):
        data = self.proc.stdout.read(n)
        if len(data) != n:raise RuntimeError(f'Native driver stopped in {self.name}')
        return data
    def compare(self, label, painted, chosen=0):
        o = self.o;prims = o.decode()
        self.send('flush', int(painted));self.proc.stdin.write(('\n'.join(self.lines)+'\n').encode());self.proc.stdin.flush();self.lines = []
        count = struct.unpack('<I', self.read(4))[0];blob = self.read(count*80);state = struct.unpack('<18I', self.read(72))
        frame = np.frombuffer(self.read(self.base.size), np.uint8).reshape(self.base.shape) if painted else None
        native = native_keys(blob, o);expected = [q['key'] for q in prims]
        if native != expected:
            for i, (a, b) in enumerate(zip(native, expected)):
                if a != b:raise AssertionError((self.name, label, 'primitive', i, len(native), len(expected), a[:-1] if a[0] == 'glyph' else a, b[:-1] if b[0] == 'glyph' else b))
            raise AssertionError((self.name, label, 'primitive count', len(native), len(expected),
                                  [k[:-1] if k[0] == 'glyph' else k for k in (native if len(native) > len(expected) else expected)[min(len(native), len(expected)):][:3]]))
        if state[:17] != o.state() or state[17] != chosen:raise AssertionError((self.name, label, 'state', state, o.state(), chosen))
        for q in prims:
            self.kinds[q['kind']] = self.kinds.get(q['kind'], 0)+1
            if q['kind'] == 'quad' and q['slot'] == 5:self.pictures.add(o.picture)
        self.primitives += len(prims);self.visits += 1
        if painted:
            o.refresh()
            wanted = paint(o, prims, self.base.astype(np.int32)).astype(np.uint8)
            if not np.array_equal(frame, wanted):
                bad = np.any(frame != wanted, axis=-1);y, x = map(int, np.argwhere(bad)[0])
                raise AssertionError((self.name, label, 'pixels', int(bad.sum()), x, y, frame[y, x].tolist(), wanted[y, x].tolist()))
            self.frames += 1;self.hashes.update(wanted.tobytes())
        return prims
    def close(self):
        self.proc.stdin.close();assert self.proc.wait() == 0
    def result(self, **extra):
        return dict(case=self.name, visits=self.visits, frames=self.frames, queue_entries=self.primitives, entries_by_kind=self.kinds,
                    pictures=sorted(self.pictures), frames_sha256=self.hashes.hexdigest(), instructions=self.o.instructions, **extra)


def setup(session, options, settings, seed, seat):
    for o, v in options:session.send('option', o, v)
    for o, v in settings:session.send('setting', o, v)
    session.send('seed', seed);session.send('help', 52);session.send('seat', seat)

class Painter:
    """Chooses the visits that are painted: every `period`-th and those following a pad change."""
    def __init__(self, period):self.period = period;self.n = 0;self.last = None;self.hold = 0
    def __call__(self, held):
        self.n += 1
        if held != self.last:self.hold = 2
        self.last = held
        if self.hold:
            self.hold -= 1;return True
        return self.n % self.period == 0

def top_case(spec):
    exe, name, seat, seed, quick = spec
    rng = random.Random(f'top{name}{seat}{seed}')
    o = Oracle(seed=seed);s = Session(exe, o, f'top/{name}/{seat}');paint_now = Painter(5)
    setup(s, (), (), seed, 0)
    o.go(0x1d2610);s.send('top_reset')
    def enter():
        o.p.write(0x4c3808, 0xd, 4)
        o.go(0x1d22f8);s.send('top_enter')
    def tick(own=0, other=0):
        held = (other, own) if seat else (own, other)
        o.sample(held);o.begin();o.go(0x1d2380)
        s.send('top', *held);s.compare(('top', s.visits), paint_now(held))
    def tap(word, other=0):tick(word, other);tick()
    enter()
    for i in range(34):tick(0x20 if i % 7 == 3 else 0)   # slide-in and fade-in: input is ignored
    if name == 'rows':
        for row in range(4):
            for _ in range(3):tick()
            tap(0x20)
        tap(0x10);tap(0x10)
        for _ in range(8):tick()
        tap(0x200);
        for _ in range(6):tick(rng.choice((0, 0x10, 0x400)))
        enter()
        for _ in range(40):tick()
        tap(0x20);tap(0x404)
        for _ in range(6):tick()
    else:
        for _ in range(60 if quick else 130):
            k = rng.random()
            word = 0 if k < .5 else rng.choice((0x10, 0x20)) if k < .93 else rng.choice((0x200, 0x8, 0x400, 0x40, 0x80))
            tick(word, rng.choice((0, 0, 0, 0x10, 0x20)))
            if o.p.read(0x582d8c, 4) and rng.random() < .25:
                enter()
                for _ in range(33):tick()
    s.close()
    return s.result(scene='top')

LOCKS = {'factory': (), 'unlocked': tuple((0x16+c, 0) for c in range(49)),
         'sparse': tuple((0x16+c, int(c % 3 == 1)) for c in range(49))}

def pictures_case(spec):
    exe, name, seat, locks, seed, quick = spec
    rng = random.Random(f'pictures{name}{seat}{locks}{seed}')
    o = Oracle(seat, LOCKS[locks], seed=seed);s = Session(exe, o, f'illustrations/{name}/{seat}/{locks}')
    paint_now = Painter(9 if name != 'all' else 1000)
    setup(s, LOCKS[locks], (), seed, seat)
    o.scene(0x13ed98, 0x13edf0);s.send('pictures_enter', seat)
    def tick(own=0, other=0, force=False):
        held = (other, own) if seat else (own, other)
        o.sample(held);o.begin();assert o.visit() == 3
        s.send('pictures', *held);s.compare(('pictures', s.visits), paint_now(held) or force)
    def tap(word):tick(word);tick()
    def fade(enabled, level, colour):
        o.fade = (enabled, level, colour);o.refresh();s.send('fade', int(enabled), level, colour)
    for _ in range(20):tick(rng.choice((0, 0x20)))
    if name == 'all':
        # Every picture once, in list order, at the default view.
        count = o.p.read(o.thread_sp+0x170+0x5c, 4)
        tap(0x200000)
        for _ in range(18):tick()
        for row in range(count):
            # The list reads the pad only at rest: 16 visits of slide after each return.
            tick(0x200);tick(force=True);tap(0x400)
            for _ in range(17):tick()
            tap(0x20)
            if quick and row >= 3:break
        if not quick:assert len(s.pictures) == count == 55, (len(s.pictures), count)
    elif name == 'view':
        tap(0x20);tap(0x200)
        for _ in range(18):tick()
        k = 4 if quick else 2
        for word, n in ((0x100000, 190), (0x80, 150), (0x40, 330), (0x20, 150), (0x10, 330), (0x400000 | 0x80 | 0x10, 200),
                        (0x100000 | 0x400000, 5), (0x40 | 0x80, 5), (0x10 | 0x20 | 0x100000, 60)):
            for _ in range(max(3, n//k)):tick(word)
        tap(0x80000);tick(0x80 | 0x20);tap(0x80000);tap(0x80000 | 0x200);tap(0x80000);tap(0x8);tap(0x80000 | 0x400)
        for _ in range(20):tick()
        tap(0x200)
        for _ in range(20):tick()
        # 116588 fades the picture CLUT with every other palette.
        for step, state in enumerate(((True, 96, 0xff000000), (True, 200, 0xffffffff), (True, 256, 0xff204080), (False, 0, 0))):
            fade(*state)
            for i in range(3):tick(0x100000 if step % 2 else 0x40, force=True)
        tap(0x404)
        for _ in range(20):tick()
        tap(0x404)
        for _ in range(24):tick(rng.choice((0, 0x200, 0x20)))
    else:
        for _ in range(60 if quick else 110):
            k = rng.random()
            if k < .3:word = 0
            elif k < .6:word = rng.choice((0x10, 0x20, 0x40, 0x80, 0x100000, 0x400000, 0x200000, 0x800000))
            elif k < .85:word = rng.choice((0x10, 0x20, 0x40, 0x80)) | rng.choice((0, 0x100000, 0x400000)) | rng.choice((0, 0x10, 0x40))
            else:word = rng.choice((0x200, 0x2, 0x8, 0x400, 0x4, 0x80000, 0x200, 0x200))
            for _ in range(rng.choice((1, 1, 2, 6, 25))):tick(word, rng.choice((0, 0x200, 0x20)))
    s.close()
    return s.result(scene='illustrations', loads=len(o.loads))

def sound_case(spec):
    exe, name, seat, locks, seed, quick = spec
    rng = random.Random(f'sound{name}{seat}{locks}{seed}')
    settings = ((5, seed & 1), (6, seed >> 1 & 1))
    o = Oracle(seat, LOCKS[locks], settings, seed);s = Session(exe, o, f'sound/{name}/{seat}/{locks}');paint_now = Painter(7)
    setup(s, LOCKS[locks], settings, seed, seat)
    o.scene(0x13e090, 0x13e0e8);s.send('sound_enter', seat)
    state = {'playing': 0, 'glyphs': 0}
    def tick(own=0, other=0, force=False):
        held = (other, own) if seat else (own, other)
        o.sample(held);o.p.write(0x5a9e6c, state['playing'], 4);o.begin();assert o.visit() == 3
        s.send('sound', *held, state['playing'])
        prims = s.compare(('sound', s.visits), paint_now(held) or force)
        state['glyphs'] += sum(q['kind'] == 'glyph' for q in prims)
    def tap(word, wait=1):
        tick(word)
        for _ in range(wait):tick()
    def settle():
        for _ in range(18):tick()
    def frame(at):return o.thread_sp+at
    settle()
    if name == 'bgm':
        for version in range(2):
            tap(0x200);settle()
            for _ in range(version):tap(0x20)
            tap(0x200);settle()
            for row in range(27):
                if (quick or seat) and row not in (0, 5, 6):
                    tap(0x20);continue
                tap(0x200, 2);state['playing'] = 1
                if row == 5:
                    for _ in range(12):tick()
                    tap(0x80000)
                    for _ in range(40):tick(rng.choice((0, 0x200)) if _ < 20 else 0)
                    # Sample the glyph colour ramps across the song without playing it out.
                    length = (0x33ae, 0x23c8)[version]
                    for value in range(40, length, length//(6 if quick else 24)):
                        o.p.write(frame(0x1afc), value, 4);s.send('sound_counter', value)
                        for i in range(3):tick(force=i == 1)
                    value = length-12
                    o.p.write(frame(0x1afc), value, 4);s.send('sound_counter', value)
                    for _ in range(24):tick()
                    tap(0x400)
                    for _ in range(40):tick()
                    tap(0x80000, 3);tap(0x200, 36);tap(0x8, 36)
                state['playing'] = 0
                tap(0x20)
            tap(0x400);settle();tap(0x400);settle()
        tap(0x4);settle();settle()
        assert state['glyphs']
    elif name == 'voice':
        tap(0x20);tap(0x200);settle()
        count = o.p.read(frame(0x9e0+0x5c), 4)
        picks = sorted(rng.sample(range(count-1), min(2 if quick else 3, count-1)))+[count-1]
        at = 0
        for pick in picks:
            while at < pick:
                tap(0x20, 0);at += 1
            tick();tap(0x200);settle()
            rows = o.p.read(frame(0x1250+0x5c), 4)
            for step in range(min(rows, 4 if quick else 9)):
                tap(0x200);tap(0x20, 0)
            tap(0x400000);tap(0x400000);tap(0x100000);tap(0x800000);tap(0x200000);tap(0x80000)
            tap(0x400);settle()
        tap(0x400);settle();tap(0x400);settle();settle()
    elif name == 'narration':
        tap(0x10);tap(0x200);settle()
        for language in range(2):
            if language:tap(0x20)
            tap(0x200);settle()
            for row in range(12 if quick else 40):
                tap(0x200) if row % 9 == 0 else None;tap(0x20, 0)
            tap(0x800000);tap(0x100000);tap(0x400);settle()
        tap(0x404);settle();tap(0x4);settle();settle()
    else:
        for _ in range(60 if quick else 110):
            k = rng.random()
            if k < .25:word = 0
            elif k < .6:word = rng.choice((0x10, 0x20, 0x20, 0x100000, 0x400000, 0x200000, 0x800000))
            elif k < .9:word = rng.choice((0x200, 0x200, 0x2, 0x8, 0x80000))
            else:word = rng.choice((0x400, 0x4, 0x40, 0x80))
            if rng.random() < .1:state['playing'] ^= 1
            for _ in range(rng.choice((1, 1, 2, 3, 20))):tick(word, rng.choice((0, 0x200, 0x20)))
    s.close()
    return s.result(scene='sound test', glyph_entries=state['glyphs'])

ENDINGS = {'none': (), 'few': tuple((0x47+c, 1) for c in (0, 4, 11, 24, 43, 48)),
           'all': tuple((0x47+c, 1) for c in range(49))}

def ending_case(spec):
    exe, name, seat, seen, seed, quick = spec
    rng = random.Random(f'ending{name}{seat}{seen}{seed}')
    o = Oracle(seat, ENDINGS[seen], seed=seed);s = Session(exe, o, f'ending/{name}/{seat}/{seen}');paint_now = Painter(6)
    setup(s, ENDINGS[seen], (), seed, seat)
    o.scene(0x182968, 0x182ce0)
    assert o.p.read(0x4c3838, 4) == 1
    s.send('ending_scene');s.send('ending_begin', seat)
    chosen = []
    def tick(own=0, other=0):
        held = (other, own) if seat else (own, other)
        o.sample(held);o.begin();stopped = o.visit()
        s.send('ending', *held)
        if stopped == 4:
            # 13f4a8 returned its selection before drawing; 182ce0 is about to start
            # the ending engine 182a98, which is outside this comparison.
            character = struct.unpack('<i', struct.pack('<I', o.p.registers[4] & 0xffffffff))[0]
            assert character >= 0 and not o.decode()
            chosen.append(character)
            s.compare(('ending', s.visits, 'chosen'), False, chosen=1)
            # Playback is skipped: the next visit resumes behind the 182a98 call and 182ce0 restarts the selection.
            s.send('ending_begin', seat)
            return
        s.compare(('ending', s.visits), paint_now(held))
    def tap(word):tick(word);tick()
    def settle():
        for _ in range(19):tick()
    settle()
    if name == 'empty':
        tap(0x20);tap(0x10);tap(0x404);settle();settle()
    elif name == 'play':
        tap(0x20);tap(0x20);tick(0x200);settle()
        for _ in range(3):tap(0x10)
        tick(0x8);settle();tap(0x400000);tap(0x800000);tap(0x100000);tick(0x2);settle();tap(0x400);settle();settle()
        assert len(chosen) == 3, chosen
    else:
        for _ in range(50 if quick else 110):
            k = rng.random()
            word = 0 if k < .3 else rng.choice((0x10, 0x20, 0x20, 0x100000, 0x400000, 0x200000, 0x800000)) if k < .85 else rng.choice((0x200, 0x2, 0x8, 0x200, 0x40))
            for _ in range(rng.choice((1, 1, 2, 4, 22))):tick(word, rng.choice((0, 0x200, 0x20)))
    s.close()
    return s.result(scene='ending select', chosen=chosen)


G, W, F, TEXT, PAD = 0x1e01000, 0x1e02000, 0x1e03000, 0x1e04000, 0x1237cc8
TOKENS = (b'I1I2I3I4I5I6I7I8I9IAIBICIDIEIWIHIZ', b'G1G2G3G4G5G6G7G8G9', b'L1L2R1R2SCSTSLBOBXBTBSBPORPL', b'EX', b'EXIT',
          b'BP\x91\x49\x91\xf0 BOBT\x8c\x88\x92\xe8 BXBS\x96\xdf\x82\xe9', b'\x82\xa0 MS\x82\xa2SC\x82\xa4', b'\x82\xa0\x82\xa2CR\x82\xa4\x82\xa6',
          b'MS\x82\xa0CRBO', b'I0IFIXG0GAL3R0SXBZOXPX', b'a\x82\xa0b', b'\x82\xa0 ', b'  \x82\xa0  BO  ', b'\x82\xa0I', b'I', b'', b'ZZBOQ')

def widget_case(spec):
    """The window library called directly on scratch objects: no scene, no coroutine."""
    exe, name, seat, seed, quick = spec
    rng = random.Random(f'widget{name}{seat}{seed}')
    options = tuple((0x16+c, rng.randrange(2)) for c in range(49))+tuple((0x47+c, rng.randrange(2)) for c in range(49))+((0x94, seat),)
    o = Oracle(seat, options, seed=seed);p = o.p;s = Session(exe, o, f'widget/{name}/{seat}');paint_now = Painter(4)
    setup(s, options, (), seed, seat)
    state = {'returned': 0}
    def call(pc, ints=(), floats=()):
        return o.call(pc, list(ints), list(floats))
    def begin():
        o.begin();call(0x17c210);s.send('w_begin');state['returned'] = 0
    def check(label, painted=None):
        s.compare((name, label, s.visits), paint_now(label) if painted is None else painted, chosen=state['returned'])
    def globals_(mode=13, extra=0, front=0, middle=0, base=0.0):
        for a, v in ((0x4c3808, mode), (0x4ee85c, front), (0x4ee860, middle), (0x4ee54c, bits(base))):p.write(a, v, 4)
        p.write(0x43d0d6, extra, 1)
        s.send('w_globals', mode, extra, front, middle, bits(base))
    def geometry():
        return [float(rng.randrange(-120, 620)+rng.choice((0, 0, .5))), float(rng.randrange(-80, 460)+rng.choice((0, 0, .25)))]
    if name == 'guide':
        keys = sorted({p.read(0x4ee870+8*i, 1) for i in range(207)})
        def step(command, pc, *args):
            if pc == 0x1822a0:assert o.go(pc, G) == 0   # runs 1ce478: served disc boundaries
            else:call(pc, (G, *args))
            s.send(*command.split())
            begin();call(0x182600, (G,));s.send('w_guide');check(command.split()[0])
        for _ in range(4 if quick else 10):
            step('g_init', 0x1822a0)
            for _ in range(20 if quick else 50):
                k = rng.randrange(14)
                if k < 3:
                    layout = rng.randrange(-1, 15);step(f'g_layout {layout} {seat}', 0x182318, layout)
                elif k < 8:step('g_tick', 0x1825b8)
                elif k == 8:step('g_open', 0x182648)
                elif k == 9:step('g_close', 0x1826b0)
                elif k == 10:
                    key = rng.choice(keys+[0x3f, 0x90]);sub = rng.randrange(3) if key < 0x38 else 0
                    step(f'g_message {key} {sub}', 0x1827c0, key, sub)
                elif k == 11:
                    layout = rng.choice((0xb, 0xc, 0xd, 0xb, rng.randrange(-1, 16)));step(f'g_extra {layout} {seat}', 0x1827d8, layout)
                elif k == 12:step('g_extra_open', 0x1827f0)
                else:step('g_extra_close', 0x182828)
    elif name == 'list':
        def pad(held, pressed, repeat):
            for i, word in enumerate((held, pressed, repeat)):p.write(PAD+12*seat+4*i, word, 4)
        def step(command, pc, *args, at=W):
            if pc:call(pc, (at, *args))
            s.send(*command.split())
            begin();call(0x20ef38, (W,));s.send('w_list');check(command.split()[0])
        for _ in range(3 if quick else 12):
            step('l_init', 0x20e570)
            style = rng.randrange(3)
            for bit in (15, 16):
                value = int(style == bit-14);step(f'l_flag {bit} {value}', 0x20e0a0, bit, value, at=W+0x50)
            for _ in range(20 if quick else 50):
                k = rng.randrange(18)
                if k == 0:
                    count, visible = rng.choice((1, 3, 12, 30, 60)), rng.choice((-1, 1, 5, 9, 10, 20))
                    step(f'l_resize {count} {visible}', 0x20e5d8, count, visible)
                elif k < 3:
                    index, text = rng.choice((0, 1, 2, 5, 11, rng.randrange(60))), rng.randrange(-1, 49)
                    step(f'l_item {index} {text}', 0x20e7f8, index, p.read(0x4d4bb0+4*text, 4) if text >= 0 else 0)
                elif k == 3:
                    a = (rng.choice((-1, 3, 8, 9, 20)), rng.randrange(3), rng.randrange(2), rng.randrange(2), rng.randrange(2))
                    step('l_chars '+' '.join(map(str, a)), 0x20eae0, *a)
                elif k == 4:
                    ident = rng.randrange(-2, 80);step(f'l_select {ident}', 0x20ed70, ident)
                elif k == 5:
                    a = (rng.randrange(-300, 600), rng.randrange(-40, 420), rng.randrange(-100, 500), rng.randrange(0, 300), rng.choice((1, 3, 16)))
                    step('l_panel '+' '.join(map(str, a)), 0x17f428, *a, at=W+0x1c)
                elif k == 6:step('l_open', 0x17f468, at=W+0x1c)
                elif k == 7:step('l_close', 0x17f4b0, at=W+0x1c)
                elif k == 8:
                    shown, active = rng.randrange(4) != 0, rng.randrange(2)
                    p.write(W+0x14, shown, 4);p.write(W+0x18, active, 4);step(f'l_state {int(shown)} {active}', 0)
                else:
                    word = rng.choice((0, 0x10, 0x20, 0x20, 0x100000, 0x400000, 0x200000, 0x800000))
                    pad(word, word, word);step(f'l_update {word} {word} {word}', 0x20ee70, seat)
    elif name == 'frames':
        for index in range(40 if quick else 150):
            globals_(base=rng.choice((0.0, 0.0, -20.0, 35.0)))
            begin()
            for _ in range(3):
                kind = rng.randrange(3)
                x, y = geometry();w, h = float(rng.randrange(0, 420)+rng.choice((0, .5))), float(rng.randrange(0, 300)+rng.choice((0, .5)))
                focused = rng.randrange(2)
                call(0x17c260, (F,));call(0x17c2d0, (F, focused))
                for off, value in ((0xc, w), (0x10, h), (0x14, x), (0x18, y)):p.write(F+off, bits(value), 4)
                if kind == 0:
                    style, gutter = rng.choice((0, 1, 1, 2, 3)), rng.choice((0, 0, 10, 3, -2))
                    p.write(F, style, 4);call(0x17c718, (F, gutter))
                    s.send('w_frame', style, *map(bits, (w, h, x, y)), focused, gutter)
                elif kind == 1:
                    # As 20e5d8 and 17f560 keep them: visible <= count, top <= count - visible.
                    count = rng.randrange(1, 200);visible = rng.randrange(1, min(count, 40)+1);top = rng.randrange(0, count-visible+1)
                    scale = rng.choice((1, 1, 1, 2, 3))
                    call(0x17f090, (F, count, visible, top, scale))
                    s.send('w_scroll', *map(bits, (w, h, x, y)), focused, count, visible, top, scale)
                else:
                    z = float(rng.randrange(-900, 0))
                    call(0x17eed8, (), (x, y, z, w, h));s.send('w_bar', *map(bits, (x, y, z, w, h)))
            check('frames')
    else:
        # 17e428 over every message of table 4ee870 and over synthetic token lines;
        # 17e228 and the small font over the character names.
        records = [p.read(0x4ee870+8*i+4, 4) for i in range(207)]
        cases = [('m', i) for i in range(207)]+[('t', t) for t in TOKENS for _ in range(3)]+[('l', i) for i in range(49)]
        if quick:cases = cases[::9]
        for index, (kind, item) in enumerate(cases):
            layer = rng.choice((0, 0, 0, 1, 2))
            globals_(extra=rng.randrange(2) if kind != 'm' else index % 2, front=int(layer == 2 or (layer and index % 5 == 0)), middle=int(layer >= 1),
                     base=rng.choice((0.0, 0.0, -20.0, 35.0)))
            begin()
            colour = rng.choice((0xffffffff, 0xffff0000, 0xffb0b0b0, rng.getrandbits(32)))
            p.write(0x4ee548, colour, 4)
            # Callers pass integral positions; fractional ones are compared as lists only
            # (an icon then lands between pixels, which the painters do not model).
            fraction = rng.random() < .25
            x, y = float(rng.randrange(-40, 420)+(.5 if fraction else 0)), float(rng.randrange(-10, 430)+(.75 if fraction else 0))
            mode, plain = rng.choice((1, 1, 2, 0, 3)), int(rng.random() < .2)
            if kind == 'l':
                ptr = p.read(0x4d4bb0+4*item, 4);style = rng.randrange(3)
                call(0x17e228, (ptr, int(x), int(y), style))
                text = bytes(p.memory[ptr:p.memory.index(0, ptr)])
                s.send('w_label', text.hex(), int(x), int(y), style, colour)
                # 17dbf8 leaves 3db900 to its caller 17db70; the sequence is reproduced here.
                saved = p.read(0x3db900, 4);p.write(0x3db900, colour, 4)
                call(0x17dbf8, (ptr, int(x), int(y)+40));p.write(0x3db900, saved, 4)
                s.send('w_small', int(x), int(y)+40, item, colour)
            else:
                if kind == 'm':ptr = records[item]
                else:
                    ptr = TEXT;p.memory[ptr:ptr+len(item)+2] = item+b'\0\0'
                value = call(0x17e428, (ptr, mode, plain), (x, y)) & 0xffffffff
                state['returned'] = value-ptr if value else 0
                if kind == 'm':s.send('w_message', mode, plain, bits(x), bits(y), colour, item)
                else:s.send('w_markup', item.hex() or '-', mode, plain, bits(x), bits(y), colour)
            check(kind, not fraction)
    s.close()
    return s.result(scene='window library')


def main():
    cli = argparse.ArgumentParser();cli.add_argument('--only');cli.add_argument('--case');cli.add_argument('--quick', action='store_true')
    cli.add_argument('--jobs', type=int, default=6)
    args = cli.parse_args()
    assert hashlib.sha256(ELF.read_bytes()).hexdigest() == ORIGINAL
    blob, _ = extract_gallery_art.extract()
    assert extract_gallery_art.OUT.read_bytes() == blob == (PACKAGE/'gallery_art.bin').read_bytes(), 'run extract_gallery_art.py first'
    q = args.quick
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp)/'driver.cpp';exe = Path(tmp)/'driver'
        cpp.write_text(DRIVER)
        sources = [ROOT/'src'/n for n in ('gallery_art.cpp', 'console_gallery.cpp', 'menu_widgets.cpp', 'menu_canvas.cpp', 'console_menu.cpp',
                                         'system_data.cpp', 'game_random.cpp', 'scalar_float.cpp')]
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp, *sources, '-o', exe], check=True)
        jobs = []
        jobs += [(top_case, (exe, name, seat, 3+seat, q)) for name in ('rows', 'random') for seat in range(2)]
        jobs += [(pictures_case, (exe, name, seat, locks, 5+seat, q)) for name, seat, locks in
                 (('all', 0, 'unlocked'), ('view', 0, 'unlocked'), ('view', 1, 'factory'), ('random', 0, 'sparse'), ('random', 1, 'factory'))]
        jobs += [(sound_case, (exe, name, seat, locks, 8+seat, q)) for name, seat, locks in
                 (('bgm', 0, 'factory'), ('bgm', 1, 'factory'), ('voice', 0, 'unlocked'), ('voice', 1, 'sparse'), ('narration', 0, 'factory'),
                  ('narration', 1, 'factory'), ('random', 0, 'factory'), ('random', 1, 'unlocked'))]
        jobs += [(ending_case, (exe, name, seat, seen, 20+seat, q)) for name, seat, seen in
                 (('empty', 0, 'none'), ('play', 0, 'few'), ('play', 1, 'all'), ('random', 0, 'all'), ('random', 1, 'few'))]
        jobs += [(widget_case, (exe, name, seat, 30+seat, q)) for name in ('guide', 'list', 'frames', 'text') for seat in range(2)]
        if args.only:jobs = [j for j in jobs if j[0].__name__.startswith(args.only)]
        if args.case:jobs = [j for j in jobs if j[1][1] == args.case]
        if args.jobs == 1:cases = [fn(spec) for fn, spec in jobs]
        else:
            with ProcessPoolExecutor(args.jobs) as pool:
                futures = [pool.submit(fn, spec) for fn, spec in jobs]
                cases = [f.result() for f in futures]
    total = dict(visits=sum(c['visits'] for c in cases), frames=sum(c['frames'] for c in cases),
                 queue_entries=sum(c['queue_entries'] for c in cases), instructions=sum(c['instructions'] for c in cases))
    pictures = sorted({i for c in cases for i in c['pictures']})
    if not args.only and not args.case and not q:
        REPORT.write_text(json.dumps(dict(status='passed', elf_sha256=ORIGINAL, cases=cases, identical_primitive_lists=total['visits'],
            identical_640x480_frames=total['frames'], original_queue_entries=total['queue_entries'], original_instructions=total['instructions'],
            pictures_drawn=pictures, asset_sha256=hashlib.sha256(blob).hexdigest(), scope=SCOPE), indent=2)+'\n')
    print(len(cases), 'EE/native gallery drawing traces;', total['visits'], 'identical primitive lists;', total['frames'], 'identical frames;',
          total['queue_entries'], 'queue entries;', len(pictures), 'pictures;', total['instructions'], 'instructions')

SCOPE = ('Japanese SLPS-25559, game mode 13, both operating seats. Whole original scene code with its drawing: top menu entry 1d22f8 and '
         'task 1d2380 per visit; illustration viewer 13ed98/13edf0, sound test 13e090/13e0e8 (with the lyrics overlay 13dc98) and ending '
         'selection 182968/182ce0/13f4a8 as coroutine bodies run on their own stack up to the yield entry 112a28 and resumed at the saved '
         'return address (the tasks are PS2 kernel threads). The window library is additionally called directly on scratch objects: guide '
         'window 1822a0..182828 + 182600 over layouts -1..15 and both key bars; list widget 20e570..20ee70 + 20ef38 in its three text styles '
         'with and without scroll bar; 17c718 styles 0..3, 17f090 (scale 1..3), 17eed8; 17e428 over all 207 records of message table 4ee870 '
         'and synthetic token lines (every icon token, EX, MS, CR, odd bytes) in modes 0..3, plain 0/1, the three text layers and both '
         'values of byte 43d0d6; 17e228 modes 0..2 and the small font 17dbf8 over the 49 character names. After every visit or call the '
         'original submission queue 68c3c0 is decoded and compared entry by entry, in submission order and with exact float bits, with the '
         'MenuDrawList of src/gallery_art.cpp built from the native logic state (console_gallery / menu_widgets driven by the same pad '
         'words); glyph entries compare the cached texel block. The renderer globals 3db900, 3db8fc, 3db8f4, 345180, 348a8c, the depth '
         'cursor 12d3850, the help marquee, the library RNG seed, the overlay population words and the three menu counters are compared '
         'after every visit, and the return value of 17e428. The painted subset uses the reference painter of validate_menu_canvas.py for '
         'the original queue (ascending depth, pixel-centre sampling; the queue-to-GS translation 106c08 and GS rasterisation are not '
         'executed) against GalleryArt::rasterise; picture frames include three scene-fade states (116588 interpolating the CLUT). '
         'Everything executes unmodified except: sound driver entries 1e7b70 1e7ba0 1e79c8 1e7d60 1e7ad0 1e7b40 1e8298 213180 213238, '
         'debug prints 316140 316218, thread creation 100e58, scene switch 1252f0 and the ending object reset 182858 1828c0 120110 '
         '(jr ra); texture load by name 1142d8 and the disc read 102810 inside the palette loader 1163c0 are served by the script with the '
         'archive members (PS2_menu_bg00_00, gl_NN); the yield 112a28 and the ending engine entry 182a98 end a visit. The .bss range '
         'that the shared probe fixture fills with character banks is cleared first. The stream word 5a9e6c is driven by the fixture and '
         'the lyric counter is poked on both sides to sample the colour ramps and the wrap. Not covered: 109de8 (guide backdrop over a '
         'battle scene), game mode 0x11 key-bar suppression, icons 33..47 of the slot 5 edit sheet, the 1252f0 fade of a leaving scene, '
         'the ending engine, fractional text positions in the painted comparison (lists only).')

if __name__ == '__main__':main()
