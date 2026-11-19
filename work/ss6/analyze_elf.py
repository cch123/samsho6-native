#!/usr/bin/env python3
"""Static inspection helpers; never executes or modifies the PS2 executable."""
import argparse
import struct
from pathlib import Path
import capstone
from inspect_iso import Elf

ELF_PATH = Path(__file__).parent / 'extracted/SLPS_255.59'


def disassemble(elf, start, end):
    decoder = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS64 | capstone.CS_MODE_LITTLE_ENDIAN)
    regs = ['zero','at','v0','v1','a0','a1','a2','a3','t0','t1','t2','t3','t4','t5','t6','t7','s0','s1','s2','s3','s4','s5','s6','s7','t8','t9','k0','k1','gp','sp','fp','ra']
    for address in range(start, end, 4):
        offset = elf.offset(address)
        raw = elf.data[offset:offset+4]
        word, = struct.unpack('<I', raw)
        op, rs, rt, rd, fn = word>>26, (word>>21)&31, (word>>16)&31, (word>>11)&31, word&63
        if op in (0x1e, 0x1f):
            imm = struct.unpack('<h', raw[:2])[0]
            assembly = f'{"lq" if op == 0x1e else "sq"} ${regs[rt]}, {imm:#x}(${regs[rs]}) [EE]'
        elif op in (0, 0x1c) and fn in (0x18, 0x19) and (rd or op == 0x1c):
            name = ('mult' if fn == 0x18 else 'multu') + ('1' if op == 0x1c else '')
            assembly = f'{name} ${regs[rd]}, ${regs[rs]}, ${regs[rt]} [EE]'
        else:
            instructions = list(decoder.disasm(raw, address))
            # Decode each word independently so an unsupported EE instruction
            # cannot silently truncate the rest of the function listing.
            assembly = instructions[0].mnemonic + ' ' + instructions[0].op_str if instructions else f'.word 0x{word:08x} [unclassified]'
        yield f'{address:08x}  {word:08x}  {assembly}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('start', type=lambda x:int(x,0))
    parser.add_argument('end', type=lambda x:int(x,0))
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    text = '\n'.join(disassemble(Elf(ELF_PATH.read_bytes()), args.start, args.end)) + '\n'
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
