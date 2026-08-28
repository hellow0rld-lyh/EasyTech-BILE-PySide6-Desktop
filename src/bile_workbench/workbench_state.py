"""工作台当前资源状态；不包含 Qt 控件或文件选择逻辑。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .assets import AssetTriplet, create_triplet
from .bile_format import BileDocument
from .preview_renderer import Atlas


@dataclass(frozen=True)
class Workspace:
    """一个已严格解析、可预览的 BILE 三件套快照。"""

    triplet: AssetTriplet
    document: BileDocument
    atlas: Atlas

    @property
    def bin_path(self) -> Path:
        return self.triplet.bin_path

    @property
    def xml_path(self) -> Path:
        return self.triplet.xml_path

    @property
    def image_path(self) -> Path:
        return self.triplet.image_path

    @classmethod
    def create(cls, bin_path: str | Path, xml_path: str | Path, image_path: str | Path, document: BileDocument, atlas: Atlas) -> "Workspace":
        return cls(create_triplet(bin_path, xml_path, image_path), document, atlas)
