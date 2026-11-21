#!/usr/bin/env python3
"""Pin the factory save image produced by the original initialiser 10f000."""
import hashlib
import json
from pathlib import Path
from extract_collision_tables import SOURCE_HASH
from extract_console_versus_art import prepare

ROOT = Path(__file__).resolve().parents[2]
IMAGE, SIZE = 0x5735c8, 0x65a8

def factory_image():
    # 10f000 clears the image, then runs 115498 (edit data), 1113e8 (game
    # option), 1c51b0 (ranking), 1183f8 (system setting), 152658 and 177118
    # (key masks). No callee is stubbed; none of them reads the pad or disc.
    p = prepare()
    p.run(0x10f000, limit=3000000)
    return bytes(p.memory[IMAGE:IMAGE+SIZE])

def main():
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    data = factory_image()
    assert data[0x65a4] == 1 and data[0x6184+4] == 100 and data[0x618c+4] == 4
    (ROOT/'work/ss6/extracted/resources/save_default.bin').write_bytes(data)
    report = dict(elf_sha256=SOURCE_HASH, asset='save_default.bin', bytes=len(data),
                  sha256=hashlib.sha256(data).hexdigest(), initialiser='0x10f000',
                  image_address=hex(IMAGE),
                  sections={'auto_save': [0, 4], 'edit_data': [4, 0x6180], 'system_setting': [0x6184, 7],
                            'game_option': [0x618c, 0x98], 'ranking': [0x6224, 0x118],
                            'records_4d7068': [0x633c, 0x80], 'key_masks': [0x63bc, 0x40],
                            'reserved': [0x63fc, 0x1a8], 'marker': [0x65a4, 1]})
    (ROOT/'outputs/ss6-feasibility/save_default_tables.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':main()
