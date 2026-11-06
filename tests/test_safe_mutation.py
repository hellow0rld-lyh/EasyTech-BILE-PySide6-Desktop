from __future__ import annotations

import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import BileFormatError, parse_file
from bile_workbench.interchange import SCHEMA, apply_patch_report, export_interchange
from bile_workbench.edit_session import EditSession
from bile_workbench.raw_image import RawBileImage
from bile_workbench.safe_mutation import BileMutationBuffer, verify_candidate_bytes


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
    struct.pack_into("<I", bmti, 24, 0)
    struct.pack_into("<I", bmti, 28, 1)
    struct.pack_into("<I", bmti, 32, 1)
    bmti_payload = bytearray(bmti)
    bmti_count = 1
    if shared_name:
        second = bytearray(56)
        struct.pack_into("<IIff", second, 0, 1, 0, 0.0, 0.0)
        bmti_payload.extend(second)
        bmti_count = 2
    brts = b"root\0"
    sections = b"".join((
        _section("BELE", bele, 1),
        _section("BXDI", bxdi, 1),
        _section("BMRF", bmrf, 1),
        _section("BYAL", byal, 1),
        _section("BMTI", bytes(bmti_payload), bmti_count),
        _section("BRTS", brts, 1),
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
    struct.pack_into("<I", bmti, 24, 0)
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

def _patch(source_bytes: bytes, *, keyframes=None, elements=None) -> dict:
    return {
        "schema": SCHEMA,
        "kind": "patch",
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "keyframes": [] if keyframes is None else keyframes,
        "elements": [] if elements is None else elements,
    }


class SafeMutationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.bin"
        self.source_bytes = _minimal_v3_bile()
        self.source.write_bytes(self.source_bytes)
        self.patch_path = self.root / "patch.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_patch(self, payload: dict) -> None:
        self.patch_path.write_text(
            json.dumps(payload, ensure_ascii=False, allow_nan=True),
            encoding="utf-8",
        )

    def test_raw_image_round_trip_preserves_all_original_bytes(self) -> None:
        image = RawBileImage.read(self.source)
        self.assertTrue(image.exact_round_trip())
        self.assertEqual(image.to_bytes(), self.source_bytes)
        self.assertEqual(image.sha256, hashlib.sha256(self.source_bytes).hexdigest())
        self.assertEqual(
            [section.tag for section in image.sections],
            ["BELE", "BXDI", "BMRF", "BYAL", "BMTI", "BRTS"],
        )
        self.assertEqual(image.section("BELE").header_bytes, self.source_bytes[20:36])

    def test_mutation_buffer_tracks_only_bytes_that_actually_change(self) -> None:
        image = RawBileImage.read(self.source)
        buffer = BileMutationBuffer(image)
        field_offset = image.document.sections["BELE"].payload_offset + 16
        buffer.replace(field_offset, struct.pack("<f", 42.0), "BELE[0].x")
        candidate, actual = verify_candidate_bytes(
            image, buffer.to_bytes(), buffer.expected_changed_offsets
        )
        self.assertEqual(candidate.document.keyframes[0].x, 42.0)
        self.assertEqual(actual, buffer.expected_changed_offsets)
        self.assertTrue(actual)
        self.assertEqual(len(candidate.data), len(image.data))

    def test_patch_publishes_exact_changed_bytes_and_keeps_source_immutable(self) -> None:
        image = RawBileImage.read(self.source)
        payload = _patch(
            self.source_bytes,
            keyframes=[{
                "index": 0,
                "transform": {"x": 42.0},
                "expected": {"transform": {"x": 10.0}},
            }],
            elements=[{
                "index": 0,
                "anchor": [3.0, -4.0],
                "expected": {"anchor": [1.0, 2.0]},
            }],
        )
        self._write_patch(payload)
        output = self.root / "candidate.bin"
        report = apply_patch_report(self.source, self.patch_path, output)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(output.stat().st_size, len(self.source_bytes))
        self.assertEqual(report.size, len(self.source_bytes))
        self.assertEqual(report.input_sha256, hashlib.sha256(self.source_bytes).hexdigest())
        self.assertEqual(report.output_sha256, hashlib.sha256(output.read_bytes()).hexdigest())
        self.assertEqual(report.document.keyframes[0].x, 42.0)
        self.assertEqual(report.document.elements[0].x, 3.0)
        self.assertEqual(report.document.elements[0].y, -4.0)
        self.assertEqual(
            report.changed_byte_offsets,
            tuple(sorted(report.changed_byte_offsets)),
        )
        self.assertTrue(report.changed_byte_offsets)
        self.assertEqual(parse_file(output).keyframes[0].x, 42.0)

    def test_expected_old_mismatch_is_rejected_before_output(self) -> None:
        self._write_patch(_patch(
            self.source_bytes,
            keyframes=[{
                "index": 0,
                "transform": {"x": 42.0},
                "expected": {"transform": {"x": 9.0}},
            }],
        ))
        output = self.root / "candidate.bin"
        with self.assertRaises(BileFormatError):
            apply_patch_report(self.source, self.patch_path, output)
        self.assertFalse(output.exists())
        self.assertEqual(self.source.read_bytes(), self.source_bytes)

    def test_stale_source_hash_is_rejected(self) -> None:
        payload = _patch(
            self.source_bytes,
            keyframes=[{"index": 0, "transform": {"x": 42.0}}],
        )
        payload["source_sha256"] = "0" * 64
        self._write_patch(payload)
        output = self.root / "stale.bin"
        with self.assertRaises(BileFormatError):
            apply_patch_report(self.source, self.patch_path, output)
        self.assertFalse(output.exists())
        self.assertEqual(self.source.read_bytes(), self.source_bytes)

    def test_same_length_element_name_edit_is_confined_to_referenced_string(self) -> None:
        self._write_patch(_patch(
            self.source_bytes,
            elements=[{
                "index": 0,
                "name": "unit",
                "expected": {"name": "root"},
            }],
        ))
        output = self.root / "renamed.bin"
        report = apply_patch_report(self.source, self.patch_path, output)
        self.assertEqual(report.document.elements[0].name, "unit")
        original_brts = RawBileImage.read(self.source).section("BRTS")
        output_brts = RawBileImage.read(output).section("BRTS")
        self.assertEqual(original_brts.payload_bytes, b"root" + bytes([0]))
        self.assertEqual(output_brts.payload_bytes, b"unit" + bytes([0]))

    def test_v2_round_trip_and_export_are_read_only(self) -> None:
        source = self.root / "source-v2.bin"
        source.write_bytes(_minimal_v2_bile())
        image = RawBileImage.read(source)
        self.assertEqual(image.document.header.version, 2)
        self.assertTrue(image.exact_round_trip())
        exported = self.root / "source-v2.json"
        export_interchange(source, exported)
        self.assertIsNone(json.loads(exported.read_text(encoding="utf-8"))["patch_template"])

    def test_v2_low_level_mutation_is_rejected(self) -> None:
        image = RawBileImage.from_bytes(_minimal_v2_bile())
        candidate = bytearray(image.data)
        offset = image.section("BELE").offset + 16 + 16
        candidate[offset:offset + 4] = struct.pack("<f", 55.0)
        with self.assertRaises(BileFormatError):
            verify_candidate_bytes(image, bytes(candidate), (offset,))

    def test_v2_patch_is_rejected_without_output(self) -> None:
        source_bytes = _minimal_v2_bile()
        source = self.root / "source-v2.bin"
        source.write_bytes(source_bytes)
        self._write_patch(_patch(
            source_bytes,
            keyframes=[{"index": 0, "transform": {"x": 55.0}}],
        ))
        output = self.root / "source-v2-candidate.bin"
        with self.assertRaises(BileFormatError):
            apply_patch_report(source, self.patch_path, output)
        self.assertFalse(output.exists())
        self.assertEqual(source.read_bytes(), source_bytes)

    def test_shared_string_name_edit_is_rejected(self) -> None:
        source_bytes = _minimal_v3_bile(shared_name=True)
        source = self.root / "shared-name.bin"
        source.write_bytes(source_bytes)
        self._write_patch(_patch(
            source_bytes,
            elements=[{
                "index": 0,
                "name": "unit",
                "expected": {"name": "root"},
            }],
        ))
        with self.assertRaises(BileFormatError):
            apply_patch_report(
                source, self.patch_path, self.root / "shared-name-candidate.bin"
            )

    def test_low_level_write_cannot_change_string_pool_boundaries(self) -> None:
        image = RawBileImage.from_bytes(self.source_bytes)
        candidate = bytearray(image.data)
        section = image.section("BRTS")
        offset = section.offset + section.header_size
        candidate[offset] = 0
        with self.assertRaises(BileFormatError):
            verify_candidate_bytes(image, bytes(candidate), (offset,))

    def test_shared_string_bytes_are_not_in_low_level_write_allowlist(self) -> None:
        image = RawBileImage.from_bytes(_minimal_v3_bile(shared_name=True))
        candidate = bytearray(image.data)
        section = image.section("BRTS")
        offset = section.offset + section.header_size
        candidate[offset] = ord("U")
        with self.assertRaises(BileFormatError):
            verify_candidate_bytes(image, bytes(candidate), (offset,))

    def test_float32_overflow_is_rejected(self) -> None:
        self._write_patch(_patch(
            self.source_bytes,
            keyframes=[{"index": 0, "transform": {"x": 10 ** 400}}],
        ))
        with self.assertRaises(BileFormatError):
            apply_patch_report(self.source, self.patch_path, self.root / "overflow.bin")

    def test_edit_session_rejects_invalid_argb(self) -> None:
        session = EditSession(self.source)
        try:
            with self.assertRaises(ValueError):
                session.set_keyframe(0, {"x": 42.0}, -1, 0)
            with self.assertRaises(ValueError):
                session.set_keyframe(0, {"x": 42.0}, 0x100000000, 0)
        finally:
            session.close()

    def test_edit_session_rejects_boolean_or_nonfinite_anchor(self) -> None:
        session = EditSession(self.source)
        try:
            with self.assertRaises(ValueError):
                session.set_anchor(0, True, 2.0)
            with self.assertRaises(ValueError):
                session.set_anchor(0, float("inf"), 2.0)
        finally:
            session.close()

    def test_legacy_patch_without_expected_values_remains_compatible(self) -> None:
        self._write_patch(_patch(
            self.source_bytes,
            keyframes=[{"index": 0, "transform": {"x": 42.0}}],
        ))
        output = self.root / "legacy-candidate.bin"
        report = apply_patch_report(self.source, self.patch_path, output)
        self.assertEqual(report.document.keyframes[0].x, 42.0)

    def test_non_finite_float_is_rejected(self) -> None:
        self._write_patch(_patch(
            self.source_bytes,
            keyframes=[{"index": 0, "transform": {"x": float("nan")}}],
        ))
        with self.assertRaises(BileFormatError):
            apply_patch_report(self.source, self.patch_path, self.root / "candidate.bin")

    def test_playback_mode_remains_no_go(self) -> None:
        self._write_patch(_patch(
            self.source_bytes,
            keyframes=[{"index": 0, "playback_mode": 1}],
        ))
        with self.assertRaises(BileFormatError):
            apply_patch_report(self.source, self.patch_path, self.root / "candidate.bin")

    def test_duplicate_record_edits_are_rejected(self) -> None:
        self._write_patch(_patch(
            self.source_bytes,
            keyframes=[
                {"index": 0, "transform": {"x": 30.0}},
                {"index": 0, "transform": {"y": 40.0}},
            ],
        ))
        with self.assertRaises(BileFormatError):
            apply_patch_report(self.source, self.patch_path, self.root / "candidate.bin")

    def test_input_and_output_must_be_distinct(self) -> None:
        self._write_patch(_patch(self.source_bytes))
        with self.assertRaises(BileFormatError):
            apply_patch_report(self.source, self.patch_path, self.source)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)

    def test_existing_output_is_never_overwritten_implicitly(self) -> None:
        self._write_patch(_patch(
            self.source_bytes,
            keyframes=[{"index": 0, "transform": {"x": 42.0}}],
        ))
        output = self.root / "existing.bin"
        previous = b"keep this output"
        output.write_bytes(previous)
        with self.assertRaises(BileFormatError):
            apply_patch_report(self.source, self.patch_path, output)
        self.assertEqual(output.read_bytes(), previous)

    def test_explicit_overwrite_replaces_output_and_cleans_backup(self) -> None:
        self._write_patch(_patch(
            self.source_bytes,
            keyframes=[{"index": 0, "transform": {"x": 42.0}}],
        ))
        output = self.root / "existing.bin"
        output.write_bytes(b"previous candidate")
        report = apply_patch_report(
            self.source, self.patch_path, output, overwrite=True
        )
        self.assertEqual(parse_file(output).keyframes[0].x, 42.0)
        self.assertEqual(report.output_sha256, hashlib.sha256(output.read_bytes()).hexdigest())
        self.assertEqual(list(self.root.glob("*.backup.tmp")), [])

    def test_failed_overwrite_verification_restores_previous_candidate(self) -> None:
        self._write_patch(_patch(
            self.source_bytes,
            keyframes=[{"index": 0, "transform": {"x": 42.0}}],
        ))
        output = self.root / "rollback.bin"
        previous = b"previous candidate must survive"
        output.write_bytes(previous)
        original_from_bytes = RawBileImage.from_bytes.__func__
        calls = {"count": 0}

        def fail_after_publish(cls, data, source_path="<memory>"):
            calls["count"] += 1
            if calls["count"] == 5:
                raise BileFormatError("forced post-publication verification failure")
            return original_from_bytes(cls, data, source_path)

        with patch.object(RawBileImage, "from_bytes", classmethod(fail_after_publish)):
            with self.assertRaises(BileFormatError):
                apply_patch_report(
                    self.source, self.patch_path, output, overwrite=True
                )
        self.assertEqual(output.read_bytes(), previous)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(list(self.root.glob("*.backup.tmp")), [])

    def test_unplanned_opaque_byte_change_is_rejected(self) -> None:
        image = RawBileImage.read(self.source)
        candidate = bytearray(image.data)
        opaque_ref_offset = image.section("BELE").offset + 16 + 36
        candidate[opaque_ref_offset] ^= 0x01
        with self.assertRaises(BileFormatError):
            verify_candidate_bytes(image, bytes(candidate), ())

    def test_opaque_field_is_rejected_even_when_caller_lists_it_as_expected(self) -> None:
        image = RawBileImage.read(self.source)
        candidate = bytearray(image.data)
        opaque_ref_offset = image.section("BELE").offset + 16 + 36
        candidate[opaque_ref_offset] ^= 0x01
        with self.assertRaises(BileFormatError):
            verify_candidate_bytes(image, bytes(candidate), (opaque_ref_offset,))

    def test_edit_session_generates_expected_old_and_reuses_preview_atomically(self) -> None:
        session = EditSession(self.source)
        try:
            session.set_keyframe(0, {"x": 42.0}, 0xFFFFFFFF, 0)
            session.set_anchor(0, 3.0, -4.0)
            payload = session.patch_payload()
            self.assertEqual(payload["keyframes"][0]["expected"]["transform"], {"x": 10.0})
            self.assertEqual(payload["keyframes"][0]["expected"]["argb"], "0xFFFFFFFF")
            self.assertEqual(payload["keyframes"][0]["expected"]["initial_phase"], 0)
            self.assertEqual(payload["elements"][0]["expected"]["anchor"], [1.0, 2.0])
            first = session.preview_document()
            second = session.preview_document()
            self.assertEqual(first.keyframes[0].x, 42.0)
            self.assertEqual(second.elements[0].x, 3.0)
        finally:
            session.close()

    def test_exported_patch_template_contains_expected_old_values(self) -> None:
        output = self.root / "source.json"
        export_interchange(self.source, output)
        payload = json.loads(output.read_text(encoding="utf-8"))
        template = payload["patch_template"]
        self.assertEqual(template["schema"], SCHEMA)
        self.assertEqual(template["keyframes"][0]["expected"]["transform"]["x"], 10.0)
        self.assertEqual(template["elements"][0]["expected"]["anchor"], [1.0, 2.0])


if __name__ == "__main__":
    unittest.main()
