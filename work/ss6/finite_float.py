"""Independent rational implementation of the documented finite model.

Only explicit opt-in tests use this model. The original probe still rejects
inexact arithmetic by default. MUL's hardware-specific low bit is unresolved.
"""
from fractions import Fraction
from math import isqrt


def value(bits):
    exponent=(bits>>23)&255
    if exponent==255 or (not exponent and bits&0x7fffff):
        raise NotImplementedError('Exceptional float outside finite model')
    if not exponent:
        return Fraction(0)
    mantissa=(bits&0x7fffff)|0x800000
    scale=exponent-150
    return (-1 if bits>>31 else 1)*Fraction(mantissa)*Fraction(2)**scale


def rounded(number):
    number=Fraction(number)
    if not number:
        return 0
    negative=number<0
    number=abs(number)
    exponent=number.numerator.bit_length()-number.denominator.bit_length()
    if number<Fraction(2)**exponent:
        exponent-=1
    if not -126<=exponent<=127:
        raise NotImplementedError('Float range outside finite model')
    significand=int(number/Fraction(2)**(exponent-23))
    return (int(negative)<<31)|((exponent+127)<<23)|(significand&0x7fffff)


def square_root(bits,exact=False):
    number=value(bits)
    if number<0:raise NotImplementedError('Negative square root outside finite model')
    if not number:return bits
    #Independent rational calculation: floor sqrt(n/d) == isqrt(floor(n/d)).
    #Choose its binary exponent before scaling; no host float sqrt involved.
    exponent=(number.numerator.bit_length()-number.denominator.bit_length())//2
    if number<Fraction(2)**(2*exponent):exponent-=1
    scaled=number/Fraction(2)**(2*(exponent-23))
    significand=isqrt(scaled.numerator//scaled.denominator)
    result=rounded(Fraction(significand)*Fraction(2)**(exponent-23))
    if exact and value(result)**2!=number:
        raise NotImplementedError('Inexact square root outside validated probe subset')
    return result


def arithmetic(op,a,b):
    left,right=value(a),value(b)
    if op in ('add','sub'):
        difference=((a>>23)&255)-((b>>23)&255)
        # Mask the smaller operand before arithmetic: one alignment guard
        # bit, as in the researched EE ADD/SUB model. Fraction retains all
        # remaining precision until the explicit result rounding.
        if difference>0:
            b=b&0x80000000 if difference>=25 else b&(~((1<<(difference-1))-1)&0xffffffff)
        elif difference<0:
            a=a&0x80000000 if difference<=-25 else a&(~((1<<(-difference-1))-1)&0xffffffff)
        left,right=value(a),value(b)
        result=left+right if op=='add' else left-right
    elif op=='mul': result=left*right
    elif op=='div': result=left/right
    else: raise ValueError(op)
    if not result:
        if op in ('mul','div'): return (a^b)&0x80000000
        return (a&(b if op=='add' else b^0x80000000))&0x80000000
    return rounded(result)
