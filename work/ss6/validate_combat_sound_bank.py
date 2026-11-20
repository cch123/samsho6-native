#!/usr/bin/env python3
"""Check the actual Japanese sound-directory lookups and decoded SPU samples."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from extract_combat_sound_bank import ELF_SHA, ISO, OUT, ROOT, extract
from inspect_iso import Iso
from mips_probe import Probe
from round_entry_oracle import buffered_stdout

REPORT = ROOT / 'outputs/ss6-feasibility/combat-sound-bank-validation.json'
CODEC_SOURCE = 'https://raw.githubusercontent.com/PCSX2/pcsx2/v2.4.0/pcsx2/SPU2/Mixer.cpp'
CODEC_HASH = 'ca74868bc51f9eafd5661a784f82eabbb3b49349d13207a12ba5104603ad5239'
# SHA-256 of the reference decoder's concatenated mono int16le output, in the
# stable test order below. The optional reference build recreates it offline.
GOLDEN_PCM = '0bd17f60a749b6f67ef0ba8f01653b0a585e7bf83c4b5da0a61a87ecab263c8e'

DRIVER = r"""
#include "combat_sound_bank.hpp"
#include <bit>
#include <iostream>
void word(uint32_t value) {std::cout.write(reinterpret_cast<const char*>(&value),4);}
int main(int argc,char** argv) {
    static_assert(std::endian::native==std::endian::little);
    ss6::CombatSoundBank bank(argv[1]);
    for(unsigned group=0;group<7;++group) {
        for(unsigned tone=0;;++tone) {
            const auto* sample=group<3 ? bank.find(group,tone) :
                group==3 ? bank.voice(tone) : group==4 ? bank.residentVoice(tone) :
                bank.narrator(tone,group-5);
            if(!sample)break;
            word(group);word(tone);word(sample->sourceOffset);word(sample->volumeCode);
            word(sample->pitch);word(uint32_t(sample->loopStart));word(uint32_t(sample->loopEnd));
            word(sample->raw.size());word(sample->pcm.size());
            std::cout.write(reinterpret_cast<const char*>(sample->raw.data()),sample->raw.size());
            std::cout.write(reinterpret_cast<const char*>(sample->pcm.data()),sample->pcm.size()*2);
        }
    }
    return (bank.find(3,0)||bank.narrator(0,2)) ? 1 : 0;
}
"""
REFERENCE_HEADER = r"""
#include <algorithm>
#include <cstdint>
#include <iostream>
using s16=int16_t; using s32=int32_t; using s8=int8_t;
#define __forceinline inline
namespace SPU2 {
    bool MsgToConsole(){return false;}
    void ConLog(const char*,int){}
}
"""
REFERENCE_MAIN = r"""
int main() {
    uint32_t bytes;
    while(std::cin.read(reinterpret_cast<char*>(&bytes),4)){
        s32 recent=0,older=0;bool ended=false;
        for(unsigned offset=0;offset<bytes;offset+=16){
            s16 encoded[8],decoded[28];
            if(!std::cin.read(reinterpret_cast<char*>(encoded),16))return 1;
            if(ended)continue;
            XA_decode_block(decoded,encoded,recent,older);
            std::cout.write(reinterpret_cast<char*>(decoded),56);
            ended=(encoded[0]&0x0100)!=0;
        }
        if(!ended)return 1;
    }
}
"""


def compile_driver(temp, name, code, objects=()):
    source = temp / (name + '.cpp')
    binary = temp / name
    source.write_text(code)
    subprocess.run(['c++', '-std=c++20','-ffp-contract=off', '-O2', '-I', str(ROOT / 'src'), str(source),
                    *map(str, objects), '-o', str(binary)], check=True)
    return binary


def upstream(temp, path, encoded):
    data = path.read_bytes()
    assert sha256(data).hexdigest() == CODEC_HASH
    source = data.decode()
    start = source.index('static const s32 tbl_XA_Factor')
    end = source.index('static void __forceinline IncrementNextA', start)
    # The standalone reference compiles the original decoder verbatim. No
    # upstream code or executable is linked into or needed by the game.
    binary = compile_driver(temp, 'reference', REFERENCE_HEADER + source[start:end] + REFERENCE_MAIN)
    return subprocess.check_output([str(binary)], input=encoded)


def compare(args, temp):
    iso = Iso(args.iso)
    executable = iso.read('/SLPS_255.59')
    assert sha256(executable).hexdigest() == ELF_SHA
    p = Probe(executable, finite_model=True)
    headers = {}
    for name, addr in [('BVOICE2', 0x5a0a98), ('BVOICE1', 0x59d028), ('NAL', 0x5a89c8)]:
        headers[name] = iso.read('/VOICE/' + name + '.MSH')
        p.memory[addr:addr+len(headers[name])] = headers[name]
    # In a mirror match the original 212dd8 bank-assignment words are 50/0/0.
    for slot, group in enumerate((50, 0, 0)):
        p.write(0x59d018 + 4 * slot, group, 4)
    groups = [('BVOICE2', 50, 592), ('BVOICE2', 0, 592), ('BVOICE2', 0, 592),
              ('BVOICE1', 0, 272), ('BVOICE1', 49, 272), ('NAL', 0, 528), ('NAL', 1, 528)]
    assert extract(iso) == args.asset.read_bytes()
    binary = compile_driver(temp, 'native', DRIVER, [ROOT/'src/combat_sound_bank.cpp'])
    buffer = subprocess.check_output([str(binary), str(args.asset.parent)])
    seen, calls = Counter(), Counter()
    encoded, decoded = bytearray(), bytearray()
    pos = insns = 0
    for g, (name, group, stride) in enumerate(groups):
        h = headers[name]
        lba, count = struct.unpack_from('<2I', h, stride*group)
        extent = iso.by_path['/VOICE/'+name+'.MSB']['lba'] + lba
        for tone in range(count):
            buffered_stdout(p)
            row = (group*stride + 16 + tone*8)
            off = struct.unpack_from('<I', h, row+4)[0]
            pitch = 0x3b0 if g < 3 else 0x761
            if g < 3:
                vol, length = struct.unpack_from('<2H', h, row)
                _, n = p.run(0x212fa0, [g,tone], stop_before=(0x213b98,), limit=10000)
                assert p.registers[4:7] == [[0x5010,0x5b010,0xb1010][g]+off,pitch,vol]
                route = '212fa0'
            elif g == 4:
                length = struct.unpack_from('<I', h, row)[0]
                _, n = p.run(0x213378, [50,tone], stop_before=(0x213b98,), limit=10000)
                vol = 15
                assert p.registers[4:7] == [0x146010+off,pitch,vol]
                route = '213378 to resident key-on'
            else:
                vol = 0xffff
                length = struct.unpack_from('<I', h, row)[0]
                p.write(0x59d008, 0, 4)  # Four-entry circular DMA parameter queue.
                if g == 3:
                    _, n = p.run(0x213378, [0,tone], limit=16000)
                    base, route = 0x1466980, '213378 to character stream'
                else:
                    p.write(0x43d055, g-5, 1)
                    # 213040 aliases 44+ to 2+; the public bank has physical indices.
                    _, n = p.run(0x213040, [tone if tone < 44 else tone+42], limit=10000)
                    base, route = 0x1373980, '213040 to narrator stream'
                assert (p.read(0x15539b0,4),p.read(0x15539b8,4),p.read(0x1553988,4)) == (base+off,length,pitch)
            insns += n
            calls[route] += 1
            record = struct.unpack_from('<9I', buffer, pos)
            assert record[:8] == (g,tone,off,vol,pitch,0xffffffff,0xffffffff,length), record
            pos += 36
            raw = iso.read_at(extent * iso.block + off, length)
            assert raw == buffer[pos:pos+length]
            # All six original banks put a mute-end just before the guard.
            assert raw[-31::16] == b'\x01\x07' and not any(raw[1:-32:16])
            pos += length
            samples = (length//16 - 1) * 28
            assert samples == record[8]
            pcm = buffer[pos:pos + samples*2]
            pos += samples*2
            encoded.extend(struct.pack('<I',length) + raw)
            decoded.extend(pcm)
            seen[g] += 1
    assert pos == len(buffer)
    if args.pcsx2_mixer:
        reference = upstream(temp, args.pcsx2_mixer, encoded)
        assert reference == decoded, (len(reference),len(decoded))
    pcm_sha = sha256(decoded).hexdigest()
    assert pcm_sha == GOLDEN_PCM, pcm_sha
    return dict(status='passed', elf_sha256=ELF_SHA, package_sha256=sha256(args.asset.read_bytes()).hexdigest(),
                unique_samples=sum(seen.values())-seen[2], logical_lookups=sum(seen.values()), groups=seen,
                first_pass_pcm_samples=len(decoded)//2, pcm_sha256=pcm_sha, ee_instructions=insns,
                ee_calls=calls, input_source=CODEC_SOURCE, codec_source_sha256=CODEC_HASH,
                native_and_reference_pcm_equal=True, upstream_decoder_rebuilt=bool(args.pcsx2_mixer),
                rates_hz=dict(ordinary=48000*0x3b0/4096, voice=48000*0x761/4096),
                scope='Exact MSH/MSB bytes, EE key-on/stream parameters and first-pass ADPCM, prior to interpolation, ADSR or mixing. SPU2 digital output and physical hardware were not sampled.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iso', type=Path, default=ISO)
    parser.add_argument('--asset', type=Path, default=OUT)
    parser.add_argument('--pcsx2-mixer', type=Path, help='optional local copy of '+CODEC_SOURCE)
    parser.add_argument('--report', type=Path, default=REPORT)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        result = compare(args, Path(directory))
    text = json.dumps(result, indent=2)
    args.report.write_text(text+'\n')
    print(text)


if __name__ == '__main__':
    main()
