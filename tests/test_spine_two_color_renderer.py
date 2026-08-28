from __future__ import annotations

from pathlib import Path
import unittest

from PIL import Image

from bile_workbench.spine_pose_renderer import _apply_slot_tint, render_pose_layers
from bile_workbench.spine_workspace import create_pose_session, load_spine_static_workspace


ROOT = Path(__file__).resolve().parents[1]
ZHENG2 = ROOT / "incoming/cross_era_20260822/征2测试/animation/[mini]effect_ui8.bin"


class SpineTwoColorRendererUnitTests(unittest.TestCase):
    def test_verified_straight_alpha_normal_input_uses_two_color_formula(self) -> None:
        source = Image.new("RGBA", (1, 1), (200, 128, 128, 128))
        output, diagnostic = _apply_slot_tint(source, (1.0, 1.0, 1.0, 1.0), (1.0, 0.0, 0.0), 0)
        self.assertEqual((255, 128, 128, 128), output.getpixel((0, 0)))
        self.assertIn("已应用受限 straight-alpha normal two-color preview", diagnostic or "")

    def test_ambiguous_alpha_or_non_normal_blend_downgrades_to_light_only(self) -> None:
        ambiguous = Image.new("RGBA", (1, 1), (32, 32, 32, 128))
        output, diagnostic = _apply_slot_tint(ambiguous, (0.5, 1.0, 1.0, 1.0), (1.0, 0.0, 0.0), 0)
        self.assertEqual((16, 32, 32, 128), output.getpixel((0, 0)))
        self.assertIn("缺少 straight-alpha 证据", diagnostic or "")
        normal_source = Image.new("RGBA", (1, 1), (255, 255, 255, 255))
        _, non_normal = _apply_slot_tint(normal_source, (1.0, 1.0, 1.0, 1.0), (1.0, 0.0, 0.0), 1)
        self.assertIn("blend_mode 非 normal", non_normal or "")


@unittest.skipUnless(ZHENG2.exists(), "需要用户提供的征2 two-color normal region 样本")
class SpineTwoColorRendererRealSampleTests(unittest.TestCase):
    def test_real_zheng2_verified_normal_region_is_rendered_readonly(self) -> None:
        before = ZHENG2.read_bytes()
        session = create_pose_session(load_spine_static_workspace(ZHENG2), "Cast")
        projection, _ = session.preview(0.06666667014360428)
        self.assertTrue(any(layer.dark_rgb is not None and layer.blend_mode == 0 for layer in projection.layers))
        rendered = render_pose_layers(projection, session.workspace.atlas)
        self.assertGreater(rendered.rendered_layer_count, 0)
        self.assertTrue(any("已应用受限 straight-alpha normal two-color preview" in item for item in rendered.diagnostics))
        self.assertEqual(before, ZHENG2.read_bytes())


if __name__ == "__main__":
    unittest.main()
