#!/usr/bin/env python3
"""Compare the native gallery scenes and menu widgets with SLPS-25559 visit by visit."""
import argparse
import hashlib
import json
import random
import struct
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from mips_probe import Probe, signed
from validate_dash_motion import ELF, PIN, ROOT, digest

ASSETS = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
REPORT = ROOT/'outputs/ss6-feasibility/console_gallery_validation.json'
RETURN = struct.pack('<II', 0x03e00008, 0x0000102d)
# Boundaries replaced by `jr ra; move v0,zero`. Everything else executes.
RENDER = (0x113f98, 0x1145c0, 0x1147d8, 0x10a460, 0x10a568, 0x10a710, 0x10a1c0, 0x109f08, 0x1135e8,
          0x1142d8, 0x1163c0, 0x116478, 0x10add8, 0x112f30, 0x17eda0, 0x1ce570, 0x1ce628, 0x182858,
          0x1828c0, 0x120110,
          # Background overlay effect 1e1620..1e2408: its set-up alone draws the library
          # generator 1,800 times before 1ce478's variant draw; MenuChrome does not model it.
          0x1e1620, 0x1e2358, 0x1e23a0, 0x1e2408)
SOUND = (0x1e7b70, 0x1e7ba0, 0x1e79c8, 0x1e7d60, 0x1e7ad0, 0x1e7b40, 0x1e8298, 0x213180, 0x213238)
PLATFORM = (0x316140, 0x316218, 0x100e58, 0x1252f0)
YIELD, PLAYBACK, TRAMPOLINE = 0x112a28, 0x182a98, 0x1f00000
OPTION, SETTING, MAP, IDS = 0x43d058, 0x43d050, 0x1373830, 0x128a1c0
(TONE, BANK_TONE, LOAD_BANK, BATTLE_SOUND, VOICE, MUSIC, MUSIC_STOP, EFFECTS_STOP, NARRATION_CHECK,
 NARRATION_LOAD, SCENE, GAME_DATA_RESET, ENDING_CHOSEN) = range(1, 14)

DRIVER = r'''
#include "console_gallery.hpp"
#include <iostream>
#include <sstream>
using namespace ss6;
static uint32_t fnv(uint32_t h,unsigned byte){return (h^(byte&255))*16777619u;}
static uint32_t text(std::string_view s){uint32_t h=2166136261u;for(unsigned char c:s)h=fnv(h,c);return h;}
static std::ostream& panel(std::ostream& o,const SlidePanel& p){for(int v:p.words())o<<v<<' ';return o;}
static void list(std::ostream& o,const ListWidget& w){
    o<<w.width<<' '<<w.height<<' '<<w.visible<<' '<<w.top<<' '<<w.shown<<' '<<w.active<<' ';panel(o,w.panel);
    auto& s=w.selector;o<<s.flags<<' '<<s.min<<' '<<s.max<<' '<<s.step<<' '<<s.current<<' '<<s.page<<' '<<w.selected()<<' ';
    uint32_t h=2166136261u;
    for(int i=0;i<s.max&&i<int(ListWidget::capacity);++i){
        if(!w.items[i].data())h=fnv(h,255);
        else {for(unsigned char c:w.items[i])h=fnv(h,c);h=fnv(h,0);}
    }
    o<<h<<' ';
}
static void bar(std::ostream& o,const GuideBar& b){o<<b.shown<<' '<<b.open<<' '<<b.configured<<' ';panel(o,b.panel)<<b.layout<<' ';}
static void guide(std::ostream& o,const GuideWindow& g){
    o<<g.initialised<<' '<<g.layout<<' '<<g.backdrop<<' ';
    bar(o,g.title);o<<g.titleRect<<' ';bar(o,g.message);o<<text(g.messageText())<<' ';
    for(const GuideKeys* k:{&g.keys,&g.extra}){
        bar(o,*k);o<<k->width<<' '<<k->height<<' '<<k->textX<<' '<<k->textY<<' '
                  <<text(k->text<0?std::string_view():std::string_view(g.data->keyHelp[k->text]))<<' ';
    }
}
static void events(std::ostream& o,const std::vector<GalleryEvent>& e){
    o<<e.size();for(auto& v:e)o<<' '<<v.kind<<' '<<v.a<<' '<<v.b<<' '<<v.c;o<<'\n';
}
static void chromeRow(std::ostream& o,const MenuChrome& c,const GameRandom& r){
    o<<c.band<<' '<<c.content<<' '<<c.legend<<' '<<c.variant<<' '<<c.helpX[0]<<' '<<c.helpX[1]<<' '<<c.helpDelay<<' '<<r.librarySeed<<' ';
}
int main(int,char** argv){
    SystemData system(argv[1]);MenuWidgetData widgets(argv[1]);GalleryData data(argv[1]);
    MenuChrome chrome;GameRandom random;MenuPadRepeat repeat;
    GalleryTopMenu top;IllustrationViewer pictures;SoundTest sound;EndingViewer ending;
    std::array<uint32_t,2> last{};
    MenuSelector selector;std::vector<uint32_t> bitmap;GuideWindow window;ListWidget single;CharacterRows singleRows{};
    std::string line,op;
    while(std::getline(std::cin,line)){
        std::istringstream in(line);in>>op;
        std::vector<long long> v;for(long long x;in>>x;)v.push_back(x);
        v.resize(16);
        const long long a=v[0],b=v[1],c=v[2];
        std::ostream& o=std::cout;
        auto tones=[&](int code,const std::vector<int>& t){o<<code<<' '<<t.size();for(int x:t)o<<' '<<x;o<<'\n';};
        auto pads=[&](unsigned seat){
            std::array<uint32_t,2> held{uint32_t(a),uint32_t(b)};
            auto m=repeat.sample(held,{held[0]&~last[0],held[1]&~last[1]});last=held;
            return std::pair{m,WidgetPad{held[seat],m[seat].pressed,m[seat].repeat}};
        };
        if(op=="selector"){
            // flags cur min max step page bitmap0 bitmap1 held pressed repeat
            bitmap={uint32_t(v[6]),uint32_t(v[7])};
            selector.flags=uint32_t(v[0]);selector.disabled=&bitmap;selector.current=int(v[1]);
            selector.setRange(int(v[2]),int(v[3]),int(v[4]),int(v[5]));
            std::vector<int> t;const int code=selector.update({uint32_t(v[8]),uint32_t(v[9]),uint32_t(v[10])},t);
            o<<selector.current<<' '<<selector.min<<' '<<selector.max<<' '<<selector.step<<' '<<selector.page<<' ';tones(code,t);
        } else if(op[0]=='g'&&op[1]=='_'){
            if(op=="g_init")window.init(widgets);
            else if(op=="g_layout")window.setLayout(int(a),unsigned(b));
            else if(op=="g_tick")window.tick();
            else if(op=="g_open")window.open();
            else if(op=="g_close")window.close();
            else if(op=="g_message")window.setMessage(int(a),int(b));
            else if(op=="g_extra")window.setExtraLayout(int(a),unsigned(b));
            else if(op=="g_extra_open")window.openExtra();
            else if(op=="g_extra_close")window.closeExtra();
            guide(o,window);o<<'\n';
        } else if(op[0]=='l'&&op[1]=='_'){
            std::vector<int> t;int code=0;
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
            else if(op=="l_update")code=single.update({uint32_t(a),uint32_t(b),uint32_t(c)},t);
            list(o,single);tones(code,t);
        } else if(op=="option")system.option(size_t(a))=uint8_t(b);
        else if(op=="setting")system.setting(size_t(a))=uint8_t(b);
        else if(op=="seed")random.librarySeed=uint64_t(a);
        else if(op=="help")chrome.setHelp(int(a));
        else if(op=="top_reset")top.reset();
        else if(op=="top_enter"||op=="top"){
            if(op=="top")top.tick(data,chrome,pads(0).first);else top.enter(data,chrome,random);
            o<<top.row<<' '<<top.leaving<<' '<<top.operatingSeat<<' '<<(op=="top"?top.alpha:0)<<' ';chromeRow(o,chrome,random);events(o,top.events);
        } else if(op=="pictures_enter")pictures.enter(unsigned(a),system,widgets,data,chrome,random);
        else if(op=="pictures"){
            auto& v=pictures;v.tick(pads(v.seat).second);
            o<<v.state<<' '<<v.previous<<' '<<v.hideUi<<' '<<v.centreX<<' '<<v.centreY<<' '<<v.size<<' '<<v.characterRows<<' '
             <<v.imageVisible()<<' '<<(v.imageVisible()?v.imageId():0)<<' '<<(v.imageVisible()?v.imageX():0)<<' '
             <<(v.imageVisible()?v.imageY():0)<<' '<<v.uiVisible()<<' ';
            chromeRow(o,chrome,random);guide(o,v.guide);list(o,v.list);events(o,v.events);
        } else if(op=="sound_enter")sound.enter(unsigned(a),system,widgets,data,chrome,random);
        else if(op=="sound_counter")sound.lyricCounter=int(a);
        else if(op=="sound"){
            auto& v=sound;v.tick(pads(v.seat).second,c!=0);
            o<<v.state<<' '<<v.previous<<' '<<v.lyricAlpha<<' '<<v.lyricCounter<<' '<<v.lyricSet<<' ';
            uint32_t h=2166136261u;
            for(int i=0;i<v.lists[2].count();++i){h=fnv(h,uint16_t(v.ids[i]));h=fnv(h,uint16_t(v.ids[i])>>8);}
            o<<h<<' ';
            const auto glyphs=v.lyricGlyphs();h=2166136261u;
            for(auto& g:glyphs)for(unsigned x:{unsigned(g.code),unsigned(g.code>>8),unsigned(g.x),unsigned(g.x>>8),unsigned(g.y),unsigned(g.y>>8),unsigned(g.r),unsigned(g.g),unsigned(g.b)})h=fnv(h,x);
            o<<glyphs.size()<<' '<<h<<' ';
            chromeRow(o,chrome,random);guide(o,v.guide);for(auto& w:v.lists)list(o,w);events(o,v.events);
        } else if(op=="ending_scene"){ending.enterScene(data,chrome,random);chromeRow(o,chrome,random);o<<"0\n";}
        else if(op=="ending_begin")ending.beginSelection(unsigned(a),system,widgets,chrome,random);
        else if(op=="ending"){
            auto& v=ending;v.tick(pads(v.seat).second);
            o<<v.chosen<<' '<<v.state<<' '<<v.previous<<' '<<v.countdown<<' ';
            chromeRow(o,chrome,random);guide(o,v.guide);list(o,v.list);events(o,v.events);
        }
    }
}
'''

def fnv(data, h=2166136261):
    for byte in data:h = ((h ^ byte)*16777619) & 0xffffffff
    return h

class Stop:
    def __init__(self, *addresses):self.addresses = addresses;self.stopped = None
    def __contains__(self, pc):
        if pc in self.addresses:
            self.stopped = pc
            return True
        return False

class Oracle:
    """Original scene code with rendering, sound-driver, disc and kernel boundaries stubbed."""
    def __init__(self, seat=0, options=(), settings=(), seed=1):
        self.p = p = Probe(ELF.read_bytes(), finite_model=True)
        for pc in RENDER+SOUND+PLATFORM:p.memory[pc:pc+8] = RETURN
        image = (ASSETS/'save_default.bin').read_bytes()
        p.memory[OPTION:OPTION+0x98] = image[0x618c:0x618c+0x98]
        p.memory[SETTING:SETTING+7] = image[0x6184:0x6184+7]
        for off, value in options:p.write(OPTION+off, value, 1)
        for off, value in settings:p.write(SETTING+off, value, 1)
        self.instructions = 0
        self.run(0x112570)  # task pool
        self.run(0x1cebb0, 52)  # help ticker as a preceding menu leaves it
        p.write(0x443150, 1, 4);p.write(0x4c3808, 0xd, 4);p.write(0x12d35c4, seat, 4)
        self.seed = p.read(0x5d1bf8, 4)+0xa8
        p.write(self.seed, seed, 8)
        self.seat = seat;self.last = [0, 0];self.events = [];self.strings = {};self.items = {}
        self.context = None;self.thread_pc = None;self.frame = None;self.observed = {}

    def run(self, pc, *args, stop=None, observe=None, limit=4000000):
        value, count = self.p.run(pc, args, limit=limit, stop_before=stop or (), observe=observe)
        self.instructions += count
        return value

    def sample(self, held):
        p = self.p
        for seat, word in enumerate(held):
            p.write(0x443568+4*seat, word, 4);p.write(0x443570+4*seat, self.last[seat], 4)
            self.run(0x117fd8, seat)
        self.last = list(held)

    def observe(self, pc):
        p = self.p;r = p.registers;e = self.events
        if pc == 0x1e7b70:e.append((TONE, signed(r[4], 32), r[5] & 0xffffffff, 0))
        elif pc == 0x1e7ba0:e.append((BANK_TONE, signed(r[4], 32), signed(r[5], 32), 0))
        elif pc == 0x1e79c8:e.append((LOAD_BANK, signed(r[4], 32), signed(r[5], 32), 0))
        elif pc == 0x1e8298:e.append((BATTLE_SOUND, signed(r[4], 32), signed(r[5], 32), signed(r[6], 32)))
        elif pc == 0x1e7d60:e.append((VOICE, signed(r[4], 32), signed(r[5], 32), p.read(0x43d055, 1)))
        elif pc == 0x214060:e.append((MUSIC, signed(r[4], 32), signed(r[5], 32), p.read(0x43d056, 1)))
        elif pc == 0x1e7ad0:e.append((MUSIC_STOP, 0, 0, 0))
        elif pc == 0x1e7b40:e.append((EFFECTS_STOP, 0, 0, 0))
        elif pc == 0x213238:e.append((NARRATION_CHECK, 0, 0, p.read(0x43d055, 1)))
        elif pc == 0x213180:e.append((NARRATION_LOAD, 0, 0, p.read(0x43d055, 1)))
        elif pc == 0x124d50:e.append((GAME_DATA_RESET, 0, 0, 0))
        elif pc == 0x1252f0:
            assert r[4] == 1 and r[5] == 0
            e.append((SCENE, r[6] & 0xffffffff, r[7] & 0xffffffff, 0))
        elif pc == 0x1d2620:self.observed['alpha'] = signed(r[4], 32)
        elif pc == 0x17eda0:
            self.observed['image'] = (signed(r[4], 32), signed(r[5], 32), int(p.float_value(12)), int(p.float_value(13)))
        elif pc == 0x182600:self.observed['ui'] = 1
        elif pc == 0x10a710 and r[31] == 0x13de8c:
            self.observed.setdefault('glyphs', []).append((r[4] & 0xffff, signed(r[5], 32), signed(r[6], 32), r[7] & 255, r[8] & 255, r[9] & 255, signed(r[10], 32)))
        elif pc == 0x1126f0:self.observed['task'] = (r[5] & 0xffffffff, r[6] & 0xffffffff, r[7] & 0xffffffff)

    # A coroutine task is a PS2 kernel thread (100e58 CreateThread, 100ef0
    # wake, 112a28 -> 100ec8 sleep). The probe has no kernel, so the thread is
    # modelled here: its body runs on its own stack up to the yield entry
    # 112a28, the complete register file is kept, and the next visit resumes
    # at the saved return address with v0 = 0.
    def start(self, entry, stack, words):
        self.thread_pc = entry;self.thread_sp = stack+4*words-0x40;self.context = None
    def visit(self):
        p = self.p
        if self.context:
            p.registers, p.registers_high, p.lo, p.hi, p.lo1, p.hi1, p.floats, p.float_acc, p.float_condition = self.context
            p.registers = list(p.registers);p.registers_high = list(p.registers_high);p.floats = list(p.floats)
            p.registers[2] = 0
        sp, pc = self.thread_sp, self.thread_pc
        code = [0x3c1d0000 | sp >> 16, 0x37bd0000 | sp & 0xffff, 0x3c1a0000 | pc >> 16, 0x375a0000 | pc & 0xffff, 0x03400008, 0]
        p.memory[TRAMPOLINE:TRAMPOLINE+24] = struct.pack('<6I', *code)
        self.events = [];self.observed = {}
        stop = Stop(YIELD, PLAYBACK)
        self.run(TRAMPOLINE, stop=stop, observe=self.observe)
        assert stop.stopped, 'the coroutine returned'
        if stop.stopped == YIELD:assert p.registers[4] == 0
        self.thread_pc = p.registers[31] & 0xffffffff;self.thread_sp = self.frame = p.registers[29] & 0xffffffff
        self.context = (list(p.registers), list(p.registers_high), p.lo, p.hi, p.lo1, p.hi1, list(p.floats), p.float_acc, p.float_condition)
        return stop.stopped

    def text(self, pointer):
        if pointer not in self.strings:
            end = self.p.memory.index(b'\0', pointer) if pointer else 0
            self.strings[pointer] = fnv(self.p.memory[pointer:end]) if pointer else fnv(b'')
        return self.strings[pointer]
    def word(self, at):return signed(self.p.read(at, 4), 32)
    def panel(self, at):return [self.word(at+4*i) for i in range(13)]
    def list(self, at):
        p = self.p;w = self.word
        flags, count, cur = p.read(at+0x50, 4), w(at+0x5c), w(at+0x64)
        pointers = bytes(p.memory[at+0x6c:at+0x6c+4*max(0, min(count, 0x200))])
        if pointers not in self.items:
            data = bytearray()
            for (q,) in struct.iter_unpack('<I', pointers):
                data += bytes(p.memory[q:p.memory.index(b'\0', q)+1]) if q else b'\xff'
            self.items[pointers] = fnv(data)
        # 20ee20 indexes the 55-entry map without a bound; rows past it read
        # unrelated bss. The native port reports -1 there.
        selected = (signed(p.read(MAP+2*cur, 2), 16) if 0 <= cur < 55 else -1) if flags & 0x2000 else cur
        return [w(at), w(at+4), w(at+0xc), w(at+0x10), w(at+0x14), w(at+0x18), *self.panel(at+0x1c),
                flags, w(at+0x58), count, w(at+0x60), cur, w(at+0x68), selected, self.items[pointers]]
    def bar(self, at):return [self.word(at), self.word(at+4), self.word(at+8), *self.panel(at+0xc), self.word(at+0x40)]
    def guide(self, at):
        w = self.word
        out = [w(at), w(at+4), w(at+8), *self.bar(at+0x10), w(at+0x58), *self.bar(at+0x60), self.text(self.p.read(at+0xa8, 4))]
        for k in (at+0xac, at+0x108):
            out += [*self.bar(k), w(k+0x48), w(k+0x4c), w(k+0x50), w(k+0x54), self.text(self.p.read(k+0x58, 4))]
        return out
    def chrome(self):
        w = self.word
        return [w(0x582b34), w(0x582b38), w(0x582b3c), w(0x582b44), w(0x582b28), w(0x582b2c), w(0x582b30), self.p.read(self.seed, 8)]
    def flat(self):return [len(self.events), *[v for e in self.events for v in e]]
    def reg(self, n):return signed(self.p.registers[n], 32)

    # Scene rows; each mirrors one output line of the native driver.
    def top_enter(self):
        self.events = [];self.observed = {}
        self.run(0x1d22f8, observe=self.observe)
        return self.top_row(0)
    def top(self, held):
        self.sample(held);self.events = [];self.observed = {}
        self.run(0x1d2380, observe=self.observe)
        return self.top_row(self.observed['alpha'])
    def top_row(self, alpha):
        w = self.word
        return [w(0x582d88), w(0x582d8c), w(0x12d35c4), alpha, *self.chrome(), *self.flat()]
    def scene(self, entry, handler):
        self.events = [];self.observed = {}
        self.run(entry, observe=self.observe)
        assert self.observed['task'][0] == handler and not self.events
        self.start(handler, *self.observed['task'][1:])
    def pictures(self, held):
        self.sample(held)
        assert self.visit() == YIELD
        f = self.frame;w = self.word
        image = self.observed.get('image')
        return [self.reg(20), self.reg(19), w(f+0x9e0), w(f+0x9e4), w(f+0x9e8), self.reg(30), self.reg(23),
                int(image is not None), *((image[0], image[2], image[3]) if image else (0, 0, 0)),
                self.observed.get('ui', 0), *self.chrome(), *self.guide(f), *self.list(f+0x170), *self.flat()], image
    def sound(self, held, playing):
        self.sample(held);self.p.write(0x5a9e6c, playing, 4)
        assert self.visit() == YIELD
        f = self.frame;w = self.word
        count = max(0, w(f+0x1250+0x5c))
        glyphs = self.observed.get('glyphs', [])
        alpha = w(f+0x1af8)
        assert all(g[6] == alpha for g in glyphs)
        packed = bytearray()
        for code, x, y, r, g, b, _ in glyphs:packed += struct.pack('<HhhBBB', code, x, y, r, g, b)
        return [self.reg(30), self.reg(19), alpha, w(f+0x1afc), w(f+0x1b00), fnv(self.p.memory[IDS:IDS+2*count]),
                len(glyphs), fnv(packed), *self.chrome(), *self.guide(f), *self.list(f+0x170), *self.list(f+0x9e0),
                *self.list(f+0x1250), *self.flat()]
    def ending(self, held):
        self.sample(held)
        stopped = self.visit()
        if stopped == PLAYBACK:
            # 13f4a8 returned its selection inside the visit; 182ce0 is about
            # to start the ending engine, which is outside this comparison.
            return None, self.reg(4), self.flat()
        f = self.frame
        return [0, self.reg(17), self.reg(19), self.reg(18), *self.chrome(), *self.guide(f), *self.list(f+0x170), *self.flat()], None, None

def compare(name, commands, expected, exe):
    native = subprocess.run([exe, ASSETS], input='\n'.join(commands)+'\n', text=True, capture_output=True, check=True)
    actual = [list(map(int, line.split())) for line in native.stdout.splitlines()]
    assert len(actual) == len(expected), (name, len(actual), len(expected))
    for i, (a, b) in enumerate(zip(actual, expected)):
        if isinstance(b, dict):
            # A visit the original does not complete: only its request list is comparable.
            events = a[b['fixed']:]
            assert a[0] == b['chosen'] and events[1:1+len(b['events'])] == b['events'] and (b['open'] or events[0]*4 == len(b['events'])), (name, i, a[:4], events, b)
            continue
        assert a == b, (name, i, len(a), len(b), [(k, v, w) for k, (v, w) in enumerate(zip(a, b)) if v != w][:12])

def setup(options, settings, seed):
    return [f'option {o} {v}' for o, v in options]+[f'setting {o} {v}' for o, v in settings]+[f'seed {seed}', 'help 52']

def top_case(spec):
    exe, name, seat, seed = spec
    rng = random.Random(f'top{name}{seat}{seed}')
    o = Oracle(seed=seed)
    commands = setup((), (), seed)+['top_reset', 'top_enter']
    o.run(0x1d2610);expected = [o.top_enter()]
    requests = []
    def tick(own=0, other=0):
        held = (other, own) if seat else (own, other)
        commands.append(f'top {held[0]} {held[1]}');expected.append(o.top(held))
        requests.extend(e for e in o.events if e[0] == SCENE)
    def tap(word, other=0):tick(word, other);tick()
    def reenter():
        # Returning from a sub-scene runs the entry again; only 1d2610 clears the row.
        o.p.write(0x4c3808, 0xd, 4)
        commands.append('top_enter');expected.append(o.top_enter())
        for _ in range(31):tick()
    for i in range(31):tick(0 if i > 27 else 0x20 if i % 7 == 3 else 0x200 if i == 20 else 0)  # not ready: ignored
    assert o.word(0x582d88) == 0 and not requests
    if name == 'rows':
        for row in range(4):
            for _ in range(row):tap(0x20)
            tap(rng.choice((0x200, 0x8, 0x2)));tick(0x10);tick()
            for _ in range(3):tick(rng.choice((0, 0x10, 0x400)))
            assert requests[-1][2] == (0x182968, 0x13e090, 0x13ed98, 0x127940)[row], requests
            reenter()
            assert o.word(0x582d88) == row
            for _ in range(4-row):tap(0x20)
    elif name == 'cancel':
        tap(0x10);tap(rng.choice((0x400, 0x4)));tick(0x200);tick()
        assert requests == [(SCENE, 0x1d24f0, 0x127940, 0)] and o.word(0x4c3808) == 0
    elif name == 'repeat':
        for _ in range(70):tick(0x20)
        for _ in range(30):tick(0x10 | 0x20)
        tick();tick(0x10, 0x20);tick();tick(0x20, 0x20);tick()
        tick(0x200 | 0x400);tick();assert requests[-1][2] == 0x127940
    elif name == 'both':
        tick(0x20, 0x200);tick()
        assert requests[-1][2] == (0x13e090 if seat == 0 else 0x182968) and o.word(0x12d35c4) == (seat ^ 1)
        reenter();tick(0x400, 0x200);tick()
    else:
        for _ in range(400):
            k = rng.random()
            word = 0 if k < .45 else rng.choice((0x10, 0x20)) if k < .9 else rng.choice((0x200, 0x8, 0x2, 0x400, 0x4, 0x40, 0x80))
            tick(word, rng.choice((0, 0, 0, 0x10, 0x20)))
            if o.word(0x582d8c) and rng.random() < .3:reenter()
    compare(('top', name, seat), commands, expected, exe)
    return dict(scene='top', case=name, seat=seat, snapshots=len(expected), requests=len(requests), instructions=o.instructions)

LOCKS = {'factory': (), 'unlocked': tuple((0x16+c, 0) for c in range(49)),
         'sparse': tuple((0x16+c, int(c % 3 == 1)) for c in range(49))}

def pictures_case(spec):
    exe, name, seat, locks, seed = spec
    rng = random.Random(f'pictures{name}{seat}{locks}{seed}')
    o = Oracle(seat, LOCKS[locks], seed=seed)
    commands = setup(LOCKS[locks], (), seed)+[f'pictures_enter {seat}']
    o.scene(0x13ed98, 0x13edf0)
    expected = [];images = set();requests = []
    def tick(own=0, other=0):
        held = (other, own) if seat else (own, other)
        row, image = o.pictures(held)
        commands.append(f'pictures {held[0]} {held[1]}');expected.append(row)
        if image:images.add((image[0], image[1]))
        requests.extend(e for e in o.events if e[0] == SCENE)
    def tap(word):tick(word);tick()
    for _ in range(20):tick(rng.choice((0, 0x20)))
    if name == 'browse':
        for _ in range(60):tick(0x20)
        tap(0x400000);tap(0x400000);tap(0x100000);tap(0x800000);tap(0x200);
        for _ in range(20):tick()
        tap(0x400)
        for _ in range(20):tick()
        tap(0x200000);tap(0x8)
        for _ in range(20):tick()
        tap(0x4);
        for _ in range(18):tick()
        for _ in range(8):tap(0x10)
        tap(0x2)
        for _ in range(18):tick()
        tap(0x400)
        for _ in range(18):tick()
        tap(0x404)
        for _ in range(24):tick(rng.choice((0, 0x200, 0x20)))
        assert requests == [(SCENE, 0x13edb0, 0x1d22f8, 0)]
    elif name == 'view':
        tap(0x20);tap(0x200)
        for _ in range(18):tick()
        for word, n in ((0x100000, 190), (0x80, 150), (0x40, 330), (0x20, 150), (0x10, 330), (0x400000 | 0x80 | 0x10, 200),
                        (0x100000 | 0x400000, 5), (0x40 | 0x80, 5), (0x10 | 0x20 | 0x100000, 60)):
            for _ in range(n):tick(word)
        tap(0x80000);tick(0x80 | 0x20);tap(0x80000);tap(0x80000 | 0x200);tap(0x80000);tap(0x8);tap(0x80000 | 0x400)
        for _ in range(20):tick()
        tap(0x200)
        for _ in range(20):tick()
        assert any(i[1] == 0x708 for i in images) and o.reg(30) == 0x1b8
    else:
        for _ in range(900):
            k = rng.random()
            if k < .3:word = 0
            elif k < .6:word = rng.choice((0x10, 0x20, 0x40, 0x80, 0x100000, 0x400000, 0x200000, 0x800000))
            elif k < .85:word = rng.choice((0x10, 0x20, 0x40, 0x80)) | rng.choice((0, 0x100000, 0x400000)) | rng.choice((0, 0x10, 0x40))
            else:word = rng.choice((0x200, 0x2, 0x8, 0x400, 0x4, 0x80000, 0x200, 0x200))
            for _ in range(rng.choice((1, 1, 2, 6, 25))):tick(word, rng.choice((0, 0x200, 0x20)))
            if requests:break
    compare(('pictures', name, seat, locks), commands, expected, exe)
    return dict(scene='illustrations', case=name, seat=seat, locks=locks, snapshots=len(expected),
                images=len({i for i, _ in images}), requests=len(requests), instructions=o.instructions)

def sound_case(spec):
    exe, name, seat, locks, seed = spec
    rng = random.Random(f'sound{name}{seat}{locks}{seed}')
    settings = ((5, seed & 1), (6, seed >> 1 & 1))
    o = Oracle(seat, LOCKS[locks], settings, seed)
    commands = setup(LOCKS[locks], settings, seed)+[f'sound_enter {seat}']
    o.scene(0x13e090, 0x13e0e8)
    steps = [];seen = set();requests = [];state = {'playing': 0, 'glyphs': 0}
    def tick(own=0, other=0):
        held = (other, own) if seat else (own, other)
        row = o.sound(held, state['playing'])
        steps.append((f'sound {held[0]} {held[1]} {state["playing"]}', row))
        seen.update(e[0] for e in o.events);state['glyphs'] += row[6]
        requests.extend(e for e in o.events if e[0] == SCENE)
        if any(e[0] == MUSIC for e in o.events):state['playing'] = 0
    def tap(word, wait=1):
        tick(word)
        for _ in range(wait):tick()
    def settle():
        for _ in range(18):tick()
    settle()
    if name == 'bgm':
        for version in range(2):
            tap(0x200);settle()
            for _ in range(version):tap(0x20)
            tap(0x200);settle()
            for row in range(27):
                tap(0x200, 2);state['playing'] = 1
                if row == 5:
                    for _ in range(40):tick()
                    tap(0x80000)
                    for _ in range(40):tick(rng.choice((0, 0x200)) if _ < 20 else 0)
                    # Sample the glyph colour ramps across the song without playing it out.
                    for value in range(40, (0x33ae, 0x23c8)[version], (0x33ae, 0x23c8)[version]//45):
                        o.p.write(o.frame+0x1afc, value, 4)
                        steps.append((f'sound_counter {value}', None))
                        for _ in range(3):tick()
                    # Jump the driver clock to the wrap point of each lyric set.
                    value = (0x33ae, 0x23c8)[version]-20
                    o.p.write(o.frame+0x1afc, value, 4)
                    steps.append((f'sound_counter {value}', None))
                    for _ in range(40):tick()
                    tap(0x400)
                    for _ in range(40):tick()
                    tap(0x80000, 3);tap(0x200, 40)
                tap(0x20)
            tap(0x400);settle();tap(0x400);settle()
        tap(0x4);settle();settle()
        assert requests == [(SCENE, 0x13e0a8, 0x1d22f8, 0)] and state['glyphs']
    elif name == 'voice':
        tap(0x20);tap(0x200);settle()
        count = o.word(o.frame+0x9e0+0x5c)
        picks = sorted(rng.sample(range(count-1), min(6, count-1)))+[count-1]
        at = 0
        for pick in picks:
            while at < pick:
                tap(0x20, 0);at += 1
            tick();tap(0x200);settle()
            rows = o.word(o.frame+0x1250+0x5c)
            for step in range(rows):
                tap(0x200)
                tap(0x20, 0)
            tap(0x400000);tap(0x100000);tap(0x800000);tap(0x200000);tap(0x80000)
            tap(0x400);settle()
        tap(0x400);settle();tap(0x400);settle();settle()
        assert requests and {BANK_TONE, BATTLE_SOUND, LOAD_BANK} <= seen
    elif name == 'narration':
        tap(0x10);tap(0x200);settle()
        for language in range(2):
            if language:tap(0x20)
            tap(0x200);settle()
            for row in range(84):
                tap(0x200);tap(0x20, 0)
            tap(0x400);settle()
        tap(0x404);settle();tap(0x4);settle();settle()
        assert requests and {VOICE, NARRATION_CHECK, LOAD_BANK, NARRATION_LOAD} <= seen
    else:
        for _ in range(700):
            k = rng.random()
            if k < .25:word = 0
            elif k < .6:word = rng.choice((0x10, 0x20, 0x20, 0x100000, 0x400000, 0x200000, 0x800000))
            elif k < .9:word = rng.choice((0x200, 0x200, 0x2, 0x8, 0x80000))
            else:word = rng.choice((0x400, 0x4, 0x40, 0x80))
            if rng.random() < .1:state['playing'] ^= 1
            for _ in range(rng.choice((1, 1, 2, 3, 20))):tick(word, rng.choice((0, 0x200, 0x20)))
            if requests:
                settle();break
    # The counter poke is applied to both sides between visits.
    wanted = [row for _, row in steps if row is not None]
    compare(('sound', name, seat, locks), commands+[c for c, _ in steps], wanted, exe)
    return dict(scene='sound test', case=name, seat=seat, locks=locks, snapshots=len(wanted), lyric_glyphs=state['glyphs'],
                event_kinds=sorted(seen), requests=len(requests), instructions=o.instructions)

SCRATCH_SELECTOR, SCRATCH_BITMAP, SCRATCH_GUIDE, SCRATCH_LIST, PAD = 0x1e00000, 0x1e00100, 0x1e01000, 0x1e02000, 0x1237cc8

def widget_case(spec):
    """The widget functions called directly: no scene, no coroutine."""
    exe, name, seat, seed = spec
    rng = random.Random(f'widget{name}{seat}{seed}')
    options = tuple((0x16+c, rng.randrange(2)) for c in range(49))+tuple((0x47+c, rng.randrange(2)) for c in range(49))+((0x94, seat),)
    o = Oracle(seat, options, seed=seed);p = o.p
    commands = setup(options, (), seed);expected = []
    def call(pc, *args):
        o.events = []
        value = o.run(pc, *args, observe=o.observe)
        assert all(e[0] == TONE and e[1] == -1 for e in o.events)
        return signed(value, 32), [e[2] for e in o.events]
    def pad(held, pressed, repeat):
        for i, word in enumerate((held, pressed, repeat)):p.write(PAD+12*seat+4*i, word, 4)
    def pad_words():
        k = rng.random()
        if k < .2:return 0
        if k < .7:return rng.choice((0x10, 0x20, 0x40, 0x80, 0x100000, 0x400000, 0x200000, 0x800000, 0x200, 0x2, 0x8, 0x400, 0x4))
        return rng.getrandbits(24) & 0xf80efe
    if name == 'selector':
        S = SCRATCH_SELECTOR
        for _ in range(6000):
            flags = sum(1 << b for b in (0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 17, 18) if rng.random() < (.5 if b < 3 else .15))
            lo = rng.randrange(-3, 4) if not flags & 0x800 else rng.randrange(0, 4)
            hi = lo+rng.randrange(-2, 40);step = rng.choice((0, 1, 1, 1, 2, 3));page = rng.choice((0, 0, 3, 9, 50, -1))
            cur = rng.randrange(-5, 45) if not flags & 0x800 else rng.randrange(0, 45)
            bitmap = [rng.getrandbits(32) & rng.getrandbits(32) for _ in range(2)]
            words = [pad_words(), pad_words()];words.append(words[1] | pad_words())
            p.write(S, flags, 4);p.write(S+4, SCRATCH_BITMAP, 4);p.write(S+0x14, cur, 4)
            for i, word in enumerate(bitmap):p.write(SCRATCH_BITMAP+4*i, word, 4)
            call(0x20e028, S, lo, hi, step, page);pad(*words)
            code, tones = call(0x20e128, S, seat)
            commands.append(' '.join(map(str, ['selector', flags, cur, lo, hi, step, page, *bitmap, *words])))
            expected.append([o.word(S+0x14), o.word(S+8), o.word(S+0xc), o.word(S+0x10), o.word(S+0x18), code, len(tones), *tones])
    elif name == 'guide':
        G = SCRATCH_GUIDE
        keys = sorted({p.read(0x4ee870+8*i, 1) for i in range(207)})
        def step(command, pc, *args):
            call(pc, G, *args);commands.append(command);expected.append(o.guide(G))
        for _ in range(40):
            step('g_init', 0x1822a0)
            for _ in range(60):
                k = rng.randrange(12)
                if k < 3:
                    layout = rng.randrange(-1, 15);step(f'g_layout {layout} {seat}', 0x182318, layout)
                elif k < 6:step('g_tick', 0x1825b8)
                elif k == 6:step('g_open', 0x182648)
                elif k == 7:step('g_close', 0x1826b0)
                elif k == 8:
                    key = rng.choice(keys+[0x3f, 0x90]);sub = rng.randrange(3) if key < 0x38 else 0
                    step(f'g_message {key} {sub}', 0x1827c0, key, sub)
                elif k == 9:
                    layout = rng.choice((0xb, 0xc, 0xd, 0xb, rng.randrange(-1, 16)));step(f'g_extra {layout} {seat}', 0x1827d8, layout)
                elif k == 10:step('g_extra_open', 0x1827f0)
                else:step('g_extra_close', 0x182828)
    else:
        W = SCRATCH_LIST
        def step(command, pc, *args, at=W):
            code, tones = call(pc, at, *args) if pc else (0, [])
            commands.append(command);expected.append([*o.list(W), code if pc == 0x20ee70 else 0, len(tones), *tones])
        for _ in range(60):
            step('l_init', 0x20e570)
            for bit in (15, 16):
                value = rng.randrange(2);step(f'l_flag {bit} {value}', 0x20e0a0, bit, value, at=W+0x50)
            for _ in range(70):
                k = rng.randrange(16)
                if k == 0:
                    count, visible = rng.choice((0, 1, 3, 12, 60, 0x200)), rng.choice((-1, 0, 1, 5, 9, 10, 80))
                    step(f'l_resize {count} {visible}', 0x20e5d8, count, visible)
                elif k == 1:
                    index, text = rng.choice((0, 1, 2, 5, 11, 0x1ff, 0x200, 0x250)), rng.randrange(-1, 49)
                    step(f'l_item {index} {text}', 0x20e7f8, index, p.read(0x4d4bb0+4*text, 4) if text >= 0 else 0)
                elif k == 2:
                    a = (rng.choice((-1, 3, 8, 9, 60)), rng.randrange(3), rng.randrange(2), rng.randrange(2), rng.randrange(2))
                    step('l_chars '+' '.join(map(str, a)), 0x20eae0, *a)
                elif k == 3:
                    ident = rng.randrange(-2, 80);step(f'l_select {ident}', 0x20ed70, ident)
                elif k == 4:
                    a = (rng.randrange(-400, 700), rng.randrange(0, 300), rng.randrange(-400, 700), rng.randrange(0, 300), rng.choice((1, 3, 16)))
                    step('l_panel '+' '.join(map(str, a)), 0x17f428, *a, at=W+0x1c)
                elif k == 5:step('l_open', 0x17f468, at=W+0x1c)
                elif k == 6:step('l_close', 0x17f4b0, at=W+0x1c)
                elif k == 7:
                    shown, active = rng.randrange(2), rng.randrange(2)
                    p.write(W+0x14, shown, 4);p.write(W+0x18, active, 4);step(f'l_state {shown} {active}', 0)
                else:
                    words = [pad_words(), pad_words()];words.append(words[1] | pad_words())
                    pad(*words);step('l_update '+' '.join(map(str, words)), 0x20ee70, seat)
    compare(('widget', name, seat), commands, expected, exe)
    return dict(scene='widget library', case=name, seat=seat, snapshots=len(expected), instructions=o.instructions)

ENDINGS = {'none': (), 'few': tuple((0x47+c, 1) for c in (0, 4, 11, 24, 43, 48)),
           'all': tuple((0x47+c, 1) for c in range(49))}

def ending_case(spec):
    exe, name, seat, seen, seed = spec
    rng = random.Random(f'ending{name}{seat}{seen}{seed}')
    o = Oracle(seat, ENDINGS[seen], seed=seed)
    commands = setup(ENDINGS[seen], (), seed)+['ending_scene']
    o.events = [];o.observed = {}
    o.run(0x182968, observe=o.observe)
    assert o.observed['task'][0] == 0x182ce0 and not o.events and o.p.read(0x4c3838, 4) == 1
    o.start(0x182ce0, *o.observed['task'][1:])
    expected = [[*o.chrome(), 0]]
    commands.append(f'ending_begin {seat}')
    chosen = [];requests = [];state = {'fixed': 0, 'null': False}
    def tick(own=0, other=0):
        held = (other, own) if seat else (own, other)
        row, character, events = o.ending(held)
        commands.append(f'ending {held[0]} {held[1]}')
        if row is not None:
            state['fixed'] = len(row)-1-4*len(o.events)
            expected.append(row);requests.extend(e for e in o.events if e[0] == SCENE)
            return
        if character < 0:
            # No ending seen: 182a98(-1) would call the null pointer at 4eefe4.
            # The native port ignores this confirm and finishes the visit.
            expected.append(dict(fixed=state['fixed'], chosen=0, events=events[1:], open=True));state['null'] = True
            return
        chosen.append(character)
        expected.append(dict(fixed=state['fixed'], chosen=1, events=events[1:]+[ENDING_CHOSEN, character, 0, 0], open=False))
        # Playback 182a98 is outside this slice; 182ce0 then restarts the selection.
        commands.append(f'ending_begin {seat}')
    def tap(word):tick(word);tick()
    def settle():
        for _ in range(19):tick()
    settle()
    if name == 'empty':
        tap(0x20);tap(0x10);tick(0x200)
        assert state['null'] and not chosen
    elif name == 'empty-cancel':
        tap(0x20);tap(0x404);settle();settle()
        assert requests == [(SCENE, 0x182a48, 0x1d22f8, 0)]
    elif name == 'play':
        tap(0x20);tap(0x20);tick(0x200);settle()
        for _ in range(3):tap(0x10)
        tick(0x8);settle();tap(0x400000);tick(0x2);settle();tap(0x400);settle();settle()
        assert len(chosen) == 3 and requests == [(SCENE, 0x182a48, 0x1d22f8, 0)], (chosen, requests)
    else:
        for _ in range(500):
            k = rng.random()
            word = 0 if k < .3 else rng.choice((0x10, 0x20, 0x20, 0x100000, 0x400000, 0x200000, 0x800000)) if k < .8 else rng.choice((0x200, 0x2, 0x8, 0x200, 0x400, 0x40))
            for _ in range(rng.choice((1, 1, 2, 4, 22))):
                tick(word, rng.choice((0, 0x200, 0x20)))
                if state['null']:break
            if requests or state['null']:break
        if requests:settle()
    compare(('ending', name, seat, seen), commands, expected, exe)
    return dict(scene='ending viewer', case=name, seat=seat, seen=seen, snapshots=len(expected), chosen=chosen,
                null_confirm=state['null'], requests=len(requests), instructions=o.instructions)

def main():
    cli = argparse.ArgumentParser();cli.add_argument('--only');cli.add_argument('--case');cli.add_argument('--jobs', type=int, default=6)
    args = cli.parse_args()
    assert digest(ELF) == PIN
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp)/'driver.cpp';exe = Path(tmp)/'driver'
        cpp.write_text(DRIVER)
        sources = [ROOT/'src'/n for n in ('console_gallery.cpp', 'menu_widgets.cpp', 'console_menu.cpp', 'system_data.cpp', 'game_random.cpp')]
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp, *sources, '-o', exe], check=True)
        jobs = []
        jobs += [(top_case, (exe, name, seat, 3+seat)) for name in ('rows', 'cancel', 'repeat', 'both', 'random') for seat in range(2)]
        jobs += [(pictures_case, (exe, name, seat, locks, 5+seat)) for name, locks in
                 (('browse', 'factory'), ('view', 'unlocked'), ('random', 'sparse'), ('random', 'factory')) for seat in range(2)]
        jobs += [(sound_case, (exe, name, seat, locks, 8+seat)) for name, locks in
                 (('bgm', 'factory'), ('voice', 'unlocked'), ('voice', 'sparse'), ('narration', 'factory'), ('random', 'factory'), ('random', 'unlocked'))
                 for seat in range(2)]
        jobs += [(ending_case, (exe, name, seat, seen, 20+seat)) for name, seen in
                 (('empty', 'none'), ('empty-cancel', 'none'), ('play', 'few'), ('play', 'all'), ('random', 'few'), ('random', 'all'))
                 for seat in range(2)]
        jobs += [(widget_case, (exe, name, seat, 30+seat)) for name in ('selector', 'guide', 'list') for seat in range(2)]
        if args.only:jobs = [j for j in jobs if j[0].__name__.startswith(args.only)]
        if args.case:jobs = [j for j in jobs if j[1][1] == args.case]
        with ProcessPoolExecutor(args.jobs) as pool:
            futures = [pool.submit(fn, spec) for fn, spec in jobs]
            cases = [f.result() for f in futures]
    total = sum(c['snapshots'] for c in cases);instructions = sum(c['instructions'] for c in cases)
    if not args.only and not args.case:
        REPORT.write_text(json.dumps(dict(status='passed', elf_sha256=PIN, cases=cases, snapshots=total, instructions=instructions,
            assets={n: hashlib.sha256((ASSETS/n).read_bytes()).hexdigest() for n in ('menu_widgets.bin', 'console_gallery.bin')},
            scope=SCOPE), indent=2)+'\n')
    print(len(cases), 'EE/native gallery traces;', total, 'snapshots;', instructions, 'instructions')

SCOPE = ('Japanese SLPS-25559, game mode 13, both operating seats. Top menu: whole entry 1d22f8 and task 1d2380 per visit with '
         '117fd8 pad sampling. Illustration viewer 13ed98/13edf0, sound test 13e090/13e0e8 and ending viewer 182968/182ce0/13f4a8: '
         'whole scene entries and coroutine bodies; the tasks are PS2 kernel threads, so the validator keeps the thread register '
         'file itself, runs the body on its own stack up to the yield entry 112a28 and resumes at the saved return address. Every '
         'visit compares the scene locals, the complete guide-window and list-widget structures (slide panels, selector, item '
         'texts), the shared menu counters, the library RNG seed and the ordered request list. Widget library additionally called '
         'directly: 20e028/20e128 over random flags, ranges, disabled bitmaps and pad words; 1822a0..182828 over layouts -1..15; '
         '20e570..20ee70 with all three text styles. Stubbed (jr ra): rendering leaves 113f98 1145c0 1147d8 10a460 10a568 10a710 '
         '10a1c0 109f08 1135e8, texture/palette loads 1142d8 1163c0 116478 10add8 112f30 17eda0, menu background draw 1ce570 '
         '1ce628 and its overlay effect 1e1620 1e2358 1e23a0 1e2408, ending object reset 182858 1828c0 120110; sound driver '
         'entries 1e7b70 1e7ba0 1e79c8 1e7d60 1e7ad0 1e7b40 1e8298 213180 213238 (arguments compared; 214060 runs); debug prints '
         '316140 316218; thread creation 100e58; scene switch 1252f0 (arguments compared). The stream word 5a9e6c is driven by '
         'the fixture; the lyric counter is poked on both sides to sample the colour ramps and the wrap. The ending engine 182a98 '
         'is not entered: the visit stops at its call and resumes after it. With no ending seen the original reaches 182a98(-1), '
         'a null call; the native port ignores that confirm.')

if __name__ == '__main__':main()
