from __future__ import annotations

import hashlib
import json
import struct
import sys
import tempfile
import unittest
import zipfile

from PIL import Image
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import BileFormatError, parse_bytes, parse_file
from bile_workbench.edit_session import EditSession
from bile_workbench.diff_analysis import compare_animation
from bile_workbench.experiment_package import create_experiment_package
from bile_workbench.regression_case import add_evidence, create_regression_case, update_case
from bile_workbench.interchange import SCHEMA, apply_patch, export_interchange
from bile_workbench.preview_renderer import load_atlas, render_frame
from bile_workbench.preflight import run_preflight
from bile_workbench.sequence_export import export_sequence


class BileFormatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assets = ROOT / "sample_assets"
        self.sample = self.assets / "anim_failure.bin"

    def test_all_original_animation_samples_parse_and_consume_timelines(self) -> None:
        for path in sorted(self.assets.glob("anim_*.bin")):
            with self.subTest(path=path.name):
                document = parse_file(path)
                self.assertEqual(document.header.version, 4)
                self.assertEqual(document.header.payload_size + document.header.header_size, path.stat().st_size)
                self.assertGreater(len(document.keyframes), 0)
                self.assertGreater(len(document.elements), 0)
                self.assertGreater(len(document.animations), 0)
                self.assertGreater(len(document.sprites), 0)

    def test_reference_backed_playback_fields_and_acyclic_sample_graphs(self) -> None:
        for path in sorted(self.assets.glob("anim_*.bin")):
            with self.subTest(path=path.name):
                document = parse_file(path)
                self.assertEqual(document.graph_cycles, ())
                self.assertTrue(all(keyframe.has_known_playback_mode for keyframe in document.keyframes))
        status = parse_file(self.assets / "anim_status.bin")
        self.assertGreater(sum(keyframe.initial_phase != 0 for keyframe in status.keyframes), 0)
        self.assertIn(2, {keyframe.playback_mode for keyframe in status.keyframes})

    def test_bmts_names_point_to_utf8_string_boundaries(self) -> None:
        document = parse_file(self.sample)
        self.assertEqual(document.elements[0].name, "failure_a")
        self.assertEqual(document.elements[1].name, "failure_b")
        self.assertEqual(len(document.sprites), 8)
        self.assertEqual(len(document.animations), 3)
        self.assertIn("失败黑底", document.strings.values())

    def test_rejects_header_size_length_mismatch(self) -> None:
        data = bytearray(self.sample.read_bytes())
        struct.pack_into("<I", data, 8, len(data))
        with self.assertRaises(BileFormatError):
            parse_bytes(bytes(data))

    def test_rejects_invalid_top_level_tag(self) -> None:
        data = bytearray(self.sample.read_bytes())
        data[20:24] = b"FAIL"
        with self.assertRaises(BileFormatError):
            parse_bytes(bytes(data))

    def test_rejects_invalid_bmti_name_offset(self) -> None:
        data = bytearray(self.sample.read_bytes())
        document = parse_file(self.sample)
        bmti_offset = document.sections["BMTI"].payload_offset
        struct.pack_into("<I", data, bmti_offset + 4, 1)
        with self.assertRaises(BileFormatError):
            parse_bytes(bytes(data))

    def test_interchange_export_and_conservative_patch(self) -> None:
        original = self.sample.read_bytes()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            interchange_path = temp / "source.json"
            patch_path = temp / "patch.json"
            output_path = temp / "edited.bin"
            export_interchange(self.sample, interchange_path)
            exported = json.loads(interchange_path.read_text(encoding="utf-8"))
            self.assertEqual(exported["schema"], SCHEMA)
            self.assertEqual(exported["source"]["sha256"], hashlib.sha256(original).hexdigest())
            patch = {
                "schema": SCHEMA,
                "kind": "patch",
                "source_sha256": hashlib.sha256(original).hexdigest(),
                "keyframes": [{"index": 0, "transform": {"x": 123.5}, "argb": "0x80FFFFFF", "initial_phase": 1}],
                "elements": [{"index": 2, "anchor": [3.0, -4.0]}],
            }
            patch_path.write_text(json.dumps(patch), encoding="utf-8")
            changed = apply_patch(self.sample, patch_path, output_path)
            self.assertEqual(changed.keyframes[0].x, 123.5)
            self.assertEqual(changed.keyframes[0].argb, 0x80FFFFFF)
            self.assertEqual(changed.keyframes[0].initial_phase, 1)
            self.assertEqual(changed.elements[2].x, 3.0)
            self.assertEqual(changed.elements[2].y, -4.0)
            self.assertNotEqual(output_path.read_bytes(), original)

    def test_patch_rejects_unverified_playback_mode_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            patch_path = temp / "unverified.json"
            patch_path.write_text(json.dumps({
                "schema": SCHEMA,
                "kind": "patch",
                "source_sha256": hashlib.sha256(self.sample.read_bytes()).hexdigest(),
                "keyframes": [{"index": 0, "playback_mode": 2}],
            }), encoding="utf-8")
            with self.assertRaises(BileFormatError):
                apply_patch(self.sample, patch_path, temp / "out.bin")

    def test_patch_rejects_mismatched_source_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            patch_path = temp / "bad.json"
            patch_path.write_text(json.dumps({"schema": SCHEMA, "kind": "patch", "source_sha256": "0" * 64}), encoding="utf-8")
            with self.assertRaises(BileFormatError):
                apply_patch(self.sample, patch_path, temp / "out.bin")

    def test_direct_edit_session_undo_redo_and_preview(self) -> None:
        original = parse_file(self.sample)
        session = EditSession(self.sample)
        try:
            session.set_keyframe(1, {"xx": 1.0, "xy": 0.0, "yx": 0.0, "yy": 1.0, "x": 42.5, "y": -9.0}, 0x80FFFFFF, 0)
            session.set_anchor(2, 5.0, -6.0)
            self.assertTrue(session.dirty)
            self.assertEqual(session.change_count, 2)
            staged = session.preview_document()
            self.assertEqual(staged.keyframes[1].x, 42.5)
            self.assertEqual(staged.keyframes[1].argb, 0x80FFFFFF)
            self.assertEqual(staged.keyframes[1].initial_phase, 0)
            self.assertEqual(staged.elements[2].x, 5.0)
            self.assertTrue(session.undo())
            after_undo = session.preview_document()
            self.assertEqual(after_undo.elements[2].x, original.elements[2].x)
            self.assertTrue(session.redo())
            after_redo = session.preview_document()
            self.assertEqual(after_redo.elements[2].x, 5.0)
            with tempfile.TemporaryDirectory() as temp_dir:
                patch_path = Path(temp_dir) / "direct.patch.json"
                session.write_patch(patch_path)
                payload = json.loads(patch_path.read_text(encoding="utf-8"))
                self.assertEqual(payload["schema"], SCHEMA)
                self.assertEqual(len(payload["keyframes"]), 1)
                self.assertEqual(len(payload["elements"]), 1)
        finally:
            session.close()

    def test_initial_phase_preflight_uses_real_nested_child_range(self) -> None:
        bin_path = self.assets / "anim_status.bin"
        atlas = load_atlas(self.assets / "anim_status.xml", self.assets / "anim_status.webp")
        document = parse_file(bin_path)
        selected = None
        for parent in document.animations:
            for channel in parent.channels:
                for frame in channel.frames:
                    for track in frame.tracks:
                        if track.element_index >= 0 and not document.elements[track.element_index].has_texture:
                            keyframe = document.keyframes[track.keyframe_index]
                            if keyframe.initial_phase != 0:
                                selected = (track.keyframe_index, document.elements[track.element_index].frame_count)
                                break
                    if selected:
                        break
                if selected:
                    break
            if selected:
                break
        self.assertIsNotNone(selected)
        index, child_frames = selected
        session = EditSession(bin_path)
        try:
            keyframe = document.keyframes[index]
            transform = {field: getattr(keyframe, field) for field in ("xx", "xy", "yx", "yy", "x", "y")}
            session.set_keyframe(index, transform, keyframe.argb, child_frames)
            report = run_preflight(session, atlas)
            self.assertTrue(report.has_errors)
            self.assertIn("INITIAL_PHASE_OUTSIDE_CHILD_RANGE", report.text)
            session.undo()
            session.set_keyframe(index, transform, keyframe.argb, child_frames - 1)
            report = run_preflight(session, atlas)
            self.assertFalse(report.has_errors)
            self.assertIn("INITIAL_PHASE_NESTED_TARGET_VALID", report.text)
        finally:
            session.close()

    def test_atlas_reference_points_are_loaded_and_renderable(self) -> None:
        atlas = load_atlas(self.assets / "anim_status.xml", self.assets / "anim_status.webp")
        referenced = [region for region in atlas.regions.values() if region.refx != 0 or region.refy != 0]
        self.assertGreater(len(referenced), 0)
        document = parse_file(self.assets / "anim_status.bin")
        frame = render_frame(document, atlas, document.animations[0].name, 0, canvas_size=(320, 240))
        self.assertEqual(frame.size, (320, 240))

    def test_candidate_animation_difference_analysis(self) -> None:
        source = self.assets / "anim_status.bin"
        original = source.read_bytes()
        document = parse_file(source)
        index = 698
        self.assertEqual(document.keyframes[index].initial_phase, 1)
        atlas = load_atlas(self.assets / "anim_status.xml", self.assets / "anim_status.webp")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            patch_path = temp / "candidate.patch.json"
            candidate = temp / "candidate.bin"
            patch_path.write_text(json.dumps({
                "schema": SCHEMA,
                "kind": "patch",
                "source_sha256": hashlib.sha256(original).hexdigest(),
                "keyframes": [{"index": index, "initial_phase": 2}],
            }), encoding="utf-8")
            apply_patch(source, patch_path, candidate)
            result = compare_animation(source, candidate, atlas, "anim_upgrade", temp / "diff", (512, 384))
            self.assertGreater(result.binary_change_count, 0)
            self.assertTrue(result.report_path.exists())
            self.assertTrue(result.markdown_path.exists())
            payload = json.loads(result.report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["animation"], "anim_upgrade")
            self.assertTrue(any(change["field"] == "initial_phase" and change["index"] == index for change in payload["binary_field_changes"]))

            visual_source = self.sample
            visual_original = visual_source.read_bytes()
            visual_patch = temp / "visual.patch.json"
            visual_candidate = temp / "visual_candidate.bin"
            visual_patch.write_text(json.dumps({
                "schema": SCHEMA,
                "kind": "patch",
                "source_sha256": hashlib.sha256(visual_original).hexdigest(),
                "keyframes": [{"index": 1, "transform": {"x": 19.5}}],
            }), encoding="utf-8")
            apply_patch(visual_source, visual_patch, visual_candidate)
            visual_atlas = load_atlas(self.assets / "anim_failure.xml", self.assets / "anim_failure.webp")
            visual_result = compare_animation(visual_source, visual_candidate, visual_atlas, "failure_a", temp / "visual_diff", (320, 240))
            self.assertGreater(visual_result.changed_slots, 0)
            self.assertGreater(visual_result.total_changed_pixels, 0)
            self.assertGreater(len(visual_result.artifacts), 0)

    def test_creates_traceable_game_regression_case(self) -> None:
        original = self.sample.read_bytes()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            patch_path = temp / "case.patch.json"
            candidate = temp / "candidate.bin"
            patch_path.write_text(json.dumps({
                "schema": SCHEMA,
                "kind": "patch",
                "source_sha256": hashlib.sha256(original).hexdigest(),
                "keyframes": [{"index": 1, "transform": {"x": 8.0}}],
            }), encoding="utf-8")
            apply_patch(self.sample, patch_path, candidate)
            case_dir = create_regression_case(temp / "case", self.sample, candidate, "failure_a", target_slots=[0, 16, 31])
            evidence = add_evidence(case_dir, patch_path, "log", "用于复现实验的补丁")
            report = update_case(
                case_dir,
                "inconclusive",
                "尚未在目标游戏版本中运行。",
                {"model": "Test Device", "game_version": "test"},
                ["backup", "replace"],
            )
            payload = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "inconclusive")
            self.assertEqual(payload["target_slots"], [0, 16, 31])
            self.assertEqual(len(payload["evidence"]), 1)
            self.assertTrue(evidence.exists())
            self.assertTrue(report.exists())
            self.assertIn("Test Device", report.read_text(encoding="utf-8"))

    def test_creates_composition_regression_case_with_controlled_variable_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            candidate = temp / "candidate.bin"
            candidate.write_bytes(self.sample.read_bytes())
            context = {
                "kind": "cross-game-root-composition",
                "manifest": "experiment_manifest.json",
                "binding_recipe": "binding_change_recipe.json",
                "target_root_animation": "target_root",
                "candidate_root_animation": "candidate_root",
                "fixed_variables": ["Army/Unit 类型", "地图", "方向", "阵列/Formation"],
                "formation_snapshot": "def_array.xml",
            }
            case_dir = create_regression_case(
                temp / "composition_case", self.sample, candidate, "candidate_root", experiment_package="composition.zip", experiment_context=context
            )
            payload = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
            report = (case_dir / "README_回归案例.md").read_text(encoding="utf-8")
            self.assertEqual(payload["schema"], "bile-workbench.game-regression/v2")
            self.assertEqual([step["id"] for step in payload["steps"]], ["backup", "baseline", "replace", "binding", "treatment", "restore"])
            self.assertEqual(payload["experiment_context"]["candidate_root_animation"], "candidate_root")
            self.assertIn("组合实验条件", report)
            self.assertIn("Army/Unit 类型", report)

    def test_creates_verified_experiment_package(self) -> None:
        original = self.sample.read_bytes()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            patch_path = temp / "experiment.patch.json"
            candidate = temp / "candidate.bin"
            patch_path.write_text(json.dumps({
                "schema": SCHEMA,
                "kind": "patch",
                "source_sha256": hashlib.sha256(original).hexdigest(),
                "keyframes": [{"index": 1, "transform": {"x": 17.25}}],
            }), encoding="utf-8")
            apply_patch(self.sample, patch_path, candidate)
            result = create_experiment_package(
                self.sample,
                candidate,
                self.assets / "anim_failure.xml",
                self.assets / "anim_failure.webp",
                temp / "game_experiment.zip",
                patch_path,
            )
            self.assertTrue(result.archive_path.exists())
            self.assertTrue(result.report_path.exists())
            report = json.loads(result.report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["candidate"]["file"], "candidate.bin")
            self.assertEqual(result.checked_animations, 3)
            with zipfile.ZipFile(result.archive_path) as archive:
                names = set(archive.namelist())
                prefix = "anim_failure_experiment/"
                self.assertIn(prefix + "replace_after_backup/anim_failure.bin", names)
                self.assertIn(prefix + "replace_after_backup/anim_failure.xml", names)
                self.assertIn(prefix + "replace_after_backup/anim_failure.webp", names)
                self.assertIn(prefix + "validation_report.json", names)
                self.assertIn(prefix + "source_patch.json", names)

    def test_exports_png_gif_and_apng_sequences(self) -> None:
        document = parse_file(self.sample)
        atlas = load_atlas(self.assets / "anim_failure.xml", self.assets / "anim_failure.webp")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            png = export_sequence(document, atlas, "failure_a", temp / "frames", "png-sequence", 0, 2, (160, 120))
            self.assertEqual(png.frame_count, 3)
            self.assertEqual(len(png.output_paths), 3)
            self.assertTrue(all(path.exists() for path in png.output_paths))
            self.assertEqual(json.loads(png.manifest_path.read_text(encoding="utf-8"))["kind"], "png-sequence")
            gif = export_sequence(document, atlas, "failure_a", temp / "failure.gif", "gif", 0, 3, (160, 120))
            apng = export_sequence(document, atlas, "failure_a", temp / "failure.apng", "apng", 0, 3, (160, 120), transparent=True)
            self.assertTrue(gif.output_paths[0].exists())
            self.assertTrue(apng.output_paths[0].exists())
            with Image.open(gif.output_paths[0]) as image:
                self.assertEqual(image.n_frames, 4)
            with Image.open(apng.output_paths[0]) as image:
                self.assertEqual(image.n_frames, 4)

    def test_renders_nonempty_failure_frame(self) -> None:
        document = parse_file(self.sample)
        atlas = load_atlas(self.assets / "anim_failure.xml", self.assets / "anim_failure.webp")
        rendered = render_frame(document, atlas, "failure_a", 16, canvas_size=(320, 240))
        self.assertEqual(rendered.size, (320, 240))
        self.assertGreater(len(set(rendered.getdata())), 1)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "frame.png"
            rendered.save(path)
            self.assertGreater(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
