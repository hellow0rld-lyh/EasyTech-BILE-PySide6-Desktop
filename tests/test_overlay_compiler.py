from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_project_model import _minimal_v2_bile, _minimal_v3_bile

from bile_workbench.overlay_compiler import (
    OverlayCompilationError,
    compile_project_candidate,
)
from bile_workbench.project_model import (
    ProjectModelError,
    append_edit_operation,
    import_bile_project,
    validate_project,
)
from bile_workbench.raw_image import RawBileImage
from bile_workbench.safe_mutation import BileMutationBuffer, BileMutationError, changed_byte_offsets


class OverlayCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "unit.bin"
        self.project = self.root / "unit-project"
        self.output = self.root / "candidate.bin"
        self.source_bytes = _minimal_v3_bile()
        self.source.write_bytes(self.source_bytes)
        import_bile_project(self.source, self.project)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_compiles_multiple_field_operations_to_separate_candidate(self) -> None:
        append_edit_operation(
            self.project, section="BELE", index=0, field="transform.x", after=12.5
        )
        append_edit_operation(
            self.project, section="BMTI", index=0, field="anchor", after=[3.0, -4.0]
        )
        append_edit_operation(
            self.project, section="BELE", index=0, field="argb", after="0x80FFFFFF"
        )
        append_edit_operation(
            self.project, section="BMTI", index=0, field="name", after="unit"
        )
        project_files = {
            path.relative_to(self.project): path.read_bytes()
            for path in self.project.rglob("*") if path.is_file()
        }

        report = compile_project_candidate(self.project, self.output)

        self.assertTrue(self.output.is_file())
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(report.operation_count, 4)
        self.assertEqual(report.version, 3)
        self.assertEqual(report.output_sha256, RawBileImage.read(self.output).sha256)
        self.assertEqual(
            report.changed_byte_offsets,
            changed_byte_offsets(self.source_bytes, self.output.read_bytes()),
        )
        candidate = RawBileImage.read(self.output).document
        self.assertEqual(candidate.keyframes[0].x, 12.5)
        self.assertEqual(candidate.keyframes[0].argb, 0x80FFFFFF)
        self.assertEqual(candidate.elements[0].x, 3.0)
        self.assertEqual(candidate.elements[0].y, -4.0)
        self.assertEqual(candidate.elements[0].name, "unit")
        self.assertEqual(
            {path.relative_to(self.project): path.read_bytes()
             for path in self.project.rglob("*") if path.is_file()},
            project_files,
        )
        self.assertFalse(list(self.project.rglob("*.bin")))
        self.assertEqual(validate_project(self.project).operation_count, 4)

    def test_repeated_field_operations_compile_to_the_final_value(self) -> None:
        append_edit_operation(
            self.project, section="BELE", index=0, field="transform.x", after=12.5
        )
        append_edit_operation(
            self.project, section="BELE", index=0, field="transform.x", after=14.25
        )
        report = compile_project_candidate(self.project, self.output)
        self.assertEqual(report.operation_count, 2)
        self.assertEqual(RawBileImage.read(self.output).document.keyframes[0].x, 14.25)

    def test_final_changed_byte_union_excludes_fields_reverted_to_original(self) -> None:
        append_edit_operation(
            self.project, section="BELE", index=0, field="transform.x", after=12.5
        )
        append_edit_operation(
            self.project, section="BELE", index=0, field="transform.x", after=10.0
        )
        append_edit_operation(
            self.project, section="BMTI", index=0, field="anchor", after=[3.0, 4.0]
        )
        report = compile_project_candidate(self.project, self.output)
        actual = changed_byte_offsets(self.source_bytes, self.output.read_bytes())
        self.assertEqual(report.changed_byte_offsets, actual)
        self.assertTrue(actual)
        self.assertFalse(any(
            offset in actual
            for offset in range(
                RawBileImage.read(self.source).document.sections["BELE"].payload_offset + 16,
                RawBileImage.read(self.source).document.sections["BELE"].payload_offset + 20,
            )
        ))

    def test_empty_edit_set_is_not_compiled(self) -> None:
        with self.assertRaises(OverlayCompilationError):
            compile_project_candidate(self.project, self.output)
        self.assertFalse(self.output.exists())

    def test_reverted_all_operations_do_not_publish_an_empty_candidate(self) -> None:
        append_edit_operation(
            self.project, section="BELE", index=0, field="transform.x", after=12.5
        )
        append_edit_operation(
            self.project, section="BELE", index=0, field="transform.x", after=10.0
        )
        with self.assertRaises(OverlayCompilationError):
            compile_project_candidate(self.project, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(), self.source_bytes)

    def test_replay_failure_discards_memory_overlay_and_preserves_existing_output(self) -> None:
        append_edit_operation(
            self.project, section="BELE", index=0, field="transform.x", after=12.5
        )
        append_edit_operation(
            self.project, section="BMTI", index=0, field="anchor", after=[3.0, 4.0]
        )
        previous = b"existing candidate survives failed overlay"
        self.output.write_bytes(previous)
        original_replace = BileMutationBuffer.replace
        calls = {"count": 0}

        def fail_second(buffer, offset, replacement, label):
            calls["count"] += 1
            if calls["count"] == 2:
                raise BileMutationError("injected overlay failure")
            return original_replace(buffer, offset, replacement, label)

        with patch("bile_workbench.overlay_compiler.BileMutationBuffer.replace", fail_second):
            with self.assertRaises(OverlayCompilationError):
                compile_project_candidate(self.project, self.output, overwrite=True)
        self.assertEqual(self.output.read_bytes(), previous)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)

    def test_metadata_drift_during_replay_aborts_before_publication(self) -> None:
        append_edit_operation(
            self.project, section="BELE", index=0, field="transform.x", after=12.5
        )
        edit_set_path = self.project / "metadata" / "edit-set.json"
        original_replace = BileMutationBuffer.replace

        def mutate_metadata(buffer, offset, replacement, label):
            result = original_replace(buffer, offset, replacement, label)
            edit_set_path.write_text(
                edit_set_path.read_text(encoding="utf-8") + "\n", encoding="utf-8"
            )
            return result

        with patch("bile_workbench.overlay_compiler.BileMutationBuffer.replace", mutate_metadata):
            with self.assertRaises(OverlayCompilationError):
                compile_project_candidate(self.project, self.output)
        self.assertFalse(self.output.exists())

    def test_source_drift_invalidates_project_before_publication(self) -> None:
        append_edit_operation(
            self.project, section="BELE", index=0, field="transform.x", after=12.5
        )
        changed = bytearray(self.source.read_bytes())
        changed[-2] ^= 0x01
        self.source.write_bytes(changed)
        with self.assertRaises(ProjectModelError):
            compile_project_candidate(self.project, self.output)
        self.assertFalse(self.output.exists())

    def test_tampered_edit_set_is_rejected_before_publication(self) -> None:
        append_edit_operation(
            self.project, section="BELE", index=0, field="transform.x", after=12.5
        )
        edit_set_path = self.project / "metadata" / "edit-set.json"
        payload = json.loads(edit_set_path.read_text(encoding="utf-8"))
        payload["operations"][0]["afterRawHex"] = "00000000"
        edit_set_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(ProjectModelError):
            compile_project_candidate(self.project, self.output)
        self.assertFalse(self.output.exists())

    def test_output_inside_project_is_rejected(self) -> None:
        append_edit_operation(
            self.project, section="BELE", index=0, field="transform.x", after=12.5
        )
        with self.assertRaises(OverlayCompilationError):
            compile_project_candidate(self.project, self.project / "candidate.bin")
        self.assertFalse((self.project / "candidate.bin").exists())

    def test_existing_output_requires_explicit_overwrite(self) -> None:
        append_edit_operation(
            self.project, section="BELE", index=0, field="transform.x", after=12.5
        )
        previous = b"keep previous output"
        self.output.write_bytes(previous)
        with self.assertRaises(OverlayCompilationError):
            compile_project_candidate(self.project, self.output)
        self.assertEqual(self.output.read_bytes(), previous)
        report = compile_project_candidate(self.project, self.output, overwrite=True)
        self.assertEqual(report.output_sha256, RawBileImage.read(self.output).sha256)
        self.assertNotEqual(self.output.read_bytes(), previous)

    def test_v2_reference_project_has_no_candidate_compiler_capability(self) -> None:
        self.source.write_bytes(_minimal_v2_bile())
        shutil.rmtree(self.project)
        import_bile_project(self.source, self.project)
        with self.assertRaises(OverlayCompilationError):
            compile_project_candidate(self.project, self.output)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
