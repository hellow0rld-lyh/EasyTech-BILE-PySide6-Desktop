"""导出保守补丁前的结构与语义预检。"""
from __future__ import annotations

from dataclasses import dataclass

from .bile_format import BileDocument
from .diagnostics import Atlas, collect_diagnostics
from .edit_session import EditSession


@dataclass(frozen=True)
class PreflightItem:
    severity: str  # INFO / WARNING / ERROR
    code: str
    message: str


@dataclass(frozen=True)
class PreflightReport:
    document: BileDocument
    items: tuple[PreflightItem, ...]

    @property
    def has_errors(self) -> bool:
        return any(item.severity == "ERROR" for item in self.items)

    @property
    def text(self) -> str:
        return "\n\n".join(f"[{item.severity}] {item.code}\n{item.message}" for item in self.items)


def _nested_targets_for_keyframe(document: BileDocument, keyframe_index: int) -> list[tuple[str, str, int]]:
    targets: list[tuple[str, str, int]] = []
    for parent in document.animations:
        for channel in parent.channels:
            for frame in channel.frames:
                for track in frame.tracks:
                    if track.keyframe_index != keyframe_index or track.element_index < 0:
                        continue
                    child = document.elements[track.element_index]
                    if not child.has_texture:
                        targets.append((parent.name, child.name, child.frame_count))
    return targets


def run_preflight(session: EditSession, atlas: Atlas) -> PreflightReport:
    """以临时 BIN 重解析为第一原则，辅以范围和实际引用位置的编辑提示。"""
    document = session.preview_document()
    items: list[PreflightItem] = [
        PreflightItem("INFO", "STRUCTURE_REPARSE_OK", "待提交补丁已应用到临时 BIN 并通过完整 BILE v4 重解析。"),
        PreflightItem("INFO", "SOURCE_SHA256_BOUND", "补丁绑定原始 BIN 的 SHA-256；错源文件会被拒绝。"),
    ]
    for diagnostic in collect_diagnostics(document, atlas):
        if diagnostic.severity == "ERROR":
            items.append(PreflightItem("ERROR", diagnostic.code, diagnostic.message))

    payload = session.patch_payload()
    for change in payload["keyframes"]:
        if "initial_phase" not in change:
            continue
        index = change["index"]
        phase = change["initial_phase"]
        targets = _nested_targets_for_keyframe(document, index)
        if not targets:
            items.append(PreflightItem(
                "WARNING",
                "INITIAL_PHASE_WITHOUT_NESTED_TARGET",
                f"BELE[{index}] 的 initial_phase={phase} 当前没有引用到子动画的轨道；该变更不会影响已知的嵌套时钟。",
            ))
            continue
        invalid = [f"{parent} → {child}（{frames} 帧）" for parent, child, frames in targets if phase >= frames]
        if invalid:
            items.append(PreflightItem(
                "ERROR",
                "INITIAL_PHASE_OUTSIDE_CHILD_RANGE",
                f"BELE[{index}] 的 initial_phase={phase} 超出至少一个被引用子动画的帧范围：{'；'.join(invalid[:6])}。",
            ))
        else:
            examples = "；".join(f"{parent} → {child}" for parent, child, _ in targets[:3])
            items.append(PreflightItem(
                "INFO",
                "INITIAL_PHASE_NESTED_TARGET_VALID",
                f"BELE[{index}] 的 initial_phase={phase} 落在 {len(targets)} 条实际子动画引用的帧范围内，例如：{examples}。",
            ))

    if not any(item.severity == "ERROR" for item in items):
        items.append(PreflightItem("INFO", "PRECHECK_PASS", "未发现阻止导出补丁的结构性错误；仍应在原游戏中回归实验 BIN。"))
    return PreflightReport(document, tuple(items))
