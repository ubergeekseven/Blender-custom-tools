"""What joins two split pieces: pins, magnet pockets or screws.

Pins and magnets cut the same hole into both pieces, centred on the cut.
Screws are one-sided: piece A gets a clearance hole running out to its outer
surface with a counterbore for the head, piece B a hole for a heat-set
insert or for the screw to tap into.
"""

import math

from mathutils import Matrix

from . import geometry as geo
from .units import mm_to_bu

# Typical metric sizes in mm: clearance hole (ISO 273 medium), socket head
# diameter and height, pilot hole for tapping into plastic, and the hole for
# a common short brass heat-set insert. Inserts vary: check their datasheet.
SCREWS = {
    'M2': {"clear": 2.4, "head_d": 3.8, "head_h": 2.0, "pilot": 1.6, "insert_d": 3.2,
           "insert_len": 4.0},
    'M2.5': {"clear": 2.9, "head_d": 4.5, "head_h": 2.5, "pilot": 2.0, "insert_d": 3.6,
             "insert_len": 4.5},
    'M3': {"clear": 3.4, "head_d": 5.5, "head_h": 3.0, "pilot": 2.5, "insert_d": 4.0,
           "insert_len": 5.7},
    'M4': {"clear": 4.5, "head_d": 7.0, "head_h": 4.0, "pilot": 3.3, "insert_d": 5.6,
           "insert_len": 8.1},
    'M5': {"clear": 5.5, "head_d": 8.5, "head_h": 5.0, "pilot": 4.2, "insert_d": 6.4,
           "insert_len": 9.5},
}
SCREW_LENGTHS = (4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 25, 30, 35, 40, 45, 50)


def apply_screw_defaults(s):
    """Fill the screw fields from the table for the chosen size."""
    t = SCREWS[s.screw_size]
    s.screw_clearance = t["clear"]
    s.screw_head_d = t["head_d"] + 0.4
    s.screw_anchor_d = t["insert_d"] if s.screw_anchor == 'INSERT' else t["pilot"]
    s.screw_anchor_depth = t["insert_len"] + 1.0 if s.screw_anchor == 'INSERT' else 8.0


def connector_dims(context):
    """(radius, depth per side) in scene units: the space a connector needs
    round its centre, for previews and Auto Place."""
    s = context.scene.print_splitter
    mm = mm_to_bu(context)
    if s.connector == 'MAGNETS':
        return ((s.magnet_diameter + s.magnet_clearance) * 0.5 * mm,
                (s.magnet_thickness + s.magnet_depth_extra) * mm)
    if s.connector == 'SCREWS':
        return (max(s.screw_anchor_d, s.screw_clearance) * 0.5 * mm,
                s.screw_anchor_depth * mm)
    return ((s.pin_diameter + s.hole_clearance) * 0.5 * mm,
            (s.pin_length * 0.5 + s.hole_extra_depth) * mm)


def connector_size_mm(s):
    """Hole diameter recorded on pieces, for the scaled-after-cut warning."""
    if s.connector == 'MAGNETS':
        return s.magnet_diameter + s.magnet_clearance
    if s.connector == 'SCREWS':
        return s.screw_anchor_d
    return s.pin_diameter + s.hole_clearance


def _cyl(radius, z0, z1, segs):
    """(mesh, local matrix) for a cylinder along the frame normal from z0 to
    z1 (signed distances from the cut plane)."""
    half = (z1 - z0) * 0.5
    me = geo.cylinder_mesh("PS_hole", radius, half, segs)
    return me, Matrix.Translation((0.0, 0.0, (z0 + z1) * 0.5))


def cutters(context, frame, centers, bvh):
    """Holes for each piece: (for A, for B, notes). Each hole is (mesh, world
    matrix). ``bvh`` is the uncut object in world space, used to find where
    a screw hole leaves piece A's outer surface."""
    s = context.scene.print_splitter
    mm = mm_to_bu(context)
    segs = s.hole_segments
    for_a, for_b, notes = [], [], []
    eps = 0.05 * mm
    basis = frame.rot.to_4x4()

    def place(me_m, c, flip=False):
        me, local = me_m
        m = Matrix.Translation(c) @ basis
        if flip:
            m = m @ Matrix.Rotation(math.pi, 4, 'X')
        return me, m @ local

    if s.connector in ('PINS', 'MAGNETS'):
        radius, depth = connector_dims(context)
        for c in centers:
            for target in (for_a, for_b):
                target.append(place(_cyl(radius, -depth, depth, segs), c))
        return for_a, for_b, notes

    # Screws: the head goes in from piece A's outer surface unless flipped.
    head_side_b = s.screw_from_b
    floor = s.screw_floor * mm
    longest = 0.0
    for i, c in enumerate(centers, start=1):
        n = -frame.n if head_side_b else frame.n
        hit = bvh.ray_cast(c + n * eps, n)
        if hit[0] is None:
            notes.append("screw %d: no outer surface found above it" % i)
            continue
        exit_d = (hit[0] - c).length
        if exit_d < floor + s.screw_head_d * 0.5 * mm:
            notes.append("screw %d: only %.1f mm of material for the head"
                         % (i, exit_d / mm))
        clear = _cyl(s.screw_clearance * 0.5 * mm, -eps, exit_d + eps * 20, segs)
        bore = _cyl(s.screw_head_d * 0.5 * mm, min(floor, exit_d), exit_d + eps * 20, segs)
        anchor = _cyl(s.screw_anchor_d * 0.5 * mm, -s.screw_anchor_depth * mm, eps, segs)
        head_list, anchor_list = (for_b, for_a) if head_side_b else (for_a, for_b)
        head_list.append(place(clear, c, head_side_b))
        head_list.append(place(bore, c, head_side_b))
        anchor_list.append(place(anchor, c, head_side_b))
        longest = max(longest, min(floor, exit_d))
    if centers and len(notes) < len(centers):
        reach = longest / mm + s.screw_anchor_depth - 1.0
        fits = [L for L in SCREW_LENGTHS if L <= reach]
        if fits:
            notes.insert(0, "use %s x %d mm screws" % (s.screw_size, fits[-1]))
        else:
            notes.insert(0, "screw holes too shallow for %s screws" % s.screw_size)
    return for_a, for_b, notes
