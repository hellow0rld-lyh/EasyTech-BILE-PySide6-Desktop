from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bile_workbench.assets import discover_triplet
from bile_workbench.bile_format import parse_file
from bile_workbench.bile_scene_proposal import BileSceneProposalError, PROPOSAL_SCHEMA, export_proposal_evidence, load_proposal, parse_proposal, proposal_template
from bile_workbench.bile_scene_proposal_apply import apply_scene_proposal
from bile_workbench.document_session import AnimationDocumentSession
from bile_workbench.preview_renderer import load_atlas
from bile_workbench.workbench_state import Workspace
from external_fixtures import require_triplet


ROOT = Path(__file__).resolve().parents[1]


def _v4_session() -> AnimationDocumentSession:
    source = ROOT / "sample_assets" / "anim_failure.bin"
    triplet = discover_triplet(source)
    workspace = Workspace.create(triplet.bin_path, triplet.xml_path, triplet.image_path, parse_file(triplet.bin_path), load_atlas(triplet.xml_path, triplet.image_path))
    return AnimationDocumentSession(workspace)


class BileSceneProposalTests(unittest.TestCase):
    def setUp(self) -> None:
        if self._testMethodName in {"test_template_is_bound_candidate_only_and_loadable", "test_evidence_exports_accepted_candidate_without_binary_writeback"}:
            require_triplet(self, ROOT / "sample_assets" / "anim_failure.bin")

    def test_accepts_only_bound_v3_v4_whitelist_intents(self) -> None:
        proposal = parse_proposal({
            "schema": PROPOSAL_SCHEMA,
            "writeback": "candidate_only",
            "source": {"bin_sha256": "a" * 64, "version": 4},
            "keyframes": [{"keyframe_index": 2, "transform": {"xx": 1, "xy": 0, "yx": 0, "yy": 1, "x": 4, "y": -3}, "argb": 0xFFAA5500, "initial_phase": 1}],
            "anchors": [{"element_index": 4, "x": 3.5, "y": 7.0}],
        })
        self.assertEqual(4, proposal.source_version)
        self.assertEqual(1, len(proposal.keyframes))
        self.assertEqual(1, len(proposal.anchors))

    def test_template_is_bound_candidate_only_and_loadable(self) -> None:
        session = _v4_session()
        try:
            payload = proposal_template(session)
            self.assertEqual(PROPOSAL_SCHEMA, payload["schema"])
            self.assertEqual("candidate_only", payload["writeback"])
            self.assertEqual(session.edit_session.source_sha256, payload["source"]["bin_sha256"])
            self.assertEqual(4, payload["source"]["version"])
            self.assertEqual({"xx", "xy", "yx", "yy", "x", "y"}, set(payload["keyframes"][0]["transform"]))
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "proposal.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                parsed = load_proposal(path)
            self.assertEqual(session.edit_session.source_sha256, parsed.source_bin_sha256)
        finally:
            session.close()

    def test_evidence_exports_accepted_candidate_without_binary_writeback(self) -> None:
        source = ROOT / "sample_assets" / "anim_failure.bin"
        before = source.read_bytes()
        session = _v4_session()
        try:
            payload = proposal_template(session)
            payload["keyframes"][0]["transform"]["x"] += 1.0
            proposal = parse_proposal(payload)
            apply_scene_proposal(session, proposal)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "evidence.json"
                evidence = export_proposal_evidence(path, session, proposal)
                self.assertEqual(evidence, json.loads(path.read_text(encoding="utf-8")))
            self.assertEqual("none", evidence["binary_writeback"])
            self.assertEqual(session.edit_session.source_sha256, evidence["source"]["bin_sha256"])
            self.assertTrue(evidence["current_staged_patch"]["keyframes"])
            self.assertEqual(before, source.read_bytes())
        finally:
            session.close()

    def test_rejects_v2_unknown_and_unverified_write_fields(self) -> None:
        base = {"schema": PROPOSAL_SCHEMA, "source": {"bin_sha256": "b" * 64, "version": 3}}
        with self.assertRaises(BileSceneProposalError):
            parse_proposal({**base, "source": {"bin_sha256": "b" * 64, "version": 2}})
        with self.assertRaises(BileSceneProposalError):
            parse_proposal({**base, "playback_mode": 1})
        with self.assertRaises(BileSceneProposalError):
            parse_proposal({**base, "keyframes": [{"keyframe_index": 0, "transform": {"x": 1}}]})


if __name__ == "__main__":
    unittest.main()
