#!/usr/bin/env python3
"""Sprite export/import on a synthetic resource (no game files needed)."""
import random
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'assets'))
import ss6sprite  # noqa: E402
import ss6tex  # noqa: E402

RESOURCE = 3


class SpriteSheet(unittest.TestCase):
    def setUp(self):
        self.random = random.Random(6)
        self.scratch = tempfile.TemporaryDirectory()
        self.root = Path(self.scratch.name)
        self.assets = self.root / 'assets'
        self.assets.mkdir()
        # Tile 0 is the empty tile; tiles 1..8 are random.
        chr_data = bytes(32) + bytes(self.random.randrange(256) for _ in range(8 * 32))
        # Image 0: 2x2 tiles, bank 0. Image 1: unused. Image 2: 4x2 tiles, bank 1, shares tile 1.
        first = bytes((2, 2)) + b''.join(t.to_bytes(3, 'little') for t in (1, 2, 0, 3))
        second = bytes((4, 2)) + b''.join(t.to_bytes(3, 'little') for t in (1, 4, 5, 6, 7, 0, 8, 2))
        idx = struct.pack('<3I', 0, ss6sprite.UNUSED, (1 << 24) | len(first))
        palette = bytearray(self.random.randrange(256) for _ in range((RESOURCE * 5 * 32 + 32) * 32))
        for name, data in (('idx', idx), ('map', first + second), ('chr', chr_data)):
            ss6sprite.resource_file(self.assets, name, RESOURCE).write_bytes(data)
        (self.assets / 'pal_all.bin').write_bytes(palette)
        self.art = self.root / 'art'
        self.meta = ss6sprite.export(self.assets, RESOURCE, self.art)

    def tearDown(self):
        self.scratch.cleanup()

    def original(self, kind):
        return ss6sprite.resource_file(self.assets, kind, RESOURCE).read_bytes()

    def test_export_lists_used_images_only(self):
        self.assertEqual([(i['image'], i['bank'], i['width'], i['height']) for i in self.meta['images']],
                         [(0, 0, 16, 16), (2, 1, 32, 16)])
        self.assertEqual(self.meta['palette_key'], RESOURCE * 5)

    def test_unedited_import_writes_nothing(self):
        self.assertEqual(ss6sprite.import_sheet(self.art, self.assets, self.root / 'mod'), [])

    def test_rebuild_preserves_every_pixel(self):
        mod = self.root / 'mod'
        ss6sprite.import_sheet(self.art, self.assets, mod, rebuild_all=True)
        before, after = ss6sprite.Sheet(self.assets, RESOURCE), self.sheet(mod)
        for (_, bank, offset), (_, new_bank, new_offset) in zip(before.images(), after.images(), strict=True):
            self.assertEqual(bank, new_bank)
            self.assertEqual(before.pixels(offset), after.pixels(new_offset))
        # Every tile already existed, so re-encoding must not grow chr.
        self.assertEqual(after.chr, before.chr)

    def sheet(self, mod):
        merged = self.root / 'merged'
        merged.mkdir(exist_ok=True)
        for source in (self.assets, mod):
            for file in source.iterdir():
                (merged / file.name).write_bytes(file.read_bytes())
        return ss6sprite.Sheet(merged, RESOURCE)

    def edit(self, name, change):
        width, height, pixels, palette = ss6tex.read_png(self.art / name)
        pixels = bytearray(pixels)
        change(pixels, palette)
        ss6tex.write_png(self.art / name, width, height, bytes(pixels), palette)

    def test_edited_image_is_appended_and_others_keep_their_bytes(self):
        def paint(pixels, palette):
            pixels[0] = (pixels[0] + 1) % 16
        self.edit('0000.png', paint)
        mod = self.root / 'mod'
        written = ss6sprite.import_sheet(self.art, self.assets, mod)
        self.assertEqual(sorted(p.name for p in written), ['chr_03.bin', 'idx_03.bin', 'map_03.bin'])
        after = self.sheet(mod)
        self.assertTrue(bytes(after.map).startswith(self.original('map')))
        self.assertTrue(bytes(after.chr).startswith(self.original('chr')))
        self.assertEqual(len(after.chr), len(self.original('chr')) + 32)  # one changed tile, three reused
        images = list(after.images())
        self.assertEqual(images[0][:2], (0, 0))
        self.assertEqual(images[0][2], len(self.original('map')))
        self.assertEqual(images[1], (2, 1, 14))
        self.assertEqual(after.pixels(images[0][2])[2], ss6tex.read_png(self.art / '0000.png')[2])

    def test_palette_edit_changes_only_its_group(self):
        self.edit('0002.png', lambda pixels, palette: palette.__setitem__(5, (255, 0, 0, 255)))
        mod = self.root / 'mod'
        written = ss6sprite.import_sheet(self.art, self.assets, mod)
        self.assertEqual([p.name for p in written], ['pal_all.bin'])
        before, after = (self.assets / 'pal_all.bin').read_bytes(), written[0].read_bytes()
        offset = (RESOURCE * 5 * 32 + 1) * 32
        self.assertEqual(struct.unpack_from('<H', after, offset + 10)[0], 0x8000 | (31 << 10))
        self.assertEqual(after[:offset + 10] + after[offset + 12:], before[:offset + 10] + before[offset + 12:])

    def test_more_than_sixteen_colours_is_rejected(self):
        self.edit('0000.png', lambda pixels, palette: pixels.__setitem__(0, 16))
        with self.assertRaisesRegex(ss6sprite.SpriteError, '16 colours'):
            ss6sprite.import_sheet(self.art, self.assets, self.root / 'mod')

    def test_size_must_be_whole_cells(self):
        ss6tex.write_png(self.art / '0000.png', 24, 16, bytes(24 * 16), [(0, 0, 0, 0)] * 16)
        with self.assertRaisesRegex(ss6sprite.SpriteError, 'multiple of 16'):
            ss6sprite.import_sheet(self.art, self.assets, self.root / 'mod')


if __name__ == '__main__':
    unittest.main()
