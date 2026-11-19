#!/usr/bin/env python3
"""Recover the archive table from the game's ELF, without modifying the ISO."""
import argparse
import collections
import hashlib
import json
import re
import struct
from pathlib import Path
from inspect_iso import Iso, Elf


def recover(elf, archive_size):
    anchor = elf.data.index(b'01HitFlash.bin\0')
    pointer = struct.pack('<Q', elf.va(anchor))
    candidates = []
    for match in re.finditer(re.escape(pointer), elf.data):
        if match.start() % 8:
            continue
        entries, expected, offset = [], 0, match.start()
        while offset + 32 <= len(elf.data):
            address, start, end, size = struct.unpack_from('<4Q', elf.data, offset)
            try:
                name = elf.cstring(address)
            except (ValueError, UnicodeDecodeError):
                break
            # A second adjacent table uses 64-byte units. Do not mistake it for
            # more archive files: this table must cover SAM_DATA in ISO sectors.
            if start != expected or not size or end - start + 1 != (size + 2047) // 2048:
                break
            if not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]*\.[A-Za-z0-9]+', name):
                break
            entries.append(dict(name=name, offset=start * 2048, size=size,
                                start_sector=start, end_sector=end,
                                table_elf_offset=offset, table_virtual_address=elf.va(offset)))
            expected, offset = end + 1, offset + 32
        if entries and expected * 2048 == archive_size:
            candidates.append(entries)
    if len(candidates) != 1:
        raise ValueError(f'Expected one complete, contiguous archive table, got {len(candidates)}')
    return candidates[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('iso', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--extract', type=Path, required=True)
    args = parser.parse_args()
    iso = Iso(args.iso)
    config = iso.read('/SYSTEM.CNF').decode('ascii')
    boot = re.search(r'BOOT2\s*=\s*cdrom0:\\([^;\r\n]+)', config).group(1)
    elf = Elf(iso.read('/' + boot))
    archive = iso.by_path['/SAM_DATA.BIN']
    entries = recover(elf, archive['size'])
    if len({e['name'] for e in entries}) != len(entries):
        raise ValueError('Duplicate archive file names')
    args.extract.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    for e in entries:
        data = iso.read_at(archive['lba'] * iso.block + e['offset'], e['size'])
        e['sha256'] = hashlib.sha256(data).hexdigest()
        (args.extract / e['name']).write_bytes(data)
    families = collections.defaultdict(list)
    for e in entries:
        match = re.fullmatch(r'(act|aid|chr|idx|jdg|map|pil)_(\d+[a-z]?)\.bin', e['name'])
        if match:
            families[match[1]].append(match[2])
    manifest = dict(archive='/SAM_DATA.BIN', archive_size=archive['size'],
                    table_entry_size=32, allocation_unit=2048,
                    layout_status='all entries bounded, contiguous and sector-size consistent',
                    file_count=len(entries), character_resource_ids=dict(families),
                    note='Resource IDs are not yet a verified playable-character/name mapping.',
                    entries=entries)
    (args.out / 'resource_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(dict(files=len(entries), bytes=sum(e['size'] for e in entries),
                         character_families={k:len(v) for k,v in families.items()}), indent=2))


if __name__ == '__main__':
    main()
