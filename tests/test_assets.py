"""资产服务测试使用临时字节文件，不代表游戏资源格式。"""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.assets import AssetTripletError, archive_tree, create_triplet, discover_triplet, sha256_file, stage_triplet


class AssetTripletTests(unittest.TestCase):
    def _write_triplet(self, directory: Path, stem: str, image_extension: str = ".webp") -> tuple[Path, Path, Path]:
        binary = directory / f"{stem}.bin"
        xml = directory / f"{stem}.xml"
        image = directory / f"{stem}{image_extension}"
        binary.write_bytes(b"BILE-demo")
        xml.write_bytes(b"<Texture name='atlas.webp'/>")
        image.write_bytes(b"image-bytes")
        return binary, xml, image

    def test_discovers_webp_then_png_and_hashes_streamed_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            binary, _xml, image = self._write_triplet(root, "demo")
            triplet = discover_triplet(binary)
            self.assertEqual(triplet.image_path, image)
            self.assertEqual(triplet.bin_sha256, hashlib.sha256(b"BILE-demo").hexdigest())
            self.assertEqual(sha256_file(image), hashlib.sha256(b"image-bytes").hexdigest())
            image.unlink()
            png = root / "demo.png"
            png.write_bytes(b"png")
            self.assertEqual(discover_triplet(binary).image_path, png)

    def test_stages_named_copy_and_optional_xml_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            binary, xml, image = self._write_triplet(root, "source")
            staged = stage_triplet(
                create_triplet(binary, xml, image), root / "stage",
                bin_name="target.bin", xml_name="target.xml", image_name="target.webp", xml_bytes=b"<Texture name='target.webp'/>",
            )
            self.assertEqual(staged.bin_path.read_bytes(), b"BILE-demo")
            self.assertEqual(staged.xml_path.read_bytes(), b"<Texture name='target.webp'/>")
            self.assertEqual(staged.image_path.read_bytes(), b"image-bytes")
            with self.assertRaises(AssetTripletError):
                stage_triplet(create_triplet(binary, xml, image), root / "unsafe", bin_name="../bad.bin")

    def test_archives_only_the_explicit_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "package"
            package.mkdir()
            (package / "manifest.json").write_text("{}", encoding="utf-8")
            (root / "outside.txt").write_text("outside", encoding="utf-8")
            archive = archive_tree(package, root / "result.zip")
            with zipfile.ZipFile(archive) as zipped:
                self.assertEqual(zipped.namelist(), ["package/manifest.json"])


if __name__ == "__main__":
    unittest.main()
