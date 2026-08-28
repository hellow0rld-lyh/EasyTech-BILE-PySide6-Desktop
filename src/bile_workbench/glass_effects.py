"""Windows Mica/Acrylic 与跨平台 QSS 玻璃回退层。

不依赖第三方无边框库：宿主仍保留原生 QMainWindow、Dock 和系统窗口行为，
仅在 Windows 上通过 DWM/Composition API 尝试设置背景材质。
"""
from __future__ import annotations

import ctypes
import re
import sys
from dataclasses import dataclass
from typing import Any



_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?$")
_MATERIALS = {"auto", "mica", "acrylic", "fallback", "none"}


class GlassSpecError(ValueError):
    """玻璃材质定义不符合插件协议。"""


@dataclass(frozen=True)
class GlassSpec:
    material: str = "auto"
    tint: str = "#202731"
    opacity: float = 0.82
    blur: int = 24
    border: str = "#506070"
    glow: str = "#8CC8FF"


@dataclass(frozen=True)
class GlassApplyResult:
    mode: str
    label: str
    native: bool
    reason: str = ""


def parse_glass_spec(value: Any) -> GlassSpec:
    """解析 manifest 的 glass 对象；缺省对象使用 auto，保证旧插件可渐进升级。"""
    if value is None:
        return GlassSpec()
    if not isinstance(value, dict):
        raise GlassSpecError("插件清单的 glass 必须是对象")
    material = value.get("material", "auto")
    if material not in _MATERIALS:
        raise GlassSpecError(f"不支持的玻璃材质：{material!r}")
    tint = _color(value.get("tint", "#202731"), "tint")
    border = _color(value.get("border", "#506070"), "border")
    glow = _color(value.get("glow", "#8CC8FF"), "glow")
    opacity = value.get("opacity", 0.82)
    blur = value.get("blur", 24)
    if not isinstance(opacity, (int, float)) or not 0.0 <= float(opacity) <= 1.0:
        raise GlassSpecError("glass.opacity 必须在 0.0 到 1.0 之间")
    if not isinstance(blur, int) or not 0 <= blur <= 96:
        raise GlassSpecError("glass.blur 必须是 0 到 96 的整数")
    return GlassSpec(material, tint, float(opacity), blur, border, glow)


def _color(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _HEX_COLOR_RE.fullmatch(value):
        raise GlassSpecError(f"glass.{name} 必须是 #RRGGBB 或 #RRGGBBAA")
    return value.upper()


class GlassBackdropController:
    """为一个 QMainWindow 应用可选的原生 Windows 背景材质。"""

    def __init__(self, window) -> None:  # type: ignore[no-untyped-def]
        self.window = window
        self.last_result = GlassApplyResult("fallback", "QSS 玻璃回退", False)

    def apply(self, spec: GlassSpec) -> GlassApplyResult:
        if spec.material == "none":
            self._set_window_translucency(False)
            self.last_result = GlassApplyResult("none", "未启用玻璃材质", False)
            return self.last_result
        if sys.platform != "win32":
            self.last_result = GlassApplyResult(
                "fallback", "QSS 玻璃回退", False, "当前平台不是 Windows"
            )
            return self.last_result
        try:
            # 保留系统标题栏、阴影和原生 QMainWindow，只关闭 Qt 自己的不透明填充。
            self._set_window_translucency(True)
            hwnd = int(self.window.winId())
            if spec.material in {"auto", "mica"} and _try_mica(hwnd):
                self.last_result = GlassApplyResult("mica", "Windows Mica", True)
                return self.last_result
            if spec.material in {"auto", "acrylic"} and _try_acrylic(hwnd, spec):
                self.last_result = GlassApplyResult("acrylic", "Windows Acrylic", True)
                return self.last_result
            if spec.material == "fallback":
                reason = "插件指定使用 QSS 玻璃"
            else:
                reason = "当前 Windows 版本或窗口策略不支持原生材质"
        except (AttributeError, OSError, TypeError, ValueError) as exc:
            reason = f"原生玻璃调用失败：{exc}"
        self._set_window_translucency(False)
        self.last_result = GlassApplyResult("fallback", "QSS 玻璃回退", False, reason)
        return self.last_result

    def _set_window_translucency(self, enabled: bool) -> None:
        if sys.platform != "win32":
            return
        # 不强行设置 WA_TranslucentBackground：标准 QMainWindow 在 Win10 上保留
        # 原生标题栏/阴影更稳定，透明表面由 QSS 与 DWM Composition 共同提供。
        if hasattr(self.window, "setAutoFillBackground"):
            self.window.setAutoFillBackground(not enabled)


def _try_mica(hwnd: int) -> bool:
    """Windows 11 DWM system backdrop type: 2 = Mica。"""
    if sys.platform != "win32":
        return False
    try:
        dwmapi = ctypes.windll.dwmapi
        value = ctypes.c_int(2)
        result = dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), 38, ctypes.byref(value), ctypes.sizeof(value)
        )
        return result == 0
    except (AttributeError, OSError):
        return False


def _try_acrylic(hwnd: int, spec: GlassSpec) -> bool:
    """先尝试 Win11 Acrylic，再尝试 Win10 SetWindowCompositionAttribute。"""
    if sys.platform != "win32":
        return False
    if _try_system_acrylic(hwnd):
        return True
    return _try_legacy_acrylic(hwnd, spec)


def _try_system_acrylic(hwnd: int) -> bool:
    if sys.platform != "win32":
        return False
    try:
        dwmapi = ctypes.windll.dwmapi
        value = ctypes.c_int(3)  # DWMSBT_TRANSIENTWINDOW / Desktop Acrylic
        result = dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), 38, ctypes.byref(value), ctypes.sizeof(value)
        )
        return result == 0
    except (AttributeError, OSError):
        return False


def _try_legacy_acrylic(hwnd: int, spec: GlassSpec) -> bool:
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32

        class AccentPolicy(ctypes.Structure):
            _fields_ = [
                ("AccentState", ctypes.c_int),
                ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint),
                ("AnimationId", ctypes.c_int),
            ]

        class WindowCompositionAttributeData(ctypes.Structure):
            _fields_ = [
                ("Attribute", ctypes.c_int),
                ("Data", ctypes.c_void_p),
                ("SizeOfData", ctypes.c_size_t),
            ]

        color = _argb_color(spec.tint, spec.opacity)
        policy = AccentPolicy(4, 2, color, 0)  # ACCENT_ENABLE_ACRYLICBLURBEHIND
        data = WindowCompositionAttributeData(
            19, ctypes.cast(ctypes.byref(policy), ctypes.c_void_p), ctypes.sizeof(policy)
        )
        result = user32.SetWindowCompositionAttribute(
            ctypes.c_void_p(hwnd), ctypes.byref(data)
        )
        return bool(result)
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def glass_overlay_qss(spec: GlassSpec, *, native: bool = False) -> str:
    """把 manifest 材质参数映射为跨平台的 QSS 玻璃表面。"""
    red, green, blue = _rgb(spec.tint)
    alpha = round(spec.opacity * 255)
    border = spec.border
    glow = spec.glow
    surface_alpha = max(128, min(238, alpha))
    panel_alpha = max(112, min(224, alpha - 12))
    soft_alpha = max(96, min(208, alpha - 28))
    window_background = "transparent" if native else f"rgba({red}, {green}, {blue}, {surface_alpha})"
    return f"""
QMainWindow#MainWindow {{ background: {window_background}; }}
QWidget#MainSurface {{
    background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 rgba({red}, {green}, {blue}, {surface_alpha}),
        stop: 1 rgba({red}, {green}, {blue}, {panel_alpha}));
    border: 1px solid {border};
    border-radius: 12px;
}}
QToolBar#TaskRibbonToolBar, QWidget#TaskRibbon, QFrame#RibbonQuickAccess {{
    background: rgba({red}, {green}, {blue}, {panel_alpha});
    border-bottom-color: {border};
}}
QWidget#TaskRibbon QTabWidget::pane {{ background: rgba({red}, {green}, {blue}, {soft_alpha}); }}
QFrame[ribbonGroup=\"true\"] {{ background: rgba({red}, {green}, {blue}, {surface_alpha}); border-color: {border}; }}
QDockWidget {{ background: rgba({red}, {green}, {blue}, {soft_alpha}); }}
QDockWidget::title {{ background: rgba({red}, {green}, {blue}, {panel_alpha}); border-bottom-color: {border}; }}
QFrame#PluginBadge {{ border: 1px solid {glow}; background: rgba({red}, {green}, {blue}, {surface_alpha}); }}
QFrame[card=\"true\"] {{ background: rgba({red}, {green}, {blue}, {surface_alpha}); border-color: {border}; }}
"""


def _rgb(color: str) -> tuple[int, int, int]:
    raw = color.lstrip("#")[:6]
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _argb_color(color: str, opacity: float) -> int:
    raw = color.lstrip("#")[:6]
    red = int(raw[0:2], 16)
    green = int(raw[2:4], 16)
    blue = int(raw[4:6], 16)
    alpha = round(max(0.0, min(1.0, opacity)) * 255)
    return (alpha << 24) | (blue << 16) | (green << 8) | red
