from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.glass_effects import (
    GlassBackdropController,
    GlassSpec,
    GlassSpecError,
    glass_overlay_qss,
    parse_glass_spec,
)


class GlassEffectsTests(unittest.TestCase):
    def test_parses_plugin_glass_contract(self) -> None:
        spec = parse_glass_spec({
            "material": "auto",
            "tint": "#112233",
            "opacity": 0.72,
            "blur": 32,
            "border": "#AABBCC",
            "glow": "#DDEEFF",
        })
        self.assertEqual(GlassSpec("auto", "#112233", 0.72, 32, "#AABBCC", "#DDEEFF"), spec)
        overlay = glass_overlay_qss(spec)
        self.assertIn("rgba(17, 34, 51, 184)", overlay)
        self.assertIn("#DDEEFF", overlay)

    def test_rejects_invalid_glass_contract(self) -> None:
        with self.assertRaises(GlassSpecError):
            parse_glass_spec({"material": "blurhash"})
        with self.assertRaises(GlassSpecError):
            parse_glass_spec({"opacity": 1.4})
        with self.assertRaises(GlassSpecError):
            parse_glass_spec({"blur": 100})
        with self.assertRaises(GlassSpecError):
            parse_glass_spec({"tint": "javascript:bad"})

    def test_non_windows_uses_qss_fallback_without_calling_win32(self) -> None:
        controller = GlassBackdropController(object())
        result = controller.apply(GlassSpec())
        if sys.platform != "win32":
            self.assertEqual("fallback", result.mode)
            self.assertFalse(result.native)
            self.assertIn("不是 Windows", result.reason)

    def test_windows_auto_prefers_acrylic_when_mica_is_unavailable(self) -> None:
        class DummyWindow:
            def winId(self) -> int:
                return 1234

        with patch("bile_workbench.glass_effects.sys.platform", "win32"), patch(
            "bile_workbench.glass_effects._try_mica", return_value=False
        ), patch("bile_workbench.glass_effects._try_acrylic", return_value=True) as acrylic:
            result = GlassBackdropController(DummyWindow()).apply(GlassSpec(material="auto"))
        acrylic.assert_called_once()
        self.assertEqual("acrylic", result.mode)
        self.assertTrue(result.native)
        self.assertEqual("Windows Acrylic", result.label)

    def test_none_material_is_explicitly_disabled(self) -> None:
        result = GlassBackdropController(object()).apply(GlassSpec(material="none"))
        self.assertEqual(("none", "未启用玻璃材质", False), (result.mode, result.label, result.native))


if __name__ == "__main__":
    unittest.main()
