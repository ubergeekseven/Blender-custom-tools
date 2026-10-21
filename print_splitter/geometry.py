"""Geometry helpers: cut-plane frames, cross sections, pin spots, cutter meshes
and boolean evaluation. Nothing here touches the UI."""

import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


# --------------------------------------------------------------------------
# Plane frame
# --------------------------------------------------------------------------

class PlaneFrame:
    """Position and orientation of a cut plane, ignoring the object's scale.

    The plane's local Z axis is its normal. Side "A" of a cut is the side the
    normal points to, side "B" the other one.
    """

    def __init__(self, matrix_world):
        loc, rot, _scale = matrix_world.decompose()
        self.rot = rot.to_matrix()
        self.origin = loc.copy()
        self.u = (self.rot @ Vector((1.0, 0.0, 0.0))).normalized()
        self.v = (self.rot @ Vector((0.0, 1.0, 0.0))).normalized()
        self.n = (self.rot @ Vector((0.0, 0.0, 1.0))).normalized()

    def matrix(self):
        return Matrix.Translation(self.origin) @ self.rot.to_4x4()

    def to_2d(self, p):
        d = p - self.origin
        return d.dot(self.u), d.dot(self.v)

    def to_3d(self, x, y):
        return self.origin + self.u * x + self.v * y

    def project(self, p):
        return p - self.n * (p - self.origin).dot(self.n)


# --------------------------------------------------------------------------
# World-space mesh access
# --------------------------------------------------------------------------

def world_bmesh(context, obj):
    """Evaluated (modifiers applied) mesh of ``obj`` as a world-space BMesh."""
    depsgraph = context.evaluated_depsgraph_get()
    bm = bmesh.new()
    bm.from_object(obj.evaluated_get(depsgraph), depsgraph)
    bm.transform(obj.matrix_world)
    bm.normal_update()
    return bm


def bmesh_size(bm):
    if not bm.verts:
        return 0.0
    co = np.array([v.co[:] for v in bm.verts])
    return float(np.linalg.norm(co.max(0) - co.min(0)))


def is_inside(bvh, p):
    """Point-in-solid test using the side of the nearest surface."""
    loc, normal, _index, _dist = bvh.find_nearest(p)
    if loc is None:
        return False
    return (p - loc).dot(normal) < 0.0


# --------------------------------------------------------------------------
# Cross section
# --------------------------------------------------------------------------

def section_segments(bm_world, frame, eps):
    """Edges where the plane cuts the mesh, as two (S, 2) arrays in plane
    coordinates (start points, end points)."""
    bm = bm_world.copy()
    try:
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        res = bmesh.ops.bisect_plane(
            bm, geom=geom, dist=eps, plane_co=frame.origin, plane_no=frame.n)
        starts, ends = [], []
        for ele in res["geom_cut"]:
            if isinstance(ele, bmesh.types.BMEdge):
                starts.append(frame.to_2d(ele.verts[0].co))
                ends.append(frame.to_2d(ele.verts[1].co))
    finally:
        bm.free()
    return np.array(starts, dtype=float).reshape(-1, 2), np.array(ends, dtype=float).reshape(-1, 2)


def section_query(points, seg_a, seg_b):
    """For 2D points return (inside, distance-to-boundary).

    ``inside`` uses the even-odd rule over all section edges, so sections with
    several islands or with holes (the ring you get cutting a hollow mask)
    work without chaining edges into loops.
    """
    points = np.asarray(points, dtype=float).reshape(-1, 2)
    n = len(points)
    inside = np.zeros(n, dtype=bool)
    dist = np.full(n, np.inf)
    if n == 0 or len(seg_a) == 0:
        return inside, dist
    d = seg_b - seg_a
    dd = (d * d).sum(1)
    dd[dd == 0.0] = 1e-30
    ay, by = seg_a[:, 1], seg_b[:, 1]
    dy = by - ay
    dy_safe = np.where(dy == 0.0, 1e-30, dy)
    chunk = max(1, 2_000_000 // len(seg_a))
    for i in range(0, n, chunk):
        p = points[i:i + chunk, None, :]
        t = np.clip(((p - seg_a) * d).sum(2) / dd, 0.0, 1.0)
        proj = seg_a + t[..., None] * d
        dist[i:i + chunk] = np.sqrt(((p - proj) ** 2).sum(2).min(1))
        py = p[..., 1]
        straddle = (ay > py) != (by > py)
        x_hit = seg_a[:, 0] + (py - ay) * d[:, 0] / dy_safe
        crossings = (straddle & (p[..., 0] < x_hit)).sum(1)
        inside[i:i + chunk] = crossings % 2 == 1
    return inside, dist


def hole_fits(bvh, frame, center, radius, depth, wall):
    """True when a hole of ``radius`` reaching ``depth`` to both sides of the
    plane stays inside the solid with at least ``wall`` around it."""
    ring = radius + wall
    for side in (1.0, -1.0):
        for frac in (0.15, 0.5, 0.85, 1.0):
            axis_pt = center + frame.n * (side * depth * frac)
            if not is_inside(bvh, axis_pt):
                return False
            for k in range(12):
                a = 2.0 * math.pi * k / 12.0
                p = axis_pt + (frame.u * math.cos(a) + frame.v * math.sin(a)) * ring
                if not is_inside(bvh, p):
                    return False
    return True


def auto_pin_spots(bm_world, frame, count, radius, depth, wall, eps):
    """Pick up to ``count`` well spread pin positions on the cut, each with
    room for the hole plus ``wall`` of material around it. May return fewer
    than ``count`` (or none) when the section is too thin."""
    seg_a, seg_b = section_segments(bm_world, frame, eps)
    if len(seg_a) == 0:
        return []
    bvh = BVHTree.FromBMesh(bm_world)

    pts = np.vstack([seg_a, seg_b])
    lo, hi = pts.min(0), pts.max(0)
    extent = float((hi - lo).max())
    step = max(extent / 150.0, radius * 0.25, 1e-9)
    while ((hi - lo) / step + 1).prod() > 40000:
        step *= 1.25
    xs = np.arange(lo[0] + step * 0.5, hi[0], step)
    ys = np.arange(lo[1] + step * 0.5, hi[1], step)
    grid = np.array(np.meshgrid(xs, ys)).reshape(2, -1).T
    inside, dist = section_query(grid, seg_a, seg_b)
    ok = inside & (dist >= radius + wall)
    cand = grid[ok]
    clearance = dist[ok]
    if len(cand) == 0:
        return []

    spacing = 2.0 * radius + wall
    max_clear = float(clearance.max())
    weight = 0.5 + 0.5 * clearance / max_clear
    # Seed with the candidate furthest from the section's middle so pins go
    # out toward the edges of the part, then keep adding the candidate
    # furthest from all chosen ones (weighted toward thicker material).
    min_d = np.linalg.norm(cand - cand.mean(0), axis=1) * weight
    rejected = np.zeros(len(cand), dtype=bool)
    chosen = []
    while len(chosen) < count:
        score = np.where(rejected, -1.0, min_d)
        idx = int(np.argmax(score))
        if score[idx] < 0.0:
            break
        p3 = frame.to_3d(float(cand[idx, 0]), float(cand[idx, 1]))
        if not hole_fits(bvh, frame, p3, radius, depth, wall * 0.5):
            rejected[idx] = True
            continue
        chosen.append(p3)
        rejected[idx] = True
        d_new = np.linalg.norm(cand - cand[idx], axis=1)
        if len(chosen) == 1:
            min_d = d_new * weight
        else:
            min_d = np.minimum(min_d, d_new * weight)
        # Anything closer than the minimum spacing is out.
        rejected |= d_new < spacing
    return chosen


# --------------------------------------------------------------------------
# Mesh builders
# --------------------------------------------------------------------------

def mesh_from_bmesh(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def halfspace_mesh(name, size):
    """Box covering the +Z half space within ``size`` of the origin."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0 * size,
                          matrix=Matrix.Translation((0.0, 0.0, size)))
    return mesh_from_bmesh(name, bm)


def cylinder_mesh(name, radius, half_length, segments=48):
    """Closed cylinder along Z, centred on the origin. The polygon is
    circumscribed so the hole is never smaller than ``radius``."""
    bm = bmesh.new()
    r = radius / math.cos(math.pi / segments)
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                          radius1=r, radius2=r, depth=2.0 * half_length)
    return mesh_from_bmesh(name, bm)


def hex_pin_bmesh(across_corners, length, chamfer):
    """Hexagonal prism along +Z from 0 to ``length`` with chamfered ends.

    Corners sit at 30, 90, 150... degrees, so flat sides face +X and -X;
    rotating the pin 90 degrees about Y lays it on one of them.
    """
    R = across_corners * 0.5
    c = max(0.0, min(chamfer, R * 0.45, length * 0.25))
    if c > 0.0:
        rings = [(0.0, R - c), (c, R), (length - c, R), (length, R - c)]
    else:
        rings = [(0.0, R), (length, R)]
    bm = bmesh.new()
    loops = []
    for z, r in rings:
        loops.append([bm.verts.new((r * math.cos(math.radians(30 + 60 * k)),
                                    r * math.sin(math.radians(30 + 60 * k)), z))
                      for k in range(6)])
    for lo, hi in zip(loops, loops[1:]):
        for k in range(6):
            bm.faces.new((lo[k], lo[(k + 1) % 6], hi[(k + 1) % 6], hi[k]))
    bm.faces.new(list(reversed(loops[0])))
    bm.faces.new(loops[-1])
    bm.normal_update()
    return bm


# --------------------------------------------------------------------------
# Booleans
# --------------------------------------------------------------------------

def apply_booleans(context, obj, steps, hole_tolerant=False):
    """Apply a list of (operation, cutter_object) booleans to ``obj``'s mesh
    with the Exact solver, in one evaluation."""
    mods = []
    for i, (operation, cutter) in enumerate(steps):
        mod = obj.modifiers.new(name="PS_Boolean_%d" % i, type='BOOLEAN')
        mod.operation = operation
        mod.object = cutter
        mod.solver = 'EXACT'
        if hasattr(mod, "use_hole_tolerant"):
            mod.use_hole_tolerant = hole_tolerant
        mods.append(mod)
    depsgraph = context.evaluated_depsgraph_get()
    depsgraph.update()
    new_mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
    for mod in mods:
        obj.modifiers.remove(mod)
    old = obj.data
    new_mesh.name = old.name
    obj.data = new_mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return obj


def cap_by_bisect(bm_world, frame, keep_positive, eps):
    """Cut a world-space BMesh in place, keeping one side, and fill the cut
    with flat faces. Works on meshes that are not watertight enough for the
    Exact boolean."""
    geom = bm_world.verts[:] + bm_world.edges[:] + bm_world.faces[:]
    res = bmesh.ops.bisect_plane(
        bm_world, geom=geom, dist=eps, plane_co=frame.origin, plane_no=frame.n,
        clear_inner=keep_positive, clear_outer=not keep_positive)
    cut_edges = [e for e in res["geom_cut"]
                 if isinstance(e, bmesh.types.BMEdge) and e.is_valid and e.is_boundary]
    if not cut_edges:
        return 0
    outward = -frame.n if keep_positive else frame.n
    filled = bmesh.ops.triangle_fill(bm_world, use_beauty=True, use_dissolve=True,
                                     edges=cut_edges, normal=outward)
    faces = [f for f in filled["geom"] if isinstance(f, bmesh.types.BMFace)]
    for f in faces:
        f.normal_update()
        if f.normal.dot(outward) < 0.0:
            f.normal_flip()
    return len(faces)


def mesh_volume(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    vol = bm.calc_volume(signed=True)
    bm.free()
    return vol
