"""面向 BILE 保守编辑的变更账本与预检视图。"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from .preflight import PreflightReport, run_preflight

if TYPE_CHECKING:
    from .bile_format import BileDocument
    from .diagnostics import Atlas
    from .edit_session import EditSession


class ChangeLedger(QWidget):
    """只读显示现有 EditSession 的补丁与预检；不会写出 BIN、JSON 或实验包。"""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(7)
        self.summary = QLabel("尚未加载 BILE 三件套。")
        self.summary.setWordWrap(True)
        self.summary.setProperty("muted", True)
        layout.addWidget(self.summary)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["类别", "对象", "状态 / 详情"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        layout.addWidget(self.tree, 1)
        self._preflight_key: str | None = None
        self._preflight_report: PreflightReport | None = None

    @staticmethod
    def _item(parent: QTreeWidgetItem, category: str, subject: str, detail: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([category, subject, detail])
        parent.addChild(item)
        return item

    def clear(self) -> None:
        self._preflight_key = None
        self._preflight_report = None
        self.summary.setText("尚未加载 BILE 三件套。")
        self.tree.clear()

    def refresh(self, document: "BileDocument", session: "EditSession", atlas: "Atlas", *, proposal_source: str | None = None) -> None:
        self.tree.clear()
        editable = document.header.version >= 3
        dirty = session.dirty
        mode = "保守编辑" if editable else "严格只读"
        self.summary.setText(
            f"BILE v{document.header.version} · {mode} · "
            f"暂存变更 {session.change_count} 项。账本只呈现当前内存补丁；源 BIN 不会被此面板写入。"
        )
        document_root = QTreeWidgetItem(["文档", "会话边界", ""])
        self.tree.addTopLevelItem(document_root)
        self._item(document_root, "版本", f"BILE v{document.header.version}", mode)
        self._item(document_root, "源绑定", "SHA-256", session.source_sha256)
        self._item(document_root, "写回白名单", "BELE / BMTI", "仿射、ARGB、initial_phase 与锚点；playback_mode 始终只读")
        if proposal_source is None:
            self._item(document_root, "候选来源", "AI 场景提案", "当前会话未加载可追溯的 AI 场景候选。")
        else:
            self._item(document_root, "候选来源", "AI 场景提案", f"已接受哈希绑定候选；源 SHA-256 {proposal_source}。后续人工受限编辑会如实混入当前暂存 patch。")

        changes_root = QTreeWidgetItem(["暂存变更", f"{session.change_count} 项", ""])
        self.tree.addTopLevelItem(changes_root)
        payload = session.patch_payload()
        for change in payload["keyframes"]:
            fields = ", ".join(field for field in ("transform", "argb", "initial_phase") if field in change)
            self._item(changes_root, "BELE", f"BELE[{change['index']}]", fields or "无字段")
        for change in payload["elements"]:
            fields = ", ".join(field for field in ("anchor",) if field in change)
            self._item(changes_root, "BMTI", f"BMTI[{change['index']}]", fields or "无字段")
        if not dirty:
            self._item(changes_root, "状态", "无暂存补丁", "可先在检查器执行一项已验证的保守编辑。")

        preflight_root = QTreeWidgetItem(["实时预检", "未运行", ""])
        self.tree.addTopLevelItem(preflight_root)
        if not editable:
            self._item(preflight_root, "边界", "BILE v2", "五节容器可读可预览；写回尚无实证，故不运行候选预检。")
        elif not dirty:
            self._item(preflight_root, "等待", "无暂存变更", "预检将在至少一项暂存编辑后使用候选 BIN 的完整重解析结果。")
        else:
            key = json.dumps(payload, sort_keys=True, ensure_ascii=False)
            if key != self._preflight_key:
                self._preflight_report = run_preflight(session, atlas)
                self._preflight_key = key
            report = self._preflight_report
            assert report is not None
            preflight_root.setText(1, "通过" if not report.has_errors else "阻止导出")
            preflight_root.setText(2, "候选 BIN 已完整重解析；仍须游戏内回归。")
            for item in report.items:
                self._item(preflight_root, item.severity, item.code, item.message)
        self.tree.expandAll()
        for column in range(3):
            self.tree.resizeColumnToContents(column)
