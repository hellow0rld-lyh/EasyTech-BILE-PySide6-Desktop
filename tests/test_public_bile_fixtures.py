"""Public synthetic BILE fixtures keep parser checks independent of game assets."""
from __future__ import annotations

import struct
import unittest

from bile_workbench.bile_format import BileFormatError, parse_bytes
from test_project_model import _minimal_v2_bile, _minimal_v3_bile


class PublicBileFixtureTests(unittest.TestCase):
    def test_v2_five_section_fixture_parses_without_private_assets(self) -> None:
        document = parse_bytes(_minimal_v2_bile())
        self.assertEqual(document.header.version, 2)
        self.assertEqual(
            tuple(document.sections),
            ("BELE", "BMRF", "BYAL", "BMTI", "BRTS"),
        )
        self.assertEqual(len(document.keyframes), 1)
        self.assertEqual(len(document.animations), 1)

    def test_v3_six_section_fixture_parses_without_private_assets(self) -> None:
        document = parse_bytes(_minimal_v3_bile())
        self.assertEqual(document.header.version, 3)
        self.assertEqual(
            tuple(document.sections),
            ("BELE", "BXDI", "BMRF", "BYAL", "BMTI", "BRTS"),
        )
        self.assertEqual(len(document.elements), 1)
        self.assertEqual(len(document.keyframes), 1)
        self.assertEqual(len(document.animations), 1)
        self.assertEqual(document.graph_cycles, ())

    def test_rejects_payload_length_mismatch_in_public_fixture(self) -> None:
        data = bytearray(_minimal_v3_bile())
        struct.pack_into("<I", data, 8, len(data))
        with self.assertRaises(BileFormatError):
            parse_bytes(bytes(data))

    def test_rejects_unknown_top_level_section_tag_in_public_fixture(self) -> None:
        data = bytearray(_minimal_v3_bile())
        data[20:24] = b"FAIL"
        with self.assertRaises(BileFormatError):
            parse_bytes(bytes(data))


if __name__ == "__main__":
    unittest.main()
