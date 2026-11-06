from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from test_project_model import _minimal_v3_bile
from bile_workbench.candidate_workflow import CandidateWorkflow, CandidateWorkflowError
from bile_workbench.edit_session import EditSession
from bile_workbench.overlay_compiler import compile_project_candidate
from bile_workbench.project_model import append_edit_operation
from bile_workbench.project_workflow import ProjectWorkflowError, ProjectWorkflowService
from bile_workbench.raw_image import RawBileImage


class ProjectWorkflowServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "unit.bin"
        self.project = self.root / "unit-project"
        self.candidate = self.root / "candidate.bin"
        self.source.write_bytes(_minimal_v3_bile())
        self.service = ProjectWorkflowService.import_source(
            self.source, self.project, candidate_path=self.candidate
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_candidate_lifecycle_current_stale_and_recompiled(self) -> None:
        self.assertEqual(self.service.inspect().candidate.status, "Missing")
        self.service.append_edit(section="BELE", index=0, field="transform.x", after=12.5)
        build = self.service.compile_candidate(self.candidate)
        self.assertTrue(build.manifest_written)
        self.assertEqual(build.validation.status, "OfflineValid")
        self.assertEqual(build.snapshot.candidate.status, "Current")
        self.assertEqual(build.snapshot.operation_count, 1)

        self.service.append_edit(section="BELE", index=0, field="transform.x", after=14.25)
        stale = self.service.inspect()
        self.assertEqual(stale.candidate.status, "Stale")
        with self.assertRaises(ProjectWorkflowError):
            self.service.validate_candidate()

        rebuilt = self.service.compile_candidate(self.candidate, overwrite=True)
        self.assertEqual(rebuilt.snapshot.candidate.status, "Current")
        self.assertEqual(rebuilt.snapshot.operation_count, 2)
        self.assertEqual(RawBileImage.read(self.candidate).document.keyframes[0].x, 14.25)

    def test_candidate_tampering_is_invalid(self) -> None:
        self.service.append_edit(section="BELE", index=0, field="transform.x", after=12.5)
        self.service.compile_candidate(self.candidate)
        changed = bytearray(self.candidate.read_bytes())
        changed[-1] ^= 1
        self.candidate.write_bytes(changed)
        state = self.service.inspect().candidate
        self.assertEqual(state.status, "Invalid")
        self.assertIn("不一致", state.message or "")

    def test_untracked_exact_candidate_can_be_validated_and_registered(self) -> None:
        self.service.append_edit(section="BELE", index=0, field="transform.x", after=12.5)
        compile_project_candidate(self.project, self.candidate)
        self.assertEqual(self.service.inspect().candidate.status, "CurrentUntracked")
        self.service.validate_candidate()
        self.assertEqual(self.service.inspect().candidate.status, "Current")

    def test_malformed_manifest_is_not_trusted(self) -> None:
        self.service.append_edit(section="BELE", index=0, field="transform.x", after=12.5)
        self.service.compile_candidate(self.candidate)
        manifest = self.candidate.with_name(self.candidate.name + ".bile-workbench.json")
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["candidateSha256"] = "0" * 64
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(self.service.inspect().candidate.status, "Invalid")

    def test_candidate_inside_project_is_rejected(self) -> None:
        self.service.append_edit(section="BELE", index=0, field="transform.x", after=12.5)
        with self.assertRaises(ProjectWorkflowError):
            self.service.compile_candidate(self.project / "candidate.bin")
        self.assertFalse((self.project / "candidate.bin").exists())

    def test_candidate_path_states_are_explicit(self) -> None:
        self.assertEqual(ProjectWorkflowService(self.project).inspect().candidate.status, "NotConfigured")
        self.assertEqual(self.service.inspect().candidate.status, "Missing")
        self.assertEqual(self.service.set_candidate_path(self.candidate).candidate.status, "Missing")
        self.assertEqual(self.service.set_candidate_path(None).candidate.status, "NotConfigured")

    def test_sync_edit_session_is_idempotent_and_tracks_later_changes(self) -> None:
        session = EditSession(self.source)
        try:
            session.set_keyframe(0, {"x": 12.5}, 0xFFFFFFFF, 0)
            first = self.service.sync_edit_session(session)
            self.assertEqual(len(first), 1)
            self.assertEqual(self.service.inspect().operation_count, 1)
            self.assertEqual(self.service.sync_edit_session(session), ())

            session.set_keyframe(0, {"x": 14.25}, 0xFFFFFFFF, 0)
            second = self.service.sync_edit_session(session)
            self.assertEqual(len(second), 1)
            self.assertEqual(second[0]["before"], 12.5)
            self.assertEqual(second[0]["after"], 14.25)
            self.assertEqual(self.service.inspect().operation_count, 2)
            build = self.service.compile_candidate(self.candidate)
            self.assertEqual(RawBileImage.read(self.candidate).document.keyframes[0].x, 14.25)
            self.assertEqual(build.snapshot.candidate.status, "Current")
        finally:
            session.close()

    def test_sync_failure_does_not_partially_mutate_project(self) -> None:
        import bile_workbench.project_workflow as module

        session = EditSession(self.source)
        try:
            session.set_keyframe(0, {"x": 12.5, "y": 13.5}, 0xFFFFFFFF, 0)
            original = (self.project / "metadata" / "edit-set.json").read_bytes()
            real_append = module.append_edit_operation
            calls = {"count": 0}

            def fail_second_append(*args, **kwargs):
                calls["count"] += 1
                if calls["count"] == 2:
                    raise ProjectWorkflowError("injected staging failure")
                return real_append(*args, **kwargs)

            with patch.object(module, "append_edit_operation", fail_second_append):
                with self.assertRaisesRegex(ProjectWorkflowError, "原 Project 未改变"):
                    self.service.sync_edit_session(session)
            self.assertEqual(
                (self.project / "metadata" / "edit-set.json").read_bytes(),
                original,
            )
            self.assertEqual(self.service.inspect().operation_count, 0)
        finally:
            session.close()

    def test_sync_clean_session_appends_revert_to_source(self) -> None:
        source_x = RawBileImage.read(self.source).document.keyframes[0].x
        session = EditSession(self.source)
        try:
            session.set_keyframe(0, {"x": 12.5}, 0xFFFFFFFF, 0)
            self.service.sync_edit_session(session)
            session.clear()
            revert = self.service.sync_edit_session(session)
            self.assertEqual(len(revert), 1)
            self.assertEqual(revert[0]["after"], source_x)
            self.assertEqual(self.service.inspect().operation_count, 2)
            self.assertEqual(RawBileImage.read(self.source).document.keyframes[0].x, source_x)
            self.assertEqual(self.service.inspect().candidate.status, "Missing")
        finally:
            session.close()

    def test_restore_project_into_clean_edit_session(self) -> None:
        self.service.append_edit(section="BELE", index=0, field="transform.x", after=12.5)
        session = EditSession(self.source)
        try:
            restored = self.service.restore_edit_session(session)
            self.assertIn(("BELE", 0, "transform.x"), restored)
            self.assertTrue(session.dirty)
            self.assertEqual(session.preview_document().keyframes[0].x, 12.5)
            self.assertEqual(self.service.sync_edit_session(session), ())
        finally:
            session.close()

    def test_restore_rejects_project_fields_not_exposed_by_desktop_edit_session(self) -> None:
        self.service.append_edit(section="BMTI", index=0, field="name", after="unit")
        session = EditSession(self.source)
        try:
            with self.assertRaisesRegex(ProjectWorkflowError, "尚不支持恢复 Project 字段：BMTI\\[0\\]\\.name"):
                self.service.restore_edit_session(session)
            self.assertFalse(session.dirty)
        finally:
            session.close()

    def test_restore_refuses_dirty_edit_session(self) -> None:
        session = EditSession(self.source)
        try:
            session.set_keyframe(0, {"x": 12.5}, 0xFFFFFFFF, 0)
            with self.assertRaisesRegex(ProjectWorkflowError, "必须先处理当前暂存编辑"):
                self.service.restore_edit_session(session)
        finally:
            session.close()

    def test_operation_history_is_ordered_and_read_only(self) -> None:
        self.service.append_edit(section="BELE", index=0, field="transform.x", after=12.5)
        self.service.append_edit(section="BELE", index=0, field="transform.x", after=14.25)
        history = self.service.operation_history()
        self.assertEqual([operation["sequence"] for operation in history], [1, 2])
        self.assertEqual([operation["after"] for operation in history], [12.5, 14.25])

    def test_inspect_rejects_project_metadata_drift_during_snapshot(self) -> None:
        import bile_workbench.project_workflow as module

        original_digest = module._metadata_digest
        calls = {"count": 0}
        edit_set_path = self.project / "metadata" / "edit-set.json"

        def mutate_after_first_digest(root, project):
            digest = original_digest(root, project)
            calls["count"] += 1
            if calls["count"] == 1:
                edit_set_path.write_text(
                    edit_set_path.read_text(encoding="utf-8") + "\n",
                    encoding="utf-8",
                )
            return digest

        with patch.object(module, "_metadata_digest", mutate_after_first_digest):
            with self.assertRaisesRegex(ProjectWorkflowError, "snapshot 期间发生变化"):
                self.service.inspect()


class EditSessionProjectAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "unit.bin"
        self.project = self.root / "unit-project"
        self.candidate = self.root / "candidate.bin"
        self.source.write_bytes(_minimal_v3_bile())
        self.service = ProjectWorkflowService.import_source(self.source, self.project)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_maps_only_changed_fields_to_ordered_edit_set(self) -> None:
        session = EditSession(self.source)
        try:
            session.set_keyframe(0, {"x": 12.5}, 0x80FFFFFF, 3)
            session.set_anchor(0, 3.0, -4.0)
            operations = self.service.apply_edit_session(session)
            self.assertEqual(
                [item["field"] for item in operations],
                ["transform.x", "argb", "initial_phase", "anchor"],
            )
            self.assertEqual([item["sequence"] for item in operations], [1, 2, 3, 4])
            build = self.service.compile_candidate(self.candidate)
            document = RawBileImage.read(self.candidate).document
            self.assertEqual(document.keyframes[0].x, 12.5)
            self.assertEqual(document.keyframes[0].argb, 0x80FFFFFF)
            self.assertEqual(document.keyframes[0].initial_phase, 3)
            self.assertEqual((document.elements[0].x, document.elements[0].y), (3.0, -4.0))
            self.assertEqual(build.validation.operation_count, 4)
        finally:
            session.close()

    def test_clean_and_noop_sessions_are_rejected(self) -> None:
        clean = EditSession(self.source)
        try:
            with self.assertRaisesRegex(ProjectWorkflowError, "为空"):
                self.service.apply_edit_session(clean)
        finally:
            clean.close()

        noop = EditSession(self.source)
        try:
            noop.set_keyframe(0, {"x": 10.0}, 0xFFFFFFFF, 0)
            with self.assertRaisesRegex(ProjectWorkflowError, "没有产生实际字段字节变化"):
                self.service.apply_edit_session(noop)
            self.assertEqual(self.service.validate().operation_count, 0)
        finally:
            noop.close()

    def test_wrong_source_and_nonempty_project_are_rejected(self) -> None:
        other = self.root / "same-bytes-different-path.bin"
        shutil.copy2(self.source, other)
        session = EditSession(other)
        try:
            session.set_keyframe(0, {"x": 12.5}, 0xFFFFFFFF, 0)
            with self.assertRaisesRegex(ProjectWorkflowError, "同一个 source BIN 路径"):
                self.service.apply_edit_session(session)
        finally:
            session.close()

        append_edit_operation(self.project, section="BELE", index=0, field="transform.x", after=12.5)
        session = EditSession(self.source)
        try:
            session.set_anchor(0, 3.0, -4.0)
            with self.assertRaisesRegex(ProjectWorkflowError, "空 Edit Set"):
                self.service.apply_edit_session(session)
        finally:
            session.close()


class CandidateWorkflowIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "unit.bin"
        self.xml = self.root / "unit.xml"
        self.image = self.root / "unit.webp"
        self.candidate = self.root / "candidate.bin"
        self.source_bytes = _minimal_v3_bile()
        self.source.write_bytes(self.source_bytes)
        self.xml.write_text("<Atlas/>", encoding="utf-8")
        self.image.write_bytes(b"reference-only-test-image")
        self.session = EditSession(self.source)
        self.session.set_keyframe(0, {"x": 12.5}, 0xFFFFFFFF, 0)
        self.workflow = CandidateWorkflow(self.source, self.xml, self.image, object(), self.session)
        # Preflight has separate integration coverage; this fixture isolates the adapter.
        self.workflow.require_preflight = lambda: None

    def tearDown(self) -> None:
        self.session.close()
        self.temp.cleanup()

    def test_candidate_workflow_uses_project_compiler_and_canonical_validation(self) -> None:
        result = self.workflow.compile_project_candidate(self.candidate)
        self.assertTrue(self.candidate.is_file())
        self.assertEqual(result.operation_count, 1)
        self.assertEqual(result.validation.status, "OfflineValid")
        self.assertEqual(RawBileImage.read(self.candidate).document.keyframes[0].x, 12.5)
        self.assertEqual(result.candidate_sha256, RawBileImage.read(self.candidate).sha256)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)

    def test_candidate_workflow_refuses_overwrite_by_default(self) -> None:
        self.candidate.write_bytes(b"preserve me")
        with self.assertRaises(CandidateWorkflowError):
            self.workflow.compile_project_candidate(self.candidate)
        self.assertEqual(self.candidate.read_bytes(), b"preserve me")

    def test_candidate_workflow_syncs_to_persistent_project_without_stealing_candidate_path(self) -> None:
        project = ProjectWorkflowService.import_source(self.source, self.root / "persistent-project")
        project.set_candidate_path(self.root / "tracked-candidate.bin")
        workflow = CandidateWorkflow(
            self.source, self.xml, self.image, object(), self.session, project_service=project
        )
        workflow.require_preflight = lambda: None
        result = workflow.compile_project_candidate(self.candidate)
        self.assertEqual(result.validation.status, "OfflineValid")
        self.assertEqual(project.inspect().operation_count, 1)
        self.assertEqual(
            project.inspect().candidate.path.casefold(),
            str((self.root / "tracked-candidate.bin").resolve(strict=False)).casefold(),
        )
        self.assertEqual(project.inspect().candidate.status, "Missing")


if __name__ == "__main__":
    unittest.main()
