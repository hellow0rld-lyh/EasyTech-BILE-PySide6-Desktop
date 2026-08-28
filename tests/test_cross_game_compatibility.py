"""用户提供的跨游戏资源验证集回归。

数据集未随源码发布；若 `cross_game_assets/` 不存在则自动跳过。
"""
from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import BileFormatError, parse_bytes, parse_file
from bile_workbench.composition_experiment import create_composition_experiment_package
from bile_workbench.diagnostics import collect_diagnostics
from bile_workbench.preview_renderer import load_atlas, render_frame

DATA_ROOT = ROOT / "cross_game_assets"
DATASETS = {
    "general3": DATA_ROOT / "general3",
    "eu6": DATA_ROOT / "eu6",
    "wc3": DATA_ROOT / "wc3",
}


def image_for(bin_path: Path) -> Path | None:
    for extension in (".webp", ".png"):
        candidate = bin_path.with_suffix(extension)
        if candidate.exists():
            return candidate
    return None


@unittest.skipUnless(DATA_ROOT.exists(), "跨游戏验证集未附加")
class CrossGameCompatibilityTests(unittest.TestCase):
    def test_all_bile_assets_use_supported_six_section_container(self) -> None:
        expected_versions = {"general3": 4, "eu6": 4, "wc3": 3}
        total = 0
        for dataset, folder in DATASETS.items():
            for bin_path in sorted(folder.glob("*.bin")):
                if bin_path.read_bytes()[:4] != b"BILE":
                    continue
                document = parse_file(bin_path)
                total += 1
                self.assertEqual(document.header.version, expected_versions[dataset], bin_path.name)
                self.assertEqual(document.header.header_size, 20, bin_path.name)
                self.assertEqual(tuple(document.sections), ("BELE", "BXDI", "BMRF", "BYAL", "BMTI", "BRTS"), bin_path.name)
                self.assertFalse(document.graph_cycles, bin_path.name)
        self.assertEqual(total, 76)

    def test_cross_game_xml_declaration_padding_and_fractional_geometry_profiles(self) -> None:
        eu6_xml = DATASETS["eu6"] / "anim_newui.xml"
        eu6_png = DATASETS["eu6"] / "anim_newui.png"
        eu6_atlas = load_atlas(eu6_xml, eu6_png)
        self.assertTrue(eu6_atlas.xml_had_declaration)
        self.assertGreaterEqual(eu6_atlas.fractional_geometry_regions, 2)
        self.assertEqual(eu6_atlas.source_image_format, "PNG")
        eu6_doc = parse_file(DATASETS["eu6"] / "anim_newui.bin")
        eu6_codes = {item.code for item in collect_diagnostics(eu6_doc, eu6_atlas)}
        self.assertIn("ATLAS_XML_DECLARATION_COMPATIBLE", eu6_codes)
        self.assertIn("ATLAS_FRACTIONAL_GEOMETRY_COMPATIBLE", eu6_codes)

        wc3_xml = DATASETS["wc3"] / "army_infantry4.xml"
        wc3_png = DATASETS["wc3"] / "army_infantry4.png"
        wc3_atlas = load_atlas(wc3_xml, wc3_png)
        self.assertGreaterEqual(wc3_atlas.stripped_control_chars, 2)
        wc3_doc = parse_file(DATASETS["wc3"] / "army_infantry4.bin")
        wc3_codes = {item.code for item in collect_diagnostics(wc3_doc, wc3_atlas)}
        self.assertIn("ATLAS_XML_CONTROL_PADDING_STRIPPED", wc3_codes)
        self.assertIn("BILE_CROSS_GAME_PROFILE", wc3_codes)

    def test_general1_v2_five_section_triplets_parse_render_and_report_readonly_profile(self) -> None:
        general1 = DATA_ROOT / "general1"
        if not general1.exists():
            self.skipTest("将军的荣耀1 BILE v2 验证集未附加")
        total = 0
        for bin_path in sorted(general1.glob("*.bin")):
            xml = bin_path.with_suffix(".xml")
            image = image_for(bin_path)
            self.assertTrue(xml.exists(), bin_path.name)
            self.assertIsNotNone(image, bin_path.name)
            document = parse_file(bin_path)
            self.assertEqual(document.header.version, 2, bin_path.name)
            self.assertEqual(tuple(document.sections), ("BELE", "BMRF", "BYAL", "BMTI", "BRTS"), bin_path.name)
            self.assertEqual(
                sum(len(frame.tracks) for element in document.elements for channel in element.channels for frame in channel.frames),
                len(document.keyframes),
                bin_path.name,
            )
            atlas = load_atlas(xml, image)
            codes = {item.code for item in collect_diagnostics(document, atlas)}
            self.assertIn("BILE_V2_FIVE_SECTION_READONLY_PROFILE", codes, bin_path.name)
            target = document.animations[0]
            frame = render_frame(document, atlas, target.name, 0, canvas_size=(256, 192))
            self.assertEqual(frame.size, (256, 192), bin_path.name)
            total += 1
        self.assertEqual(total, 12)

    def test_v2_rejects_incomplete_track_consumption_and_invalid_bele_target(self) -> None:
        general1 = DATA_ROOT / "general1"
        source = general1 / "mtank.bin"
        if not source.exists():
            self.skipTest("将军的荣耀1 BILE v2 验证集未附加")
        document = parse_file(source)
        bmrf_offset = document.sections["BMRF"].payload_offset
        incomplete = bytearray(source.read_bytes())
        struct.pack_into("<I", incomplete, bmrf_offset + 4, 0)
        with self.assertRaises(BileFormatError):
            parse_bytes(bytes(incomplete))

        invalid_target = bytearray(source.read_bytes())
        last_bele = document.sections["BELE"].payload_offset + (len(document.keyframes) - 1) * 48
        struct.pack_into("<i", invalid_target, last_bele + 44, len(document.elements))
        with self.assertRaises(BileFormatError):
            parse_bytes(bytes(invalid_target))

    def test_creates_cross_game_root_composition_experiment_package(self) -> None:
        general3 = DATASETS["general3"]
        wc4 = DATA_ROOT / "wc4_extended"
        required = [
            general3 / "unit_infantry.bin", general3 / "unit_infantry.xml", general3 / "unit_infantry.webp",
            wc4 / "unit_infantry.bin", wc4 / "unit_infantry.xml", wc4 / "unit_infantry.webp",
        ]
        if not all(path.exists() for path in required):
            self.skipTest("将3/世4 unit_infantry 组合实验样本未附加")
        import tempfile
        import zipfile
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "composition_experiment.zip"
            result = create_composition_experiment_package(
                wc4 / "unit_infantry.bin", wc4 / "unit_infantry.xml", wc4 / "unit_infantry.webp",
                general3 / "unit_infantry.bin", general3 / "unit_infantry.xml", general3 / "unit_infantry.webp",
                "通用普通步兵待机组合动画", "盟军通用普通士兵待机动画", output,
                target_unit_name="Soldier", target_motion_type="standby", target_resource="unit_infantry",
            )
            self.assertTrue(result.archive_path.exists())
            self.assertEqual(result.candidate_root_profile["max_concurrent_direct_child_animations"], 0)
            manifest = result.manifest_path.read_text(encoding="utf-8")
            self.assertIn("must_remain_target_side", manifest)
            with zipfile.ZipFile(result.archive_path) as archive:
                names = archive.namelist()
                self.assertTrue(any(name.endswith("replace_after_backup/unit_infantry.bin") for name in names))
                self.assertTrue(any(name.endswith("binding_change_recipe.json") for name in names))
                staged_xml_name = next(name for name in names if name.endswith("replace_after_backup/unit_infantry.xml"))
                staged_xml = archive.read(staged_xml_name)
                self.assertNotEqual(staged_xml, (general3 / "unit_infantry.xml").read_bytes())
                self.assertIn(b'<Texture name="unit_infantry.webp"', staged_xml)
                self.assertIn('"only_change": "Texture.name"', manifest)

    def test_root_animation_composition_profiles_for_cross_game_infantry(self) -> None:
        general3_bin = DATASETS["general3"] / "unit_infantry.bin"
        general3_xml = DATASETS["general3"] / "unit_infantry.xml"
        general3_image = image_for(general3_bin)
        wc4_dir = DATA_ROOT / "wc4_extended"
        wc4_bin = wc4_dir / "unit_infantry.bin"
        wc4_xml = wc4_dir / "unit_infantry.xml"
        wc4_image = image_for(wc4_bin)
        if not all((general3_bin.exists(), general3_xml.exists(), general3_image, wc4_bin.exists(), wc4_xml.exists(), wc4_image)):
            self.skipTest("将3/世4 unit_infantry 跨游戏组合样本未附加")
        general3_codes = {item.code for item in collect_diagnostics(parse_file(general3_bin), load_atlas(general3_xml, general3_image))}
        wc4_codes = {item.code for item in collect_diagnostics(parse_file(wc4_bin), load_atlas(wc4_xml, wc4_image))}
        self.assertIn("ROOT_ANIMATION_DIRECT_SPRITE_COMPOSITION", general3_codes)
        self.assertIn("ROOT_ANIMATION_NESTED_COMPOSITION", wc4_codes)

    def test_complete_cross_game_triplets_load_and_render_representative_frames(self) -> None:
        total = 0
        for _dataset, folder in DATASETS.items():
            for bin_path in sorted(folder.glob("*.bin")):
                if bin_path.read_bytes()[:4] != b"BILE":
                    continue
                xml = bin_path.with_suffix(".xml")
                image = image_for(bin_path)
                if not xml.exists() or image is None:
                    continue
                document = parse_file(bin_path)
                atlas = load_atlas(xml, image)
                self.assertGreater(len(atlas.regions), 0, bin_path.name)
                if not document.animations:
                    continue
                target = document.animations[0]
                for slot in {0, target.frame_count // 2, target.frame_count - 1}:
                    frame = render_frame(document, atlas, target.name, slot, canvas_size=(256, 192))
                    self.assertEqual(frame.size, (256, 192), f"{bin_path.name}@{slot}")
                total += 1
        self.assertEqual(total, 70)


if __name__ == "__main__":
    unittest.main()
