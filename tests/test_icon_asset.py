import unittest
import struct
from pathlib import Path


class IconAssetTests(unittest.TestCase):
    def test_windows_icon_contains_all_required_sizes(self):
        icon_path = Path(__file__).resolve().parents[1] / "assets" / "rvb_vault.ico"
        self.assertTrue(icon_path.exists())
        raw = icon_path.read_bytes()
        reserved, icon_type, count = struct.unpack_from("<HHH", raw, 0)
        self.assertEqual((reserved, icon_type), (0, 1))
        sizes = set()
        for index in range(count):
            width, height = struct.unpack_from("<BB", raw, 6 + index * 16)
            sizes.add((width or 256, height or 256))
        self.assertEqual(
            sizes,
            {(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)},
        )


if __name__ == "__main__":
    unittest.main()
