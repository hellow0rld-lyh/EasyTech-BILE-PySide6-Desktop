from __future__ import annotations

import json
import os
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from test_project_model import _minimal_v2_bile, _minimal_v3_bile
from bile_workbench.candidate_validation import (
    CandidateValidationError,
    validate_candidate_bytes,
    validate_project_candidate,
)
from bile_workbench.overlay_compiler import compile_project_candidate
from bile_workbench.project_model import append_edit_operation, import_bile_project
from bile_workbench.raw_image import RawBileImage
from bile_workbench.safe_mutation import BileMutationBuffer


class CanonicalCandidateValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "unit.bin"
        self.project = self.root / "unit-project"
        self.output = self.root / "candidate.bin"
        self.source_bytes = _minimal_v3_bile()
        self.source.write_bytes(self.source_bytes)
        import_bile_project(self.source, self.project)
        append_edit_operation(
            self.project, section="BELE", index=0, field="transform.x", after=12.5
        )
        self.compile_report = compile_project_candidate(self.project, self.output)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_compiler_returns_canonical_offline_validation_evidence(self) -> None:
        validation = self.compile_report.canonical_validation
        self.assertEqual(validation.status, "OfflineValid")
        self.assertEqual(validation.scope, "OfflineStructuralAndEditSet")
        self.assertEqual(validation.candidate_sha256, self.compile_report.output_sha256)
        self.assertEqual(validation.expected_candidate_sha256, validation.candidate_sha256)
        self.assertTrue(validation.candidate_exact_match)
        self.assertEqual(validation.original_game_validation, "NotPerformed")
        self.assertEqual(
            validation.checks["candidateFileStableDuringValidation"], "NotApplicable"
        )
        self.assertTrue(all(
            value == "Passed"
            for key, value in validation.checks.items()
            if key != "candidateFileStableDuringValidation"
        ))

    def test_validates_published_candidate_and_serializes_report(self) -> None:
        report = validate_project_candidate(self.project, self.output)
        payload = report.to_dict()
        self.assertEqual(payload["schema"], "bile-workbench.candidate-validation/v1")
        self.assertEqual(payload["status"], "OfflineValid")
        self.assertEqual(payload["candidate_sha256"], RawBileImage.read(self.output).sha256)
        self.assertEqual(payload["operation_ids"], ["op-000001"])
        self.assertEqual(payload["changed_byte_count"], len(report.changed_byte_offsets))
        self.assertEqual(payload["checks"]["candidateFileStableDuringValidation"], "Passed")
        json.dumps(payload, ensure_ascii=False, allow_nan=False)

    def test_memory_candidate_validation_works_without_publishing(self) -> None:
        report = validate_candidate_bytes(
            self.project,
            self.output.read_bytes(),
            candidate_path=self.root / "not-yet-published.bin",
        )
        self.assertEqual(report.status, "OfflineValid")
        self.assertEqual(report.checks["candidateFileStableDuringValidation"], "NotApplicable")
        self.assertEqual(
            os.path.normcase(report.candidate_path),
            os.path.normcase(str((self.root / "not-yet-published.bin").resolve(strict=False))),
        )

    def test_different_but_structurally_valid_allowed_field_value_is_rejected(self) -> None:
        candidate = bytearray(self.output.read_bytes())
        section = RawBileImage.read(self.source).document.sections["BELE"]
        struct.pack_into("<f", candidate, section.payload_offset + 16, 13.5)
        self.output.write_bytes(candidate)
        with self.assertRaisesRegex(CandidateValidationError, "不完全一致"):
            validate_project_candidate(self.project, self.output)

    def test_unapproved_opaque_field_change_is_rejected(self) -> None:
        candidate = bytearray(self.output.read_bytes())
        section = RawBileImage.read(self.source).document.sections["BELE"]
        struct.pack_into("<I", candidate, section.payload_offset + 40, 0xDEADBEEF)
        self.output.write_bytes(candidate)
        with self.assertRaises(CandidateValidationError):
            validate_project_candidate(self.project, self.output)

    def test_source_path_cannot_be_used_as_candidate(self) -> None:
        with self.assertRaises(CandidateValidationError):
            validate_project_candidate(self.project, self.source)

    def test_hardlink_to_source_cannot_be_used_as_candidate(self) -> None:
        linked = self.root / "source-hardlink.bin"
        try:
            linked.hardlink_to(self.source)
        except (OSError, NotImplementedError):
            self.skipTest("当前文件系统不支持硬链接")
        with self.assertRaises(CandidateValidationError):
            validate_project_candidate(self.project, linked)

    def test_candidate_inside_project_is_rejected(self) -> None:
        inside = self.project / "candidate.bin"
        shutil.copy2(self.output, inside)
        with self.assertRaises(CandidateValidationError):
            validate_project_candidate(self.project, inside)

    def test_candidate_symlink_is_rejected(self) -> None:
        link = self.root / "candidate-link.bin"
        try:
            link.symlink_to(self.output)
        except (OSError, NotImplementedError):
            self.skipTest("当前 Windows 环境不允许创建文件符号链接")
        with self.assertRaises(CandidateValidationError):
            validate_project_candidate(self.project, link)

    def test_empty_edit_set_cannot_validate_a_candidate(self) -> None:
        empty_project = self.root / "empty-project"
        import_bile_project(self.source, empty_project)
        copy = self.root / "empty-copy.bin"
        shutil.copy2(self.source, copy)
        with self.assertRaises(CandidateValidationError):
            validate_project_candidate(empty_project, copy)

    def test_v2_source_cannot_validate_a_writable_candidate(self) -> None:
        v2_source = self.root / "v2.bin"
        v2_project = self.root / "v2-project"
        v2_candidate = self.root / "v2-candidate.bin"
        v2_source.write_bytes(_minimal_v2_bile())
        import_bile_project(v2_source, v2_project)
        shutil.copy2(v2_source, v2_candidate)
        with self.assertRaises(CandidateValidationError):
            validate_project_candidate(v2_project, v2_candidate)

    def test_source_drift_during_replay_aborts_validation(self) -> None:
        original_replace = BileMutationBuffer.replace

        def drift_source(buffer, offset, replacement, label):
            result = original_replace(buffer, offset, replacement, label)
            changed = bytearray(self.source.read_bytes())
            changed[-2] ^= 1
            self.source.write_bytes(changed)
            return result

        with patch("bile_workbench.candidate_validation.BileMutationBuffer.replace", drift_source):
            with self.assertRaisesRegex(CandidateValidationError, "source BIN 内容发生变化"):
                validate_candidate_bytes(self.project, self.output.read_bytes())
        self.source.write_bytes(self.source_bytes)

    def test_project_metadata_change_between_load_and_digest_is_rejected(self) -> None:
        import bile_workbench.candidate_validation as module
        original_digest = module._project_metadata_digest
        changed = {"done": False}
        edit_set_path = self.project / "metadata" / "edit-set.json"

        def mutate_before_digest(root, project):
            if not changed["done"]:
                payload = json.loads(edit_set_path.read_text(encoding="utf-8"))
                payload["operations"][0]["after"] = 13.5
                payload["operations"][0]["afterRawHex"] = struct.pack("<f", 13.5).hex()
                edit_set_path.write_text(
                    json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                )
                changed["done"] = True
            return original_digest(root, project)

        with patch.object(module, "_project_metadata_digest", mutate_before_digest):
            with self.assertRaisesRegex(CandidateValidationError, "读取期间发生变化"):
                validate_candidate_bytes(self.project, self.output.read_bytes())

    def test_project_metadata_drift_during_replay_aborts_validation(self) -> None:
        edit_set_path = self.project / "metadata" / "edit-set.json"
        original_replace = BileMutationBuffer.replace

        def drift_edit_set(buffer, offset, replacement, label):
            result = original_replace(buffer, offset, replacement, label)
            edit_set_path.write_text(
                edit_set_path.read_text(encoding="utf-8") + "\n", encoding="utf-8"
            )
            return result

        with patch("bile_workbench.candidate_validation.BileMutationBuffer.replace", drift_edit_set):
            with self.assertRaises(CandidateValidationError):
                validate_candidate_bytes(self.project, self.output.read_bytes())

    def test_candidate_file_drift_after_validation_is_detected(self) -> None:
        import bile_workbench.candidate_validation as module
        original = module._validate_candidate_bytes

        def validate_then_mutate(project_dir, candidate_bytes, *, candidate_path):
            report = original(project_dir, candidate_bytes, candidate_path=candidate_path)
            changed = bytearray(candidate_path.read_bytes())
            changed[-1] ^= 1
            candidate_path.write_bytes(changed)
            return report

        with patch.object(module, "_validate_candidate_bytes", validate_then_mutate):
            with self.assertRaisesRegex(CandidateValidationError, "候选 BIN 内容发生变化"):
                validate_project_candidate(self.project, self.output)

    def test_optional_asset_drift_is_reported_as_warning(self) -> None:
        xml = self.source.with_suffix(".xml")
        xml.write_text("<Atlas/>", encoding="utf-8")
        project = self.root / "asset-project"
        import_bile_project(self.source, project, xml_path=xml)
        append_edit_operation(
            project, section="BELE", index=0, field="transform.x", after=12.5
        )
        output = self.root / "asset-candidate.bin"
        compile_project_candidate(project, output)
        xml.write_text("<Atlas changed='1'/>", encoding="utf-8")
        report = validate_project_candidate(project, output)
        self.assertIn("OptionalAssetHashMismatch:atlas-xml", report.warnings)


if __name__ == "__main__":
    unittest.main()
