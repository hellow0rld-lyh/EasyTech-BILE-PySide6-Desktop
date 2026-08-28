"""轨道上下文服务使用真实 BILE 样本的回归测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import parse_file
from bile_workbench.track_context import TrackContextError, active_tracks_at_slot, keyframe_contexts, tracks_for_animation


class TrackContextTests(unittest.TestCase):
    def _assert_animation_context(self, binary: Path) -> None:
        document = parse_file(binary)
        animation = document.animations[0]
        contexts = tracks_for_animation(document, animation.index)
        self.assertGreater(len(contexts), 0)
        context = contexts[0]
        self.assertEqual(context.animation_index, animation.index)
        self.assertLessEqual(context.frame_slot, context.hold_end_slot)
        self.assertIn(context.target_element_index, range(len(document.elements)))
        active = active_tracks_at_slot(document, animation.index, context.frame_slot)
        self.assertIn(context, active)
        self.assertIn(context, keyframe_contexts(document, context.keyframe_index))

    def test_v4_contexts_preserve_track_and_holding_segment(self) -> None:
        self._assert_animation_context(ROOT / "sample_assets" / "anim_failure.bin")

    def test_v3_contexts_share_same_track_projection(self) -> None:
        self._assert_animation_context(ROOT / "cross_game_assets" / "wc3" / "anim_gameover.bin")

    def test_sprite_root_is_rejected(self) -> None:
        document = parse_file(ROOT / "sample_assets" / "anim_failure.bin")
        with self.assertRaises(TrackContextError):
            tracks_for_animation(document, document.sprites[0].index)


if __name__ == "__main__":
    unittest.main()
