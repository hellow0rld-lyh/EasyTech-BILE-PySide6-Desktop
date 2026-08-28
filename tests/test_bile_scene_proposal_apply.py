from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from bile_workbench.bile_scene_proposal import BileSceneProposal, BileSceneProposalError, KeyframeProposal
from bile_workbench.bile_scene_proposal_apply import apply_scene_proposal
from bile_workbench.document_session import AnimationDocumentSession
from bile_workbench.assets import discover_triplet
from bile_workbench.bile_format import parse_file
from bile_workbench.preview_renderer import load_atlas
from bile_workbench.workbench_state import Workspace


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "sample_assets" / "anim_failure.bin"


def _session() -> AnimationDocumentSession:
    triplet = discover_triplet(BIN)
    return AnimationDocumentSession(Workspace.create(triplet.bin_path, triplet.xml_path, triplet.image_path, parse_file(triplet.bin_path), load_atlas(triplet.xml_path, triplet.image_path)))


class BileSceneProposalApplyTests(unittest.TestCase):
    def test_stages_whitelisted_v4_proposal_without_source_mutation(self) -> None:
        before = BIN.read_bytes()
        session = _session()
        try:
            keyframe = session.snapshot.document.keyframes[0]
            proposal = BileSceneProposal(hashlib.sha256(before).hexdigest(), 4, (KeyframeProposal(0, {"xx": keyframe.xx, "xy": keyframe.xy, "yx": keyframe.yx, "yy": keyframe.yy, "x": keyframe.x + 1.0, "y": keyframe.y}, None, None),), ())
            self.assertEqual(1, apply_scene_proposal(session, proposal))
            self.assertTrue(session.snapshot.dirty)
            self.assertEqual(keyframe.x + 1.0, session.snapshot.document.keyframes[0].x)
            self.assertEqual(before, BIN.read_bytes())
        finally:
            session.close()

    def test_rejects_cross_source_proposal(self) -> None:
        session = _session()
        try:
            with self.assertRaises(BileSceneProposalError):
                apply_scene_proposal(session, BileSceneProposal("0" * 64, 4, (), ()))
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
