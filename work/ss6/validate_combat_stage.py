#!/usr/bin/env python3
"""Compare the stage drawn by a live versus replay with the Japanese stage-zero callback."""
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile

import numpy as np
from PIL import Image

from character_tiles_oracle import ASSETS, ROOT
from extract_collision_tables import SOURCE_HASH
from extract_versus_draw_stage import capture, prepare
from validate_versus_draw_stage import render
import validate_jump_light_presentation as hurt
import validate_native_scene as actors

OUT = ROOT / 'outputs/ss6-feasibility'
PACKAGE = OUT / 'native-viewer'
LIB = ROOT / 'work/ss6/build-native/libss6-runtime.a'
PROJECTION = (0x4a2a58, 0x4a2a5c, 0x4a2a60, 0x4a2a6c, 0x4a2a68)


class SourceStage:
    number = 0
    def __init__(self):
        assert hashlib.sha256((ASSETS.parent / 'SLPS_255.59').read_bytes()).hexdigest() == SOURCE_HASH
        self.p = prepare()
        self.cache = {}
        self.rows = [0x513138 + 72 * i for i in range(23)
                     if self.p.read(0x513138 + 72 * i + 4, 4) & 0x100]
        assert len(self.rows) == 7
        self.states = [self.p.read(self.p.read(row + 0x28, 4), 4) for row in self.rows]

    def layers(self):
        return [tuple(self.p.read(state + n, 4) for n in (0, 4, 0x2c)) for state in self.states]

    def visit(self, delta, projection_words, draw=False):
        p = self.p
        p.write(0x46a908, delta, 4)
        for address, word in zip(PROJECTION, projection_words, strict=True):
            p.write(address, word, 4)
        if draw:
            return capture(p)
        # Intermediate visits need the seven persistent clocks. Execute the
        # original compare, carry/loop, picture selection and delta addition
        # on each record. Sampled frames always run the complete callback.
        for row in self.rows:
            p.registers[16] = row
            p.run(0x1a7ce8, stop_before=[0x1a7d38])

    def rgba(self, frame, tones, height=448):
        # The GPU palette upload follows scene tasks. Sample colors using the
        # final palette state of this tick and the earlier queued geometry.
        key = tuple(tones)
        if key not in self.cache:
            assert len(key) == 512
            p = self.p
            start = 0x3ebf30 + 512 * 2
            p.memory[start:start + 1024] = struct.pack('<512H', *key)
            textures = {}
            for i in range(4):
                if i in (0, 2):
                    dest = 512 if i == 0 else 768
                    palette = (ASSETS / f'bg{self.number:02}_{i+1}.pal').read_bytes()
                    scratch = 0x1410000
                    p.memory[scratch:scratch + len(palette)] = palette
                    p.write(scratch, 0, 2)  # The stage loader clears entry zero before transfer.
                    p.write(0x439b68, 0, 4)
                    p.run(0x116478, [dest, 256, scratch], limit=150000)
                    p.run(0x116588, limit=350000)
                    clut = np.frombuffer(p.memory, np.uint8, 1024, 0x11e7980 + 4 * dest).reshape(256, 4).copy()
                    if not any(key):
                        assert np.count_nonzero(clut[:, 0] != clut[:, 2]) > 100
                size = 1024 if i < 2 else 512
                tex = np.frombuffer((ASSETS / f'bg{self.number:02}_{i+1}.tex').read_bytes(), np.uint8).reshape(size, size)
                textures[i + 4] = clut[tex]
            self.cache[key] = textures
        return render(frame, self.cache[key])[:height]


DRIVER = r'''
#include "native_match.hpp"
#include "combat_stage.hpp"
#include <algorithm>
#include <bit>
#include <fstream>
#include <iostream>
#include <set>
#include <string_view>

int main(int argc,char** argv) {
    int firstSample=3;
    std::array<unsigned,2> spirits{};
    if(argc>3&&std::string_view(argv[3])=="--spirits") {
        if(argc<6)return 2;
        spirits={unsigned(std::stoul(argv[4])),unsigned(std::stoul(argv[5]))};
        firstSample=6;
    }
    ss6::NativeMatch match(argv[1],-1,ss6::VersusMode::Console,nullptr,spirits);
    ss6::CombatStage art(argv[1]);
    const std::filesystem::path temp=argv[2];
    auto file=[&](unsigned i,const char* ext) {return temp/(std::to_string(i)+ext);};
    std::set<unsigned> wanted;
    for(int i=firstSample;i<argc;++i)wanted.insert(std::stoul(argv[i]));
    std::array<unsigned,2> prev{},held{};
    unsigned count, tick=0;
    while(std::cin>>count>>held[0]>>held[1])while(count--) {
        ++tick;
        const auto& battle=match.battle();
        const auto camera=battle.camera;
        const auto& g=battle.gauges;
        const auto& tasks=battle.entry.tasks.tasks;
        const auto has=[&](uint32_t id) {
            return std::any_of(tasks.begin(),tasks.end(),[&](const auto& t){
                return t[0]==id && t[1]==0x10 && int32_t(t[2])<=0;
            });
        };
        // The stage reads the previous fighter-camera publication. Priority 5
        // can change the stage delta before priority 10 visits in this frame.
        unsigned delta=g.delta46a908;
        const bool menu=battle.consoleMenu.active;
        if(!menu && has(0x11e708)) delta=g.paused46a940?0:(g.scale1239d84*g.scale1239d88)>>8;
        const bool visit=has(0x1a7810) && (!match.finished || menu);
        std::array<ss6::NormalizedPadSample,2> pads;
        for(unsigned i=0;i<2;++i)pads[i]={held[i],held[i]&~prev[i]};
        prev=held;
        match.tick(pads);
        const auto& stage=match.combatStage();
        std::cout<<tick<<' '<<visit<<' '<<delta<<' '<<battle.currentState<<' '<<battle.consoleMenu.active;
        for(float x:{camera.projectionX,camera.projectionY,camera.depth,camera.depthOffset,camera.verticalOffset})
            std::cout<<' '<<std::bit_cast<uint32_t>(x);
        for(unsigned i=0;i<2;++i) {
            const auto& f=match.fighter(i);
            std::cout<<' '<<f.actor.fieldA30<<' '<<f.body.timeline.action().id()<<' '<<std::bit_cast<uint32_t>(f.actor.y);
        }
        for(const auto& layer:stage.layers)std::cout<<' '<<layer.elapsed<<' '<<layer.picture<<' '<<layer.step;
        std::cout<<'\n';
        if(!wanted.contains(tick))continue;
        std::ofstream geometry(file(tick,".strips"),std::ios::binary);
        auto word=[&](uint32_t w){geometry.write(reinterpret_cast<const char*>(&w),4);};
        for(const auto& strip:art.geometry(stage)) {
            word(std::bit_cast<uint32_t>(float(strip.z)));word(strip.slot);word(strip.color);word(strip.vertices.size());
            for(const auto& v:strip.vertices)
                for(float x:{v.x,v.y,v.u,v.v})word(std::bit_cast<uint32_t>(x));
        }
        std::ofstream tone(file(tick,".tones"),std::ios::binary);
        tone.write(reinterpret_cast<const char*>(&g.paletteTones[512]),1024);
        std::vector<uint8_t> pixels(640*480*4);
        art.paint(stage,g.paletteTones,pixels);
        std::ofstream(file(tick,".rgba"),std::ios::binary).write(reinterpret_cast<const char*>(pixels.data()),pixels.size());
        if(tick==1) {
            // Separate CLUT fixture. Adjacent colors have different tones in
            // each bank; a whole-screen grayscale switch cannot pass this.
            auto tones=g.paletteTones;
            for(unsigned i=0;i<512;++i)tones[512+i]=(i^(i>>8))%8;
            art.paint(stage,tones,pixels);
            std::ofstream(file(tick,".mixed"),std::ios::binary).write(reinterpret_cast<const char*>(pixels.data()),pixels.size());
        }
    }
}
'''


def scenario(mirror=False):
    commands = [(500, 0, 0), (160, 64, 128), (1, 144, 80), (55, 0, 0), (130, 128, 0),
                (1, 16, 16), (55, 0, 0)] + [(45, 128, 0), (1, 1024, 0), (84, 0, 0)] * 30
    if mirror:
        def flip(bits):
            return (bits & ~192) | ((bits & 128) >> 1) | ((bits & 64) << 1)
        commands = [(n, flip(b), flip(a)) for n, a, b in commands]
    return commands


def replay_text(segments, last=None):
    out = []
    for n, a, b in segments:
        if last is not None:
            n = min(n, last)
            last -= n
        if n:
            out.append(f'{n} {a} {b}\n')
    return ''.join(out)


def pack_strip(strip):
    z, slot, color, vertices = strip
    return struct.pack('<fIII', z, slot, color, len(vertices)) + b''.join(struct.pack('<4f', *v) for v in vertices)


def compare_pixels(actual, expected, context):
    different = np.any(actual != expected, axis=2)
    if np.any(different):
        y, x = np.argwhere(different)[0]
        raise ValueError((context, int(np.count_nonzero(different)), (int(x), int(y)),
                          expected[y, x].tolist(), actual[y, x].tolist()))


def decode_floats(words):
    return list(struct.unpack(f'<{len(words)}f', struct.pack(f'<{len(words)}I', *words)))


def sample_frames(rows, mirror):
    victim = 10 if mirror else 13
    ko = next(r[0] for r in rows if r[victim] == 0)
    menu = next(r[0] for r in rows if r[4])
    first_victory = next(r[0] for r in rows if r[3] == 8)
    # These sample different real published camera trajectories as well as
    # different clocks. Detect the KO/menu relative to the gameplay result.
    samples = {1:'first-visit',65:'introduction',500:'combat-ready',565:'zooming-out',620:'full-zoom',
               690:'jump-and-zoom',780:'walking-pan',867:'jump-away-from-center',ko:'heavy-KO',
               ko+16:'KO-reaction',first_victory+40:'victory-camera',menu:'menu-entry',
               menu+1:'menu-before-freeze',menu+2:'menu-first-frozen',menu+21:'menu-frozen'}
    if mirror:
        return {k: v for k, v in samples.items() if v in {'walking-pan','jump-away-from-center','heavy-KO','victory-camera'}}
    return samples


def jump_draw_records(tmp, segments, samples):
    # This is the same original queue/sorting oracle used by the pose test.
    # Here its background comes directly from 1a7810 at the matching tick.
    source = tmp / 'draw-queue.cpp'
    source.write_text(hurt.CAPTURE_DRIVER)
    exe = tmp / 'draw-queue'
    subprocess.run(['c++','-std=c++20','-O2','-ffp-contract=off','-I',ROOT/'src',source,LIB,'-o',exe],check=True)
    inputs = [(a,b) for n,a,b in segments for _ in range(n)]
    commands = ''.join(f'tick {a} {b} {int(tick in samples)}\n' for tick,(a,b) in enumerate(inputs,1))
    records = subprocess.run([exe,ASSETS], input=commands.encode(), capture_output=True,check=True)
    p = actors.fixture()
    for n,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin')):
        at=0x4a4810+n*0x3da0
        p.memory[at:at+0x3da0]=(ASSETS/name).read_bytes()
    return p,io.BytesIO(records.stdout)


def validate(tmp):
    (tmp / 'probe.cpp').write_text(DRIVER)
    exe = tmp / 'stage-probe'
    subprocess.run(['c++', '-std=c++20', '-O2', '-I', ROOT / 'src', tmp / 'probe.cpp',
                    LIB, '-o', exe], check=True)
    tests, sheet, hist, composed = [], [], Counter(), []
    jump_pads=[(500,0,0),(1,144,0),(29,0,0),(1,256,0),(17,0,0)]
    jump_samples={541:'jump-light-contact',546:'jump-light-hurt-second-pose',548:'jump-light-hurt-third-pose'}
    p, records = jump_draw_records(tmp,jump_pads,jump_samples)
    actor_stats=Counter()
    for case, segments in [('P1',scenario()),('P2',scenario(True)),('P1-jump-light',jump_pads)]:
        jump=case=='P1-jump-light'
        def run(steps, samples=()):
            log = subprocess.run([exe, ASSETS, tmp, *map(str, samples)], input=replay_text(steps),
                                 capture_output=True, text=True, check=True)
            return [list(map(int, line.split())) for line in log.stdout.splitlines()]
        baseline = run(segments)
        samples = jump_samples if jump else sample_frames(baseline, case=='P2')
        rows = run(segments, samples)
        assert rows == baseline
        src = SourceStage()
        for row in rows[:max(samples)]:
            tick, visit, delta, state, menu = row[:5]
            if not visit:
                assert tick not in samples
                continue
            camera = row[5:10]
            hist[delta] += 1
            frame = src.visit(delta, camera, tick in samples)
            assert src.layers() == list(zip(row[16::3], row[17::3], row[18::3])), (case, tick, 'animation')
            if tick not in samples:
                continue
            wanted = b''.join(pack_strip(strip) for strip in frame)
            actual = (tmp / f'{tick}.strips').read_bytes()
            if wanted != actual:
                offset = next((i for i, (a,b) in enumerate(zip(actual, wanted)) if a != b), min(len(actual),len(wanted)))
                raise ValueError(('GS submission', case, tick, offset, len(actual), len(wanted),
                                  actual[offset&~3:(offset&~3)+4].hex(), wanted[offset&~3:(offset&~3)+4].hex()))
            tones = struct.unpack('<512H', (tmp / f'{tick}.tones').read_bytes())
            image = src.rgba(frame, tones, 480)
            compare_pixels(np.fromfile(tmp / f'{tick}.rgba', np.uint8).reshape(480,640,4), image, ('640x480',case,tick))
            replay = tmp / 'sample.pad'
            replay.write_text(replay_text(segments, tick))
            dump = tmp / 'viewer.rgba'
            args=[PACKAGE / 'ss6-viewer', '--mode', 'versus', '--match-replay', replay, '--dump-stage', dump]
            if jump:
                args+=['--dump',tmp/'scene.rgba']
            screenshot='combat-stage00-center.png' if case=='P1' and tick==500 else 'combat-stage00-jump.png' if jump and tick==546 else None
            if screenshot:
                args+=['--snapshot',tmp/'window.bmp']
            subprocess.run(args,check=True)
            packed = dump.read_bytes()
            assert struct.unpack_from('<2I', packed) == (640,448) and len(packed)==8+640*448*4
            compare_pixels(np.frombuffer(packed, np.uint8, offset=8).reshape(448,640,4),
                           image[:448], ('packaged viewer',case,tick))
            if jump:
                assert row[13:15]==[191,356]
                scene=(tmp/'scene.rgba').read_bytes()
                assert struct.unpack_from('<2I',scene)==(640,448)
                n,=struct.unpack('<I',records.read(4))
                unsorted=[records.read(328) for _ in range(n)]
                hurt.verify_queue(p,unsorted,records.getbuffer()[records.tell():])
                visibility=dict(slot=1,action=356,steps=[])
                result=actors.compare(p,records,actor_stats,samples[tick],scene[8:],visibility,image[:448].tobytes())
                assert result['p1_hits']==1 and result['p2_life']==191
                assert visibility['steps']==[{541:0,546:1,548:2}[tick]] and visibility['visible_pixels']>100
                composed.append(dict(tick=tick,source_draw_records=n,**visibility,scene_sha256=result['viewer_sha256']))
            if screenshot:
                with Image.open(tmp/'window.bmp') as window:
                    assert window.size==(640,480)
                    window.convert('RGB').save(OUT/screenshot)
            if tick==1:
                mixed=src.rgba(frame, [(i^(i>>8))%8 for i in range(512)], 480)
                assert 30000 < np.count_nonzero(np.any(image!=mixed,axis=2)) < 250000
                compare_pixels(np.fromfile(tmp/'1.mixed',np.uint8).reshape(480,640,4),mixed,'per-entry CLUT tones')
            if samples[tick] in {'full-zoom','jump-and-zoom','walking-pan','jump-away-from-center','heavy-KO'}:
                sheet.append(Image.fromarray(image[:448]).resize((320,224),Image.Resampling.LANCZOS))
            tests.append(dict(scenario=case,sample=samples[tick],tick=tick,round_state=state,
                              menu=bool(menu),delta=delta,projection=decode_floats(camera),stage_tones=sorted(set(tones)),
                              health=[row[10],row[13]],act=[row[11],row[14]],strips=len(frame),
                              vertices=sum(len(strip[3]) for strip in frame),geometry_sha256=hashlib.sha256(wanted).hexdigest(),
                              packed_rgba_sha256=hashlib.sha256(packed[8:]).hexdigest()))
    assert {0,256} <= hist.keys()
    assert not records.read(1)
    assert min(t['projection'][0] for t in tests)<200 and max(t['projection'][0] for t in tests)>440
    assert min(t['projection'][2] for t in tests)<-475 and max(t['projection'][1] for t in tests)>135
    composite = Image.new('RGB', (320*4,224*((len(sheet)+3)//4)))
    for i, img in enumerate(sheet):
        composite.paste(img, ((i%4)*320,(i//4)*224))
    composite.save(OUT / 'combat-stage00-scenes.png')
    return dict(status='passed',elf_sha256=SOURCE_HASH,
                viewer_sha256=hashlib.sha256((PACKAGE/'ss6-viewer').read_bytes()).hexdigest(),
                stage_visits_by_delta=hist, samples=tests, compared_pixels=len(tests)*640*(480+448),
                mixed_tone_fixture_pixels=640*480,
                jump_compositions=composed, jump_composition_pixels=len(composed)*640*448,
                scope='Stage zero during real console-mode native inputs. All sampled stages execute the Japanese '
                      '1a7810 with its callees; compare all 1149d0 submitted strips and complete raster from source '
                      '116478/116588 palettes. Native 640x480 rendering and packaged --dump-stage 640x448 crop. '
                      'Three P1 jumping-light samples additionally feed the original stage to the original actor '
                      'and effect packet raster and compare the complete playable scene before the HUD. Independent software '
                      'triangle raster under the finite EE scalar model, without a hardware GS capture.')


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='ss6-combat-stage-') as directory:
        report = validate(Path(directory))
    (OUT/'combat-stage-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f"{len(report['samples'])} stage samples, {report['compared_pixels']:,} pixels")
