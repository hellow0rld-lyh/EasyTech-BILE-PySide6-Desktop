"""修改后 BILE 的回读验证与原游戏实验包生成。"""
from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .assets import archive_tree, create_triplet, sha256_file, stage_triplet
from .bile_format import BileDocument, parse_file
from .diagnostics import collect_diagnostics
from .preview_renderer import Atlas, load_atlas, render_frame


@dataclass(frozen=True)
class ExperimentPackageResult:
    archive_path: Path
    report_path: Path
    candidate_sha256: str
    checked_animations: int
    warnings: tuple[str, ...]


def verify_candidate_triplet(candidate_bin: str | Path, xml_path: str | Path, image_path: str | Path, animation_names: tuple[str, ...] | None = None) -> tuple[BileDocument, Atlas, dict]:
    """重开候选 BIN 并渲染代表槽位；未指定名称时验证全部动画。"""
    candidate = Path(candidate_bin)
    xml = Path(xml_path)
    image = Path(image_path)
    document = parse_file(candidate)
    atlas = load_atlas(xml, image)
    diagnostics = collect_diagnostics(document, atlas)
    errors = [item.message for item in diagnostics if item.severity == "ERROR"]
    if errors:
        raise ValueError("候选资源存在阻断性诊断：" + "；".join(errors))
    animation_checks = []
    selected_animation_names = set(animation_names) if animation_names is not None else None
    available_animation_names = {element.name for element in document.animations}
    if selected_animation_names is not None:
        missing_animation_names = selected_animation_names - available_animation_names
        if missing_animation_names:
            raise ValueError("候选 BIN 缺少指定验证动画：" + "；".join(sorted(missing_animation_names)))
    for element in document.animations:
        if selected_animation_names is not None and element.name not in selected_animation_names:
            continue
        slots = sorted({0, max(0, element.frame_count // 2), max(0, element.frame_count - 1)})
        rendered = []
        for slot in slots:
            frame = render_frame(document, atlas, element.name, slot, canvas_size=(256, 192))
            non_background = len(set(frame.getdata())) > 1
            rendered.append({"slot": slot, "nonuniform_pixels": non_background})
        animation_checks.append({"index": element.index, "name": element.name, "frame_count": element.frame_count, "samples": rendered})
    report = {
        "schema": "bile-workbench.experiment-package/v1",
        "candidate": {"file": candidate.name, "sha256": sha256_file(candidate), "version": document.header.version, "fps": document.header.fps},
        "atlas": {"xml": xml.name, "image": image.name, "image_sha256": sha256_file(image)},
        "counts": {"elements": len(document.elements), "animations": len(document.animations), "sprites": len(document.sprites), "keyframes": len(document.keyframes)},
        "diagnostics": [{"severity": item.severity, "code": item.code, "message": item.message, "context": item.context} for item in diagnostics],
        "animation_checks": animation_checks,
        "contract": "candidate BIN parsed anew; XML/WebP loaded anew; selected representative frames rendered with reference_v4. Game-side acceptance remains a separate test.",
        "validated_animation_scope": "all" if selected_animation_names is None else sorted(selected_animation_names),
    }
    return document, atlas, report


def create_experiment_package(
    original_bin_path: str | Path,
    candidate_bin_path: str | Path,
    xml_path: str | Path,
    image_path: str | Path,
    archive_path: str | Path,
    patch_path: str | Path | None = None,
) -> ExperimentPackageResult:
    """生成 ZIP：候选 BIN 使用原始基名，以便用户手工备份后覆盖游戏内对应三件套。"""
    original = Path(original_bin_path)
    candidate = Path(candidate_bin_path)
    xml = Path(xml_path)
    image = Path(image_path)
    output = Path(archive_path)
    if not original.is_file():
        raise FileNotFoundError(f"实验包缺少目标原始 BIN：{original}")
    candidate_triplet = create_triplet(candidate, xml, image)
    document, _atlas, report = verify_candidate_triplet(candidate_triplet.bin_path, candidate_triplet.xml_path, candidate_triplet.image_path)
    warnings = tuple(item["message"] for item in report["diagnostics"] if item["severity"] == "WARNING")
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path = output.with_suffix(".validation_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="bile-experiment-") as temp_dir:
        root = Path(temp_dir) / f"{original.stem}_experiment"
        resources = root / "replace_after_backup"
        resources.mkdir(parents=True)
        stage_triplet(
            candidate_triplet,
            resources,
            bin_name=original.name,
            xml_name=xml.name,
            image_name=image.name,
        )
        shutil.copy2(report_path, root / "validation_report.json")
        readme = """# BILE Workbench 游戏内实验包

此包包含候选 BIN、其同名 XML 与图集。候选 BIN 已在工作台中重新解析，并完成 XML/WebP 绑定和代表槽位离线渲染。

## 使用方法

1. 在游戏资源目录中备份同名原始 `.bin`、`.xml` 和图集文件。
2. 将 `replace_after_backup/` 内的三件套复制到相同资源目录，保持文件名不变。
3. 打开对应效果或单位动作，在目标槽位截图/录屏。
4. 若出现加载失败、错位、闪烁或层级异常，恢复备份，并保存截图、设备和游戏版本信息。

> 离线结构验证通过不等于原游戏运行时必然接受。此实验包不会包含 APK、签名材料或私钥。
"""
        (root / "README_游戏内验证.md").write_text(readme, encoding="utf-8")
        if patch_path is not None:
            patch = Path(patch_path)
            if patch.exists():
                shutil.copy2(patch, root / "source_patch.json")
        archive_tree(root, output)
    return ExperimentPackageResult(output, report_path, sha256_file(candidate), len(document.animations), warnings)
