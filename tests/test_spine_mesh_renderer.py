from __future__ import annotations

import unittest

from PIL import Image

from bile_workbench.spine38_format import SpineMeshAttachment
from bile_workbench.spine_mesh_pose import project_unweighted_mesh
from bile_workbench.spine_mesh_renderer import rasterize_mesh
from bile_workbench.spine_pose import BoneWorld


class SpineMeshRendererTests(unittest.TestCase):
    def test_rasterizes_two_triangles_with_uv_mapping(self) -> None:
        mesh = SpineMeshAttachment("default", 0, "quad", "quad", 0xFFFFFFFF, (0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0), (0, 1, 2, 2, 3, 0), (0.0, 0.0, 4.0, 0.0, 4.0, 4.0, 0.0, 4.0), 4)
        world = BoneWorld(0, "root", 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        pose, diagnostic = project_unweighted_mesh(mesh, world)
        self.assertIsNone(diagnostic)
        assert pose is not None
        source = Image.new("RGBA", (4, 4), (240, 50, 30, 255))
        canvas = Image.new("RGBA", (12, 12), (20, 23, 28, 255))
        drawn = rasterize_mesh(canvas, source, pose, scale=1.0, offset_x=4.0, offset_y=8.0)
        self.assertEqual(2, drawn)
        self.assertEqual((240, 50, 30, 255), canvas.getpixel((6, 6)))


if __name__ == "__main__":
    unittest.main()
