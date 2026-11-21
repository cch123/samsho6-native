#!/usr/bin/env python3
"""Compare one battle stage (2..11) with its original scenery task, visit by visit.

A single continuous run drives the unmodified task and the native state with
the same projection, delta, hide flag and library random seed. Every visit
compares the complete, depth-sorted 1149d0 submission list (positions, UVs,
depth keys, color, alpha mode) and the next order number, so the animation
clocks are verified through the pictures and motions they select. Sampled
visits are also rasterized by an independent software model and compared
pixel for pixel.

Optional stage_fixture_NN keys used here: cameras (extra projections),
long_deltas (the two long steps), visits (default run length), steer(n, delta,
memo) -> delta, seeded_init (repeat the constructor tail after seeding),
pokes {visit: ((address, bits, native index), ...)} explicit state fixtures,
current(p, row) / empty_pictures for objects that are not rows, and coverage
hooks whose results are asserted on runs of 600+ visits and written to the
report: before(p, counter) / after(p, counter), watch_tags(p, frame) with
expect_tags, watch(p) with expect, probe(p, pc, seen) with probe_expected,
observe(p, coverage) with covered(coverage).
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

import numpy as np
from PIL import Image

from extract_collision_tables import SOURCE_HASH
from extract_combat_stage_n import extract, path as geometry_path, pictures, prefix_clocks, timeline_keys
from stage_fixture import DELTA, HIDE, STAGES, animated_rows, clock, prepare, run_init, set_camera, submissions
from validate_dash_motion import ASSETS, ROOT

OUT = ROOT / 'outputs/ss6-feasibility'
LIB = ROOT / 'work/ss6/build-native/libss6-runtime.a'
SOURCES = ('combat_stage.cpp', 'combat_stage_state.cpp')
DRIVER = r'''
#include "combat_stage.hpp"
#include "game_random.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
using namespace ss6;
int main(int argc,char** argv) {
    const unsigned stage=std::stoul(argv[3]);
    CombatStage art(argv[1],stage);const std::filesystem::path out=argv[2];
    CombatStageState s;s.stage=stage;
    GameRandom random;StageCamera c;
    auto write=[](std::ofstream& f,auto v){f.write(reinterpret_cast<const char*>(&v),sizeof(v));};
    char op;
    while(std::cin>>op) {
        if(op=='S'){std::cin>>random.librarySeed;continue;}
        if(op=='R'){CombatStageState next;next.stage=stage;next.inheritRematch(s);s=next;continue;}
        if(op=='P') {
            // Explicit state fixture: the same word is written to the
            // original descriptor and to the native state.
            unsigned index;uint32_t bits;std::cin>>index>>bits;
            [&](auto& state){if constexpr(requires{state.poke(index,bits);})state.poke(index,bits);
                             else throw std::logic_error("stage has no poke fixture");}(s.stage08);
            continue;
        }
        unsigned id,delta,tones,full;bool hide;
        std::cin>>id>>delta>>hide>>tones>>full;
        std::cin>>c.projectionX>>c.projectionY>>c.depth>>c.depthOffset>>c.verticalOffset;
        s.visit(c,delta,hide,&random);
        unsigned depth;const auto strips=art.geometry(s,&depth);
        std::ofstream gs(out/(std::to_string(id)+".gs"),std::ios::binary);
        write(gs,random.librarySeed);write(gs,depth);write(gs,unsigned(strips.size()));
        for(const auto& strip:strips) {
            write(gs,strip.z);write(gs,strip.slot);write(gs,strip.color);write(gs,strip.mode);write(gs,unsigned(strip.vertices.size()));
            for(unsigned i=0;i<strip.vertices.size();++i) {
                const auto& v=strip.vertices[i];
                write(gs,v.x);write(gs,v.y);write(gs,v.u);write(gs,v.v);
                write(gs,strip.depths.empty()?strip.z:strip.depths[i]);
            }
        }
        if(full) {
            std::array<uint16_t,1024> paletteTones{};
            for(unsigned i=512;i<1024;++i)paletteTones[i]=tones==7?(i%11<4?1:0):tones;
            std::vector<uint8_t> rgba(640*480*4);
            if(art.paint(s,paletteTones,rgba)!=depth)return 1;
            std::ofstream f(out/(std::to_string(id)+".rgba"),std::ios::binary);
            f.write(reinterpret_cast<const char*>(rgba.data()),rgba.size());
        }
    }
}
'''


def pack(seed, depth, frame):
    data = bytearray(struct.pack('<Q2I', seed, depth, len(frame)))
    for z, slot, color, mode, vertices in frame:
        data.extend(struct.pack('<f4I', z, slot, color, mode, len(vertices)))
        for vertex in vertices:
            data.extend(struct.pack('<5f', *vertex))
    return bytes(data)


def render(frame, textures):
    """Painter's model of the queued strips: modulate, then source-alpha blend."""
    dst = np.zeros((480, 640, 4), np.uint8)
    dst[:, :, 3] = 255

    def edge(a, b, x, y):
        return (b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0])

    def inside(w, a, b):
        return (w > 0) | ((w == 0) & ((b[1] < a[1]) | ((b[1] == a[1]) & (b[0] > a[0]))))

    for _, slot, color, mode, verts in frame:
        tex = textures[slot]
        v = np.array(verts, dtype=np.float64)
        modulate = np.array([(((color >> (8 * k)) & 255) + 1) // 2 for k in range(3)], np.int32)
        strip_alpha = ((color >> 24) + 1) // 2 if mode == 1 else 128
        for i in range(2, len(v)):
            a, b, c = v[i - 2:i + 1]
            area = edge(a, b, c[0], c[1])
            if area < 0:
                b, c = c, b
                area = -area
            if not area:
                continue
            corners = np.asarray([a[:2], b[:2], c[:2]])
            lower = np.maximum([0, 0], np.ceil(corners.min(axis=0) - .5).astype(int))
            upper = np.minimum([640, 480], np.ceil(corners.max(axis=0) - .5).astype(int))
            if any(upper <= lower):
                continue
            y, x = np.mgrid[lower[1]:upper[1], lower[0]:upper[0]]
            wa = edge(b, c, x + .5, y + .5)
            wb = edge(c, a, x + .5, y + .5)
            wc = edge(a, b, x + .5, y + .5)
            mask = inside(wa, b, c) & inside(wb, c, a) & inside(wc, a, b)
            x = x[mask]
            y = y[mask]
            # Truncation toward zero, as the native integer conversion does.
            uv = [np.clip(np.trunc((wa[mask] * a[k] + wb[mask] * b[k] + wc[mask] * c[k]) * tex.shape[0] / area),
                          0, tex.shape[0] - 1).astype(int) for k in (2, 3)]
            texel = tex[uv[1], uv[0]].astype(np.int32)
            current = dst[y, x, :3].astype(np.int32)
            alpha = (texel[:, 3:4] * strip_alpha) >> 7
            rgb = (texel[:, :3] * modulate) >> 7
            dst[y, x, :3] = current + ((rgb - current) * alpha >> 7)
    return dst


class Original:
    def __init__(self, stage):
        assert hashlib.sha256((ASSETS.parent / 'SLPS_255.59').read_bytes()).hexdigest() == SOURCE_HASH
        self.stage = stage
        self.cfg = STAGES[stage]
        self.p = prepare(stage)
        self.reent = self.p.read(0x5d1bf8, 4) + 0xa8
        self.cache = {}
        self.instructions = self.strips = 0
        files = sorted(ASSETS.glob(f'bg{stage:02}_*.tex'))
        self.files = [f.name for f in files]
        self.seen = set()
        probe = self.cfg.get('probe')
        self.extra = (lambda pc: probe(self.p, pc, self.seen)) if probe else None
        self.early = stage in (3, 9, 11)  # second CLUT is file 2, bound from the second slot on

    def reload(self):
        p = self.p
        for address, value in self.cfg['globals']:
            p.write(address, value, 4)
        for routine in self.cfg['init']:
            if routine not in self.cfg.get('once', ()):
                run_init(p, routine)

    def visit(self, camera, hide, delta):
        p = self.p
        set_camera(p, camera)
        p.write(HIDE, hide, 4)
        p.write(DELTA, delta, 4)
        frame, depth, steps = submissions(p, self.stage, extra=self.extra)
        self.instructions += steps
        self.strips += len(frame)
        return sorted(frame, key=lambda s: s[0]), depth, p.read(self.reent, 8)

    def rgba(self, frame, tones):
        key = tuple(tones)
        if key not in self.cache:
            p = self.p
            start = 0x3ebf30 + 512 * 2
            p.memory[start:start + 1024] = struct.pack('<512H', *key)
            cluts = []
            for bank, number in enumerate((1, 2 if self.early else 3)):
                palette = (ASSETS / f'bg{self.stage:02}_{number}.pal').read_bytes()
                scratch = 0x1410000
                p.memory[scratch:scratch + len(palette)] = palette
                p.write(scratch, 0, 2)  # The stage loader clears entry zero before transfer.
                p.write(0x439b68, 0, 4)
                dest = 512 + 256 * bank
                p.run(0x116478, [dest, 256, scratch], limit=150000)
                p.run(0x116588, limit=350000)
                cluts.append(np.frombuffer(p.memory, np.uint8, 1024, 0x11e7980 + 4 * dest).reshape(256, 4).copy())
            textures = {}
            for i, name in enumerate(self.files):
                raw = (ASSETS / name).read_bytes()
                size = 1024 if len(raw) == 1 << 20 else 512
                tex = np.frombuffer(raw, np.uint8).reshape(size, size)
                textures[i + 4] = cluts[i >= (1 if self.early else 2)][tex]
            self.cache[key] = textures
        return render(frame, self.cache[key])


CAMERAS = ((320, 120, -400, 0, -120), (177, 125, -423, 0, -125), (468, 132, -478, -2, -132),
           (310.25, 194.5, -545.5, 5, -184.5), (330, 215, -660, 0, -215), (320.75, 112, -385.25, -12, -108),
           (160, 120, -400, 0, -120), (480, 120, -400, 0, -120))


def plan(visits, cfg):
    cameras = CAMERAS + tuple(cfg.get('cameras', ()))
    long_deltas = cfg.get('long_deltas', (64 * 256, 25 * 256))
    memo = {}
    for n in range(visits):
        delta = (256, 256, 128, 64, 0, 256)[n % 6]
        if n % 533 < 12 and n > 20:
            delta = 0
        # Long steps reach slow phases; 64-tick steps keep every state observable.
        if n % 90 >= 60:
            delta = long_deltas[0] if n % 2 else long_deltas[1]
        if 'steer' in cfg:
            delta = cfg['steer'](n, delta, memo)
        hide = int(n % 117 in (19, 20))
        full = n < 6 or n % 61 == 0
        tones = (0, 1, 4, 7)[(n // 61) % 4] if n >= 6 else (0, 7)[n % 2]
        yield cameras[(n // 3) % len(cameras)], hide, delta, tones, full, n in (150, 151, 400)


def verify(stage, visits):
    geometry, counts, direct = extract(stage)
    assert geometry == geometry_path(stage).read_bytes(), 'stale combat stage asset; rerun extract_combat_stage_n.py'
    source = Original(stage)
    p = source.p
    seed = 0x5deece66d0000001
    p.write(source.reent, seed, 8)
    commands = [f'S {seed}']
    cfg = source.cfg
    if cfg.get('seeded_init'):
        source.reload()
        commands.append('R')
    expected = []
    shown = {row: set() for row in animated_rows(p, stage) if pictures(p, stage, row) is not None}
    shapes = Counter()
    vertices = 0
    free = {state: set() for state, _, _ in cfg.get('clocks', ())}
    free.update({state: set() for _, state, _ in cfg.get('clocks_ranked', ())})
    prefix = {state: (set(), keys) for state, keys in prefix_clocks(p, stage)}
    counter = Counter()
    tags = set()
    reached = {}
    coverage = {}
    pokes = []
    rolls = 0
    for i, (camera, hide, delta, tones, full, reload) in enumerate(plan(visits, cfg)):
        if reload:
            source.reload()
            commands.append('R')
        for address, bits, index in cfg.get('pokes', {}).get(i, ()):
            p.write(address, bits, 4)
            commands.append(f'P {index} {bits}')
            pokes.append((i, hex(address), hex(bits)))
        before = p.read(source.reent, 8)
        if 'before' in cfg:
            cfg['before'](p, counter)
        frame, depth, after = source.visit(camera, hide, delta)
        rolls += before != after
        if 'after' in cfg:
            cfg['after'](p, counter)
        if 'observe' in cfg:
            cfg['observe'](p, coverage)
        if 'watch_tags' in cfg:
            tags |= cfg['watch_tags'](p, frame)
        if 'watch' in cfg:
            for name, value in cfg['watch'](p).items():
                reached.setdefault(name, set()).add(value)
        for state in free:
            free[state].add(p.read(state + 4, 4))
        for state, (seen, _) in prefix.items():
            seen.add(p.read(state + 4, 4))
        if hide:
            assert not frame, 'a hidden stage submitted geometry'
        for row in shown:
            shown[row].add(cfg['current'](p, row) if 'current' in cfg else p.read(clock(p, stage, row)[0] + 4, 4))
        commands.append(' '.join(map(str, ['V', i, delta, hide, tones, int(full), *camera])))
        expected.append((frame, depth, after, tones, full))
        shapes.update((s[1], s[3], len(s[4])) for s in frame)
        vertices += sum(len(s[4]) for s in frame)
    for row, seen in shown.items():
        if visits < 600:
            break  # short diagnostic runs
        assert seen - set(cfg.get('empty_pictures', ())) == set(pictures(p, stage, row)), ('picture coverage', row, seen)
    if visits >= 600:
        for state, timeline, _ in cfg.get('clocks', ()):
            assert free[state] == set(timeline_keys(p, timeline)), ('clock coverage', hex(state), free[state])
        for _, state, timeline in cfg.get('clocks_ranked', ()):
            assert free[state] == set(timeline_keys(p, timeline)), ('clock coverage', hex(state), free[state])
        for state, (seen, keys) in prefix.items():
            assert seen == set(keys), ('prefix clock coverage', hex(state), seen)
        assert cfg.get('expect_tags', set()) <= tags, ('state coverage', tags)
        for name, want in cfg.get('expect', {}).items():
            assert reached.get(name) == want, ('private state coverage', name, sorted(reached.get(name, ())))
        if 'probe_expected' in cfg:
            assert source.seen == cfg['probe_expected'], ('state coverage', sorted(source.seen ^ cfg['probe_expected']))
        if 'covered' in cfg:
            coverage = cfg['covered'](coverage)
    images = 0
    previews = []
    with tempfile.TemporaryDirectory() as temp:
        tmp = Path(temp)
        cpp = tmp / 'stage.cpp'
        cpp.write_text(DRIVER)
        exe = tmp / 'stage'
        subprocess.run(['c++', '-std=c++20', '-O2', '-ffp-contract=off', '-I', ROOT / 'src', cpp,
                        *[ROOT / 'src' / name for name in SOURCES],
                        *sorted((ROOT / 'src').glob('combat_stage_[0-9][0-9].cpp')), LIB, '-o', exe], check=True)
        subprocess.run([exe, ASSETS, tmp, str(stage)], input='\n'.join(commands) + '\n', text=True, check=True)
        for i, (frame, depth, after, tones, full) in enumerate(expected):
            want = pack(after, depth, frame)
            got = (tmp / f'{i}.gs').read_bytes()
            if want != got:
                describe(i, commands, want, got)
            if full:
                tone = [(1 if j % 11 < 4 else 0) if tones == 7 else tones for j in range(512, 1024)]
                model = source.rgba(frame, tone)
                seen = np.fromfile(tmp / f'{i}.rgba', np.uint8).reshape(480, 640, 4)
                if not np.array_equal(seen, model):
                    bad = np.any(seen != model, axis=-1)
                    y, x = next(zip(*np.where(bad)))
                    raise ValueError(('pixel mismatch', i, int(bad.sum()), int(x), int(y), model[y, x].tolist(), seen[y, x].tolist()))
                images += 1
                if len(previews) < 4 and frame:
                    previews.append(Image.fromarray(seen[:448]).resize((320, 224)))
    sheet = Image.new('RGB', (320 * len(previews), 224))
    for i, image in enumerate(previews):
        sheet.paste(image, (320 * i, 0))
    sheet.save(OUT / f'combat-stage{stage:02}-cameras.png')
    report = dict(status='passed', stage=stage, elf_sha256=SOURCE_HASH,
                  geometry_sha256=hashlib.sha256(geometry).hexdigest(), actual_callback=hex(STAGES[stage]['handler']),
                  visits=len(expected), original_instructions=source.instructions, submitted_strips=source.strips,
                  exact_vertices=vertices, shape_counts={str(k): v for k, v in sorted(shapes.items())},
                  full_images=images, compared_RGBA_pixels=images * 640 * 480,
                  pictures_per_group=counts, direct_strips_per_group=direct,
                  animated_rows={str(k): sorted(v) for k, v in shown.items()},
                  task_clocks={hex(k): sorted(v) for k, v in free.items()},
                  prefix_clocks={hex(k): sorted(v[0]) for k, v in prefix.items()},
                  library_random_visits=rolls, state_fixtures=pokes,
                  stage_state_coverage=dict(sorted(counter.items())), state_tags=sorted(tags),
                  private_state_reached={k: sorted(v) for k, v in sorted(reached.items())},
                  private_states=sorted(map(str, source.seen)),
                  stage_coverage=coverage if 'covered' in cfg and visits >= 600 else None,
                  scope='One continuous run of the whole original task per visit: complete depth-sorted 1149d0 '
                        'submissions with per-vertex depth keys, color and alpha mode, next order number and '
                        'library random seed. Panned, raised, zoomed, fractional and shaken projections; zero, '
                        'fractional and long deltas; hidden visits; reloads through the constructor tail. '
                        'Pixels use an independent painter model with the original CLUT conversion in color and '
                        'full or partial grayscale. Disc I/O and live GS output are not executed.')
    (OUT / f'combat_stage{stage:02}_validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


def describe(i, commands, want, got):
    def parse(data):
        seed, depth, n = struct.unpack_from('<Q2I', data)
        at = 16
        strips = []
        for _ in range(n):
            z, slot, color, mode, count = struct.unpack_from('<f4I', data, at)
            at += 20
            strips.append((z, slot, color, mode, [struct.unpack_from('<5f', data, at + 20 * j) for j in range(count)]))
            at += 20 * count
        return seed, depth, strips
    a, b = parse(want), parse(got)
    if a[:2] != b[:2]:
        raise ValueError(('seed/depth mismatch', i, a[:2], b[:2], len(a[2]), len(b[2])))
    for n, (x, y) in enumerate(zip(a[2], b[2])):
        if x != y:
            raise ValueError(('strip mismatch', i, n, 'original', x[:4], x[4][:4], 'native', y[:4], y[4][:4],
                              [c for c in commands if c.startswith(f'V {i} ')]))
    raise ValueError(('strip count mismatch', i, len(a[2]), len(b[2]),
                      'next original', a[2][len(b[2])][:4] if len(a[2]) > len(b[2]) else None,
                      'next native', b[2][len(a[2])][:4] if len(b[2]) > len(a[2]) else None))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', type=int, required=True)
    parser.add_argument('--visits', type=int)
    args = parser.parse_args()
    verify(args.stage, args.visits or STAGES[args.stage].get('visits', 900))
