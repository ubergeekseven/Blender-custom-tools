"""Procedural head proxy sized from three tape/caliper measurements.

The measurements follow the usual anthropometric definitions:

* width  - maximum breadth of the head above the ears (ears not included)
* length - glabella (between the eyebrows) to the back of the head (nose not
           included)
* height - chin to the top of the head

The head is built so its skull matches those numbers exactly; the nose and
ears are added on top, as on a real head. It faces -Y (Blender's front view)
with Z up and its origin at the centre of the measured box.
"""

import math

import bmesh

# Shape tables: (height h from -1 chin to +1 crown, value relative to the
# half-width a or half-length b). Linear interpolation between rows.
_WIDTH = [(-1.0, 0.0), (-0.97, 0.22), (-0.9, 0.42), (-0.75, 0.70), (-0.55, 0.82),
          (-0.3, 0.92), (-0.05, 0.97), (0.15, 1.0)]
_FRONT = [(-1.0, 0.0), (-0.97, 0.55), (-0.9, 0.86), (-0.75, 0.84), (-0.55, 0.90),
          (-0.3, 0.93), (-0.1, 0.95), (0.05, 1.0), (0.15, 1.0)]
_BACK = [(-1.0, 0.0), (-0.95, 0.20), (-0.8, 0.45), (-0.6, 0.62), (-0.4, 0.82),
         (-0.2, 0.95), (0.0, 1.0), (0.15, 1.0)]
_DOME_START = 0.15


def _interp(table, h):
    if h <= table[0][0]:
        return table[0][1]
    for (h0, v0), (h1, v1) in zip(table, table[1:]):
        if h <= h1:
            t = (h - h0) / (h1 - h0)
            return v0 + (v1 - v0) * t
    return table[-1][1]


def _profile(table, h):
    if h <= _DOME_START:
        return _interp(table, h)
    # Elliptical dome from the widest point up to the crown.
    t = (h - _DOME_START) / (1.0 - _DOME_START)
    return table[-1][1] * math.sqrt(max(0.0, 1.0 - t * t))


def _gauss(x, s):
    return math.exp(-(x / s) ** 2)


def _smooth(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


def _point(a, b, c, h, theta):
    """Surface point for height ``h`` in [-1, 1] and angle ``theta`` around
    the vertical axis (0 = +X, -pi/2 = front)."""
    w = a * _profile(_WIDTH, h)
    f = b * _profile(_FRONT, h)
    k = b * _profile(_BACK, h)
    ct, st = math.cos(theta), math.sin(theta)
    p = 2.0 / 2.4  # superellipse exponent: slightly boxier than an ellipse
    x = w * math.copysign(abs(ct) ** p, ct)
    depth = f if st < 0.0 else k
    y = depth * math.copysign(abs(st) ** p, st)
    z = c * h

    xn = x / a if a else 0.0
    front = max(0.0, -st) ** 4

    # Nose: grows from the bridge to the tip, then tucks under.
    if -0.45 < h < 0.05 and st < 0.0:
        if h > -0.34:
            prof = 0.15 + 0.85 * _smooth(0.05, -0.34, h)
        else:
            prof = 1.0 - _smooth(-0.34, -0.45, h)
        width = 0.06 + 0.08 * _smooth(0.05, -0.34, h)
        y -= 0.11 * 2.0 * b * prof * _gauss(xn, width) * front
    # Eye sockets, brow ridge, cheekbones, lips, chin.
    y += 0.06 * b * _gauss(abs(xn) - 0.33, 0.13) * _gauss(h + 0.03, 0.09) * front
    y -= 0.02 * b * _gauss(abs(xn) - 0.30, 0.25) * _gauss(h - 0.09, 0.05) * front
    y -= 0.03 * b * _gauss(xn, 0.20) * _gauss(h + 0.57, 0.06) * front
    y -= 0.03 * b * _gauss(xn, 0.22) * _gauss(h + 0.86, 0.06) * front
    x += math.copysign(0.03 * a * _gauss(abs(xn) - 0.70, 0.15) * _gauss(h + 0.22, 0.10)
                       * front, x)
    # Ears: just behind the middle, centred a little below eye level.
    side = abs(ct) ** 6
    if side > 1e-4:
        ear = 0.12 * a * _gauss(h + 0.12, 0.17) * _gauss(st - 0.12, 0.18) * side
        x += math.copysign(ear, x)
    return x, y, z


def head_bmesh(width, length, height, rings=72, segments=96):
    """Closed, manifold head mesh. Dimensions are full sizes in scene units."""
    a, b, c = width * 0.5, length * 0.5, height * 0.5
    bm = bmesh.new()
    bottom = bm.verts.new((0.0, 0.0, -c))
    top = bm.verts.new((0.0, 0.0, c))
    grid = []
    for i in range(1, rings):
        phi = -math.pi / 2.0 + math.pi * i / rings
        h = math.sin(phi)
        row = []
        for j in range(segments):
            theta = 2.0 * math.pi * j / segments
            row.append(bm.verts.new(_point(a, b, c, h, theta)))
        grid.append(row)
    n = segments
    first, last = grid[0], grid[-1]
    for j in range(n):
        bm.faces.new((bottom, first[(j + 1) % n], first[j]))
        bm.faces.new((top, last[j], last[(j + 1) % n]))
    for lo, hi in zip(grid, grid[1:]):
        for j in range(n):
            bm.faces.new((lo[j], lo[(j + 1) % n], hi[(j + 1) % n], hi[j]))
    bm.normal_update()
    return bm


def head_circumference(width, length):
    """Ramanujan's ellipse perimeter for the head's widest horizontal slice.
    Close to a tape measured head circumference (a real head measures a few
    percent more) and a handy check that the three numbers are right."""
    a, b = width * 0.5, length * 0.5
    return math.pi * (3.0 * (a + b) - math.sqrt((3.0 * a + b) * (a + 3.0 * b)))
