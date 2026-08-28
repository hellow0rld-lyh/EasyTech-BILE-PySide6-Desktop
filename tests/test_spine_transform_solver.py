from __future__ import annotations

import math
import unittest

from bile_workbench.spine_pose import BoneWorld
from bile_workbench.spine_transform_solver import apply_absolute_world_transform


def _bone(index: int, x: float, y: float, rotation: float = 0.0, scale_x: float = 1.0, scale_y: float = 1.0) -> BoneWorld:
    radians = math.radians(rotation)
    return BoneWorld(index, f"bone{index}", x, y, rotation, scale_x, scale_y, 0.0, 0.0, math.cos(radians) * scale_x, -math.sin(radians) * scale_y, math.sin(radians) * scale_x, math.cos(radians) * scale_y, x, y)


class SpineTransformSolverTests(unittest.TestCase):
    def test_absolute_world_copies_target_transform_at_full_mix(self) -> None:
        source = _bone(0, 0.0, 0.0)
        target = _bone(1, 10.0, 20.0, rotation=90.0, scale_x=2.0, scale_y=3.0)
        solved = apply_absolute_world_transform(
            source, target,
            offset_rotation=0.0, offset_x=0.0, offset_y=0.0, offset_scale_x=0.0, offset_scale_y=0.0, offset_shear_y=0.0,
            mix_rotate=1.0, mix_x=1.0, mix_y=1.0, mix_scale_x=1.0, mix_scale_y=1.0, mix_shear_y=0.0,
        )
        self.assertAlmostEqual(solved.world_x, 10.0, places=6)
        self.assertAlmostEqual(solved.world_y, 20.0, places=6)
        self.assertAlmostEqual(math.degrees(math.atan2(solved.c, solved.a)), 90.0, places=6)
        self.assertAlmostEqual(math.hypot(solved.a, solved.c), 2.0, places=6)
        self.assertAlmostEqual(math.hypot(solved.b, solved.d), 3.0, places=6)

    def test_absolute_world_uses_per_property_mix_and_target_space_offset(self) -> None:
        source = _bone(0, 0.0, 0.0)
        target = _bone(1, 10.0, 20.0, rotation=90.0)
        solved = apply_absolute_world_transform(
            source, target,
            offset_rotation=0.0, offset_x=2.0, offset_y=0.0, offset_scale_x=0.0, offset_scale_y=0.0, offset_shear_y=0.0,
            mix_rotate=0.5, mix_x=0.5, mix_y=0.5, mix_scale_x=0.0, mix_scale_y=0.0, mix_shear_y=0.0,
        )
        # target local (2, 0) rotates to world (10, 22), then x/y mixes at 50%.
        self.assertAlmostEqual(solved.world_x, 5.0, places=6)
        self.assertAlmostEqual(solved.world_y, 11.0, places=6)
        self.assertAlmostEqual(math.degrees(math.atan2(solved.c, solved.a)), 45.0, places=6)
        self.assertEqual(source.world_x, 0.0)
        self.assertEqual(target.world_y, 20.0)


if __name__ == "__main__":
    unittest.main()
