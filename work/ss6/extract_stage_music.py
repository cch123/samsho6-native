#!/usr/bin/env python3
"""Extract the Japanese title, selection, twelve stages and victory music as separate original SPU channels."""
import argparse
from hashlib import sha256
from pathlib import Path
from extract_combat_sound_bank import ELF_SHA, ISO, ROOT
from inspect_iso import Iso

CHANNELS = {
    '/BGM1/BGM01_L.VB': '59cdab697e40dc5b5284396987387a716ba8cca0dbe45de7bc78f6c268a003bf',
    '/BGM1/BGM01_R.VB': '2a49c6e7e69a2a6b50b6de42bd03d83216c23a50fcf27e33d72acb6a9bc09485',
    '/BGM1/BGM02_L.VB': '915e4acbd0e8fa05a2b0131c5b6964caa28d6879f32e437445bef06a99a2da44',
    '/BGM1/BGM02_R.VB': '0781e7f5e3e753f8759f0a402511b56047ac2e57254d3b4787aed897954b5429',
    '/BGM1/BGM05_L.VB': '863e4c502f2f04e870c05f03ae267e774155be6c15e57ed70a6581c3dfd27276',
    '/BGM1/BGM05_R.VB': '9ac3cf99956471b68e557eaf7bf78fb5e9fd50ca723840bdca8ad99e2af69d8d',
    '/BGM1/BGM06_L.VB': 'cff16721b897c8edd3e9405b679701c68fa12d590ddf8b84b68210c4e68fc87f',
    '/BGM1/BGM06_R.VB': '40fa61be36acee8309ce8af24ed4de5728922520cd603757835bff68e66d8921',
    '/BGM1/BGM07_L.VB': 'bd34ea219e984ec1124343a148fbc7f8a53b1421240021bdf3a44e6e5ec6a759',
    '/BGM1/BGM07_R.VB': 'c5427f9042d69bf9a0490f82e7b230fb4176070045b2983f5d39419c68f410e5',
    '/BGM1/BGM08_L.VB': '6abcf80932cda8ddc60e5b263c42e26b22d3dcf2d452375962ca05ab5146147a',
    '/BGM1/BGM08_R.VB': '76f6392ee66583bf871260d73be10fb1853955a5357d81c984597c51bc639be9',
    '/BGM1/BGM09_L.VB': '3744d3f0fbd77a192e27647585480e253682390ad7c8e1b027264d3bf01d57a1',
    '/BGM1/BGM09_R.VB': '860876cd1e1689e1517cc8e6641bdf11f898a77eb89d607ea5c9da0e906dadba',
    '/BGM1/BGM10_L.VB': '08eb3662e654fe451b4316d453bacc2da36e5a47031e738dc47cad8e68ccfd8a',
    '/BGM1/BGM10_R.VB': '1be25771311de88528b9b9515760b2aa57e7dc0b2fc4d0ba8e54c646b16cc202',
    '/BGM1/BGM11_L.VB': '464d068bfe7623e5e0efd6dc02e398017f7275f1f71d461d892d05e02eb19a70',
    '/BGM1/BGM11_R.VB': '7ccea5a68aaa0083b71b942abdc61fd3f6d0c071384b345e332afdb35d8dc973',
    '/BGM1/BGM12_L.VB': '9de06e4adbb359899be7b50393bc23f325c24d9c60fd351ac2d64cba1f820837',
    '/BGM1/BGM12_R.VB': '54b9ffd259a31e2b1166650f07010e1168d013fc30e13b29cc4a69209db7d9e4',
    '/BGM1/BGM13_L.VB': 'efd4cbe11b0f48b2d46ff559a7f1e4bb075cd7bc01960b90da60bbb785e8cffb',
    '/BGM1/BGM13_R.VB': 'f95dc8e722fe3e7c35e940bd0fd97cbb0f2d3b5b6d91b047035a058b3f53d561',
    '/BGM1/BGM14_L.VB': '863418c24968d306f56518b5119f179af57bbf8ce186fd774f46e7e85483299f',
    '/BGM1/BGM14_R.VB': '52f48a5924feba28ecda2d51d6f9d27f94f770e3a8230d49de156f65aa733e01',
    '/BGM2/BGM15_L.VB': 'b2bcdf14b3510587e41527d22838d6df118088415c6489a6d0617cd28b1bcbce',
    '/BGM2/BGM15_R.VB': 'fc2a29729d638da7921d6f997c5c0691b24fa0ecadcf02943e85dcce0dd7c119',
    '/BGM2/BGM16_L.VB': 'fd7bf33893bfd0f5ae6c80863dddffb82eaf338d237d00b4e62a38d5baff64aa',
    '/BGM2/BGM16_R.VB': 'b19ac6e8b14a21602524e5249d4800a8eed51f02ee3b7c8adf7d08118de74872',
    '/BGM2/BGM24_L.VB': 'a5782f8a85792955d8a4602560e14bf4b4e11c9c0b135188e9e7d3d48cbaedd6',
    '/BGM2/BGM24_R.VB': '5e340c8b11ee2947d83c5627dcc794bb4e5f0a00e71cd6300da5b654db6905c8',
}
def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('iso',nargs='?',type=Path,default=ISO)
    cli.add_argument('--assets',type=Path,default=ROOT/'work/ss6/extracted/resources')
    args=cli.parse_args()
    source=Iso(args.iso)
    if sha256(source.read('/SLPS_255.59')).hexdigest()!=ELF_SHA:
        raise ValueError('Unsupported disc revision')
    for disc_path,expected in CHANNELS.items():
        # 13abb0 adds five to the stage number; 2140b8 selects BGM1 for the
        # default soundtrack. Each file belongs to its own SPU voice.
        # 1444e4 selects track 24 once the complete set reaches victory.
        name=Path(disc_path).name
        raw=source.read(disc_path)
        if sha256(raw).hexdigest()!=expected:raise ValueError(f'Unexpected music stream {name}')
        if name.startswith('BGM01') and source.read('/BGM3/'+name)!=raw:
            raise ValueError(f'Soundtrack variants differ for {name}')
        (args.assets/name.lower()).write_bytes(raw)
        print(name,len(raw),expected)
if __name__=='__main__':main()
