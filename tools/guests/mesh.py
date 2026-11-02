# SPDX-License-Identifier: GPL-3.0-or-later
"""The neutral form both model readers (vmx.py, vmg.py) give, for comparing them and writing a VMX."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Influence:
    bone: int
    weight: float
    position: tuple   # in the bone's space
    normal: tuple


@dataclass(frozen=True)
class Vertex:
    position: tuple   # bind pose (skinned) or the mesh's bone space (rigid)
    normal: tuple
    colour: int       # ARGB
    uv: tuple
    skin: tuple = ()  # Influences; empty for a rigid mesh


@dataclass
class Mesh:
    group: int
    kind: int
    material: int
    bone: int
    triangles: list = field(default_factory=list)
    bounds: tuple = None


@dataclass
class Model:
    meshes: list = field(default_factory=list)
    materials: int = 0
    bones: int = 0
    skinned_vertices: int = 0
