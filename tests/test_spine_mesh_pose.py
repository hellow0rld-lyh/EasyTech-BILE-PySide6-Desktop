from __future__ import annotations

import unittest

from bile_workbench.spine38_format import SpineMeshAttachment
from bile_workbench.spine_mesh_pose import project_unweighted_mesh, project_weighted_mesh_setup
from bile_workbench.spine_pose import BoneWorld


class SpineMeshPoseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = BoneWorld(0, "root", 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 10.0, 20.0)

    def test_projects_unweighted_vertices_and_preserves_triangle_mapping(self) -> None:
        mesh = SpineMeshAttachment("default", 0, "quad", "quad", 0xFFFFFFFF, (0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0), (0, 1, 2, 2, 3, 0), (0.0, 0.0, 4.0, 0.0, 4.0, 4.0, 0.0, 4.0), 4)
        pose, diagnostic = project_unweighted_mesh(mesh, self.world)
        self.assertIsNone(diagnostic)
        assert pose is not None
        self.assertEqual((10.0, 20.0, 14.0, 20.0, 14.0, 24.0, 10.0, 24.0), pose.world_vertices)
        self.assertEqual(mesh.triangles, pose.triangles)

    def test_projects_weighted_setup_vertices_and_rejects_invalid_influences(self) -> None:
        second = BoneWorld(1, "second", 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 20.0, 20.0)
        mesh = SpineMeshAttachment("default", 0, "weighted", "weighted", 0xFFFFFFFF, (0.0, 0.0, 1.0, 0.0, 0.5, 1.0), (0, 1, 2), None, 3, (((0, 0.0, 0.0, 1.0),), ((1, 2.0, 0.0, 1.0),), ((0, 0.0, 2.0, 0.5), (1, 0.0, 2.0, 0.5))))
        pose, diagnostic = project_weighted_mesh_setup(mesh, (self.world, second))
        self.assertIsNone(diagnostic)
        assert pose is not None
        self.assertEqual((10.0, 20.0, 22.0, 20.0, 15.0, 22.0), pose.world_vertices)
        invalid = SpineMeshAttachment("default", 0, "bad-weight", "bad-weight", 0xFFFFFFFF, (0.0, 0.0, 1.0, 0.0, 0.5, 1.0), (0, 1, 2), None, 3, (((2, 0.0, 0.0, 1.0),), ((1, 0.0, 0.0, 1.0),), ((1, 0.0, 0.0, 1.0),)))
        pose, diagnostic = project_weighted_mesh_setup(invalid, (self.world, second))
        self.assertIsNone(pose)
        self.assertIn("无效", diagnostic or "")

    def test_refuses_weighted_or_malformed_meshes(self) -> None:
        weighted = SpineMeshAttachment("default", 0, "weighted", "weighted", 0xFFFFFFFF, (), (), None, 0)
        pose, diagnostic = project_unweighted_mesh(weighted, self.world)
        self.assertIsNone(pose)
        self.assertIn("加权", diagnostic or "")
        malformed = SpineMeshAttachment("default", 0, "bad", "bad", 0xFFFFFFFF, (0.0, 0.0), (0, 1, 2), (0.0, 0.0), 0)
        pose, diagnostic = project_unweighted_mesh(malformed, self.world)
        self.assertIsNone(pose)
        self.assertIn("索引", diagnostic or "")


if __name__ == "__main__":
    unittest.main()
