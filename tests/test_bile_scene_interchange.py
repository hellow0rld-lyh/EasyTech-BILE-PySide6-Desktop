from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from bile_workbench.bile_format import parse_file
from bile_workbench.bile_scene_interchange import SCENE_SCHEMA, export_scene_interchange

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sample_assets" / "anim_failure.bin"


def _image_for(bin_path: Path) -> Path:
    for extension in (".webp", ".png"):
        image = bin_path.with_suffix(extension)
        if image.exists():
            return image
    raise FileNotFoundError(f"缺少 {bin_path.name} 的 WebP/PNG 图集")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BileSceneInterchangeTests(unittest.TestCase):
    def _export(self, bin_path: Path, *, include_render_witnesses: bool = False) -> tuple[dict, Path, Path]:
        xml_path = bin_path.with_suffix(".xml")
        image_path = _image_for(bin_path)
        before = (_sha256(bin_path), _sha256(xml_path), _sha256(image_path))
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "scene.json"
            payload = export_scene_interchange(
                bin_path,
                xml_path,
                image_path,
                output,
                include_render_witnesses=include_render_witnesses,
            )
            serialized = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload, serialized)
        self.assertEqual(before, (_sha256(bin_path), _sha256(xml_path), _sha256(image_path)), "只读场景导出不得修改三件套")
        return payload, xml_path, image_path

    def test_v4_export_is_hash_bound_and_covers_parsed_structure(self) -> None:
        payload, _xml_path, _image_path = self._export(SAMPLE)
        document = parse_file(SAMPLE)
        self.assertEqual(payload["schema"], SCENE_SCHEMA)
        self.assertEqual(payload["kind"], "read_only_scene")
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["writeback"], "forbidden")
        self.assertEqual(payload["source"]["bin"]["sha256"], _sha256(SAMPLE))
        self.assertEqual(payload["source"]["bin"]["version"], document.header.version)
        self.assertEqual(len(payload["nodes"]), len(document.elements))
        self.assertEqual(len(payload["keyframes"]), len(document.keyframes))
        self.assertEqual(len(payload["timelines"]), len(document.animations))
        self.assertEqual(payload["diagnostics"]["source_structure"]["track_count"], sum(
            len(frame.tracks) for element in document.animations for channel in element.channels for frame in channel.frames
        ))
        serialized_text = json.dumps(payload, ensure_ascii=False)
        for forbidden_field in ("opaque_ref", "opaque_flags", "payload_offset", "section_offset", "name_offset"):
            self.assertNotIn(forbidden_field, serialized_text)
        self.assertIn("point(x,y)", payload["coordinate_contract"]["matrix"])

    def test_render_witnesses_cover_each_root_timeline_transition(self) -> None:
        payload, _xml_path, _image_path = self._export(SAMPLE, include_render_witnesses=True)
        document = parse_file(SAMPLE)
        witnesses = payload["render_witnesses"]
        self.assertEqual(witnesses["renderer"], "bile_workbench.preview_renderer/reference_v4")
        self.assertEqual(witnesses["canvas"], {"width": 256, "height": 192})
        coverage = witnesses["animation_coverage"]
        self.assertEqual(coverage["candidate_animation_count"], len(document.animations))
        self.assertEqual(coverage["selected_animation_count"], len(witnesses["animations"]))
        self.assertLessEqual(coverage["selected_animation_count"], 8)
        self.assertEqual(coverage["per_animation_slot_budget"], 8)
        if len(document.animations) <= 8:
            self.assertEqual(coverage["sampling"], "all_animations")
        else:
            self.assertEqual(coverage["sampling"], "deterministic_stratified_animations")
        originals = {f"element:{animation.index}": animation for animation in document.animations}
        for entry in witnesses["animations"]:
            animation = originals[entry["animation_id"]]
            expected_slots = {0, max(0, animation.frame_count - 1)}
            expected_slots.update(frame.slot for channel in animation.channels for frame in channel.frames if 0 <= frame.slot < animation.frame_count)
            self.assertEqual(entry["candidate_transition_slot_count"], len(expected_slots))
            if len(expected_slots) <= 8:
                self.assertEqual(entry["sampling"], "all_transition_slots")
                self.assertEqual([frame["slot"] for frame in entry["frames"]], sorted(expected_slots))
            else:
                self.assertEqual(entry["sampling"], "deterministic_stratified_transition_slots")
                self.assertLessEqual(len(entry["frames"]), 8)
            self.assertTrue(all(len(frame["rgba_sha256"]) == 64 for frame in entry["frames"]))

    def test_sprite_and_animation_nodes_keep_explicit_scene_roles(self) -> None:
        payload, _xml_path, _image_path = self._export(SAMPLE)
        document = parse_file(SAMPLE)
        nodes = {node["element_index"]: node for node in payload["nodes"]}
        for sprite in document.sprites:
            self.assertEqual(nodes[sprite.index]["kind"], "sprite")
            self.assertIn("atlas_region", nodes[sprite.index])
        for animation in document.animations:
            self.assertEqual(nodes[animation.index]["kind"], "animation")
            self.assertEqual(nodes[animation.index]["frame_count"], animation.frame_count)
            self.assertEqual(nodes[animation.index]["channel_count"], animation.channel_count)

    def test_cross_game_render_witnesses_cover_v2_v3_v4_when_available(self) -> None:
        data_root = ROOT / "cross_game_assets"
        cases = (
            (data_root / "general1" / "mtank.bin", 2),
            (data_root / "wc3" / "anim_gameover.bin", 3),
            (data_root / "general3" / "anim_fire.bin", 4),
        )
        if not all(path.exists() and path.with_suffix(".xml").exists() for path, _version in cases):
            self.skipTest("完整 v2/v3/v4 跨游戏验证集未附加")
        for path, expected_version in cases:
            payload, _xml_path, _image_path = self._export(path, include_render_witnesses=True)
            self.assertEqual(payload["source"]["bin"]["version"], expected_version, path.name)
            witnesses = payload["render_witnesses"]["animations"]
            self.assertGreater(len(witnesses), 0, path.name)
            self.assertTrue(all(entry["frames"] for entry in witnesses), path.name)
            self.assertTrue(all(len(entry["frames"]) <= 8 for entry in witnesses), path.name)
            self.assertTrue(all(entry["candidate_transition_slot_count"] >= len(entry["frames"]) for entry in witnesses), path.name)
            self.assertTrue(all(entry["sampling"] in {"all_transition_slots", "deterministic_stratified_transition_slots"} for entry in witnesses), path.name)
            self.assertTrue(all(len(frame["rgba_sha256"]) == 64 for entry in witnesses for frame in entry["frames"]), path.name)

    def test_cross_game_versions_export_when_optional_dataset_is_available(self) -> None:
        data_root = ROOT / "cross_game_assets"
        cases = (
            (data_root / "general3" / "anim_fire.bin", 4),
            (data_root / "wc3" / "anim_gameover.bin", 3),
            (data_root / "general1" / "mtank.bin", 2),
        )
        available = [(path, version) for path, version in cases if path.exists() and path.with_suffix(".xml").exists()]
        if not available:
            self.skipTest("跨游戏验证集未附加")
        for path, expected_version in available:
            payload, _xml_path, _image_path = self._export(path)
            self.assertEqual(payload["source"]["bin"]["version"], expected_version, path.name)
            self.assertEqual(payload["diagnostics"]["source_structure"]["element_count"], len(parse_file(path).elements), path.name)


if __name__ == "__main__":
    unittest.main()
