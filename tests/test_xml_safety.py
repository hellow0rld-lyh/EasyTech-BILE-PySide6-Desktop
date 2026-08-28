"""defusedxml 适配层安全与兼容性测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.formation_config import FormationConfigError, parse_def_array_bytes
from bile_workbench.xml_safety import SafeXmlError, parse_untrusted_xml


class XmlSafetyTests(unittest.TestCase):
    def test_parses_ordinary_utf8_xml_with_standard_element_api(self) -> None:
        root = parse_untrusted_xml("<Images><Image name='unit.png' x='1'/></Images>", "atlas.xml")
        image = root.find("Image")
        self.assertIsNotNone(image)
        self.assertEqual(image.get("name"), "unit.png")

    def test_rejects_dtd_and_entity_declarations(self) -> None:
        xml = "<!DOCTYPE root [<!ENTITY payload 'unsafe'>]><root>&payload;</root>"
        with self.assertRaises(SafeXmlError) as context:
            parse_untrusted_xml(xml, "malicious.xml")
        self.assertIn("无法安全解析", str(context.exception))

    def test_formation_parser_preserves_its_domain_error_contract(self) -> None:
        xml = b"<!DOCTYPE Arrays [<!ENTITY point '0,0'>]><Arrays><Array name='A'><Pos soldier='&point;'/></Array></Arrays>"
        with self.assertRaises(FormationConfigError) as context:
            parse_def_array_bytes(xml)
        self.assertIn("阵列配置 XML 无法解析", str(context.exception))


if __name__ == "__main__":
    unittest.main()
