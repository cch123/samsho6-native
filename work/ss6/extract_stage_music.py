#!/usr/bin/env python3
"""Extract every original two-channel music stream of both soundtracks, with the stream catalogue."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import struct
from extract_combat_sound_bank import ELF_SHA, ISO, ROOT
from inspect_iso import Iso

ASSETS = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
MANIFEST = ROOT/'outputs/ss6-feasibility/music_streams.json'
HALF = 0x8000
CACHE = 160*2048  # one IOP CD read (ADPCMST.IRX): 160 sectors per channel
TRACKS = 28       # 214210 formats BGM%02d from the request track; 0..27 exist on the disc
CHANNELS = {
    '/BGM1/BGM00_L.VB': '610179619a11ed40dac895df27d72904f3be4d7976c2fc9cb6305248e18c470d',
    '/BGM1/BGM00_R.VB': 'd0672f813d56e11e960516a270bb455aec6100a154fe8bb60b4f3ac85987b3da',
    '/BGM1/BGM01_L.VB': '59cdab697e40dc5b5284396987387a716ba8cca0dbe45de7bc78f6c268a003bf',
    '/BGM1/BGM01_R.VB': '2a49c6e7e69a2a6b50b6de42bd03d83216c23a50fcf27e33d72acb6a9bc09485',
    '/BGM1/BGM02_L.VB': '915e4acbd0e8fa05a2b0131c5b6964caa28d6879f32e437445bef06a99a2da44',
    '/BGM1/BGM02_R.VB': '0781e7f5e3e753f8759f0a402511b56047ac2e57254d3b4787aed897954b5429',
    '/BGM1/BGM03_L.VB': 'a410380cd751d7f5e1606960a70ccebd9a2746cf8719ca7fba78fd0cae9c682d',
    '/BGM1/BGM03_R.VB': 'a739dcc80f9225c1e8d413032625c526be63cf63bc92b0ed913e1e3fafb4145c',
    '/BGM1/BGM04_L.VB': '452e565c19c25ac3e12f2b6852c4b5f568f273e8640cbee8b3c136f54b2e5f87',
    '/BGM1/BGM04_R.VB': '56411cf3167679030c2c2a9195cab67f292914b628df77405e1d251ea2fb399f',
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
    '/BGM2/BGM17_L.VB': '7d612bb5f43f6a17d03e2b0c871811ccbdc8237dba9ba34f7fd7acb3942a3322',
    '/BGM2/BGM17_R.VB': 'eda5991bddece2558c3e83205ad49d63a9fd53c23fbe27ab668f523ab5432219',
    '/BGM2/BGM18_L.VB': '39c64fb89411657dcf166228056228c598300c4a3d64ba5708af6137433facf6',
    '/BGM2/BGM18_R.VB': 'a76e55124c9edd66eb4b9da4ec59b193a0af22692eb87531960305c2591be31d',
    '/BGM2/BGM19_L.VB': '598bbc2affb258c63ff6799deb94bac297e860f3d44820174775a17e6a98f621',
    '/BGM2/BGM19_R.VB': 'a881baf4b21bf9f4fb288d52208134f08a85fbe530a5a19e8434e3750d9fd40e',
    '/BGM2/BGM20_L.VB': '69f5161f7328deceb66685d5a47890c48ce7ffa36a44a4f69ddb3a9a28301986',
    '/BGM2/BGM20_R.VB': 'e89920daea6e838ff6f6aa7647a8f9da48c1ad232867576a24e0d9c6548d972b',
    '/BGM2/BGM21_L.VB': 'e16aed9c73e922cb6e05ec0e84dcd66cfb42b24369157c59a10da6c0550d5aed',
    '/BGM2/BGM21_R.VB': 'd2da983bfd38c008dbdea16500ad6aef664acb68bc5a99fd152498300cea188f',
    '/BGM2/BGM22_L.VB': 'ff36f489409077b5326165b133e488fd8fec2cbdf913ae156aaa430114ebeaa1',
    '/BGM2/BGM22_R.VB': '56f45426a687ac46e2984b57c24954c5b51e06e186033308b163102c513f0405',
    '/BGM2/BGM23_L.VB': 'fc530f6b16e6105ea414e05ec26900f73337b2c0ab44afb47b927f3bd07a7d46',
    '/BGM2/BGM23_R.VB': '0bcbf17d159e9e21510e34dafc63ca15f00f9f1ad7ac1f62d2134c1d41f9eec5',
    '/BGM2/BGM24_L.VB': 'a5782f8a85792955d8a4602560e14bf4b4e11c9c0b135188e9e7d3d48cbaedd6',
    '/BGM2/BGM24_R.VB': '5e340c8b11ee2947d83c5627dcc794bb4e5f0a00e71cd6300da5b654db6905c8',
    '/BGM2/BGM25_L.VB': '59394215190f0edb1bb0121ce6b2397daba0af2e42afb450a461101992f2c666',
    '/BGM2/BGM25_R.VB': '70cdb0c8fdd20450c72f8521cc59aecc852c8e8218296e183e169ea22ec590f9',
    '/BGM2/BGM26_L.VB': 'd8c8d85d782befdec59aabe63ffef90f71df7e769465af05a93cc49728a0c6ec',
    '/BGM2/BGM26_R.VB': '64d6a8d77e02771804b88736056f6e0119af00ddb5411d80daf0d9f18fb1377c',
    '/BGM2/BGM27_L.VB': 'c5efe29b06daec6f88d811212a6f57ac9e363b064492ce58d702e8da47874287',
    '/BGM2/BGM27_R.VB': '000221aa333640695552edcf3e8adea9a1d602c3d870a7332951344040f158c0',
    '/BGM3/BGM00_L.VB': '610179619a11ed40dac895df27d72904f3be4d7976c2fc9cb6305248e18c470d',
    '/BGM3/BGM00_R.VB': 'd0672f813d56e11e960516a270bb455aec6100a154fe8bb60b4f3ac85987b3da',
    '/BGM3/BGM01_L.VB': '59cdab697e40dc5b5284396987387a716ba8cca0dbe45de7bc78f6c268a003bf',
    '/BGM3/BGM01_R.VB': '2a49c6e7e69a2a6b50b6de42bd03d83216c23a50fcf27e33d72acb6a9bc09485',
    '/BGM3/BGM02_L.VB': '57845387ac8d0543a2b304361ffd579c95c8219884fd88f281d221fc4ac00bd9',
    '/BGM3/BGM02_R.VB': '31009aa3dbd2e1f33d4f47427487647ea5d768cae248c3c27621e9b5b29acfa5',
    '/BGM3/BGM03_L.VB': '0a6bfaa4ca54b255ee04e2f89f275a43eaf28471d9225fc02af3cf0dd7f828e6',
    '/BGM3/BGM03_R.VB': '506b32e5cbca056f96b1b352b8108907aafc94fc9c794f37b32ec5ab59ee52ed',
    '/BGM3/BGM04_L.VB': '452e565c19c25ac3e12f2b6852c4b5f568f273e8640cbee8b3c136f54b2e5f87',
    '/BGM3/BGM04_R.VB': '56411cf3167679030c2c2a9195cab67f292914b628df77405e1d251ea2fb399f',
    '/BGM3/BGM05_L.VB': 'f079aae3863ffb9ffb2f7c845d0d6f00466bd7b367f87637026462b452fc31f2',
    '/BGM3/BGM05_R.VB': '77e8dd523fbec6cd1672eed4a418ec5fa5d7a8167a821575de1b94fd174fd124',
    '/BGM3/BGM06_L.VB': 'f556dffba800665adf92222054ad600a7ece8fffdf6bdb13e7fd753bc721300d',
    '/BGM3/BGM06_R.VB': '4a701fd33bf34f59900cb0873d586fe9e377980e09517a1b50ed0c5204efbdbf',
    '/BGM3/BGM07_L.VB': '36f4979164c7de2bfbf968110cb1181e9918cedddf5da7e57ac41f30f9d23371',
    '/BGM3/BGM07_R.VB': 'e2175c8218eb2ac0f26173814d792cfb48e21b3edbb767ef83e38e3cb13160a3',
    '/BGM3/BGM08_L.VB': '0b6d83dffcc4271b07786233f28827a8738ff00711228d7b11d3c9a8df2e542a',
    '/BGM3/BGM08_R.VB': '6ed2f9d8805cd16f3afd3b6f7b249fb3a09b802b3460617e4cc6604d9f39e666',
    '/BGM3/BGM09_L.VB': 'ca95477be6afe0058ec3ed377c5e6c06e34e80435e7e462d2f37eb884c792376',
    '/BGM3/BGM09_R.VB': '61633844bd2bea0f778d0d928be4bcddf8c669a393ec9b5739199740a824e30c',
    '/BGM3/BGM10_L.VB': '69ce511dd7e7e822536290cca38fab45f85a9d9ff598d42ce4c7a48b7d7b42c6',
    '/BGM3/BGM10_R.VB': 'd466662a2b9f84ff221f25cce78670d6997592f4d5455e96133fab547bfa2b1a',
    '/BGM3/BGM11_L.VB': '6d0e34edf4271cf26992975b2398bd0805be8dec14e5e23779cab707d8e164a2',
    '/BGM3/BGM11_R.VB': '7d94612c3db90510b598efedd95800ac686fa55a818a7ed8500a5ee2e99dcb9f',
    '/BGM3/BGM12_L.VB': '4e53560116da305030bc06bf7714542cb6be9317e80376d452f8ed5dcbb6e2c8',
    '/BGM3/BGM12_R.VB': '56491397d9fde134f150270424ef7750f198c3d8d0b217e99f4fa498767fdd59',
    '/BGM3/BGM13_L.VB': '3b5896ece98018080a7ae7781fbcd2230d81753978fb0b018eff2e163b17b7f0',
    '/BGM3/BGM13_R.VB': '1dfed70ba9ee86016f1f3429dae8e76de656ca257042afce568685f0b027edd3',
    '/BGM3/BGM14_L.VB': 'a82361b47a0aec583505f48d42308b8617bf4255cb4e0ffd31d8368bc94bef39',
    '/BGM3/BGM14_R.VB': 'e3ca7a6017588063d07cd4251a885e727a3916e8297f08ed0bcca884621a036c',
    '/BGM4/BGM15_L.VB': 'c25bb3070a677d147e9ae1015c842ae9ab77260d993fa7a214dedeac88749ede',
    '/BGM4/BGM15_R.VB': '98a96a0402112be51fdc8eeba61124eaae62b8b60cdc9053fee7b7bcc3b9e1ac',
    '/BGM4/BGM16_L.VB': 'f5a88e0b0a8f25a36e8bd60248dcf1a5cc4f67a8a893d967da6f65f23d0e7c61',
    '/BGM4/BGM16_R.VB': '8ed1aa94fe9095390292918094294285f3079e4b56834e649103c7ac12d7abfa',
    '/BGM4/BGM17_L.VB': '7d612bb5f43f6a17d03e2b0c871811ccbdc8237dba9ba34f7fd7acb3942a3322',
    '/BGM4/BGM17_R.VB': 'eda5991bddece2558c3e83205ad49d63a9fd53c23fbe27ab668f523ab5432219',
    '/BGM4/BGM18_L.VB': '39c64fb89411657dcf166228056228c598300c4a3d64ba5708af6137433facf6',
    '/BGM4/BGM18_R.VB': 'a76e55124c9edd66eb4b9da4ec59b193a0af22692eb87531960305c2591be31d',
    '/BGM4/BGM19_L.VB': '598bbc2affb258c63ff6799deb94bac297e860f3d44820174775a17e6a98f621',
    '/BGM4/BGM19_R.VB': 'a881baf4b21bf9f4fb288d52208134f08a85fbe530a5a19e8434e3750d9fd40e',
    '/BGM4/BGM20_L.VB': '69f5161f7328deceb66685d5a47890c48ce7ffa36a44a4f69ddb3a9a28301986',
    '/BGM4/BGM20_R.VB': 'e89920daea6e838ff6f6aa7647a8f9da48c1ad232867576a24e0d9c6548d972b',
    '/BGM4/BGM21_L.VB': 'e16aed9c73e922cb6e05ec0e84dcd66cfb42b24369157c59a10da6c0550d5aed',
    '/BGM4/BGM21_R.VB': 'd2da983bfd38c008dbdea16500ad6aef664acb68bc5a99fd152498300cea188f',
    '/BGM4/BGM22_L.VB': 'ff36f489409077b5326165b133e488fd8fec2cbdf913ae156aaa430114ebeaa1',
    '/BGM4/BGM22_R.VB': '56f45426a687ac46e2984b57c24954c5b51e06e186033308b163102c513f0405',
    '/BGM4/BGM23_L.VB': 'fc530f6b16e6105ea414e05ec26900f73337b2c0ab44afb47b927f3bd07a7d46',
    '/BGM4/BGM23_R.VB': '0bcbf17d159e9e21510e34dafc63ca15f00f9f1ad7ac1f62d2134c1d41f9eec5',
    '/BGM4/BGM24_L.VB': 'a5782f8a85792955d8a4602560e14bf4b4e11c9c0b135188e9e7d3d48cbaedd6',
    '/BGM4/BGM24_R.VB': '5e340c8b11ee2947d83c5627dcc794bb4e5f0a00e71cd6300da5b654db6905c8',
    '/BGM4/BGM25_L.VB': 'e5ba872d669fec2f0da41953ee0be7330f641166e0c83973fac48cc378930d25',
    '/BGM4/BGM25_R.VB': 'ff857601a536763014622416c1c45e494c4fdd42cad29741be05ddb8c878c73c',
    '/BGM4/BGM26_L.VB': 'd8c8d85d782befdec59aabe63ffef90f71df7e769465af05a93cc49728a0c6ec',
    '/BGM4/BGM26_R.VB': '64d6a8d77e02771804b88736056f6e0119af00ddb5411d80daf0d9f18fb1377c',
    '/BGM4/BGM27_L.VB': 'c5efe29b06daec6f88d811212a6f57ac9e363b064492ce58d702e8da47874287',
    '/BGM4/BGM27_R.VB': '000221aa333640695552edcf3e8adea9a1d602c3d870a7332951344040f158c0',
}


def directory(track, variant):
    # 214210: BGM1 below track 15, BGM2 below 29, BGM3 beyond; a non-zero
    # soundtrack byte 43d056 (copied to 1553b54 by every request) adds two.
    return (1 if track < 15 else 2 if track < 29 else 3)+(2 if variant else 0)


def tail(iso, path, size):
    """Bytes the IOP uploads after EOF to complete the final 32 KiB SPU half.

    The last half of a stream whose size is not a multiple of 32 KiB still
    transfers whole. A stream of at most one cache read was read in full 160
    sectors, so the padding is the disc data following the file. A longer
    stream ends with a short read whose unread remainder still holds the
    previous fill of that buffer, 160 sectors earlier in the same file."""
    pad = -size % HALF
    if not pad: return b''
    if size <= CACHE:
        return iso.read_at(iso.by_path[path]['lba']*iso.block+size, pad)
    return iso.read(path)[size-CACHE:size-CACHE+pad]


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('iso', nargs='?', type=Path, default=ISO)
    cli.add_argument('--assets', type=Path, default=ROOT/'work/ss6/extracted/resources')
    args = cli.parse_args()
    source = Iso(args.iso)
    if sha256(source.read('/SLPS_255.59')).hexdigest() != ELF_SHA:
        raise ValueError('Unsupported disc revision')
    catalogue = bytearray(b'S6BGMv01')+struct.pack('<I', 2*TRACKS)
    manifest = []
    for variant in range(2):
        for track in range(TRACKS):
            d = directory(track, variant)
            raws = []
            for side in 'LR':
                path = f'/BGM{d}/BGM{track:02}_{side}.VB'
                raw = source.read(path)
                if sha256(raw).hexdigest() != CHANNELS[path]: raise ValueError(f'Unexpected music stream {path}')
                raws.append((path, raw))
            size = len(raws[0][1])
            if len(raws[1][1]) != size or size % 16: raise ValueError(f'Unequal stereo stream {track}')
            # The arranged soundtrack reuses some recordings byte for byte.
            own = variant == 1 and any(raw != source.read(f'/BGM{directory(track, 0)}/BGM{track:02}_{s}.VB')
                                       for (_, raw), s in zip(raws, 'LR'))
            tails = [tail(source, path, size) for path, _ in raws]
            for (path, raw), side in zip(raws, 'lr'):
                if variant == 0 or own:
                    name = f'bgm{track:02}{"a" if own else ""}_{side}.vb'
                    (args.assets/name).write_bytes(raw)
                    if ASSETS.is_dir(): shutil.copyfile(args.assets/name, ASSETS/name)
            catalogue += struct.pack('<IBBH', size, d, int(own), len(tails[0]))+tails[0]+tails[1]
            manifest.append(dict(variant=variant, track=track, directory=f'BGM{d}', bytes=size, own_asset=own,
                                 tail_bytes=len(tails[0]), files=[p for p, _ in raws]))
    (args.assets/'music_streams.bin').write_bytes(catalogue)
    if ASSETS.is_dir(): shutil.copyfile(args.assets/'music_streams.bin', ASSETS/'music_streams.bin')
    MANIFEST.write_text(json.dumps(dict(elf_sha256=ELF_SHA, catalogue_sha256=sha256(catalogue).hexdigest(),
                                        catalogue_bytes=len(catalogue), streams=manifest), indent=1)+'\n')
    print(len(catalogue), sha256(catalogue).hexdigest())


if __name__ == '__main__': main()
