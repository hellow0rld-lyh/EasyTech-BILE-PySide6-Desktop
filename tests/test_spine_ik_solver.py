from __future__ import annotations

import math
import unittest

from bile_workbench.spine_ik_solver import solve_one_bone_ik, solve_two_bone_ik
from bile_workbench.spine_pose import BoneWorld


def _bone(index: int, x: float, y: float, rotation: float = 0.0) -> BoneWorld:
    radians = math.radians(rotation)
    return BoneWorld(index, f"bone{index}", x, y, rotation, 1.0, 1.0, 0.0, 0.0, math.cos(radians), -math.sin(radians), math.sin(radians), math.cos(radians), x, y)


class SpineIkSolverTests(unittest.TestCase):
    def test_one_bone_points_at_target_and_supports_stretch(self) -> None:
        source = _bone(0, 0.0, 0.0)
        solved, diagnostic = solve_one_bone_ik(source, 0.0, 10.0, mix=1.0, bone_length=5.0, stretch=True, uniform=True)
        self.assertIsNone(diagnostic)
        self.assertAlmostEqual(math.degrees(math.atan2(solved.c, solved.a)), 90.0, places=5)
        self.assertAlmostEqual(solved.scale_x, 2.0, places=5)
        self.assertAlmostEqual(solved.scale_y, 2.0, places=5)

    def test_one_bone_degenerate_target_is_explicit(self) -> None:
        source = _bone(0, 2.0, 3.0)
        solved, diagnostic = solve_one_bone_ik(source, 2.0, 3.0, mix=1.0, bone_length=5.0)
        self.assertEqual(solved, source)
        self.assertIn("重合", diagnostic or "")

    def test_two_bone_reaches_target_with_selected_bend(self) -> None:
        parent = _bone(0, 0.0, 0.0)
        child = _bone(1, 5.0, 0.0)
        (solved_parent, solved_child), diagnostic = solve_two_bone_ik(parent, child, 5.0, 5.0, parent_length=5.0, child_length=5.0, bend_direction=1, mix=1.0)
        self.assertIsNone(diagnostic)
        tip_x = solved_child.world_x + math.cos(math.atan2(solved_child.c, solved_child.a)) * 5.0
        tip_y = solved_child.world_y + math.sin(math.atan2(solved_child.c, solved_child.a)) * 5.0
        self.assertAlmostEqual(tip_x, 5.0, places=4)
        self.assertAlmostEqual(tip_y, 5.0, places=4)
        self.assertNotEqual(solved_child.rotation, child.rotation)

    def test_two_bone_invalid_bend_downgrades_without_change(self) -> None:
        parent = _bone(0, 0.0, 0.0)
        child = _bone(1, 5.0, 0.0)
        solved, diagnostic = solve_two_bone_ik(parent, child, 5.0, 5.0, parent_length=5.0, child_length=5.0, bend_direction=0, mix=1.0)
        self.assertEqual(solved, (parent, child))
        self.assertIn("bend", diagnostic or "")


if __name__ == "__main__":
    unittest.main()
