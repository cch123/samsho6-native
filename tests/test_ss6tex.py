#!/usr/bin/env python3
"""Texture codec round trips on synthetic data (no game files needed)."""
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'assets'))
import ss6tex  # noqa: E402


class TextureCodec(unittest.TestCase):
    def setUp(self):
        self.random = random.Random(6)
        self.scratch = tempfile.TemporaryDirectory()
        self.root = Path(self.scratch.name)
        (self.root / 'base').mkdir()

    def tearDown(self):
        self.scratch.cleanup()

    def blob(self, size, limit=256):
        return bytes(self.random.randrange(limit) for _ in range(size))

    def palette32(self, alpha_limit):
        return b''.join(self.blob(3) + self.blob(1, alpha_limit) for _ in range(256))

    def round_trip(self, files, **options):
        for name, data in files.items():
            (self.root / 'base' / name).write_bytes(data)
        tex = next(name for name in files if name.endswith('.tex'))
        png = self.root / 'png' / 'picture.png'
        meta = ss6tex.decode(self.root / 'base' / tex, png, **options)
        for produced in ss6tex.encode(png, self.root / 'out'):
            self.assertEqual(produced.read_bytes(), files[produced.name], produced.name)
        return meta

    def test_separate_16_bit_palette(self):
        meta = self.round_trip({'a.tex': self.blob(64 * 64), 'a.pal': self.blob(512)})
        self.assertEqual((meta['width'], meta['height'], meta['palette']['bits']), (64, 64, 16))

    def test_separate_32_bit_palette(self):
        meta = self.round_trip({'b.tex': self.blob(64 * 64), 'b.pal': self.palette32(0x81)})
        self.assertEqual(meta['palette']['alpha'], 'ps2')

    def test_palette_alpha_above_gs_range_is_kept_verbatim(self):
        meta = self.round_trip({'c.tex': self.blob(64 * 64), 'c.pal': self.palette32(256)})
        self.assertEqual(meta['palette']['alpha'], 'raw')

    def test_embedded_palette_uses_csm1_order(self):
        meta = self.round_trip({'d.tex': self.blob(128 * 128) + self.palette32(0x81)})
        self.assertEqual(meta['palette'], {'source': 'embedded', 'order': 'csm1', 'bits': 32, 'alpha': 'ps2'})

    def test_embedded_palette_survives_when_a_palette_file_is_shown(self):
        self.round_trip({'e.tex': self.blob(64 * 64) + self.palette32(0x81), 'e.pal': self.blob(512)},
                        pal_path=self.root / 'base' / 'e.pal')

    def test_wide_page_without_palette(self):
        meta = self.round_trip({'f.tex': self.blob(128 * 64)})
        self.assertEqual((meta['width'], meta['height'], meta['palette']['source']), (128, 64, 'none'))

    def test_explicit_width(self):
        meta = self.round_trip({'g.tex': self.blob(48 * 20)}, width=48)
        self.assertEqual((meta['width'], meta['height']), (48, 20))

    def test_csm1_is_an_involution(self):
        self.assertEqual([ss6tex.csm1(ss6tex.csm1(i)) for i in range(256)], list(range(256)))
        self.assertEqual(ss6tex.csm1(8), 16)

    def test_true_colour_png_is_rejected(self):
        png = self.root / 'rgb.png'
        header = ss6tex._chunk(b'IHDR', ss6tex.struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
        pixels = ss6tex._chunk(b'IDAT', ss6tex.zlib.compress(b'\0\1\2\3'))
        png.write_bytes(ss6tex.PNG_SIGNATURE + header + pixels + ss6tex._chunk(b'IEND', b''))
        with self.assertRaisesRegex(ss6tex.TexError, 'indexed'):
            ss6tex.read_png(png)

    def test_low_bit_depth_and_filtered_png(self):
        # Editors emit 4-bit indices and non-trivial row filters for small palettes.
        width, height, indices = 5, 3, bytes([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15])
        rows, previous = b'', bytes(3)
        for y in range(height):
            line = bytearray(3)
            for x, value in enumerate(indices[y * width:(y + 1) * width]):
                line[x // 2] |= value << (0 if x % 2 else 4)
            kind = (0, 1, 2)[y]
            filtered = bytes((line[x] - ((line[x - 1] if x else 0) if kind == 1 else previous[x] if kind == 2 else 0)) & 255
                             for x in range(3))
            rows += bytes([kind]) + filtered
            previous = bytes(line)
        png = self.root / 'low.png'
        png.write_bytes(ss6tex.PNG_SIGNATURE
                        + ss6tex._chunk(b'IHDR', ss6tex.struct.pack('>IIBBBBB', width, height, 4, 3, 0, 0, 0))
                        + ss6tex._chunk(b'PLTE', bytes(48)) + ss6tex._chunk(b'IDAT', ss6tex.zlib.compress(rows))
                        + ss6tex._chunk(b'IEND', b''))
        self.assertEqual(ss6tex.read_png(png)[:3], (width, height, indices))


if __name__ == '__main__':
    unittest.main()
