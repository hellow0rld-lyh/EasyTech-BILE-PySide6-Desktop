"""BILE v4 的非破坏性诊断与可共享文本报告。"""
from __future__ import annotations

from dataclasses import dataclass

from .bile_format import BileDocument
from .preview_renderer import Atlas


@dataclass(frozen=True)
class Diagnostic:
    severity: str  # INFO / WARNING / ERROR
    code: str
    message: str
    context: str = ""


def collect_diagnostics(document: BileDocument, atlas: Atlas) -> tuple[Diagnostic, ...]:
    findings: list[Diagnostic] = []
    if document.header.version in (3, 4):
        findings.append(Diagnostic("INFO", "BILE_CROSS_GAME_PROFILE", f"BILE v{document.header.version} 使用已在世界征服者3、将军的荣耀3、欧洲战争6与世界征服者4样本中实测的六块容器布局。", "解析器仍会对长度、块顺序、引用和字符串边界进行严格校验。"))
    elif document.header.version == 2:
        findings.append(Diagnostic("INFO", "BILE_V2_FIVE_SECTION_READONLY_PROFILE", "BILE v2 使用已在将军的荣耀1 12 个样本中验证的五节容器：BELE、BMRF、BYAL、BMTI、BRTS。", "v2 的 48 字节 BELE 与 12 字节合并 BMRF 当前仅支持严格解析、预览和导出；保守补丁与直接编辑已禁用。"))
    else:
        findings.append(Diagnostic("WARNING", "BILE_VERSION_UNVALIDATED", f"BILE v{document.header.version} 不属于当前跨游戏验证版本集合 v2/v3/v4。", "可尝试解析，但应先生成诊断和离线回归证据。"))
    if document.graph_cycles:
        for cycle in document.graph_cycles:
            findings.append(Diagnostic("ERROR", "ANIMATION_REFERENCE_CYCLE", f"检测到动画元素引用环：{' → '.join(map(str, cycle))}", "预览已安全截断该环"))
    else:
        findings.append(Diagnostic("INFO", "ANIMATION_REFERENCE_GRAPH_ACYCLIC", "动画元素引用图无环。"))

    unknown_modes = [index for index, keyframe in enumerate(document.keyframes) if not keyframe.has_known_playback_mode]
    if unknown_modes:
        findings.append(Diagnostic("WARNING", "UNKNOWN_PLAYBACK_MODE", f"{len(unknown_modes)} 条 BELE 使用未识别 playback_mode。", f"索引：{', '.join(map(str, unknown_modes[:12]))}"))
    else:
        findings.append(Diagnostic("INFO", "PLAYBACK_MODE_VALUES_KNOWN", "所有 BELE playback_mode 均落在 0/1/2。"))

    phased = [index for index, keyframe in enumerate(document.keyframes) if keyframe.initial_phase != 0]
    if phased:
        findings.append(Diagnostic("INFO", "NONZERO_INITIAL_PHASE", f"{len(phased)} 条 BELE 使用非零 initial_phase。", f"索引：{', '.join(map(str, phased[:12]))}"))

    nested_root_profiles: list[str] = []
    for element in document.animations:
        # 每个通道的活动帧仅在其 BMRF 槽位变化；按变化量合并可避免对大型兵模逐槽重复扫描。
        slot_deltas: dict[int, int] = {}
        for channel in element.channels:
            previous_child_track_count = 0
            for frame in channel.frames:
                child_track_count = sum(
                    track.element_index >= 0 and not document.elements[track.element_index].has_texture
                    for track in frame.tracks
                )
                slot_deltas[frame.slot] = slot_deltas.get(frame.slot, 0) + child_track_count - previous_child_track_count
                previous_child_track_count = child_track_count
        active_child_track_count = 0
        max_child_animation_tracks = 0
        for _slot, delta in sorted(slot_deltas.items()):
            active_child_track_count += delta
            max_child_animation_tracks = max(max_child_animation_tracks, active_child_track_count)
        if max_child_animation_tracks:
            nested_root_profiles.append(f"{element.name}（最多 {max_child_animation_tracks} 条并发子动画轨道）")
    if nested_root_profiles:
        findings.append(Diagnostic(
            "INFO",
            "ROOT_ANIMATION_NESTED_COMPOSITION",
            f"{len(nested_root_profiles)} 个根动画通过并发子动画轨道组合画面。",
            "；".join(nested_root_profiles[:4]) + "。该指标描述单个 BILE 根动作内部组合，不等于游戏格子中的编队实例数。",
        ))
    else:
        findings.append(Diagnostic(
            "INFO",
            "ROOT_ANIMATION_DIRECT_SPRITE_COMPOSITION",
            "动画根节点未发现并发子动画轨道；当前根动作以直接精灵轨道为主。",
            "该指标只描述 BILE 内部组合，不等于游戏格子中的编队实例数。",
        ))

    null_tracks = []
    unordered_channels = []
    for element in document.animations:
        for channel_index, channel in enumerate(element.channels):
            slots = [frame.slot for frame in channel.frames]
            if slots != sorted(slots):
                unordered_channels.append(f"{element.name}/通道{channel_index + 1}")
            for frame in channel.frames:
                for track in frame.tracks:
                    if track.element_index == -1:
                        null_tracks.append(track.keyframe_index)
    if null_tracks:
        findings.append(Diagnostic("INFO", "LEGAL_NULL_TRACK", f"发现 {len(null_tracks)} 个 element_index=-1 的空轨道引用。", "不会生成绘制命令"))
    if unordered_channels:
        findings.append(Diagnostic("WARNING", "UNORDERED_FRAME_SLOTS", "部分通道 BMRF 槽位不升序。", "；".join(unordered_channels[:8])))

    missing = []
    for element in document.sprites:
        if element.name not in atlas.regions and f"{element.name}.png" not in atlas.regions:
            missing.append(element.name)
    if missing:
        findings.append(Diagnostic("WARNING", "ATLAS_FRAME_NOT_FOUND", f"{len(missing)} 个图片元素未在 XML 图集中匹配。", "；".join(missing[:12])))
    else:
        findings.append(Diagnostic("INFO", "ATLAS_IMAGE_NAMES_RESOLVED", "所有 BMTI 图片元素均可在 XML 图集中解析。"))

    referenced = [region for name, region in atlas.regions.items() if name.endswith(".png") and (region.refx != 0 or region.refy != 0)]
    if referenced:
        findings.append(Diagnostic("INFO", "ATLAS_REFERENCE_POINT_APPLIED", f"{len(referenced)} 个 XML 精灵具有非零 refx/refy；渲染器已应用。"))
    if atlas.xml_had_declaration:
        findings.append(Diagnostic("INFO", "ATLAS_XML_DECLARATION_COMPATIBLE", "图集 XML 含声明，已在包装多顶层资源片段前兼容处理。"))
    if atlas.stripped_control_chars:
        findings.append(Diagnostic("WARNING", "ATLAS_XML_CONTROL_PADDING_STRIPPED", f"图集 XML 含 {atlas.stripped_control_chars} 个非法控制填充字符，已在只读加载时剔除。", "原文件未被修改；建议游戏内实验包保留原始 XML。"))
    if atlas.fractional_geometry_regions:
        findings.append(Diagnostic("INFO", "ATLAS_FRACTIONAL_GEOMETRY_COMPATIBLE", f"{atlas.fractional_geometry_regions} 个图集区域使用小数几何值；渲染器保留几何并用覆盖像素边界裁切。"))
    if atlas.source_image_format:
        findings.append(Diagnostic("INFO", "ATLAS_SOURCE_FORMAT", f"图集源格式：{atlas.source_image_format.upper()}。"))
    return tuple(findings)


def format_diagnostics(document: BileDocument, atlas: Atlas) -> str:
    rows = collect_diagnostics(document, atlas)
    lines = [
        f"BILE v{document.header.version} · {len(document.elements)} BMTI · {len(document.keyframes)} BELE · {document.header.fps:.3f} FPS",
        "",
    ]
    for item in rows:
        suffix = f"\n    {item.context}" if item.context else ""
        lines.append(f"[{item.severity}] {item.code}\n    {item.message}{suffix}")
    return "\n\n".join(lines)
