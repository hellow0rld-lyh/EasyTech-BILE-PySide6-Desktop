"""文档中心化的 BILE 编辑会话。

会话将工作区、暂存补丁、当前显示文档和选择状态整合为单一事实来源；不依赖 Qt，
因此预览、时间线、检查器和自动化回归可以订阅同一快照。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from .bile_format import BileDocument, Element
from .candidate_workflow import CandidateWorkflow
from .edit_session import EditSession
from .workbench_state import Workspace
from .track_context import TrackContext, active_tracks_at_slot


class DocumentSessionError(ValueError):
    """文档会话状态或编辑命令违反 BILE 工作台的保守合同。"""


@dataclass(frozen=True)
class DocumentSelection:
    element_index: int | None = None
    slot: int = 0
    channel_index: int | None = None
    frame_slot: int | None = None
    track_index: int | None = None
    keyframe_index: int | None = None


@dataclass(frozen=True)
class SessionSnapshot:
    workspace: Workspace
    document: BileDocument
    selection: DocumentSelection
    dirty: bool
    change_count: int

    @property
    def selected_element(self) -> Element | None:
        index = self.selection.element_index
        return self.document.elements[index] if index is not None else None

    @property
    def bile_version(self) -> int:
        return self.document.header.version

    @property
    def editable(self) -> bool:
        return self.bile_version >= 3


class DocumentEditCommand(Protocol):
    """只允许投影到既有 EditSession 白名单的编辑意图。"""

    label: str

    def apply(self, edit_session: EditSession) -> None:
        """向暂存补丁加入一个受限编辑。"""


@dataclass(frozen=True)
class SetKeyframeCommand:
    index: int
    transform: dict[str, float]
    argb: int
    initial_phase: int
    label: str = "更新 BELE 关键帧"

    def apply(self, edit_session: EditSession) -> None:
        edit_session.set_keyframe(self.index, dict(self.transform), self.argb, self.initial_phase)


@dataclass(frozen=True)
class SetAnchorCommand:
    index: int
    x: float
    y: float
    label: str = "更新 BMTI 精灵锚点"

    def apply(self, edit_session: EditSession) -> None:
        edit_session.set_anchor(self.index, self.x, self.y)


SessionListener = Callable[[SessionSnapshot], None]


class AnimationDocumentSession:
    """围绕单个 BILE 三件套的文档状态、命令和观察通知。"""

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace
        self._edit_session = EditSession(workspace.bin_path)
        self._document = workspace.document
        self._selection = DocumentSelection()
        self._listeners: list[SessionListener] = []

    @property
    def workspace(self) -> Workspace:
        return self._workspace

    @property
    def edit_session(self) -> EditSession:
        """仅供既有候选工作流适配；UI 编辑入口应使用 execute。"""
        return self._edit_session

    @property
    def snapshot(self) -> SessionSnapshot:
        return SessionSnapshot(
            workspace=self._workspace,
            document=self._document,
            selection=self._selection,
            dirty=self._edit_session.dirty,
            change_count=self._edit_session.change_count,
        )

    def subscribe(self, listener: SessionListener, *, emit_current: bool = True) -> Callable[[], None]:
        self._listeners.append(listener)
        if emit_current:
            listener(self.snapshot)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def _emit(self) -> None:
        snapshot = self.snapshot
        for listener in tuple(self._listeners):
            listener(snapshot)

    def _refresh_document(self) -> None:
        self._document = self._edit_session.preview_document() if self._edit_session.dirty else self._workspace.document
        self._selection = self._normalize_selection(self._selection)

    def _normalize_selection(self, selection: DocumentSelection) -> DocumentSelection:
        if selection.element_index is None:
            return DocumentSelection(None, 0)
        if not 0 <= selection.element_index < len(self._document.elements):
            raise DocumentSessionError(f"元素索引超出当前文档范围：{selection.element_index}")
        element = self._document.elements[selection.element_index]
        slot = max(0, min(selection.slot, max(0, element.frame_count - 1)))
        if element.has_texture or selection.keyframe_index is None:
            return DocumentSelection(element.index, slot)
        contexts = active_tracks_at_slot(self._document, element.index, slot)
        matching = [
            context
            for context in contexts
            if context.channel_index == selection.channel_index
            and context.frame_slot == selection.frame_slot
            and context.track_index == selection.track_index
            and context.keyframe_index == selection.keyframe_index
        ]
        if not matching:
            raise DocumentSessionError("轨道选择不属于当前动画槽位或已失效")
        return DocumentSelection(
            element.index,
            slot,
            selection.channel_index,
            selection.frame_slot,
            selection.track_index,
            selection.keyframe_index,
        )

    def select_element(self, element_index: int | None) -> None:
        self._selection = self._normalize_selection(DocumentSelection(element_index, self._selection.slot))
        self._emit()

    def set_slot(self, slot: int) -> None:
        if not isinstance(slot, int):
            raise DocumentSessionError("动画槽位必须是整数")
        self._selection = self._normalize_selection(DocumentSelection(self._selection.element_index, slot))
        self._emit()

    def select_track(self, context: TrackContext) -> None:
        if context.animation_index != self._selection.element_index:
            raise DocumentSessionError("轨道必须属于当前选中的动画根")
        self._selection = self._normalize_selection(
            DocumentSelection(
                context.animation_index,
                context.frame_slot,
                context.channel_index,
                context.frame_slot,
                context.track_index,
                context.keyframe_index,
            )
        )
        self._emit()

    def execute(self, command: DocumentEditCommand) -> None:
        if self._document.header.version < 3:
            raise DocumentSessionError("BILE v2 当前严格只读，不能执行编辑命令")
        command.apply(self._edit_session)
        self._refresh_document()
        self._emit()

    def undo(self) -> bool:
        if not self._edit_session.undo():
            return False
        self._refresh_document()
        self._emit()
        return True

    def redo(self) -> bool:
        if not self._edit_session.redo():
            return False
        self._refresh_document()
        self._emit()
        return True

    def clear_edits(self) -> bool:
        if not self._edit_session.dirty:
            return False
        self._edit_session.clear()
        self._refresh_document()
        self._emit()
        return True

    def refresh(self) -> None:
        """在受控外部恢复暂存会话后刷新显示文档并通知所有视图。"""
        self._refresh_document()
        self._emit()

    def candidate_workflow(self) -> CandidateWorkflow:
        return CandidateWorkflow(
            self._workspace.bin_path,
            self._workspace.xml_path,
            self._workspace.image_path,
            self._workspace.atlas,
            self._edit_session,
        )

    def close(self) -> None:
        self._listeners.clear()
        self._edit_session.close()
