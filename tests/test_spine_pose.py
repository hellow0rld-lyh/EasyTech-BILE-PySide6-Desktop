from __future__ import annotations

import math
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from bile_workbench.spine38_timeline import _decode_draw_order as decode_draw_order38, parse_spine38_pose_animation
from bile_workbench.spine41_timeline import parse_spine41_pose_animation
from bile_workbench.spine_atlas import load_spine_atlas
from bile_workbench.spine38_format import Spine38Bone, Spine38RegionAttachment, Spine38Slot, SpineIkConstraint, SpineTransformConstraint, _Reader
from bile_workbench.spine_pose import PoseAnimation, PoseFrame, PoseTrack, _interpolate, project_pose
from bile_workbench.spine_pose_renderer import _apply_light_rgba, render_pose_layers
from external_fixtures import require_files

ROOT = Path(__file__).resolve().parents[1]
EU7 = ROOT / "incoming/cross_era_20260822/欧7测试/animation/Arthur2.bin"
ZHENG2 = ROOT / "incoming/cross_era_20260822/征2测试/animation/[mini]effect_ui10.bin"
EU7_DEFORM = ROOT / "incoming/cross_era_20260822/欧7测试/animation/Empress Matilda2.bin"
ZHENG2_DEFORM = ROOT / "incoming/cross_era_20260822/征2测试/animation/[mini]form_main1.bin"


class SpinePoseProjectionTests(unittest.TestCase):
    def test_light_tint_multiplies_slot_attachment_and_renderer_channels(self) -> None:
        static = SimpleNamespace(
            bones=(Spine38Bone(0, "root", None, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0, False),),
            slots=(Spine38Slot(0, "slot", 0, 0x8040FF80, None, "region", 0),),
            region_attachments=(Spine38RegionAttachment("default", 0, "region", "region", 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 0x4080FF40),),
        )
        pose = project_pose(static, PoseAnimation("setup", 0.0, (), ()), 0.0)
        self.assertEqual(len(pose.layers), 1)
        self.assertAlmostEqual(pose.layers[0].rgba[0], 128 / 255 * 64 / 255, places=6)
        self.assertAlmostEqual(pose.layers[0].rgba[1], 64 / 255 * 128 / 255, places=6)
        self.assertAlmostEqual(pose.layers[0].rgba[2], 1.0, places=6)
        self.assertAlmostEqual(pose.layers[0].rgba[3], 128 / 255 * 64 / 255, places=6)
        tinted = _apply_light_rgba(Image.new("RGBA", (1, 1), (200, 100, 50, 255)), (0.5, 0.25, 1.0, 0.5))
        self.assertEqual(tinted.getpixel((0, 0)), (100, 25, 50, 128))

    def test_setup_constraint_subset_updates_pose_world_matrices_in_order(self) -> None:
        bones = (
            Spine38Bone(0, "root", None, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0, False),
            Spine38Bone(1, "arm", 0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 5.0, 0, False),
            Spine38Bone(2, "target", 0, 0.0, 0.0, 5.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0, False),
        )
        ik = SpineIkConstraint(0, "aim", 0, False, (1,), 2, 1.0, 0.0, 1, False, False, False)
        static = SimpleNamespace(bones=bones, slots=(), region_attachments=(), ik_constraints=(ik,), transform_constraints=())
        pose = project_pose(static, PoseAnimation("setup", 0.0, (), ()), 0.0)
        self.assertAlmostEqual(math.degrees(math.atan2(pose.bones[1].c, pose.bones[1].a)), 90.0, places=5)
        self.assertTrue(pose.coverage_complete, pose.diagnostics)

        transform = SpineTransformConstraint(0, "copy", 1, False, (1,), 2, False, False, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0)
        static = SimpleNamespace(bones=bones, slots=(), region_attachments=(), ik_constraints=(), transform_constraints=(transform,))
        pose = project_pose(static, PoseAnimation("setup", 0.0, (), ()), 0.0)
        self.assertAlmostEqual(pose.bones[1].world_y, 5.0, places=5)
        self.assertTrue(pose.coverage_complete, pose.diagnostics)

        animated_ik = PoseAnimation("ik-mix", 1.0, (
            PoseTrack("ik", "mix", 0, "aim", (PoseFrame(0.0, (0.0, 0.0)), PoseFrame(1.0, (1.0, 0.0)))),
            PoseTrack("ik", "state", 0, "aim", (PoseFrame(0.0, (1, 0, 0)),)),
        ), ())
        static = SimpleNamespace(bones=bones, slots=(), region_attachments=(), ik_constraints=(ik,), transform_constraints=())
        pose = project_pose(static, animated_ik, 0.5)
        self.assertAlmostEqual(math.degrees(math.atan2(pose.bones[1].c, pose.bones[1].a)), 45.0, places=5)

        animated_transform = PoseAnimation("transform-mix", 1.0, (
            PoseTrack("transform", "mix", 0, "copy", (PoseFrame(0.0, (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)), PoseFrame(1.0, (1.0, 1.0, 1.0, 0.0, 0.0, 0.0)))),
        ), ())
        static = SimpleNamespace(bones=bones, slots=(), region_attachments=(), ik_constraints=(), transform_constraints=(transform,))
        pose = project_pose(static, animated_transform, 0.5)
        self.assertAlmostEqual(pose.bones[1].world_y, 2.5, places=5)

    def test_draw_order_offset_decode_and_layer_order_projection(self) -> None:
        slots = (
            Spine38Slot(0, "first", 0, 0xFFFFFFFF, None, "a", 0),
            Spine38Slot(1, "second", 0, 0xFFFFFFFF, None, "b", 0),
            Spine38Slot(2, "third", 0, 0xFFFFFFFF, None, "c", 0),
        )
        static = SimpleNamespace(slots=slots)
        # offset_count=1, changed slot=0, positive destination offset=2 → [1, 2, 0].
        self.assertEqual(decode_draw_order38(_Reader(bytes((1, 0, 2))), static, "draw"), (1, 2, 0))

        projection_static = SimpleNamespace(
            bones=(Spine38Bone(0, "root", None, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0, False),),
            slots=slots[:2],
            region_attachments=(
                Spine38RegionAttachment("default", 0, "a", "a", 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 0xFFFFFFFF),
                Spine38RegionAttachment("default", 1, "b", "b", 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 0xFFFFFFFF),
            ),
        )
        animation = PoseAnimation("reorder", 0.0, (PoseTrack("draw_order", "order", -1, "slots", (PoseFrame(0.0, (1, 0)),)),), ())
        pose = project_pose(projection_static, animation, 0.0)
        self.assertEqual([layer.slot_index for layer in pose.layers], [1, 0])

    def test_cubic_bezier_interpolation_supports_single_and_per_component_controls(self) -> None:
        single = PoseTrack(
            "bone", "rotate", 0, "root",
            (PoseFrame(0.0, (0.0,), ((0.25, 0.0, 0.25, 1.0),)), PoseFrame(1.0, (10.0,))),
        )
        diagnostics: list[str] = []
        value = _interpolate(single, 0.5, diagnostics)
        self.assertAlmostEqual(float(value[0]), 7.835, places=3)
        self.assertFalse(diagnostics)

        per_component = PoseTrack(
            "bone", "translate", 0, "root",
            (PoseFrame(0.0, (0.0, 0.0), ((0.0, 0.0, 1.0, 1.0), (0.25, 0.0, 0.25, 1.0))), PoseFrame(1.0, (10.0, 10.0))),
        )
        value = _interpolate(per_component, 0.5, diagnostics)
        self.assertAlmostEqual(float(value[0]), 5.0, places=3)
        self.assertAlmostEqual(float(value[1]), 7.835, places=3)

    def test_bezier_marker_without_controls_remains_explicitly_degraded(self) -> None:
        track = PoseTrack("bone", "rotate", 0, "root", (PoseFrame(0.0, (0.0,), "bezier"), PoseFrame(1.0, (10.0,))))
        diagnostics: list[str] = []
        value = _interpolate(track, 0.5, diagnostics)
        self.assertAlmostEqual(float(value[0]), 5.0, places=3)
        self.assertTrue(any("控制点未捕获" in item for item in diagnostics))

    def test_eu7_pose_capture_retains_bezier_controls_when_present(self) -> None:
        require_files(self, EU7, label="private EU7 Spine 3.8 sample")
        _static, animation = parse_spine38_pose_animation(EU7, "Wait")
        bezier_frames = [frame for track in animation.tracks for frame in track.frames if isinstance(frame.curve, tuple)]
        self.assertGreater(len(bezier_frames), 0)
        self.assertTrue(all(len(frame.curve[0]) == 4 for frame in bezier_frames))

    def test_eu7_supported_tracks_project_after_bezier_evaluation(self) -> None:
        require_files(self, EU7, EU7.with_suffix(".atlas"), label="private EU7 Spine 3.8 sample and atlas")
        static, animation = parse_spine38_pose_animation(EU7, "Wait")
        pose = project_pose(static, animation, animation.duration * 0.5)
        self.assertGreater(len(animation.tracks), 0)
        self.assertEqual(len(static.bones), len(pose.bones))
        self.assertGreater(len(pose.layers), 0)
        self.assertFalse(any("bezier" in item for item in pose.diagnostics), pose.diagnostics)
        self.assertTrue(any("transform_mode" in item or "blend_mode" in item for item in pose.diagnostics), pose.diagnostics)
        rendered = render_pose_layers(pose, load_spine_atlas(EU7.with_suffix(".atlas")))
        self.assertGreater(rendered.rendered_layer_count, 0)
        self.assertFalse(any("bezier" in item for item in rendered.diagnostics), rendered.diagnostics)

    def test_real_deform_evidence_remains_readonly_and_partial_for_both_engines(self) -> None:
        require_files(self, EU7_DEFORM, ZHENG2_DEFORM, label="private Spine deform evidence samples")
        cases = (
            (EU7_DEFORM, "Wait", parse_spine38_pose_animation),
            (ZHENG2_DEFORM, "Wait", parse_spine41_pose_animation),
        )
        for path, animation_name, loader in cases:
            before = path.read_bytes()
            static, animation = loader(path, animation_name)
            self.assertTrue(animation.deform_evidence, path.name)
            self.assertGreater(sum(len(item.frames) for item in animation.deform_evidence), 0, path.name)
            self.assertGreater(sum(len(frame.values) for item in animation.deform_evidence for frame in item.frames), 0, path.name)
            self.assertTrue(all(item.skin is not None and item.slot_index >= 0 for item in animation.deform_evidence), path.name)
            curve_frames = [frame for item in animation.deform_evidence for frame in item.frames]
            self.assertTrue(any(frame.curve is not None for frame in curve_frames[:-1]), path.name)
            for item in animation.deform_evidence:
                self.assertIsNone(item.frames[-1].curve, path.name)
                self.assertTrue(all(frame.curve is None or frame.curve in ("linear", "stepped") or (isinstance(frame.curve, tuple) and all(len(component) == 4 and all(isinstance(value, float) for value in component) for component in frame.curve)) for frame in item.frames), path.name)
            pose = project_pose(static, animation, animation.duration * 0.5)
            self.assertFalse(pose.coverage_complete, path.name)
            self.assertTrue(any("deform:vertices" in item or "attachment:deform" in item for item in pose.diagnostics), pose.diagnostics)
            self.assertEqual(before, path.read_bytes(), path.name)

    def test_zheng2_setup_compatible_animation_can_be_coverage_complete(self) -> None:
        require_files(self, ZHENG2, ZHENG2.with_suffix(".atlas"), label="private Zheng2 Spine 4.1 sample and atlas")
        static, animation = parse_spine41_pose_animation(ZHENG2, "Wait")
        pose = project_pose(static, animation, animation.duration * 0.5)
        self.assertGreater(len(animation.tracks), 0)
        self.assertEqual(len(static.bones), len(pose.bones))
        self.assertGreater(len(pose.layers), 0)
        self.assertTrue(pose.coverage_complete, pose.diagnostics)
        rendered = render_pose_layers(pose, load_spine_atlas(ZHENG2.with_suffix(".atlas")))
        self.assertGreater(rendered.rendered_layer_count, 0)
        self.assertFalse(rendered.diagnostics, rendered.diagnostics)


if __name__ == "__main__":
    unittest.main()
