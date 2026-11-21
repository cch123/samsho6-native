#!/usr/bin/env python3
"""Replay-driven check of the menu scenes reachable from the mode menu.

SPIRITS EDIT, COLOR EDIT, GALLERY (top, illustrations, sound test, ending selection) and
OPTION -> KEY CONFIGURATION are entered through the title of the shipping programs
(ss6-match-replay --scene-fields for state, ss6-viewer --dump for the rasterised frame).
Each session performs an edit, leaves, and is checked for: the scene sequence, the save image
bytes that changed, the file written by AUTO SAVE, the return to the mode menu on the row that
started the scene, and - at fixed ticks - equality of the rendered frame with the frame the
validated logic and art modules produce in an independent driver fed with the same pads, the
same library generator state and the same save image.

The logic and the drawing themselves are compared with SLPS-25559 by validate_spirits_edit.py,
validate_color_edit.py, validate_console_gallery.py, validate_edit_art.py,
validate_gallery_art.py, validate_pause_menu.py and validate_pause_art.py; this file covers the
scene wiring of src/native_match_menus.cpp only."""
import argparse
import json
import shutil
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
REPORT = ROOT/'outputs/ss6-feasibility/menu_scenes_validation.json'
ENV = {'SDL_VIDEO_DRIVER': 'dummy', 'SDL_RENDER_DRIVER': 'software', 'SDL_AUDIO_DRIVER': 'dummy', 'PATH': '/usr/bin:/bin'}

# Logical pad bits (src/native_match.hpp BattleButton).
UP, DOWN, LEFT, RIGHT, START = 0x10, 0x20, 0x40, 0x80, 8
SQUARE, TRIANGLE, CIRCLE, CROSS, R1, R2, L1, L2 = (0x100 << i for i in range(8))
SELECT = 0x10000
CONFIRM, CANCEL = TRIANGLE, CROSS
# NativeMatch::MenuScene
NONE, OPTION, KEYS, SPIRITS, COLOR, G_TOP, G_PICTURES, G_SOUND, G_ENDING = range(9)
# --scene-fields columns
C_SCENE, C_TITLE, C_MENU, C_ROW, C_MODE, C_SUB, C_FADE, C_SEED, C_EDIT, C_SPIRIT, C_KEYS, C_AUTO, C_COUNT, C_W0 = range(23, 37)
C_MASKS = 40
C_ENTRY_SEED = 56
C_RUNTIME = 57
C_SELECT = 59

DEBUG = False
DRIVER = r'''
#include "edit_art.hpp"
#include "gallery_art.hpp"
#include "pause_art.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <sstream>
using namespace ss6;
static uint32_t physical(uint32_t logical){
    static constexpr uint32_t buttons[8]={0x400,0x200,2,4,0x400000,0x800000,0x100000,0x200000};
    uint32_t bits=logical&0xf8;
    if(logical&0x10000)bits|=0x80000;
    for(unsigned i=0;i<8;++i)if(logical&(0x100u<<i))bits|=buttons[i];
    return bits;
}
int main(int,char** argv){
    const std::string assets=argv[1];
    if(argv[2]){
        // A card file of the factory image with AUTO SAVE on (10f158 writes only then).
        SystemData card(assets);card.setAutoSave(1);card.save(argv[2]);return 0;
    }
    SystemData system(assets);system.option(0x7e)=1;system.markEndingSeen(0);
    MenuCanvas canvas(assets);EditArt edit(assets,canvas);GalleryArt gallery(canvas,assets);PauseArt pause(canvas,gallery,assets);
    MenuWidgetData widgets(assets);EditWidgetAssets editWidgets(assets);SpiritsEditAssets spiritAssets(assets);
    ColorEditTables tables(assets);GalleryData data(assets);KeyConfigAssets keyAssets(assets);
    std::ifstream palFile(assets+"/pal_all.bin",std::ios::binary);
    std::vector<uint8_t> pal((std::istreambuf_iterator<char>(palFile)),std::istreambuf_iterator<char>());
    GameRandom random;MenuBackdrop backdrop;MenuDrawList list;MenuPadRepeat repeat;SceneFade fade;EditPen pen;MenuChrome chrome;
    std::unique_ptr<SpiritsEdit> spirits;std::unique_ptr<EditFrame> frame;
    std::unique_ptr<EditPaletteBank> bank;std::unique_ptr<ColorEdit> color;
    GalleryTopMenu top;std::unique_ptr<IllustrationViewer> pictures;std::unique_ptr<SoundTest> sound;std::unique_ptr<EndingViewer> ending;
    KeyConfigWindow keys;PauseWindowContext context;
    enum Scene {None,Spirits,Color,Top,Pictures,Sound,Ending,Keys} scene=None;
    unsigned seat=0;int mode=0,titleTick=0,music=-1;uint32_t pending=0;bool reselect=false;
    std::array<uint32_t,2> last{};
    const auto galleryScene=[&](uint32_t next){
        const uint64_t seed=random.librarySeed;
        pictures.reset();sound.reset();ending.reset();
        if(next==uint32_t(GalleryScene::TopMenu)){top.enter(data,chrome,random);scene=Top;}
        else if(next==uint32_t(GalleryScene::Illustrations)){
            gallery.forget();pictures=std::make_unique<IllustrationViewer>();
            pictures->enter(unsigned(top.operatingSeat),system,widgets,data,chrome,random);scene=Pictures;
        } else if(next==uint32_t(GalleryScene::SoundTest)){
            sound=std::make_unique<SoundTest>();sound->enter(unsigned(top.operatingSeat),system,widgets,data,chrome,random);scene=Sound;
        } else {
            ending=std::make_unique<EndingViewer>();ending->enterScene(data,chrome,random);
            enterGalleryBackdrop(backdrop,chrome,random,seed);
            const uint64_t second=random.librarySeed;
            ending->beginSelection(unsigned(top.operatingSeat),system,widgets,chrome,random);
            enterGalleryBackdrop(backdrop,chrome,random,second);
            reselect=false;scene=Ending;return;
        }
        enterGalleryBackdrop(backdrop,chrome,random,seed);
    };
    const auto events=[&](const std::vector<GalleryEvent>& all){
        for(const auto& e:all){
            if(e.kind==GalleryEvent::Scene&&!fade.active()){pending=uint32_t(e.b);fade.begin(true);}
            else if(e.kind==GalleryEvent::EndingChosen)reselect=true;
            else if(e.kind==GalleryEvent::Music)music=0; // every track streams since music_streams.bin
            else if(e.kind==GalleryEvent::MusicStop)music=-1;
        }
    };
    std::string line,op;
    while(std::getline(std::cin,line)){
        std::istringstream in(line);in>>op;
        if(op=="seed"){unsigned long long v;in>>v;random.librarySeed=v;}
        else if(op=="enter"){
            // fromTitle: the white fade of the mode menu is at its midpoint (visit 15).
            std::string name;int fromTitle;in>>name>>seat>>mode>>fromTitle;
            titleTick=fromTitle?15:0;list=MenuDrawList();pending=0;
            if(name=="spirits"){
                const uint64_t seed=random.librarySeed;
                spirits=std::make_unique<SpiritsEdit>(system,spiritAssets,editWidgets,random);
                enterGalleryBackdrop(backdrop,spirits->chrome,random,seed);
                frame=std::make_unique<EditFrame>(edit.assets(),editWidgets,seat);
                pen=EditPen();pen.colour=edit.assets().initialTextColour;scene=Spirits;
            } else if(name=="color"){
                chrome=MenuChrome();chrome.enter(backdrop.enter(random));
                bank=std::make_unique<EditPaletteBank>(tables,system,pal);
                color=std::make_unique<ColorEdit>(tables,system,pal,*bank);
                frame=std::make_unique<EditFrame>(edit.assets(),editWidgets,seat);
                pen=EditPen();pen.colour=edit.assets().initialTextColour;scene=Color;
            } else if(name=="gallery"){
                gallery.gameMode=mode;gallery.extraIcons=system.option(0x7e)!=0;top.reset();music=-1;
                galleryScene(uint32_t(GalleryScene::TopMenu));
            } else if(name=="keys"){
                // Entered at the midpoint of the OPTION page's own 1252f0 request.
                fade=SceneFade();fade.begin(true);while(!fade.tick()){}
                seat=KeyConfigWindow::operatingSeat(unsigned(mode),0,0);
                keys=KeyConfigWindow{};keys.start(widgets,seat);
                chrome=MenuChrome();chrome.enter(backdrop.enter(random));
                context.gameMode=unsigned(mode);context.seat=seat;scene=Keys;
            } else return 3;
        } else if(op=="tick"){
            std::array<uint32_t,2> logical{};in>>logical[0]>>logical[1];
            const std::array<uint32_t,2> held{physical(logical[0]),physical(logical[1])};
            if(titleTick&&++titleTick>=27)titleTick=0;
            const auto pads=repeat.sample(held,{held[0]&~last[0],held[1]&~last[1]});last=held;
            const auto widgetPad=[&](unsigned i){return WidgetPad{held[i],pads[i].pressed,pads[i].repeat};};
            const auto applyFade=[&]{
                bool enabled=fade.active();int level=fade.level();
                if(!enabled&&titleTick){enabled=true;level=titleTick<=15?std::min(256,(titleTick-1)*25):std::max(0,256-(titleTick-16)*25);}
                canvas.setBrightness(system.brightness());pause.setBrightness(system.brightness());
                canvas.setFade(enabled,level,0xffffffffu);edit.setFade(enabled,level,0xffffffffu);gallery.setFade(enabled,level,0xffffffffu);
            };
            bool leave=false;
            switch(scene){
            case Spirits:{
                frame->tick();const auto r=spirits->tick(pads[seat]);frame->follow(*spirits);
                applyFade();list.beginFrame();
                drawSpiritsEdit(edit,list,pen,*spirits,*frame,seat,system.option(0x7e)!=0);
                leave=r.exitToTitle;break;
            }
            case Color:
                bank->beginFrame();frame->tick();
                for(const auto& e:color->tick({held[seat],pads[seat].pressed,pads[seat].repeat})){frame->apply(e);if(e.kind==ColorEditEvent::SceneSwitch)leave=true;}
                applyFade();list.beginFrame();
                drawColorEdit(edit,list,pen,*color,tables,*frame,editWidgets,seat,system.option(0x7e)!=0);
                break;
            case Top:{
                applyFade();list.beginFrame();
                const MenuChrome before=chrome;top.tick(data,chrome,pads);gallery.seat=unsigned(top.operatingSeat);
                gallery.drawGalleryTop(list,backdrop,random,before,top,data);events(top.events);break;
            }
            case Pictures:
                applyFade();list.beginFrame();pictures->tick(widgetPad(pictures->seat));
                gallery.drawIllustrationViewer(list,backdrop,random,chrome,*pictures);events(pictures->events);break;
            case Sound:
                applyFade();list.beginFrame();
                if(music>=0&&music<18)++music;
                sound->tick(widgetPad(sound->seat),music>=18);
                gallery.drawSoundTest(list,backdrop,random,chrome,*sound,data);events(sound->events);break;
            case Ending:
                applyFade();
                if(reselect){
                    const uint64_t seed=random.librarySeed;
                    ending->beginSelection(unsigned(top.operatingSeat),system,widgets,chrome,random);
                    enterGalleryBackdrop(backdrop,chrome,random,seed);reselect=false;
                }
                ending->tick(widgetPad(ending->seat));
                if(!ending->chosen){list.beginFrame();gallery.drawEndingSelect(list,backdrop,random,chrome,*ending);}
                events(ending->events);break;
            case Keys:{
                std::vector<int> tones;
                keys.tick({widgetPad(0),widgetPad(1)},system,keyAssets,true,tones);
                applyFade();list.beginFrame();context.unlocks=SkillUnlocks(system);
                pause.drawKeyConfig(list,keyAssets,keys,system,context,backdrop,random,chrome);break;
            }
            default:return 4;
            }
            if(leave&&!fade.active())fade.begin(true);
            if(fade.tick()&&pending&&scene>=Top&&scene<=Ending&&pending!=uint32_t(GalleryScene::Title)){
                const uint32_t next=pending;pending=0;galleryScene(next);
            }
        } else if(op=="dump"){
            std::string path;in>>path;
            std::vector<uint8_t> rgba(640*480*4);
            for(size_t i=3;i<rgba.size();i+=4)rgba[i]=255;
            if(scene==Spirits||scene==Color)edit.rasterise(list,rgba);
            else if(scene==Keys)pause.rasterise(list,rgba);
            else gallery.rasterise(list,rgba);
            for(size_t i=3;i<rgba.size();i+=4)rgba[i]=255;
            std::ofstream out(path,std::ios::binary);out.write(reinterpret_cast<const char*>(rgba.data()),std::streamsize(rgba.size()));
            std::cout<<list.records.size()<<std::endl;
        } else return 5;
    }
}
'''
DRIVER_SOURCES = ['edit_art', 'gallery_art', 'pause_art', 'menu_canvas', 'console_menu', 'system_data', 'spirits_edit',
                  'edit_widgets', 'color_edit', 'console_gallery', 'menu_widgets', 'key_config', 'skill_list', 'pause_menu',
                  'scalar_float', 'game_random', 'soft_double']


def tap(bits, gap=8, seat=0):
    pad = (bits, 0) if seat == 0 else (0, bits)
    return [pad] + [(0, 0)]*gap


def wait(n):
    return [(0, 0)]*n


class Session:
    def __init__(self, build, tmp):
        self.replay = build/'ss6-match-replay'
        self.viewer = build/'ss6-viewer'
        self.tmp = Path(tmp)
        self.frames = 0
        self.ticks = 0

    def rows(self, pads, save=None):
        text = ''.join(f'1 {a} {b}\n' for a, b in pads)
        args = [self.replay, ASSETS, '--mode', 'title', '--unlock-all', '--scene-fields']
        if save:
            args += ['--save', save]
        out = subprocess.run(args, input=text, capture_output=True, text=True, check=True).stdout.splitlines()
        assert len(out) == len(pads), (len(out), len(pads))
        self.ticks += len(pads)
        return [line.split() for line in out]

    def frame(self, pads):
        replay = self.tmp/'replay.txt'
        replay.write_text(''.join(f'1 {a} {b}\n' for a, b in pads))
        out = self.tmp/'frame.rgba'
        subprocess.run([self.viewer, '--assets', ASSETS, '--mode', 'title', '--unlock-modes', 'yes', '--match-replay', replay,
                        '--dump', out], check=True, env=ENV, capture_output=True)
        raw = out.read_bytes()
        assert struct.unpack('<II', raw[:8]) == (640, 480)
        return raw[8:]


def num(row, col):
    return int(row[col])


def to_mode_menu():
    return wait(40) + tap(START, 40)


def find_rows(s):
    """Mode-menu cursor steps for each scene the menu can enter directly."""
    found = {}
    for steps in range(9):
        pads = to_mode_menu()
        for _ in range(steps):
            pads += tap(DOWN, 20)
        before = len(pads)
        pads += tap(CONFIRM, 40)
        rows = s.rows(pads)
        scene = num(rows[-1], C_SCENE)
        if scene != NONE and scene not in found:
            found[scene] = (steps, num(rows[before-1], C_ROW))
    return found


def entry_tick(rows, scene, start=0):
    """First tick (row index) at which `scene` is the running menu scene."""
    return next(i for i in range(start, len(rows)) if num(rows[i], C_SCENE) == scene)


def menu_path(found, scene):
    steps, row = found[scene]
    pads = to_mode_menu()
    for _ in range(steps):
        pads += tap(DOWN, 20)
    return pads, row


class Driver:
    def __init__(self, exe, tmp):
        self.p = subprocess.Popen([exe, ASSETS], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.tmp = Path(tmp)

    def send(self, line):
        self.p.stdin.write(line+'\n')

    def dump(self):
        out = self.tmp/'driver.rgba'
        self.send(f'dump {out}')
        self.p.stdin.flush()
        count = int(self.p.stdout.readline())
        return out.read_bytes(), count

    def close(self):
        self.p.stdin.close()
        assert self.p.wait() == 0, self.p.returncode


def compare_frames(s, exe, pads, rows, entry, name, seat, mode, from_title, points, counters):
    """Frames of the session at `points` (ticks after `entry`) against the driver."""
    seed = num(rows[entry], C_ENTRY_SEED)
    d = Driver(exe, s.tmp)
    d.send(f'seed {seed}')
    d.send(f'enter {name} {seat} {mode} {int(from_title)}')
    at = entry + 1
    for point in sorted(points):
        while at <= entry + point:
            d.send(f'tick {pads[at][0]} {pads[at][1]}')
            at += 1
        expected, count = d.dump()
        assert count == num(rows[entry+point], C_COUNT), (name, point, count, rows[entry+point][C_COUNT])
        actual = s.frame(pads[:entry+point+1])
        if actual != expected:
            bad = sum(actual[i:i+4] != expected[i:i+4] for i in range(0, len(actual), 4))
            raise AssertionError(f'{name}: frame at tick {point} after entry differs in {bad} pixels')
        assert any(expected[i] or expected[i+1] or expected[i+2] for i in range(0, len(expected), 4096)), 'empty frame'
        counters['frames'] += 1
        counters['submissions'] += count
    d.close()


def image_of(path):
    raw = Path(path).read_bytes()
    assert len(raw) == 0x6800
    return raw[:0x65a8]


def check_returned(rows, row, label):
    last = rows[-1]
    assert num(last, C_SCENE) == NONE and last[C_TITLE] == '1' and last[C_MENU] == '1', (label, last[23:36])
    assert num(last, C_ROW) == row, (label, 'row', last[C_ROW], row)
    assert num(last, C_MODE) == 4, (label, 'mode word', last[C_MODE])


def spirits_session(s, exe, found, factory, counters):
    pads, row = menu_path(found, SPIRITS)
    pads += tap(CONFIRM, 40)
    pads += tap(CONFIRM, 30)            # slot 1 -> editor (state 8)
    pads += tap(DOWN, 8)                # second category
    pads += tap(CONFIRM, 20)            # its option list
    pads += tap(UP, 8) + tap(CONFIRM, 20)     # a cheaper option (a dearer one is refused by the point budget)
    edited = len(pads)
    pads += tap(CANCEL, 30)             # back to the slot list (commit)
    pads += tap(CANCEL, 30) + wait(60)  # leave: auto save, white fade, mode menu
    save = s.tmp/'spirits.sav'
    shutil.copy(s.tmp/'base.sav', save)
    rows = s.rows(pads, save)
    entry = entry_tick(rows, SPIRITS)
    assert num(rows[entry], C_MODE) == 0xf and num(rows[entry], C_SUB) == 0
    assert num(rows[edited], C_W0) == 8, ('editor state', rows[edited][C_W0:C_W0+4])
    assert rows[edited][C_SPIRIT] != rows[entry][C_SPIRIT], 'the spirit records did not change'
    assert rows[-1][C_EDIT] == rows[entry][C_EDIT] and rows[-1][C_KEYS] == rows[entry][C_KEYS]
    check_returned(rows, row, 'spirits')
    assert rows[entry][C_AUTO] == '1'
    image = image_of(save)
    changed = [i for i in range(len(image)) if image[i] != factory[i]]
    # Unlock bytes of this session (option 7e, ending 0) and record 0 of 4d7068.
    allowed = {0x618c+0x7e, 0x618c+0x47}
    assert changed and all(i in allowed or 0x633c <= i < 0x633c+16 for i in changed), [hex(i) for i in changed]
    assert any(0x633c <= i < 0x633c+16 for i in changed)
    compare_frames(s, exe, pads, rows, entry, 'spirits', 0, 0xf, True, [4, 20, 60, edited-entry], counters)
    return {'ticks': len(pads), 'changed_bytes': [hex(i) for i in changed if i not in allowed]}


def color_session(s, exe, found, factory, counters):
    pads, row = menu_path(found, COLOR)
    pads += tap(CONFIRM, 40)
    pads += tap(DOWN, 8)                # second fighter of the list
    pads += tap(CONFIRM, 30)            # colour number list
    pads += tap(CONFIRM, 30)            # part selector
    pads += tap(CONFIRM, 30)            # swatch row
    pads += tap(RIGHT, 8) + tap(CONFIRM, 30)   # second swatch -> sliders
    slider = len(pads)
    for _ in range(6):
        pads += tap(LEFT, 4)            # red channel down
    pads += tap(CONFIRM, 30)            # accept
    edited = len(pads)
    for _ in range(4):
        pads += tap(CANCEL, 30)
    pads += wait(70)
    left = len(pads)-1
    # VS MODE from the mode menu: the card task copies the saved edit block to both runtime tables.
    for _ in range(row):
        pads += tap(UP, 20)
    pads += tap(CONFIRM, 40)
    save = s.tmp/'color.sav'
    shutil.copy(s.tmp/'base.sav', save)
    rows = s.rows(pads, save)
    entry = entry_tick(rows, COLOR)
    assert num(rows[entry], C_MODE) == 0xf and num(rows[entry], C_SUB) == 0
    character = num(rows[edited], C_W0+1)
    assert character == 1, ('second list row is Nakoruru', character)
    assert rows[slider][C_W0+3] != rows[edited][C_W0+3], 'the slider word did not change'
    assert rows[edited][C_EDIT] != rows[entry][C_EDIT], 'the edit block did not change'
    assert rows[-1][C_SPIRIT] == rows[entry][C_SPIRIT] and rows[-1][C_KEYS] == rows[entry][C_KEYS]
    check_returned(rows[:left+1], row, 'color')
    image = image_of(save)
    assert rows[-1][C_SELECT] == '1' and num(rows[-1], C_SUB) == 2, rows[-1][C_SELECT]
    stored = zlib.crc32(image[4:4+0x6180])
    assert stored != zlib.crc32(factory[4:4+0x6180])
    assert [num(rows[left], C_RUNTIME+i) for i in range(2)] == [zlib.crc32(factory[4:4+0x6180])]*2, 'runtime tables before VS'
    assert [num(rows[-1], C_RUNTIME+i) for i in range(2)] == [stored]*2, 'runtime tables after the VS card read'
    # edit_pal_tbl: fighter 1, colour 0: 0x30 words from image + 4 + (1*5 + 0)*0x60.
    lo = 4 + (character*5)*0x60
    changed = [i for i in range(4, 4+0x6180) if image[i] != factory[i]]
    assert changed and all(lo <= i < lo+0x60 for i in changed), [hex(i) for i in changed]
    # The edited entry is swatch 2 of stored bank 0 (entry 0 is never edited); 115f08 also clears entry 0.
    words = {(i-lo)//2 for i in changed}
    assert 2 in words and words <= {0, 2, 16, 32}, sorted(words)
    value = struct.unpack_from('<H', image, lo+4)[0]
    assert value & 0x8000 and (value >> 10 & 31) == num(rows[edited], C_W0+3) >> 19 & 31
    compare_frames(s, exe, pads, rows, entry, 'color', 0, 0xf, True, [4, 20, 70, slider-entry, edited-entry], counters)
    return {'ticks': len(pads), 'edited_word': hex(value), 'changed_words': sorted(words)}


def gallery_session(s, exe, found, counters):
    pads, row = menu_path(found, G_TOP)
    pads += tap(CONFIRM, 50)
    marks = {}
    # Illustrations (row 2): open the first picture, zoom, leave.
    pads += tap(DOWN, 8) + tap(DOWN, 8) + tap(CONFIRM, 60)
    pads += tap(DOWN, 8) + tap(CONFIRM, 30)
    marks['picture'] = len(pads)-1
    pads += [(R1, 0)]*10 + wait(6)
    marks['zoom'] = len(pads)-1
    pads += tap(CANCEL, 30) + tap(CANCEL, 70)
    marks['top_after_pictures'] = len(pads)-1
    # Sound test (row 1): BGM category, original version, first track.
    pads += tap(UP, 8) + tap(CONFIRM, 60)
    pads += tap(CONFIRM, 30) + tap(CONFIRM, 30) + tap(DOWN, 8) + tap(CONFIRM, 30)
    marks['sound'] = len(pads)-1
    pads += tap(CANCEL, 30) + tap(CANCEL, 30) + tap(CANCEL, 30) + wait(60)
    marks['top_after_sound'] = len(pads)-1
    # Ending selection (row 0): choosing an ending plays it (182a98); CANCEL (404) leaves the
    # playback back to the list, a second CANCEL leaves the list.
    pads += tap(UP, 8) + tap(CONFIRM, 70)
    marks['ending'] = len(pads)-1
    pads += tap(CONFIRM, 40) + tap(CANCEL, 40)
    marks['ending_again'] = len(pads)-1
    pads += tap(CANCEL, 80)
    # EXIT (row 3).
    pads += tap(UP, 8) + tap(CONFIRM, 80)
    rows = s.rows(pads)
    entry = entry_tick(rows, G_TOP)
    assert num(rows[entry], C_MODE) == 0xd and num(rows[entry], C_SUB) == 0
    scenes = []
    for r in rows[entry:]:
        scene = num(r, C_SCENE)
        if not scenes or scenes[-1] != scene:
            scenes.append(scene)
    if DEBUG:
        for k, i in marks.items():
            print(k, rows[i][C_SCENE], rows[i][C_W0:C_W0+2])
    assert scenes == [G_TOP, G_PICTURES, G_TOP, G_SOUND, G_TOP, G_ENDING, G_TOP, NONE], scenes
    assert num(rows[marks['picture']], C_W0+1) == 1, 'second picture row'
    assert num(rows[marks['top_after_pictures']], C_W0) == 2, 'the top row survives the sub-scene'
    assert num(rows[marks['top_after_sound']], C_W0) == 1
    assert num(rows[marks['ending']], C_SCENE) == G_ENDING and num(rows[marks['ending_again']], C_SCENE) == G_ENDING
    for column in (C_EDIT, C_SPIRIT, C_KEYS):
        assert rows[-1][column] == rows[entry][column]
    check_returned(rows, row, 'gallery')
    # The list after a played ending is not compared: its record count differs from the
    # original there (open item of the gallery ending integration).
    points = [4, 30] + [marks[k]-entry for k in ('picture', 'zoom', 'top_after_pictures', 'sound', 'ending')]
    compare_frames(s, exe, pads, rows, entry, 'gallery', 0, 0xd, True, points, counters)
    return {'ticks': len(pads), 'scenes': scenes}


def keys_session(s, exe, found, factory, counters):
    pads, row = menu_path(found, OPTION)
    pads += tap(CONFIRM, 50)
    pads += tap(DOWN, 8) + tap(CONFIRM, 50)     # KEY CONFIGURATION
    opened = len(pads)
    pads += tap(DOWN, 8)                        # MIDDLE
    pads += tap(CROSS, 20)                      # a button pressed on a slot row is assigned to it
    # Seat 1 assigns R1 to LIGHT with its own cursor.
    pads += tap(R1, 20, 1)
    edited = len(pads)
    pads += tap(SELECT, 60)                     # leave: back to the OPTION top page
    back = len(pads)
    pads += tap(CANCEL, 70)                     # OPTION -> mode menu
    # SPIRITS EDIT, entered and left unchanged: its exit runs the auto save that stores the masks.
    steps = found[SPIRITS][0]-found[OPTION][0]
    for _ in range(steps % 9):
        pads += tap(DOWN, 20)
    pads += tap(CONFIRM, 40) + tap(CANCEL, 30) + wait(60)
    save = s.tmp/'keys.sav'
    shutil.copy(s.tmp/'base.sav', save)
    rows = s.rows(pads, save)
    entry = entry_tick(rows, KEYS)
    assert num(rows[entry-1], C_SCENE) == OPTION and num(rows[entry], C_MODE) == 0x11
    first = [num(rows[entry], C_MASKS+i) for i in range(16)]
    assert first == [0x100 << i for i in range(8)]*2, first
    masks = [num(rows[edited], C_MASKS+i) for i in range(16)]
    # 178d50: the slot that held the mask takes the old content of the assigned slot.
    assert masks[:8] == [SQUARE, CROSS, CIRCLE, TRIANGLE, R1, R2, L1, L2], [hex(m) for m in masks[:8]]
    assert masks[8:] == [R1, TRIANGLE, CIRCLE, CROSS, SQUARE, R2, L1, L2], [hex(m) for m in masks[8:]]
    assert rows[edited][C_KEYS] != rows[entry][C_KEYS]
    assert num(rows[back], C_SCENE) == OPTION, rows[back][C_SCENE]
    assert num(rows[-1], C_SCENE) == NONE and rows[-1][C_MENU] == '1'
    image = image_of(save)
    words = struct.unpack_from('<16I', image, 0x63bc)
    assert words[:8] == (0x400, 4, 2, 0x200, 0x400000, 0x800000, 0x100000, 0x200000), [hex(w) for w in words]
    assert words[8:] == (0x400000, 0x200, 2, 4, 0x400, 0x800000, 0x100000, 0x200000), [hex(w) for w in words]
    # A fight built from that file (NativeMatch constructor) maps the buttons the same way.
    fight = subprocess.run([s.replay, ASSETS, '--mode', 'versus', '--save', save, '--scene-fields'], input='1 0 0\n',
                           capture_output=True, text=True, check=True).stdout.split()
    assert [int(fight[C_MASKS+i]) for i in range(16)] == masks
    compare_frames(s, exe, pads, rows, entry, 'keys', 0, 0x11, False, [3, 30, edited-entry], counters)
    return {'ticks': len(pads), 'masks': [hex(w) for w in words]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', default=str(ROOT/'work/ss6/build-native'))
    args = parser.parse_args()
    build = Path(args.build)
    counters = {'frames': 0, 'submissions': 0}
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp)/'driver'
        (Path(tmp)/'driver.cpp').write_text(DRIVER)
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', Path(tmp)/'driver.cpp',
                        *[ROOT/'src'/f'{name}.cpp' for name in DRIVER_SOURCES], '-o', exe], check=True)
        s = Session(build, tmp)
        subprocess.run([exe, ASSETS, s.tmp/'base.sav'], check=True)
        factory = image_of(s.tmp/'base.sav')
        assert factory[4:] == (ASSETS/'save_default.bin').read_bytes()[4:] and factory[:4] == b'\x01\0\0\0'
        found = find_rows(s)
        for scene in (OPTION, SPIRITS, COLOR, G_TOP):
            assert scene in found, ('mode menu row missing', scene, found)
        report = {
            'spirits_edit': spirits_session(s, exe, found, factory, counters),
            'color_edit': color_session(s, exe, found, factory, counters),
            'gallery': gallery_session(s, exe, found, counters),
            'key_configuration': keys_session(s, exe, found, factory, counters),
        }
    report.update(passed=True, session_ticks=s.ticks, identical_frames=counters['frames'],
                  submissions_in_compared_frames=counters['submissions'], build=str(build.name),
                  scope='Scene wiring only: mode-menu entry, pad routing, fades, save image and file, return row, '
                        'and frame equality with an independent driver of the validated logic/art modules. '
                        'No original instructions are executed here. Not covered: audio routing, the COLOR EDIT '
                        'preview objects (not drawn), ending playback 182a98 (not ported).')
    REPORT.write_text(json.dumps(report, indent=1)+'\n')
    print(f"PASS menu scenes: {s.ticks} session ticks, {counters['frames']} identical frames, "
          f"{counters['submissions']} submissions")


if __name__ == '__main__':
    main()
