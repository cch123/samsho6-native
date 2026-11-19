#!/usr/bin/env python3
"""Read-only, bounded ISO9660/ELF inventory for the supplied PS2 image."""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path


class Iso:
    def __init__(self, path):
        self.path = Path(path)
        self.file = self.path.open('rb')
        self.size = self.path.stat().st_size
        pvd = self.read_at(16 * 2048, 2048)
        if pvd[:7] != b'\x01CD001\x01':
            raise ValueError('Expected an ISO9660 primary volume descriptor')
        self.block = self.both16(pvd, 128)
        self.volume = pvd[40:72].decode('ascii').strip()
        self.volume_created_raw = pvd[813:830].hex()
        self.entries = []
        self._walk(self.record(pvd[156:190]), '', set())
        self.by_path = {x['path']: x for x in self.entries}

    @staticmethod
    def both16(data, offset):
        a, b = struct.unpack_from('<H', data, offset)[0], struct.unpack_from('>H', data, offset + 2)[0]
        if a != b:
            raise ValueError('ISO dual-endian field disagrees')
        return a

    @staticmethod
    def both32(data, offset):
        a, b = struct.unpack_from('<I', data, offset)[0], struct.unpack_from('>I', data, offset + 4)[0]
        if a != b:
            raise ValueError('ISO dual-endian field disagrees')
        return a

    def read_at(self, offset, size):
        if offset < 0 or size < 0 or offset + size > self.size:
            raise ValueError(f'Read outside image: {offset}, {size}')
        self.file.seek(offset)
        data = self.file.read(size)
        if len(data) != size:
            raise ValueError('Short read')
        return data

    def record(self, data):
        if len(data) < 34 or data[0] != len(data):
            raise ValueError('Malformed ISO directory record')
        if data[25] & 128 or data[26] or data[27]:
            # Multi-extent/interleaved records must not silently become truncated files.
            raise ValueError('Unsupported multi-extent/interleaved file')
        name = data[33:33 + data[32]].decode('ascii').split(';')[0]
        if '/' in name or name == '..':
            raise ValueError('Unsafe ISO file name')
        return dict(name=name, lba=self.both32(data, 2) + data[1],
                    size=self.both32(data, 10), directory=bool(data[25] & 2))

    def _walk(self, entry, parent, visited):
        if entry['lba'] in visited:
            raise ValueError('Directory loop')
        visited.add(entry['lba'])
        data = self.read_at(entry['lba'] * self.block, entry['size'])
        offset = 0
        while offset < len(data):
            length = data[offset]
            if length == 0:
                offset = (offset // self.block + 1) * self.block
                continue
            child = self.record(data[offset:offset + length])
            offset += length
            if child['name'] in ('\0', '\1'):
                continue
            child['path'] = parent + '/' + child['name']
            if child['lba'] * self.block + child['size'] > self.size:
                raise ValueError('Extent outside image')
            self.entries.append(child)
            if child['directory']:
                self._walk(child, child['path'], visited)

    def read(self, path):
        entry = self.by_path[path]
        if entry['directory']:
            raise ValueError('Expected a file')
        return self.read_at(entry['lba'] * self.block, entry['size'])


class Elf:
    def __init__(self, data):
        self.data = data
        if data[:6] != b'\x7fELF\x01\x01':
            raise ValueError('Expected ELF32 little endian')
        h = struct.unpack_from('<16sHHIIIIIHHHHHH', data)
        self.entry, self.machine = h[4], h[2]
        sections = [struct.unpack_from('<10I', data, h[6] + i * h[11]) for i in range(h[12])]
        strings = sections[h[13]]
        names = data[strings[4]:strings[4] + strings[5]]
        self.sections = [dict(name=names[s[0]:].split(b'\0')[0].decode('ascii'),
                              type=s[1], flags=s[2], address=s[3], offset=s[4], size=s[5]) for s in sections]

    def va(self, offset):
        for s in self.sections:
            if s['type'] != 8 and s['flags'] & 2 and s['offset'] <= offset < s['offset'] + s['size']:
                return s['address'] + offset - s['offset']
        raise ValueError('No loaded section for file offset')

    def offset(self, address):
        for s in self.sections:
            if s['type'] != 8 and s['flags'] & 2 and s['address'] <= address < s['address'] + s['size']:
                return s['offset'] + address - s['address']
        raise ValueError('No file-backed section for address')

    def cstring(self, address):
        offset = self.offset(address)
        end = self.data.find(b'\0', offset, offset + 256)
        if end == -1:
            raise ValueError('Unterminated string')
        return self.data[offset:end].decode('ascii')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('iso', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--scratch', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    args.scratch.mkdir(parents=True, exist_ok=True)
    iso = Iso(args.iso)
    with args.iso.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    config = iso.read('/SYSTEM.CNF').decode('ascii')
    boot = re.search(r'BOOT2\s*=\s*cdrom0:\\([^;\r\n]+)', config).group(1)
    exe = iso.read('/' + boot)
    elf = Elf(exe)
    (args.scratch / boot).write_bytes(exe)
    (args.scratch / 'SYSTEM.CNF').write_text(config)
    manifest = dict(source=str(args.iso), bytes=iso.size, sha256=digest,
                    volume=iso.volume, volume_created_raw=iso.volume_created_raw,
                    logical_block_size=iso.block, boot_config=config,
                    file_count=sum(not x['directory'] for x in iso.entries),
                    directory_count=sum(x['directory'] for x in iso.entries), entries=iso.entries,
                    executable=dict(path=boot, bytes=len(exe), sha256=hashlib.sha256(exe).hexdigest(),
                                    machine=elf.machine, entry=elf.entry, sections=elf.sections,
                                    has_symbol_table=any(s['type'] == 2 for s in elf.sections)))
    (args.out / 'iso_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    strings = []
    for match in re.finditer(rb'[ -~]{5,}\x00', exe):
        try:
            address = elf.va(match.start())
        except ValueError:
            continue
        strings.append(dict(offset=match.start(), address=address, text=match.group()[:-1].decode('ascii')))
    (args.scratch / 'elf_strings.json').write_text(json.dumps(strings, indent=2) + '\n')
    print(json.dumps({key: manifest[key] for key in ('bytes', 'sha256', 'file_count', 'directory_count', 'boot_config')}, indent=2))


if __name__ == '__main__':
    main()
