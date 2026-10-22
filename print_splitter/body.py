"""Body part references built from a few tape measurements.

Each builder takes sizes in scene units and returns (bmesh, points), where
points maps a name to an (x, y, z) position. The bodies face -Y with Z up,
so their left is +X. Shapes are simple: they are for sizing and checking
clearance, not for looking at.
"""

import math

import bmesh
from mathutils import Matrix, Vector


# --------------------------------------------------------------------------
# Shape helpers
# --------------------------------------------------------------------------

def ellipse_perimeter(a, b):
    return math.pi * (3.0 * (a + b) - math.sqrt((3.0 * a + b) * (a + 3.0 * b)))


def ellipse_from_circumference(circ, aspect):
    """Semi-axes (wide, narrow) of an ellipse with this perimeter and
    width/depth ratio."""
    unit = ellipse_perimeter(1.0, 1.0 / aspect)
    a = circ / unit
    return a, a / aspect


def _ring(cx, cy, rx, ry, segs, power=2.0):
    """Points round a superellipse (power 2 is an ellipse)."""
    e = 2.0 / power
    pts = []
    for k in range(segs):
        t = 2.0 * math.pi * k / segs
        c, s = math.cos(t), math.sin(t)
        pts.append((cx + rx * math.copysign(abs(c) ** e, c),
                    cy + ry * math.copysign(abs(s) ** e, s)))
    return pts


def loft(bm, sections, segs=32, power=2.0, axis='Z'):
    """Closed tube through cross-sections (pos, rx, ry, cx, cy) along an axis,
    capped at both ends. Along Y, the section's x is X and its y is Z.
    Call _finish() on the bmesh afterwards to fix the face winding."""
    rings = []
    for pos, rx, ry, cx, cy in sections:
        ring = []
        for u, v in _ring(cx, cy, rx, ry, segs, power):
            co = (u, v, pos) if axis == 'Z' else (u, pos, v)
            ring.append(bm.verts.new(co))
        rings.append(ring)
    # Winding is fixed afterwards by _finish(), which points every closed
    # shell outward.
    for lo, hi in zip(rings, rings[1:]):
        for k in range(segs):
            bm.faces.new((lo[k], lo[(k + 1) % segs], hi[(k + 1) % segs], hi[k]))
    caps = [bm.faces.new(rings[0][::-1]), bm.faces.new(rings[-1])]
    bmesh.ops.triangulate(bm, faces=caps)
    return rings


def capsule(bm, p0, p1, r0, r1, segs=20):
    """Tapered capsule from p0 (radius r0) to p1 (radius r1)."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    length = d.length
    geom = bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=segs // 2 + 2,
                                     radius=1.0)
    verts = geom["verts"]
    rot = Vector((0.0, 0.0, 1.0)).rotation_difference(d.normalized()).to_matrix() \
        if length > 0.0 else Matrix.Identity(3)
    for v in verts:
        x, y, z = v.co
        if z >= 0.0:  # top half becomes the p1 end
            v.co = Vector((x * r1, y * r1, z * r1 + length))
        else:
            v.co = Vector((x * r0, y * r0, z * r0))
        v.co = rot @ v.co + p0
    return verts


def cylinder(bm, radius, depth, segs=48, z0=0.0, rx=None):
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=radius,
                          radius2=radius, depth=depth,
                          matrix=Matrix.Translation((0.0, 0.0, z0 + depth * 0.5)))
    if rx is not None:
        for v in bm.verts:
            v.co.x *= rx / radius


def _finish(bm):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.normal_update()
    return bm


# --------------------------------------------------------------------------
# Parts
# --------------------------------------------------------------------------

def hand(length, breadth, right=True):
    """Open hand, fingers up (+Z), palm facing -Y, wrist at the origin."""
    L, B = length, breadth
    sx = 1.0 if right else -1.0  # thumb toward the hand's own inside
    bm = bmesh.new()
    loft(bm, [(-0.15 * L, 0.33 * B, 0.17 * B, 0, 0), (0.0, 0.36 * B, 0.17 * B, 0, 0),
              (0.25 * L, 0.48 * B, 0.16 * B, 0, 0), (0.5 * L, 0.5 * B, 0.14 * B, 0, 0),
              (0.56 * L, 0.46 * B, 0.12 * B, 0, 0)], segs=32, power=3.0)
    r = B / 9.5
    fingers = {"Index": (0.375, 0.53, 0.43), "Middle": (0.125, 0.55, 0.45),
               "Ring": (-0.125, 0.54, 0.44), "Little": (-0.375, 0.50, 0.35)}
    pts = {"Wrist": (0.0, 0.0, 0.0)}
    for name, (fx, base, flen) in fingers.items():
        x = sx * fx * B
        rr = r * (0.85 if name == "Little" else 1.0)
        capsule(bm, (x, 0.0, base * L - rr), (x, 0.0, (base + flen) * L - 0.8 * rr),
                rr, 0.8 * rr)
        pts["%s tip" % name] = (x, 0.0, (base + flen) * L)
    t0 = (sx * 0.38 * B, -0.06 * B, 0.12 * L)
    t1 = (sx * 0.78 * B, -0.16 * B, 0.42 * L)
    capsule(bm, t0, t1, 1.25 * r, 1.05 * r)
    d = (Vector(t1) - Vector(t0)).normalized()
    pts["Thumb tip"] = tuple(Vector(t1) + d * 1.05 * r)
    return _finish(bm), pts


def grip(diameter, length):
    """Upright cylinder of a comfortable grip diameter."""
    bm = bmesh.new()
    cylinder(bm, diameter * 0.5, length)
    return _finish(bm), {"Bottom": (0.0, 0.0, 0.0), "Top": (0.0, 0.0, length)}


def forearm(wrist_circ, forearm_circ, length):
    """Forearm along +Z from the wrist (origin) to the elbow."""
    wa, wb = ellipse_from_circumference(wrist_circ, 1.45)
    fa, fb = ellipse_from_circumference(forearm_circ, 1.25)
    ea, eb = ellipse_from_circumference(forearm_circ * 0.92, 1.2)
    bm = bmesh.new()
    loft(bm, [(-0.08 * length, wa * 1.05, wb * 1.05, 0, 0), (0.0, wa, wb, 0, 0),
              (0.35 * length, (wa + fa) * 0.5 * 1.05, (wb + fb) * 0.5, 0, 0),
              (0.65 * length, fa, fb, 0, 0), (length, ea, eb, 0, 0),
              (1.08 * length, ea, eb, 0, 0)], segs=48)
    pts = {"Wrist": (0.0, 0.0, 0.0), "Elbow": (0.0, 0.0, length),
           "Wrist outside": (wa, 0.0, 0.0), "Forearm outside": (fa, 0.0, 0.65 * length)}
    return _finish(bm), pts


def ring_size_to_diameter(system, size):
    """Inside diameter in mm for a ring size."""
    if system == 'US':  # US/Canada: size 0 = 11.63 mm, +0.8128 mm per size
        return 11.63 + 0.8128 * size
    if system == 'EU':  # ISO 8653: the inside circumference in mm
        return size / math.pi
    return size  # already a diameter


def finger(diameter, length):
    """Finger as an upright cylinder with a rounded tip."""
    bm = bmesh.new()
    r = diameter * 0.5
    capsule(bm, (0.0, 0.0, 0.0), (0.0, 0.0, length - r), r, r, segs=32)
    return _finish(bm), {"Base": (0.0, 0.0, 0.0), "Tip": (0.0, 0.0, length)}


def foot(length, width, right=True):
    """Foot standing on Z = 0, heel at the origin, toes toward -Y."""
    L, W = length, width
    sx = 1.0 if right else -1.0  # big toe on the foot's inside
    half = [(0.0, 0.05), (0.03, 0.26), (0.1, 0.33), (0.3, 0.36), (0.55, 0.45),
            (0.72, 0.5), (0.85, 0.46), (0.95, 0.33), (1.0, 0.08)]
    high = [(0.0, 0.06), (0.03, 0.14), (0.15, 0.26), (0.35, 0.2), (0.55, 0.14),
            (0.72, 0.1), (0.9, 0.07), (1.0, 0.04)]

    def interp(table, t):
        for (t0, v0), (t1, v1) in zip(table, table[1:]):
            if t <= t1:
                return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
        return table[-1][1]

    sections = []
    for i in range(25):
        t = i / 24.0
        hw = interp(half, t) * W
        hh = interp(high, t) * L * 0.5
        cx = sx * 0.12 * W * max(0.0, (t - 0.7) / 0.3)
        sections.append((-t * L, hw, hh, cx, hh))
    bm = bmesh.new()
    loft(bm, sections, segs=32, power=2.6, axis='Y')
    aa, ab = 0.3 * W, 0.27 * W
    loft(bm, [(0.08 * L, aa, ab, 0.0, -0.17 * L), (0.45 * L, aa * 0.95, ab * 0.95, 0.0, -0.17 * L)],
         segs=32)
    pts = {"Heel": (0.0, 0.0, 0.05 * L), "Toe tip": (sx * 0.12 * W, -L, 0.03 * L),
           "Ball inside": (sx * 0.5 * W, -0.72 * L, 0.04 * L),
           "Ball outside": (-sx * 0.5 * W, -0.72 * L, 0.04 * L)}
    return _finish(bm), pts


def torso(chest_circ, waist_circ, shoulder_width, length, neck_circ):
    """Torso from the waist (origin) up to the neck, facing -Y."""
    ca, cb = ellipse_from_circumference(chest_circ, 1.3)
    wa, wb = ellipse_from_circumference(waist_circ, 1.35)
    na, nb = ellipse_from_circumference(neck_circ, 1.1)
    sw = shoulder_width * 0.5
    L = length
    bm = bmesh.new()
    loft(bm, [(-0.05 * L, wa * 1.03, wb * 1.03, 0, 0), (0.0, wa, wb, 0, 0),
              (0.3 * L, (wa + ca) * 0.5, (wb + cb) * 0.5, 0, 0), (0.62 * L, ca, cb, 0, 0),
              (0.8 * L, max(ca, sw * 0.85), cb * 0.95, 0, 0),
              (0.93 * L, sw * 0.9, cb * 0.7, 0, 0), (1.0 * L, na * 1.6, nb * 1.25, 0, 0),
              (1.04 * L, na, nb, 0, 0), (1.2 * L, na, nb, 0, 0)], segs=48, power=2.3)
    cap = 0.1 * shoulder_width
    for sx in (1.0, -1.0):
        capsule(bm, (sx * (sw - cap), 0.0, 0.88 * L), (sx * (sw - cap), 0.0, 0.9 * L), cap, cap)
    pts = {"Neck front": (0.0, -nb, 1.08 * L), "Neck back": (0.0, nb, 1.08 * L),
           "Left shoulder": (sw, 0.0, 0.9 * L), "Right shoulder": (-sw, 0.0, 0.9 * L),
           "Chest front": (0.0, -cb, 0.62 * L), "Waist front": (0.0, -wb, 0.0)}
    return _finish(bm), pts


def figure(height):
    """Standing person about 7.5 heads tall, feet on Z = 0."""
    H = height
    h = H / 7.5
    bm = bmesh.new()
    head = bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=16, radius=1.0)["verts"]
    for v in head:
        v.co = Vector((v.co.x * 0.33 * h, v.co.y * 0.4 * h, v.co.z * 0.5 * h + H - 0.5 * h))
    capsule(bm, (0, 0.03 * h, H - 1.25 * h), (0, 0.03 * h, H - 0.85 * h), 0.2 * h, 0.2 * h)
    loft(bm, [(H - 3.6 * h, 0.75 * h, 0.45 * h, 0, 0), (H - 3.0 * h, 0.62 * h, 0.4 * h, 0, 0),
              (H - 2.2 * h, 0.75 * h, 0.5 * h, 0, 0), (H - 1.5 * h, 0.9 * h, 0.4 * h, 0, 0),
              (H - 1.25 * h, 0.3 * h, 0.25 * h, 0, 0)], segs=24, power=2.4)
    pts = {"Top of head": (0.0, 0.0, H), "Chin": (0.0, -0.33 * h, H - h)}
    for side, sx in (("Left", 1.0), ("Right", -1.0)):
        hip, knee, ankle = (sx * 0.42 * h, 0, 0.52 * H), (sx * 0.4 * h, -0.05 * h, 0.28 * H), \
            (sx * 0.38 * h, 0, 0.045 * H)
        capsule(bm, hip, knee, 0.33 * h, 0.22 * h)
        capsule(bm, knee, ankle, 0.22 * h, 0.13 * h)
        capsule(bm, (sx * 0.38 * h, 0.1 * h, 0.12 * h), (sx * 0.4 * h, -0.85 * h, 0.12 * h),
                0.12 * h, 0.12 * h)  # foot, resting on Z = 0
        sh, el, wr = (sx * 0.95 * h, 0, H - 1.6 * h), (sx * 1.1 * h, 0.05 * h, 0.62 * H), \
            (sx * 1.15 * h, 0, 0.47 * H)
        capsule(bm, sh, el, 0.19 * h, 0.15 * h)
        capsule(bm, el, wr, 0.15 * h, 0.1 * h)
        capsule(bm, wr, (sx * 1.17 * h, 0, 0.39 * H), 0.11 * h, 0.08 * h)
        pts["%s shoulder" % side] = (sx * 1.13 * h, 0.0, H - 1.6 * h)
        pts["%s hand" % side] = (sx * 1.17 * h, 0.0, 0.38 * H)
        pts["%s heel" % side] = (sx * 0.38 * h, 0.22 * h, 0.0)
    return _finish(bm), pts
