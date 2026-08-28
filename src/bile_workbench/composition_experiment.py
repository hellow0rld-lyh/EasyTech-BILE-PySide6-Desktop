"""跨游戏兵模组合的单变量实验包。

不写入游戏目录，不自动改 def_motion，也不修改用户源文件。包内候选三件套以目标基名暂存，
XML 仅允许将 Texture.name 改为暂存图像名；所有其他运行时配置变更以可审计手工配方给出。
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .assets import AssetTriplet, archive_tree, create_triplet, sha256_file, stage_triplet
from .bile_format import BileDocument, parse_file
from .experiment_package import verify_candidate_triplet


class CompositionExperimentError(ValueError):
    """跨游戏组合实验的输入或单变量约束不满足。"""


@dataclass(frozen=True)
class CompositionExperimentResult:
    archive_path: Path
    manifest_path: Path
    binding_recipe_path: Path
    validation_report_path: Path
    target_sha256: str
    candidate_sha256: str
    candidate_root_profile: dict


def _active_tracks(element, slot: int):
    tracks = []
    for channel in element.channels:
        active = None
        for frame in channel.frames:
            if frame.slot <= slot:
                active = frame
            else:
                break
        if active is not None:
            tracks.extend(active.tracks)
    return tracks


def root_composition_profile(document: BileDocument, animation_name: str) -> dict:
    """描述单个根动作的内部并发结构，不解释为游戏格子人数。"""
    element = next((item for item in document.animations if item.name == animation_name), None)
    if element is None:
        raise CompositionExperimentError(f"BILE 中不存在候选根动作：{animation_name}")
    direct_animation_max = 0
    direct_sprite_max = 0
    for slot in range(element.frame_count):
        tracks = _active_tracks(element, slot)
        direct_animation_max = max(direct_animation_max, sum(
            track.element_index >= 0 and not document.elements[track.element_index].has_texture
            for track in tracks
        ))
        direct_sprite_max = max(direct_sprite_max, sum(
            track.element_index >= 0 and document.elements[track.element_index].has_texture
            for track in tracks
        ))
    return {
        "root": element.name,
        "element_index": element.index,
        "frame_count": element.frame_count,
        "channel_count": len(element.channels),
        "max_concurrent_direct_child_animations": direct_animation_max,
        "max_concurrent_direct_sprites": direct_sprite_max,
        "contract": "根动作内部并发轨道画像；不等于游戏格子中的最终单位数量。",
    }


def _patch_texture_name(xml_bytes: bytes, destination_image_name: str) -> tuple[bytes, dict]:
    """只替换第一个 <Texture ... name='...'> 的 name 值，保持其余字节不变。"""
    match = re.search(rb"(<Texture\b[^>]*?\bname\s*=\s*)([\"'])(.*?)(\2)", xml_bytes, flags=re.DOTALL)
    if match is None:
        return xml_bytes, {
            "old_texture_name": None,
            "new_texture_name": destination_image_name,
            "only_change": "none: XML 未声明 Texture.name，保持原字节；图像仅按目标基名暂存",
        }
    try:
        old_name = match.group(3).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CompositionExperimentError("候选 XML Texture.name 不是 UTF-8") from exc
    replacement = match.group(1) + match.group(2) + destination_image_name.encode("utf-8") + match.group(4)
    patched = xml_bytes[:match.start()] + replacement + xml_bytes[match.end():]
    return patched, {"old_texture_name": old_name, "new_texture_name": destination_image_name, "only_change": "Texture.name"}


def _asset_manifest_entry(triplet: AssetTriplet, destination: AssetTriplet, version: int | None = None) -> dict:
    entry = {
        "bin": {"source": str(triplet.bin_path), "sha256": triplet.bin_sha256, "destination": destination.bin_path.name},
        "xml": {"source": str(triplet.xml_path), "sha256": triplet.xml_sha256, "destination": destination.xml_path.name},
        "image": {"source": str(triplet.image_path), "sha256": triplet.image_sha256, "destination": destination.image_path.name},
    }
    if version is not None:
        entry["bin"]["bile_version"] = version
    return entry


def create_composition_experiment_package(
    target_bin: str | Path,
    target_xml: str | Path,
    target_image: str | Path,
    candidate_bin: str | Path,
    candidate_xml: str | Path,
    candidate_image: str | Path,
    target_root_animation: str,
    candidate_root_animation: str,
    archive_path: str | Path,
    *,
    target_unit_name: str = "",
    target_motion_type: str = "standby",
    target_resource: str = "",
    optional_target_formation_config: str | Path | None = None,
) -> CompositionExperimentResult:
    """生成跨游戏组合实验 ZIP；运行时绑定修改必须由用户按配方手工完成。"""
    target_triplet = create_triplet(target_bin, target_xml, target_image)
    candidate_triplet = create_triplet(candidate_bin, candidate_xml, candidate_image)
    target_doc = parse_file(target_triplet.bin_path)
    candidate_doc = parse_file(candidate_triplet.bin_path)
    target_profile = root_composition_profile(target_doc, target_root_animation)
    candidate_profile = root_composition_profile(candidate_doc, candidate_root_animation)
    output = Path(archive_path)
    formation_snapshot = Path(optional_target_formation_config) if optional_target_formation_config else None
    if formation_snapshot is not None and not formation_snapshot.is_file():
        raise FileNotFoundError(f"可选阵列配置不存在：{formation_snapshot}")

    destination_stub = AssetTriplet(
        Path(target_triplet.bin_path.name), Path(target_triplet.xml_path.name), Path(target_triplet.image_path.name)
    )
    target_assets = _asset_manifest_entry(target_triplet, destination_stub, target_doc.header.version)
    target_assets["root_animation"] = target_profile
    target_assets["resource"] = target_resource or target_triplet.stem
    candidate_assets = _asset_manifest_entry(candidate_triplet, destination_stub, candidate_doc.header.version)
    candidate_assets["root_animation"] = candidate_profile
    patched_xml, xml_change = _patch_texture_name(candidate_triplet.xml_path.read_bytes(), destination_stub.image_path.name)
    candidate_assets["xml"]["source_sha256"] = candidate_triplet.xml_sha256
    candidate_assets["xml_transform"] = xml_change
    manifest = {
        "schema": "bile-workbench.composition-experiment/v1",
        "kind": "cross-game-root-composition",
        "target": target_assets,
        "candidate": candidate_assets,
        "controlled_variables": {
            "must_remain_target_side": ["游戏版本", "目标资源路径", "Army/Unit 类型", "地图与关卡", "单位方向", "阵列/Formation 选择", "镜头缩放"],
            "treatment": "以候选三件套覆盖目标资源基名；候选 XML 仅把 Texture.name 改为目标图像文件名；def_motion 绑定按独立配方手工改为候选根动作。",
            "not_claimed": "本包不证明 Army/Unit 到 Formation 的运行时选择关系，也不修改任何上层配置。",
        },
        "optional_target_formation_config": (
            {"source": str(formation_snapshot), "sha256": sha256_file(formation_snapshot), "destination": f"configuration_snapshot/{formation_snapshot.name}"}
            if formation_snapshot else None
        ),
    }
    binding_recipe = {
        "schema": "bile-workbench.motion-binding-recipe/v1",
        "contract": "只给出单个 Motion.name 的人工变更配方，不提供自动写回 def_motion.xml；执行前必须确认基线哈希和目标 Unit/资源。",
        "target_unit_name": target_unit_name,
        "target_resource": target_resource or target_triplet.stem,
        "target_motion_type": target_motion_type,
        "expected_baseline_motion_name": target_root_animation,
        "replacement_motion_name": candidate_root_animation,
        "required_post_change_checks": [
            "候选三件套和目标 def_motion.xml 均先备份。",
            "仅将匹配 Unit / res / Motion type 的 name 从 expected_baseline_motion_name 改为 replacement_motion_name。",
            "确认除这一处 Motion.name 和候选 XML 的 Texture.name 外不存在其他资源配置变化。",
            "在相同 Army/地图/方向下截图或录屏，并登记到回归案例。",
            "实验结束后恢复所有目标资源与配置备份。",
        ],
    }
    with tempfile.TemporaryDirectory(prefix="bile-composition-experiment-") as temp_dir:
        root = Path(temp_dir) / f"{target_triplet.stem}_composition_experiment"
        replacements = root / "replace_after_backup"
        staged_triplet = stage_triplet(
            candidate_triplet,
            replacements,
            bin_name=destination_stub.bin_path.name,
            xml_name=destination_stub.xml_path.name,
            image_name=destination_stub.image_path.name,
            xml_bytes=patched_xml,
        )
        _document, _atlas, validation = verify_candidate_triplet(
            staged_triplet.bin_path, staged_triplet.xml_path, staged_triplet.image_path, animation_names=(candidate_root_animation,)
        )
        validation["experiment_scope"] = manifest["controlled_variables"]
        validation["candidate_root_animation"] = candidate_profile
        validation["target_root_animation"] = target_profile
        validation["warning"] = "离线验证通过不等于目标游戏会接受跨游戏根动作或 def_motion 绑定。"
        (root / "validation_report.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
        (root / "experiment_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (root / "binding_change_recipe.json").write_text(json.dumps(binding_recipe, ensure_ascii=False, indent=2), encoding="utf-8")
        if formation_snapshot:
            config_dir = root / "configuration_snapshot"
            config_dir.mkdir()
            shutil.copy2(formation_snapshot, config_dir / formation_snapshot.name)
        readme = """# 跨游戏根动画组合实验包

本包的**唯一资源处理**是：将候选 BIN、图集 XML 与图像文件以目标三件套的基名暂存。候选 XML 只将 `<Texture name>` 改为暂存目标图像名，精确改动见 `experiment_manifest.json`。

`binding_change_recipe.json` 是需要在目标游戏配置中手工执行的单个 `Motion.name` 绑定配方；它不会自动修改 `def_motion.xml`，以免把配置重排、格式化或额外变量混入实验。

请固定游戏版本、Army/Unit 类型、地图、方向、阵列/Formation 选择和镜头条件。完成截图/录屏后，使用工作台“回归”菜单登记证据。离线验证成功只证明候选三件套可被工作台回读与渲染，不保证游戏运行时接受。
"""
        (root / "README_实验说明.md").write_text(readme, encoding="utf-8")
        archive_tree(root, output)
    report_path = output.with_suffix(".validation_report.json")
    manifest_path = output.with_suffix(".experiment_manifest.json")
    recipe_path = output.with_suffix(".binding_change_recipe.json")
    report_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    recipe_path.write_text(json.dumps(binding_recipe, ensure_ascii=False, indent=2), encoding="utf-8")
    return CompositionExperimentResult(
        output, manifest_path, recipe_path, report_path, target_triplet.bin_sha256, candidate_triplet.bin_sha256, candidate_profile
    )
