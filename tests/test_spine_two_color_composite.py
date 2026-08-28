from __future__ import annotations

import unittest

from PIL import Image

from bile_workbench.spine_two_color_composite import TwoColorCompositeError, compose_two_color_straight_alpha


class SpineTwoColorCompositeTests(unittest.TestCase):
    def test_straight_alpha_tint_black_formula_for_exact_pixels(self) -> None:
        source = Image.new("RGBA", (4, 1))
        source.putdata(((255, 255, 255, 255), (0, 0, 0, 255), (128, 128, 128, 255), (90, 30, 15, 0)))
        output = compose_two_color_straight_alpha(source, (0.8, 0.6, 0.4, 0.5), (0.2, 0.3, 0.4))
        self.assertEqual(
            ((204, 153, 102, 128), (51, 76, 102, 128), (128, 115, 102, 128), (0, 0, 0, 0)),
            tuple(output.getdata()),
        )

    def test_source_alpha_and_light_alpha_are_preserved_as_normal_alpha(self) -> None:
        source = Image.new("RGBA", (1, 1), (51, 102, 153, 128))
        output = compose_two_color_straight_alpha(source, (1.0, 1.0, 1.0, 0.5), (0.0, 0.0, 0.0))
        self.assertEqual((51, 102, 153, 64), output.getpixel((0, 0)))

    def test_invalid_channels_are_rejected_without_fallback(self) -> None:
        source = Image.new("RGBA", (1, 1), (255, 255, 255, 255))
        with self.assertRaisesRegex(TwoColorCompositeError, "light_rgba"):
            compose_two_color_straight_alpha(source, (1.0, 1.0, 1.0, 1.1), (0.0, 0.0, 0.0))
        with self.assertRaisesRegex(TwoColorCompositeError, "dark_rgb"):
            compose_two_color_straight_alpha(source, (1.0, 1.0, 1.0, 1.0), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
