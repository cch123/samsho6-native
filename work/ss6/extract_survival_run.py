#!/usr/bin/env python3
"""Pin the survival-mode reward rule table and every text the survival controller shows."""
import hashlib
import json
import shutil
import struct
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH

ROOT = Path(__file__).resolve().parents[2]
NAME = 'survival_run.bin'
OUT = ROOT/'work/ss6/extracted/resources'/NAME
ASSET = ROOT/'outputs/ss6-feasibility/native-viewer/assets'/NAME
MANIFEST = ROOT/'outputs/ss6-feasibility/survival_run_tables.json'

# 17b9e8 dispatches through 22 code pointers at 5f1ea4. Each target is one
# reward rule; the native module stores the rule index, not the reward.
RULES = {0x17ba10: 0,   # lifeTurn ? 0 : 4
         0x17ba6c: 1,   # lifeTurn ? 1 : 5
         0x17ba30: 2,   # lifeTurn ? 2 : 6
         0x17ba20: 3,   # spirit 1 ? 3 : rule 2
         0x17ba44: 4,   # spirit 5 ? 2 : rule 2
         0x17ba58: 5,   # spirit 4 ? 3 : rule 2
         0x17ba64: 6,   # 3
         0x17ba80: 7,   # 1
         0x17ba78: 8,   # 0
         0x17ba3c: 9}   # 8
# 180fd0 dispatches through 22 code pointers at 5f2160: flag, counter >= 3,
# per-event (never "achieved") and the plain victory rule.
KINDS = {0x181064: 0, 0x181088: 1, 0x181080: 2, 0x1810b0: 3}
# 181498 jump table 5f2290: each target loads one immediate gain, in the
# branch delay slot for targets 1..3, 5 and 6.
GAIN_TARGETS = [0x1814dc, 0x1814f4, 0x1814fc, 0x181504, 0x18150c, 0x18151c, 0x181524]
GAIN_SITES = [0x1814dc, 0x1814f8, 0x181500, 0x181508, 0x18150c, 0x181520, 0x181528]

def build():
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    elf = Elf(raw)
    word = lambda at: struct.unpack_from('<I', raw, elf.offset(at))[0]
    def text(at):
        start = elf.offset(at)
        return raw[start:raw.index(b'\0', start)]
    rules = bytes(RULES[word(0x5f1ea4+4*i)] for i in range(22))
    kinds = bytes(KINDS[word(0x5f2160+4*i)] for i in range(22))
    # Life gains for rewards 0..3 and clock gains for 4..6 are the addiu
    # immediates at the seven jump targets; reward 7 loads c8 and 64.
    assert [word(0x5f2290+4*i) for i in range(8)] == GAIN_TARGETS+[0x18152c]
    gains = [word(site)&0xffff for site in GAIN_SITES]+[word(0x181530)&0xffff, word(0x181538)&0xffff]
    assert all(word(site)>>16 == 0x240e for site in GAIN_SITES) and word(0x181530)>>16 == 0x240e and word(0x181538)>>16 == 0x240d
    # 1821f8 walks {u8 id, pad, u32 text} rows until id ff and returns the row
    # at (first row with the id) + sub.
    table = []
    at = 0x4ee870
    while raw[elf.offset(at)] != 0xff:
        table.append((raw[elf.offset(at)], word(at+4))); at += 8
    def message(key, sub):
        return text(table[[k for k, _ in table].index(key)+sub][1])
    groups = dict(
        rewards=[text(word(0x59cf38+4*i)) for i in range(9)],
        missions=[text(word(0x59cf60+4*i)) for i in range(22)],
        fighters=[text(word(0x4d4bb0+4*i)) for i in range(49)],
        # 31 choose, 32 cleared, 33 next stage, 34 achieved, 35 failed, then 36+reward 0..8.
        messages=[message(k, 0) for k in range(0x31, 0x36)]+[message(0x36, r) for r in range(9)],
        # 5f2100 select/decide, 5f2118 next, 5f22c0 legend installed by layout 7, 22+7 initial message.
        legends=[text(0x5f2100), text(0x5f2118), text(0x5f22c0), message(0x22, 7)],
        # elapsed time, reward, condition, achieved, then the four progress lines of missions c..f.
        hud=[text(a) for a in (0x5f21b8, 0x5f21d8, 0x5f21e8, 0x5f2280, 0x5f21f8, 0x5f2218, 0x5f2238, 0x5f2258)],
        selector=[text(0x665170), text(0x665180)])
    data = bytearray(b'SSV1'+rules+kinds+struct.pack('<9H', *gains))
    for name in ('rewards', 'missions', 'fighters', 'messages', 'legends', 'hud', 'selector'):
        data += struct.pack('<H', len(groups[name]))
        for s in groups[name]:
            data += struct.pack('<H', len(s))+s
    return bytes(data), groups, rules, kinds, gains

def main():
    data, groups, rules, kinds, gains = build()
    OUT.write_bytes(data)
    shutil.copyfile(OUT, ASSET)
    report = dict(elf_sha256=SOURCE_HASH, asset=NAME, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  reward_rule_jump_table='0x5f1ea4', reward_rules=list(rules),
                  mission_kind_jump_table='0x5f2160', mission_kinds=list(kinds),
                  reward_gain_jump_table='0x5f2290', reward_gains=gains,
                  message_table='0x4ee870', pointer_tables=dict(rewards='0x59cf38', missions='0x59cf60', fighters='0x4d4bb0'),
                  strings={k: [s.decode('shift_jis') for s in v] for k, v in groups.items()})
    MANIFEST.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps(dict(asset=NAME, bytes=len(data), sha256=report['sha256']), indent=2))

if __name__ == '__main__':main()
