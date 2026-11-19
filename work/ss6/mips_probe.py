#!/usr/bin/env python3
"""Bounded EE instruction runner for offline tests, not a PS2 runtime.

Only instructions reached by the selected original functions are supported.
An unknown instruction raises immediately; no hardware or BIOS is emulated.
COP1 rejects inexact arithmetic by default. Explicit finite-model tests opt in
to a separately documented rounding model, not a hardware-accuracy claim.
"""
import struct
import math
from inspect_iso import Elf

MASK64 = (1 << 64) - 1


def signed(value, bits):
    value &= (1 << bits) - 1
    return value - (1 << bits) if value >> (bits-1) else value


class Probe:
    def __init__(self, executable, finite_model=False):
        elf = Elf(executable)
        self.memory = bytearray(32 * 1024 * 1024)
        for section in elf.sections:
            if section['flags'] & 2 and section['type'] != 8:
                self.memory[section['address']:section['address']+section['size']] = executable[section['offset']:section['offset']+section['size']]
        self.registers = [0] * 32
        # Scalar instructions preserve the upper half of the EE's128-bit
        # GPRs. Keep it separate so existing scalar tests stay64-bit.
        self.registers_high = [0] * 32
        self.lo = self.hi = 0
        self.lo1 = self.hi1 = 0
        self.floats = [0] * 32
        self.float_acc = 0
        self.float_condition = False
        self.finite_model = finite_model

    def float_value(self, reg):
        bits = self.floats[reg]
        exponent = bits & 0x7f800000
        if exponent == 0x7f800000 or (exponent == 0 and bits & 0x7fffff):
            raise NotImplementedError('Exceptional EE floating point is outside this probe')
        return struct.unpack('<f', struct.pack('<I', bits))[0]

    def put_exact_float(self, reg, value):
        # The selected movement/rectangle fixtures use exactly representable
        # finite values. Refuse rounding instead of pretending host IEEE math
        # models all EE FPU behavior (denormals, overflow, rounding differences).
        raw = struct.pack('<f', value)
        if not math.isfinite(value) or struct.unpack('<f', raw)[0] != value:
            raise NotImplementedError('Inexact float operation outside validated probe subset')
        self.floats[reg] = struct.unpack('<I', raw)[0]

    def read(self, address, size):
        if not 0 <= address <= len(self.memory)-size:
            raise ValueError(f'Out-of-bounds read {address:#x}')
        return int.from_bytes(self.memory[address:address+size], 'little')

    def write(self, address, value, size):
        if not 0 <= address <= len(self.memory)-size:
            raise ValueError(f'Out-of-bounds write {address:#x}')
        self.memory[address:address+size] = (value & ((1 << (size*8))-1)).to_bytes(size, 'little')

    def put(self, reg, value, word=False):
        if reg:
            self.registers[reg] = (signed(value, 32) if word else value) & MASK64

    def run(self, start, arguments=(), limit=10000, stop_before=(), observe=None):
        self.registers[29] = 0x1fff000
        self.registers[31] = 0x1ffff00
        for i, value in enumerate(arguments):
            self.put(4+i, value)
        pc, pending, count = start, None, 0
        while pc != 0x1ffff00:
            # Explicit basic-block fixture boundary. Stop before executing
            # the address; never skip a callee and resume after its return.
            # Such runs prove only the executed slice, not a whole function.
            if pc in stop_before:
                break
            #Read-only tracing observes the actual path; no callee or opcode
            #is replaced and the observer cannot redirect the program counter.
            if observe is not None:
                observe(pc)
            count += 1
            if count > limit:
                raise RuntimeError(f'Original function exceeded instruction budget at {pc:#x}')
            word = self.read(pc, 4)
            op, rs, rt, rd, sa, fn = word>>26, (word>>21)&31, (word>>16)&31, (word>>11)&31, (word>>6)&31, word&63
            imm = signed(word, 16)
            r = self.registers
            branch, annul = None, False
            if op == 0:
                if fn == 0: self.put(rd, r[rt] << sa, word=True)
                elif fn == 2: self.put(rd, (r[rt]&0xffffffff) >> sa, word=True)
                elif fn == 3: self.put(rd, signed(r[rt],32) >> sa, word=True)
                elif fn == 4: self.put(rd, r[rt] << (r[rs]&31), word=True)
                elif fn == 6: self.put(rd, (r[rt]&0xffffffff) >> (r[rs]&31), word=True)
                elif fn == 7: self.put(rd, signed(r[rt],32) >> (r[rs]&31), word=True)
                elif fn == 0x16: self.put(rd, r[rt] >> (r[rs]&63)) #DSRLV, libc float formatting
                elif fn == 0x38: self.put(rd,r[rt]<<sa)
                elif fn == 0x3a: self.put(rd,r[rt]>>sa)
                elif fn == 0x3c: self.put(rd,r[rt]<<(sa+32))
                elif fn == 0x3e: self.put(rd,r[rt]>>(sa+32))
                elif fn == 0x3f: self.put(rd,signed(r[rt],64)>>(sa+32))
                elif fn == 8: branch = r[rs]
                elif fn == 9:
                    # Capture the target before writing rd: JALR may use
                    # the same register for its source and return address.
                    branch = r[rs]
                    self.put(rd,pc+8)
                elif fn == 0x0a:
                    if r[rt] == 0: self.put(rd, r[rs])
                elif fn == 0x0b:
                    if r[rt] != 0: self.put(rd, r[rs])
                elif fn == 0x10: self.put(rd, self.hi)
                elif fn == 0x11: self.hi = r[rs]  #MTHI:121b80 keeps its CHR pointer in HI.
                elif fn == 0x12: self.put(rd, self.lo)
                elif fn == 0x13: self.lo = r[rs]  # MTLO restores the paired accumulator in 1c1160.
                elif fn in (0x18, 0x19):
                    left = signed(r[rs],32) if fn == 0x18 else r[rs]&0xffffffff
                    right = signed(r[rt],32) if fn == 0x18 else r[rt]&0xffffffff
                    product = left*right
                    self.lo, self.hi = signed(product,32)&MASK64, signed(product>>32,32)&MASK64
                    self.put(rd, self.lo)  # EE MULT also writes rd when nonzero.
                elif fn == 0x1a:
                    left, right = signed(r[rs],32), signed(r[rt],32)
                    # These exceptional cases are not needed by the selected
                    # decoder. Refuse them instead of guessing EE DIV results.
                    if right == 0 or (left == -2**31 and right == -1):
                        raise NotImplementedError('Exceptional DIV outside probe subset')
                    quotient = abs(left)//abs(right) * (-1 if (left<0)!=(right<0) else 1)
                    self.lo = signed(quotient,32)&MASK64
                    self.hi = signed(left-quotient*right,32)&MASK64
                elif fn == 0x1b:
                    left,right=r[rs]&0xffffffff,r[rt]&0xffffffff
                    if right==0:raise NotImplementedError('DIVU by zero outside probe subset')
                    # EE stores sign-extended words in the64-bit HI/LO
                    # halves even though the division operands are unsigned.
                    self.lo=signed(left//right,32)&MASK64
                    self.hi=signed(left%right,32)&MASK64
                elif fn == 0x21: self.put(rd, r[rs]+r[rt], word=True)
                elif fn == 0x23: self.put(rd, r[rs]-r[rt], word=True)
                elif fn == 0x24: self.put(rd, r[rs]&r[rt])
                elif fn == 0x25: self.put(rd, r[rs]|r[rt])
                elif fn == 0x26: self.put(rd, r[rs]^r[rt])
                elif fn == 0x27: self.put(rd, ~(r[rs]|r[rt]))
                elif fn == 0x2a: self.put(rd, int(signed(r[rs],64)<signed(r[rt],64)))
                elif fn == 0x2b: self.put(rd, int(r[rs]<r[rt]))
                elif fn == 0x2d: self.put(rd, r[rs]+r[rt])
                elif fn == 0x2f: self.put(rd, r[rs]-r[rt])
                else: raise NotImplementedError(f'{pc:#x}: SPECIAL {word:#010x}')
            elif op in (2,3):
                branch = ((pc+4)&0xf0000000) | ((word&0x3ffffff)<<2)
                if op == 3: self.put(31,pc+8)
            elif op in (1,4,5,6,7,0x14,0x15,0x16,0x17):
                if op == 1:
                    if rt not in (0,1,2,3): raise NotImplementedError('REGIMM variant')
                    take = (signed(r[rs],64)<0) if rt in (0,2) else (signed(r[rs],64)>=0)
                    likely = rt in (2,3)
                else:
                    base = op & 0xf
                    take = {4:r[rs]==r[rt],5:r[rs]!=r[rt],6:signed(r[rs],64)<=0,7:signed(r[rs],64)>0}[base]
                    likely = op >= 0x14
                if take: branch = pc+4+(imm<<2)
                elif likely: annul = True
            elif op == 9: self.put(rt,r[rs]+imm,word=True)
            elif op == 0x19: self.put(rt,r[rs]+imm)
            elif op == 0x0a: self.put(rt,int(signed(r[rs],64)<imm))
            elif op == 0x0b: self.put(rt,int(r[rs]<(imm&MASK64)))
            elif op == 0x0c: self.put(rt,r[rs]&(word&65535))
            elif op == 0x0d: self.put(rt,r[rs]|(word&65535))
            elif op == 0x0e: self.put(rt,r[rs]^(word&65535))
            elif op == 0x0f: self.put(rt,(word&65535)<<16,word=True)
            elif op == 0x1c and ((fn==8 and sa==9) or (fn==9 and sa==0x12) or (fn==0x29 and sa==0x13)):
                a=r[rs]|(self.registers_high[rs]<<64);b=r[rt]|(self.registers_high[rt]<<64)
                if fn==8: #PSUBB: wrapping subtraction within each byte, no borrow across lanes.
                    value=sum((((a>>(i*8))-(b>>(i*8)))&255)<<(i*8) for i in range(16))
                elif fn==9:value=a&b #PAND
                else:value=(~(a|b))&((1<<128)-1) #PNOR
                if rd:
                    self.put(rd,value&MASK64);self.registers_high[rd]=value>>64
            elif op == 0x1c and fn == 0x29 and sa == 0x1b:  # PCPYH
                low,high=r[rt]&0xffff,self.registers_high[rt]&0xffff
                if rd:
                    self.put(rd,low*0x0001000100010001)
                    self.registers_high[rd]=high*0x0001000100010001
            elif op == 0x1c and fn == 0x09 and sa == 0x0e:  # PCPYLD
                low,high=r[rt],r[rs]
                if rd:
                    self.put(rd,low)
                    self.registers_high[rd]=high
            elif op == 0x1c and fn in (0x18,0x19):  # MULT1/MULTU1
                product = signed(r[rs],32)*signed(r[rt],32) if fn==0x18 else (r[rs]&0xffffffff)*(r[rt]&0xffffffff)
                self.lo1, self.hi1 = signed(product,32)&MASK64, signed(product>>32,32)&MASK64
                self.put(rd,self.lo1)
            elif op == 0x1c and fn in (0,0x20):  #MADD/MADD1, independent accumulator pairs
                lo,hi=(self.lo1,self.hi1) if fn==0x20 else (self.lo,self.hi)
                value=((hi&0xffffffff)<<32)|(lo&0xffffffff)
                value+=signed(r[rs],32)*signed(r[rt],32)
                lo,hi=signed(value,32)&MASK64,signed(value>>32,32)&MASK64
                if fn==0x20:self.lo1,self.hi1=lo,hi
                else:self.lo,self.hi=lo,hi
                self.put(rd,lo)
            elif op == 0x1c and fn == 0x30 and sa == 0:  # PMFHL.LW
                if rd:
                    self.put(rd,(self.lo&0xffffffff)|((self.hi&0xffffffff)<<32))
                    self.registers_high[rd]=(self.lo1&0xffffffff)|((self.hi1&0xffffffff)<<32)
            elif op == 0x1c and fn == 0x29 and sa == 0x0e:  # PCPYUD
                low,high=self.registers_high[rs],self.registers_high[rt]
                if rd:
                    self.put(rd,low);self.registers_high[rd]=high
            elif op in (0x31,0x39):
                address = (r[rs]+imm)&MASK64
                if op == 0x31: self.floats[rt] = self.read(address,4)
                else: self.write(address,self.floats[rt],4)
            elif op == 0x11:
                # COP1 fields reuse rd/sa as fs/fd. Only exact finite scalar
                # arithmetic and bounded truncation are needed by these tests.
                if rs == 0: self.put(rt,self.floats[rd],word=True)
                elif rs == 4: self.floats[rd] = r[rt]&0xffffffff
                elif rs == 8:
                    if rt not in (0,1,2,3): raise NotImplementedError('COP1 branch variant')
                    take = self.float_condition == bool(rt&1)
                    if take: branch = pc+4+(imm<<2)
                    elif rt&2: annul = True
                elif rs == 20 and fn == 0x20:
                    if self.finite_model:
                        from finite_float import rounded
                        self.floats[sa] = rounded(signed(self.floats[rd],32))
                    else: self.put_exact_float(sa,signed(self.floats[rd],32))
                elif rs == 16 and fn == 0x18:  # ADDA.S sets ACC for the VS portrait's subsequent MADD.S.
                    if self.finite_model:
                        from finite_float import arithmetic
                        self.float_acc=arithmetic('add',self.floats[rd],self.floats[rt])
                    else:
                        value=self.float_value(rd)+self.float_value(rt)
                        packed=struct.pack('<f',value)
                        if struct.unpack('<f',packed)[0]!=value: raise NotImplementedError('Inexact ADDA.S')
                        self.float_acc=struct.unpack('<I',packed)[0]
                elif rs == 16 and fn in (0x19,0x1a,0x1c,0x1d,0x1e):
                    # EE MULA.S writes ACC; MADD.S/MSUB.S read ACC without
                    # changing it. The optional finite model rounds MUL and
                    # the subsequent ADD/SUB
                    # separately. This remains a model, not hardware proof.
                    if self.finite_model:
                        from finite_float import arithmetic
                        product = arithmetic('sub' if fn==0x19 else 'mul',self.floats[rd],self.floats[rt])
                        if fn in (0x19,0x1a): self.float_acc = product
                        elif fn==0x1e: self.float_acc=arithmetic('add',self.float_acc,product)  # MADDA.S
                        else: self.floats[sa] = arithmetic('sub' if fn==0x1d else 'add',self.float_acc,product)
                    else:
                        product = self.float_value(rd)-self.float_value(rt) if fn==0x19 else self.float_value(rd)*self.float_value(rt)
                        packed = struct.pack('<f',product)
                        if struct.unpack('<f',packed)[0] != product:
                            raise NotImplementedError('Inexact ACC multiply outside validated probe subset')
                        if fn in (0x19,0x1a): self.float_acc = struct.unpack('<I',packed)[0]
                        else:
                            from finite_float import value
                            total=float(value(self.float_acc))+(-product if fn==0x1d else product)
                            if fn==0x1e:
                                packed=struct.pack('<f',total)
                                if struct.unpack('<f',packed)[0]!=total: raise NotImplementedError('Inexact MADDA.S')
                                self.float_acc=struct.unpack('<I',packed)[0]
                            else: self.put_exact_float(sa,total)
                elif rs == 16 and fn == 4:
                    from finite_float import square_root
                    # R5900 SQRT.S encodes the input in FT. Mamahaha's 1a3a00
                    # uses f1 for FT/FD with FS zero, exposing a source mix-up.
                    bits = self.floats[rt]
                    # After the riding callback's 32-bit integer square overflows,
                    # EE SQRT.S returns sqrt(abs(FT)); its invalid flag is unused here.
                    # See PCSX2 pcsx2/FPU.cpp, COP1::SQRT_S. Leave other exceptional
                    # inputs outside this finite, instruction-local oracle.
                    if self.finite_model and pc in (0x1eca70,0x1ecaf8):
                        bits &= 0x7fffffff
                    self.floats[sa] = square_root(bits,exact=not self.finite_model)
                # These two exact hardware vectors occur together in Ten's
                # full-health explosion (11f374). Keep every other unsupported
                # exceptional operand gated by the ordinary finite model.
                elif self.finite_model and rs==16 and fn==3 and self.floats[rd]==self.floats[rt]==0:
                    self.floats[sa]=0x7fffffff  # ps2autotests ee_fpu/muldiv.expected
                elif self.finite_model and rs==16 and fn==0x24 and self.floats[rd]==0x7fffffff:
                    self.floats[sa]=0x7fffffff  # ps2autotests ee_fpu/convert.expected
                elif rs == 16 and fn in (0,1,2,3,6,7,0x24,0x32,0x34,0x36):
                    left = self.float_value(rd)
                    if fn == 6: self.floats[sa] = self.floats[rd]
                    elif fn == 7: self.floats[sa] = self.floats[rd]^0x80000000
                    elif fn == 0x24:
                        if not -(1<<31)<=left<(1<<31): raise NotImplementedError('Float conversion overflow')
                        self.floats[sa] = int(left)&0xffffffff
                    elif fn in (0x32,0x34,0x36):
                        right = self.float_value(rt)
                        self.float_condition = left==right if fn==0x32 else left<right if fn==0x34 else left<=right
                    elif self.finite_model:
                        from finite_float import arithmetic
                        self.floats[sa] = arithmetic(('add','sub','mul','div')[fn],self.floats[rd],self.floats[rt])
                    else:
                        right = self.float_value(rt)
                        value = left+right if fn==0 else left-right if fn==1 else left*right if fn==2 else left/right
                        self.put_exact_float(sa,value)
                else: raise NotImplementedError(f'{pc:#x}: unsupported COP1 {word:#010x}')
            elif op in (0x20,0x21,0x23,0x24,0x25,0x27,0x37):
                size = {0x20:1,0x21:2,0x23:4,0x24:1,0x25:2,0x27:4,0x37:8}[op]
                value = self.read((r[rs]+imm)&MASK64,size)
                self.put(rt,signed(value,size*8) if op in (0x20,0x21,0x23) else value)
            elif op == 0x1e:  #LQ, used by the original vector strlen.
                address=(r[rs]+imm)&MASK64
                if address&15: raise NotImplementedError('Unaligned LQ outside probe subset')
                value=self.read(address,16)
                if rt:
                    self.put(rt,value&MASK64);self.registers_high[rt]=value>>64
            elif op == 0x1f:  # SQ, used by the original aligned memset.
                address=(r[rs]+imm)&MASK64
                if address&15: raise NotImplementedError('Unaligned SQ outside probe subset')
                self.write(address,r[rt]|(self.registers_high[rt]<<64),16)
            elif op in (0x28,0x29,0x2b,0x3f):
                size = {0x28:1,0x29:2,0x2b:4,0x3f:8}[op]
                self.write((r[rs]+imm)&MASK64,r[rt],size)
            elif op in (0x1a,0x1b,0x2c,0x2d):
                # Little-endian LDL/LDR and SDL/SDR merge bytes. Original
                # event records are 108 bytes, so alternating copies are not
                # eight-byte aligned; treating these as ordinary LD is wrong.
                address = (r[rs]+imm)&MASK64
                base, offset = address&~7, address&7
                left = op in (0x1a,0x2c)
                byte_count = offset+1 if left else 8-offset
                memory_start = base if left else address
                register_start = 8-byte_count if left else 0
                if op in (0x1a,0x1b):
                    shift = register_start*8
                    mask = ((1<<(byte_count*8))-1)<<shift
                    self.put(rt,(r[rt]&~mask)|(self.read(memory_start,byte_count)<<shift))
                else:
                    self.write(memory_start,r[rt]>>(register_start*8),byte_count)
            else: raise NotImplementedError(f'{pc:#x}: opcode {word:#010x}')
            if pending is not None:
                if branch is not None or annul: raise RuntimeError('Branch in delay slot')
                pc, pending = pending, None
            else:
                pc, pending = pc+(8 if annul else 4), branch
        return self.registers[2], count


def idle_fixture(executable, aid, act, speed=256):
    probe = Probe(executable)
    probe.memory[0x46a9b0:0x46a9b0+len(aid)] = aid
    probe.memory[0x1700000:0x1700000+len(act)] = act
    probe.write(0x4751b0,0x1700000,4)
    obj = 0x1e00000
    probe.write(obj+0x30,speed,4)
    return probe, obj
