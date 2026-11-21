#!/usr/bin/env python3
"""Pin the gallery scene tables and the shared menu-widget tables of SLPS-25559.

Two assets are written. menu_widgets.bin holds what the widget library
(list 20e570.., guide window 1822a0..) reads; console_gallery.bin holds the
tables of the four gallery scenes. Both are tagged-section containers:
u32 count, then per section {char tag[4]; u32 size; payload}. A string table
payload is u32 count followed by {u16 length; bytes} with the Shift_JIS bytes
verbatim (no terminator).
"""
import hashlib
import json
import shutil
import struct
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH

ROOT = Path(__file__).resolve().parents[2]
RESOURCES = ROOT/'work/ss6/extracted/resources'
PACKAGE = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
MESSAGES, TITLE_RECTS = 0x4ee870, 0x4c7660
KEY_HELP = (0x5f22c0, 0x5f22e0, 0x5f22f8, 0x5f2318, 0x5f2328)
KEY_CASES = {0x181960: 0, 0x1819f0: 1, 0x181a54: 2, 0x181ae0: 3, 0x181b64: 4}
SOUND_LISTS = dict(common=0x4cef58, bgm=0x4cf0b8, narration=0x4cf160, character=0x4cf360)
LABELS = dict(bgm=0x4d3110, voice=0x4d2f80, effect=0x4d2df0, narration=0x4d31b8)

class Source:
    def __init__(self):
        self.raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
        assert hashlib.sha256(self.raw).hexdigest() == SOURCE_HASH
        self.elf = Elf(self.raw)
    def at(self, address): return self.elf.offset(address)
    def u8(self, address): return self.raw[self.at(address)]
    def s16(self, address): return struct.unpack_from('<h', self.raw, self.at(address))[0]
    def u16(self, address): return struct.unpack_from('<H', self.raw, self.at(address))[0]
    def word(self, address): return struct.unpack_from('<I', self.raw, self.at(address))[0]
    def s32(self, address): return struct.unpack_from('<i', self.raw, self.at(address))[0]
    def text(self, address):
        start = self.at(address)
        return self.raw[start:self.raw.index(b'\0', start)]
    def pointers(self, address, count=None):
        out = []
        while count is None and self.word(address+4*len(out)) or count is not None and len(out) < count:
            out.append(self.word(address+4*len(out)))
        return out
    def messages(self):
        # 1821f8: {u8 key; char* text} records up to key ff; fe continues the previous key.
        out = []
        while self.u8(MESSAGES+8*len(out)) != 0xff:
            at = MESSAGES+8*len(out)
            out.append((at, self.u8(at), self.word(at+4)))
        return out
    def sound_list(self, address, single=True):
        # {s16 key; u8 type; u8 pad; u16 id}; key -2 closes the table.
        out = []
        while self.s16(address+6*len(out)) != -2:
            at = address+6*len(out)
            out.append((self.s16(at), self.u8(at+2), self.u16(at+4)))
        return out
    def lyrics(self, address):
        # {GlyphRec* line; s32 base} up to a null line; GlyphRec = {u8* sjis; s32 time},
        # the record with time -1 closes its line and carries no glyph.
        lines = []
        while self.word(address+8*len(lines)):
            rec, base = self.word(address+8*len(lines)), self.s32(address+8*len(lines)+4)
            glyphs = []
            while self.s32(rec+8*len(glyphs)+4) != -1:
                p = self.word(rec+8*len(glyphs))
                glyphs.append((self.u8(p) << 8 | self.u8(p+1), self.s32(rec+8*len(glyphs)+4)))
            lines.append((base, glyphs))
        return lines

def strings(items):
    return struct.pack('<I', len(items))+b''.join(struct.pack('<H', len(s))+s for s in items)

def container(sections):
    body = b''.join(tag.encode()+struct.pack('<I', len(data))+data for tag, data in sections)
    return struct.pack('<I', len(sections))+body

def widget_tables(s):
    messages = s.messages()
    def jump(table, count): return [s.word(table+4*i) for i in range(count)]
    def title_index(target):
        # 181d70's cases are `addiu t7,zero,N` either at the target or in
        # the delay slot of its branch to the common store.
        for at in (target, target+4):
            w = s.word(at)
            if w >> 16 == 0x240f: return w & 0xffff
        raise AssertionError(hex(target))
    def backdrop(target):
        # 182318: every case starts addiu a0,a0,8; jal 1817c8; <a1 = kind>.
        assert s.word(target+4) == 0x0c0605f2
        w = s.word(target+8)
        if w == 0x0000282d: return 0
        assert w >> 16 == 0x2405
        return struct.unpack('<h', struct.pack('<H', w & 0xffff))[0]
    layouts = struct.pack('<11b', *[backdrop(t) for t in jump(0x5f3f08, 11)])
    layouts += bytes(title_index(t) for t in jump(0x5f2380, 11))
    layouts += bytes({0x182054: 0, 0x1820c0: 1}[t] for t in jump(0x5f3ec8, 11))
    layouts += bytes(KEY_CASES[t] for t in jump(0x5f2340, 14))
    rects = b''.join(struct.pack('<4i', *[s.s32(TITLE_RECTS+0x18*i+4*k) for k in range(4)]) for i in range(17))
    sections = [
        ('NAME', strings([s.text(p) for p in s.pointers(0x4d4bb0, 49)])),
        ('ORDR', bytes(s.u8(0x59cd20+i) for i in range(53))),
        ('EXNM', strings([s.text(a) for a in (0x664820, 0x664810, 0x664850, 0x664838, 0x664800)])),
        ('UNDF', strings([s.text(0x6647f0)])),
        ('MSGK', bytes(key for _, key, _ in messages)),
        ('MSGT', strings([s.text(p) if p else b'' for _, _, p in messages])),
        ('KEYS', strings([s.text(a) for a in KEY_HELP])),
        ('LAYT', layouts),
        ('RECT', rects),
    ]
    return container(sections), dict(messages=len(messages), message_addresses=[hex(p) for _, _, p in messages])

def gallery_tables(s):
    def records(items): return b''.join(struct.pack('<hBBH', k, t, 0, i) for k, t, i in items)
    def lyric(lines):
        out = struct.pack('<I', len(lines))
        for base, glyphs in lines:
            out += struct.pack('<iI', base, len(glyphs))+b''.join(struct.pack('<Hi', c, t) for c, t in glyphs)
        return out
    lists = {k: s.sound_list(a) for k, a in SOUND_LISTS.items()}
    labels = {k: [s.text(p) for p in s.pointers(a)] for k, a in LABELS.items()}
    help_rows = [(s.word(0x582d90+8*i), s.word(0x582d94+8*i)) for i in range(4)]
    assert s.word(0x4eefd8) == 0x5f3f38 and s.word(0x4eefe4) == 0
    sections = [
        ('TOPL', strings([s.text(p) for p in s.pointers(0x657630, 4)])),
        ('TOPH', strings([s.text(p) for p, _ in help_rows])),
        ('TOPS', bytes(scroll for _, scroll in help_rows)),
        ('ILEX', strings([s.text(0x5e9a48+0x10*i) for i in range(6)])),
        ('SCAT', strings([s.text(p) for p in s.pointers(0x4d2de0)])),
        ('SBGM', strings([s.text(p) for p in s.pointers(0x4d31a8)])),
        ('SNAR', strings([s.text(p) for p in s.pointers(0x4d3198)])),
        ('SCOM', strings([s.text(0x5e99f0)])),
        ('LBGM', strings(labels['bgm'])), ('LVOI', strings(labels['voice'])),
        ('LSE_', strings(labels['effect'])), ('LNAR', strings(labels['narration'])),
        ('RCOM', records(lists['common'])), ('RBGM', records(lists['bgm'])),
        ('RNAR', records(lists['narration'])), ('RCHR', records(lists['character'])),
        ('LYR0', lyric(s.lyrics(0x4d3bf8))), ('LYR1', lyric(s.lyrics(0x4d3c98))),
        ('ENDH', strings([s.text(0x5f3f38)])),
        ('LYRK', strings([s.text(0x5e9980)])),
    ]
    return container(sections), dict(sound_records={k: len(v) for k, v in lists.items()},
                                     row_labels={k: len(v) for k, v in labels.items()},
                                     lyric_lines=[len(s.lyrics(a)) for a in (0x4d3bf8, 0x4d3c98)])

def main():
    s = Source()
    report = dict(elf_sha256=SOURCE_HASH, assets={})
    for name, (data, detail) in (('menu_widgets.bin', widget_tables(s)), ('console_gallery.bin', gallery_tables(s))):
        (RESOURCES/name).write_bytes(data)
        shutil.copyfile(RESOURCES/name, PACKAGE/name)
        report['assets'][name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), **detail)
    report['sources'] = dict(character_names='0x4d4bb0', list_order='0x59cd20', messages=hex(MESSAGES),
                             title_rects=hex(TITLE_RECTS), layout_jump_tables=['0x5f3f08', '0x5f2380', '0x5f3ec8', '0x5f2340'],
                             top_labels='0x657630', top_help='0x582d90', sound_lists={k: hex(v) for k, v in SOUND_LISTS.items()},
                             row_labels={k: hex(v) for k, v in LABELS.items()}, lyrics=['0x4d3bf8', '0x4d3c98'])
    (ROOT/'outputs/ss6-feasibility/console_gallery_tables.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: {a: b for a, b in v.items() if a != 'message_addresses'} for k, v in report['assets'].items()}, indent=2))

if __name__ == '__main__':main()
