#!/usr/bin/env python3
"""Collect Haohmaru's original sixteen victory messages and their 24px disc glyphs."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from inspect_iso import Elf, Iso

ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'work/ss6/extracted/resources'
ORIGINAL='72420e74e04d7ac39119d1b6ec7d70ed004fc98c5035fade96e87d05d4b9ffbf'
ISO_PATH=Path(json.loads((ROOT/'outputs/ss6-feasibility/iso_manifest.json').read_text())['source'])


def extract(path):
    disc=Iso(path)
    data=disc.read('/SLPS_255.59')
    if hashlib.sha256(data).hexdigest()!=ORIGINAL:raise ValueError('Expected Japanese SLPS-25559')
    elf=Elf(data)
    if elf.cstring(0x5d4640)!=r'cdrom0:\BIN\GOTH_24.BIN;1':raise ValueError('Unexpected 109e20 font source')
    font=disc.read('/BIN/GOTH_24.BIN')
    def word(addr):return struct.unpack_from('<I',data,elf.offset(addr))[0]
    def raw(addr,n):
        off=elf.offset(addr)
        return data[off:off+n]
    glyphs={};quotes=[]
    for q in range(16):
        record=word(word(0x50d550)+0xd8+q*4)
        lines=[]
        for i in range(3):
            ptr=word(record+8+4*i)
            if not ptr:break
            at=elf.offset(ptr);line=data[at:data.index(0,at)]
            decoded=line.decode('cp932')
            if any(len(c.encode('cp932'))!=2 for c in decoded):
                raise ValueError('Expected only double-byte characters in the resource 00 victory set')
            for hi,lo in zip(line[::2],line[1::2],strict=True):
                # 10a1c0 subtracts the SJIS high-byte gap before looking up
                # the dense glyph record. The header and tail each consume 12 bytes.
                index=(hi-(0x40 if hi>=0xa0 else 0)-0x81)*192+lo-0x40
                pos=word(0x3aa168+4*index)*312+12
                glyph=font[pos:pos+288]
                if len(glyph)!=288:raise ValueError('Invalid GOTH_24 glyph record')
                glyphs[hi<<8|lo]=glyph
            lines.append(line)
        quotes.append(lines)
    # The game uploads the same original 16-entry CLUT to both font banks.
    out=bytearray(b'SQ00'+struct.pack('<H',len(glyphs))+raw(0x348a48,64))
    for code,glyph in sorted(glyphs.items()):
        out.extend(code.to_bytes(2,'big')+glyph)
    for lines in quotes:
        out.append(len(lines))
        for line in lines:
            out.append(len(line)//2);out.extend(line)
    return bytes(out)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('iso',type=Path,nargs='?',default=ISO_PATH)
    parser.add_argument('--output',type=Path,default=ASSETS/'versus_quotes_00.bin')
    args=parser.parse_args()
    result=extract(args.iso)
    args.output.write_bytes(result)
    print(f'{len(result)} bytes  {hashlib.sha256(result).hexdigest()}')
