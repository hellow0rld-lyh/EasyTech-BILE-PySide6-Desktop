"""文档中心与命令化编辑的真实资源回归测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.assets import discover_triplet
from bile_workbench.bile_format import parse_file
from bile_workbench.document_session import (
    AnimationDocumentSession,
    DocumentSessionError,
    SetAnchorCommand,
    SetKeyframeCommand,
)
from bile_workbench.preview_renderer import load_atlas
from bile_workbench.track_context import tracks_for_animation
from bile_workbench.workbench_state import Workspace
from external_fixtures import require_triplet


def load_workspace(binary: Path) -> Workspace:
    triplet = discover_triplet(binary)
    return Workspace.create(
        triplet.bin_path,
        triplet.xml_path,
        triplet.image_path,
        parse_file(triplet.bin_path),
        load_atlas(triplet.xml_path, triplet.image_path),
    )


class AnimationDocumentSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        sample = ROOT / "sample_assets" / "anim_failure.bin"
        require_triplet(self, sample)
        self.workspace = load_workspace(sample)

    def test_selection_snapshot_and_listener_share_one_state(self) -> None:
        session = AnimationDocumentSession(self.workspace)
        snapshots = []
        try:
            unsubscribe = session.subscribe(snapshots.append)
            animation = self.workspace.document.animations[0]
            session.select_element(animation.index)
            session.set_slot(animation.frame_count + 50)
            snapshot = session.snapshot
            self.assertEqual(snapshot.selected_element.name, animation.name)
            self.assertEqual(snapshot.selection.slot, animation.frame_count - 1)
            self.assertGreaterEqual(len(snapshots), 3)
            unsubscribe()
            session.set_slot(0)
            self.assertEqual(len(snapshots), 3)
        finally:
            session.close()

    def test_track_selection_carries_verified_context_and_slot_navigation_clears_it(self) -> None:
        session = AnimationDocumentSession(self.workspace)
        try:
            animation = self.workspace.document.animations[0]
            session.select_element(animation.index)
            context = tracks_for_animation(self.workspace.document, animation.index)[0]
            session.select_track(context)
            selection = session.snapshot.selection
            self.assertEqual(selection.element_index, animation.index)
            self.assertEqual(selection.slot, context.frame_slot)
            self.assertEqual(selection.channel_index, context.channel_index)
            self.assertEqual(selection.track_index, context.track_index)
            self.assertEqual(selection.keyframe_index, context.keyframe_index)
            session.set_slot(min(animation.frame_count - 1, context.hold_end_slot + 1))
            self.assertIsNone(session.snapshot.selection.keyframe_index)
        finally:
            session.close()

    def test_commands_drive_preview_undo_and_candidate_workflow(self) -> None:
        session = AnimationDocumentSession(self.workspace)
        try:
            original = self.workspace.document.keyframes[1]
            command = SetKeyframeCommand(
                1,
                {"xx": 1.0, "xy": 0.0, "yx": 0.0, "yy": 1.0, "x": 42.5, "y": -9.0},
                0x80FFFFFF,
                0,
            )
            session.execute(command)
            self.assertTrue(session.snapshot.dirty)
            self.assertEqual(session.snapshot.change_count, 1)
            changed = session.snapshot.document.keyframes[1]
            self.assertEqual((changed.x, changed.y, changed.argb), (42.5, -9.0, 0x80FFFFFF))
            self.assertEqual(session.candidate_workflow().session.source_path, self.workspace.bin_path)
            self.assertTrue(session.undo())
            restored = session.snapshot.document.keyframes[1]
            self.assertEqual((restored.x, restored.y, restored.argb), (original.x, original.y, original.argb))
            self.assertFalse(session.snapshot.dirty)
        finally:
            session.close()

    def test_anchor_command_and_v2_write_rejection(self) -> None:
        session = AnimationDocumentSession(self.workspace)
        try:
            session.execute(SetAnchorCommand(2, 5.0, -6.0))
            self.assertEqual(session.snapshot.document.elements[2].x, 5.0)
            self.assertEqual(session.snapshot.document.elements[2].y, -6.0)
        finally:
            session.close()
        v2_source = ROOT / "cross_game_assets" / "general1" / "mtank.bin"
        require_triplet(self, v2_source, label="private BILE v2 sample triplet")
        v2_workspace = load_workspace(v2_source)
        v2 = AnimationDocumentSession(v2_workspace)
        try:
            with self.assertRaises(DocumentSessionError):
                v2.execute(SetAnchorCommand(0, 1.0, 2.0))
        finally:
            v2.close()


if __name__ == "__main__":
    unittest.main()
