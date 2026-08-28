from __future__ import annotations

import math
from typing import Iterable

import numpy as np
from PIL import Image


class TwoColorCompositeError(ValueError):
    """受限 two-color normal-alpha 审阅合成的输入不满足契约。"""


def _components(values: Iterable[float], expected: int, label: str) -> tuple[float, ...]:
    result = tuple(float(value) for value in values)
    if len(result) != expected or not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in result):
        raise TwoColorCompositeError(f"{label} 必须是 {expected} 个有限的 0..1 通道")
    return result


def compose_two_color_straight_alpha(
    source: Image.Image,
    light_rgba: tuple[float, float, float, float],
    dark_rgb: tuple[float, float, float],
) -> Image.Image:
    """合成官方 Tint Black straight-alpha 分支的受限 normal-alpha 可视等价输出。

    输入和输出都是 Pillow 的 straight-alpha RGBA。该函数不支持 PMA 输入、gamma/linear
    色彩空间转换、_Black 外部偏置、dark alpha additive 或任何非 normal blend。
    """
    light = _components(light_rgba, 4, "light_rgba")
    dark = _components(dark_rgb, 3, "dark_rgb")
    pixels = np.asarray(source.convert("RGBA"), dtype=np.float32) / 255.0
    texture_rgb = pixels[..., :3]
    texture_alpha = pixels[..., 3:4]
    light_rgb = np.asarray(light[:3], dtype=np.float32)
    light_alpha = light[3]
    dark_values = np.asarray(dark, dtype=np.float32)

    output_alpha = texture_alpha * light_alpha
    # Official straight-alpha shader branch emits PMA RGB:
    # tex.a * light.a * (tex.rgb * light.rgb + (1 - tex.rgb) * dark.rgb).
    # Pillow alpha_composite expects straight RGB, so unpremultiply only for alpha > 0.
    straight_rgb = texture_rgb * light_rgb + (1.0 - texture_rgb) * dark_values
    straight_rgb = np.where(texture_alpha > 0.0, straight_rgb, 0.0)
    output = np.concatenate((straight_rgb, output_alpha), axis=2)
    return Image.fromarray(np.rint(np.clip(output, 0.0, 1.0) * 255.0).astype(np.uint8), "RGBA")
