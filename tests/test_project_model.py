from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.project_model import (
    ProjectModelError,
    append_edit_operation,
    import_bile_project,
    validate_project,
)


def _section(tag: str, payload: bytes, count: int) -> bytes:
    header_size = 12 if tag == "BRTS" else 16
    header = tag.encode("ascii") + struct.pack("<II", header_size + len(payload), count)
    if header_size == 16:
        header += struct.pack("<I", 0xA1B2C3D4)
    return header + payload


def _minimal_v3_bile(*, shared_name: bool = False) -> bytes:
    bele = struct.pack(
        "<6f5I",
        1.0, 0.0, 0.0, 1.0, 10.0, 20.0,
        0xFFFFFFFF, 0, 0, 0x12345678, 0x9ABCDEF0,
    )
    bxdi = struct.pack("<Ii", 0, -1)
    bmrf = struct.pack("<HHI", 0, 1, 0x11223344)
    byal = struct.pack("<II", 1, 0x55667788)
    bmti = bytearray(56)
    struct.pack_into("<IIff", bmti, 0, 0, 0, 1.0, 2.0)
    struct.pack_into("<I", bmti, 28, 1)
    struct.pack_into("<I", bmti, 32, 1)
    bmti_payload = bytearray(bmti)
    bmti_count = 1
    if shared_name:
        second = bytearray(56)
        struct.pack_into("<IIff", second, 0, 1, 0, 0.0, 0.0)
        bmti_payload.extend(second)
        bmti_count = 2
    sections = b"".join((
        _section("BELE", bele, 1),
        _section("BXDI", bxdi, 1),
        _section("BMRF", bmrf, 1),
        _section("BYAL", byal, 1),
        _section("BMTI", bytes(bmti_payload), bmti_count),
        _section("BRTS", b"root\0", 1),
    ))
    return b"BILE" + struct.pack("<IIHHf", 3, len(sections), 20, 6, 30.0) + sections


def _minimal_v2_bile() -> bytes:
    bele = struct.pack(
        "<6ff5I",
        1.0, 0.0, 0.0, 1.0, 10.0, 20.0,
        1.0, 0, 0, 0x12345678, 0, 0xFFFFFFFF,
    )
    bmrf = struct.pack("<III", 0, 1, 0x11223344)
    byal = struct.pack("<II", 1, 0x55667788)
    bmti = bytearray(56)
    struct.pack_into("<IIff", bmti, 0, 0, 0, 1.0, 2.0)
    struct.pack_into("<I", bmti, 28, 1)
    struct.pack_into("<I", bmti, 32, 1)
    sections = b"".join((
        _section("BELE", bele, 1),
        _section("BMRF", bmrf, 1),
        _section("BYAL", byal, 1),
        _section("BMTI", bytes(bmti), 1),
        _section("BRTS", b"root\0", 1),
    ))
    return b"BILE" + struct.pack("<IIHHf", 2, len(sections), 20, 5, 30.0) + sections


class ProjectModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "unit.bin"
        self.project = self.root / "unit-project"
        self.source.write_bytes(_minimal_v3_bile())

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_import_creates_reference_only_project_without_raw_copies(self) -> None:
        report = import_bile_project(self.source, self.project)
        self.assertEqual(report.status, "Valid")
        self.assertEqual(report.project_kind, "ImportedOriginal")
        self.assertEqual(report.writer_capability, "Conditional")
        self.assertEqual(report.operation_count, 0)
        self.assertFalse(list(self.project.rglob("*.bin")))
        self.assertFalse(list(self.project.rglob("*.xml")))
        self.assertFalse(list(self.project.rglob("*.webp")))
        self.assertTrue((self.project / "motions" / "README.md").is_file())
        self.assertTrue((self.project / "raw" / "README.md").is_file())

        manifest = json.loads((self.project / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["originKind"], "ImportedOriginal")
        self.assertTrue(manifest["source"]["bin"]["referenceOnly"])
        self.assertEqual(manifest["compiler"]["writesBinary"], True)
        self.assertTrue(manifest["compiler"]["candidateOnly"])
        self.assertFalse(manifest["compiler"]["inPlaceWrite"])

    def test_import_references_optional_assets_without_copying_them(self) -> None:
        xml = self.source.with_suffix(".xml")
        texture = self.source.with_suffix(".webp")
        xml.write_text("<Atlas/>", encoding="utf-8")
        texture.write_bytes(b"not-decoded-here")
        import_bile_project(self.source, self.project)
        assets = json.loads((self.project / "assets" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([item["role"] for item in assets["references"]], ["bile", "atlas-xml", "texture"])
        self.assertEqual(assets["storagePolicy"], "ReferenceOnly")
        self.assertEqual(assets["copiedPayloads"], [])
        self.assertFalse((self.project / "assets" / "unit.bin").exists())
        self.assertFalse((self.project / "assets" / "unit.xml").exists())
        self.assertFalse((self.project / "assets" / "unit.webp").exists())

    def test_record_identity_file_contains_hashes_not_raw_records(self) -> None:
        import_bile_project(self.source, self.project)
        identities = json.loads(
            (self.project / "metadata" / "record-identities.json").read_text(encoding="utf-8")
        )
        self.assertFalse(identities["rawPayloadIncluded"])
        bele = next(item for item in identities["sections"] if item["tag"] == "BELE")
        self.assertEqual(bele["records"][0]["recordId"].split(":")[:2], ["BELE", "0"])
        self.assertEqual(len(bele["records"][0]["sha256"]), 64)
        self.assertNotIn("raw", bele["records"][0])

    def test_append_transform_operation_captures_identity_before_after_and_raw_bits(self) -> None:
        import_bile_project(self.source, self.project)
        operation = append_edit_operation(
            self.project, section="BELE", index=0, field="transform.x", after=12.5
        )
        self.assertEqual(operation["kind"], "SetField")
        self.assertEqual(operation["before"], 10.0)
        self.assertEqual(operation["after"], 12.5)
        self.assertEqual(operation["target"]["section"], "BELE")
        self.assertEqual(operation["target"]["index"], 0)
        self.assertEqual(operation["storage"]["section"], "BELE")
        self.assertEqual(operation["storage"]["width"], 4)
        self.assertEqual(len(operation["beforeRawHex"]), 8)
        self.assertEqual(len(operation["afterRawHex"]), 8)
        report = validate_project(self.project)
        self.assertEqual(report.project_kind, "ImportedModified")
        self.assertEqual(report.operation_count, 1)

    def test_repeated_operations_form_an_explicit_before_after_chain(self) -> None:
        import_bile_project(self.source, self.project)
        first = append_edit_operation(
            self.project, section="BELE", index=0, field="transform.x", after=12.5
        )
        second = append_edit_operation(
            self.project, section="BELE", index=0, field="transform.x", after=14.25
        )
        self.assertEqual(second["sequence"], 2)
        self.assertEqual(second["before"], 12.5)
        self.assertEqual(second["beforeRawHex"], first["afterRawHex"])
        self.assertEqual(validate_project(self.project).operation_count, 2)

    def test_anchor_argb_initial_phase_and_same_length_name_operations_are_supported(self) -> None:
        import_bile_project(self.source, self.project)
        anchor = append_edit_operation(
            self.project, section="BMTI", index=0, field="anchor", after=[3.0, -4.0]
        )
        argb = append_edit_operation(
            self.project, section="BELE", index=0, field="argb", after="0x80FFFFFF"
        )
        phase = append_edit_operation(
            self.project, section="BELE", index=0, field="initial_phase", after=1
        )
        name = append_edit_operation(
            self.project, section="BMTI", index=0, field="name", after="unit"
        )
        self.assertEqual(anchor["before"], [1.0, 2.0])
        self.assertEqual(argb["after"], 0x80FFFFFF)
        self.assertEqual(phase["after"], 1)
        self.assertEqual(name["before"], "root")
        self.assertEqual(name["after"], "unit")
        self.assertEqual(validate_project(self.project).operation_count, 4)

    def test_v2_import_is_read_only_and_rejects_edit_operations(self) -> None:
        self.source.write_bytes(_minimal_v2_bile())
        report = import_bile_project(self.source, self.project)
        self.assertEqual(report.writer_capability, "NoGo")
        self.assertEqual(report.source_version, 2)
        with self.assertRaises(ProjectModelError):
            append_edit_operation(
                self.project, section="BELE", index=0, field="transform.x", after=20.0
            )

    def test_shared_string_name_is_not_editable(self) -> None:
        self.source.write_bytes(_minimal_v3_bile(shared_name=True))
        import_bile_project(self.source, self.project)
        with self.assertRaises(ProjectModelError):
            append_edit_operation(
                self.project, section="BMTI", index=0, field="name", after="unit"
            )

    def test_structural_and_playback_mode_operations_are_rejected(self) -> None:
        import_bile_project(self.source, self.project)
        with self.assertRaises(ProjectModelError):
            append_edit_operation(
                self.project, section="BELE", index=0, field="playback_mode", after=1
            )
        with self.assertRaises(ProjectModelError):
            append_edit_operation(
                self.project, section="BMRF", index=0, field="frame_count", after=2
            )

    def test_noop_and_length_changing_name_operations_are_rejected(self) -> None:
        import_bile_project(self.source, self.project)
        with self.assertRaises(ProjectModelError):
            append_edit_operation(
                self.project, section="BELE", index=0, field="transform.x", after=10.0
            )
        with self.assertRaises(ProjectModelError):
            append_edit_operation(
                self.project, section="BMTI", index=0, field="name", after="longer"
            )

    def test_source_drift_invalidates_project(self) -> None:
        import_bile_project(self.source, self.project)
        source = bytearray(self.source.read_bytes())
        source[-2] ^= 0x01
        self.source.write_bytes(source)
        with self.assertRaises(ProjectModelError):
            validate_project(self.project)

    def test_edit_set_tampering_is_detected(self) -> None:
        import_bile_project(self.source, self.project)
        append_edit_operation(
            self.project, section="BELE", index=0, field="transform.x", after=12.5
        )
        path = self.project / "metadata" / "edit-set.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["operations"][0]["beforeRawHex"] = "00000000"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(ProjectModelError):
            validate_project(self.project)

    def test_record_identity_tampering_is_detected(self) -> None:
        import_bile_project(self.source, self.project)
        path = self.project / "metadata" / "record-identities.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["sections"][0]["records"][0]["sha256"] = "0" * 64
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(ProjectModelError):
            validate_project(self.project)

    def test_optional_asset_drift_is_a_warning_not_a_source_identity_change(self) -> None:
        xml = self.source.with_suffix(".xml")
        xml.write_text("<Atlas/>", encoding="utf-8")
        import_bile_project(self.source, self.project)
        xml.write_text("<Atlas changed='1'/>", encoding="utf-8")
        report = validate_project(self.project)
        self.assertIn("OptionalAssetHashMismatch:atlas-xml", report.warnings)

    def test_existing_project_directory_is_never_overwritten(self) -> None:
        self.project.mkdir()
        sentinel = self.project / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        with self.assertRaises(ProjectModelError):
            import_bile_project(self.source, self.project)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_project_writer_boundary_cannot_be_relaxed(self) -> None:
        import_bile_project(self.source, self.project)
        path = self.project / "project.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["compiler"]["inPlaceWrite"] = True
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(ProjectModelError):
            validate_project(self.project)

    def test_project_paths_cannot_escape_project_root(self) -> None:
        import_bile_project(self.source, self.project)
        path = self.project / "project.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["paths"]["editSet"] = "../outside.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(ProjectModelError):
            validate_project(self.project)

    def test_edit_set_cannot_enable_structural_edits(self) -> None:
        import_bile_project(self.source, self.project)
        path = self.project / "metadata" / "edit-set.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["structuralEditsAllowed"] = True
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(ProjectModelError):
            validate_project(self.project)

    def test_synthetic_fixture_origin_kind_is_preserved(self) -> None:
        report = import_bile_project(
            self.source, self.project, origin_kind="SyntheticFixture"
        )
        self.assertEqual(report.project_kind, "SyntheticFixture")


if __name__ == "__main__":
    unittest.main()
