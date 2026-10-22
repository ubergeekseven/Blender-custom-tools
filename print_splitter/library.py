"""Real-world reference objects generated from their published dimensions.

Every entry is built from numbers, not downloaded models: the ISO ID-1
card, paper sizes, coins, batteries, LEDs, development boards, disc magnets
and miniature bases. Sizes are in millimetres. Entries marked (approx.) vary
between makers: check them against the actual part.
"""

import math

import bmesh
from mathutils import Matrix

from . import body

# --------------------------------------------------------------------------
# Builders (sizes in mm; scaled to scene units afterwards)
# --------------------------------------------------------------------------


def _box(bm, x, y, z, cx=0.0, cy=0.0, z0=0.0):
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((cx, cy, z0 + z / 2))
                          @ Matrix.Diagonal((x, y, z, 1.0)))


def _cyl(bm, r, h, z0=0.0, segs=64, r2=None, cx=0.0, cy=0.0):
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r,
                          radius2=r if r2 is None else r2, depth=h,
                          matrix=Matrix.Translation((cx, cy, z0 + h / 2)))


def _rounded_plate(bm, w, h, t, r, segs=8):
    """Flat plate with rounded corners, centred, from Z = 0 to t."""
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
                       (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for k in range(segs + 1):
            a = math.radians(a0 + 90.0 * k / segs)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    bottom = [bm.verts.new((x, y, 0.0)) for x, y in pts]
    face = bm.faces.new(bottom[::-1])
    ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    for v in ext["geom"]:
        if isinstance(v, bmesh.types.BMVert):
            v.co.z = t


def card(bm):
    _rounded_plate(bm, 85.60, 53.98, 0.76, 3.18)
    return {"Corner 1": (-42.8, 26.99, 0.76), "Corner 2": (42.8, 26.99, 0.76),
            "Corner 3": (42.8, -26.99, 0.76), "Corner 4": (-42.8, -26.99, 0.76)}


def paper(w, h):
    def build(bm):
        _box(bm, w, h, 0.1)
        return {"Corner 1": (-w / 2, h / 2, 0.1), "Corner 2": (w / 2, h / 2, 0.1),
                "Corner 3": (w / 2, -h / 2, 0.1), "Corner 4": (-w / 2, -h / 2, 0.1)}
    return build


def ruler(length):
    def build(bm):
        _box(bm, length + 10.0, 25.0, 1.5, cx=length / 2)
        for mm in range(int(length) + 1):
            tick = 7.0 if mm % 10 == 0 else 5.0 if mm % 5 == 0 else 3.0
            _box(bm, 0.2, tick, 0.2, cx=mm, cy=12.5 - tick / 2 - 0.5, z0=1.5)
        marks = {"0 mm": (0.0, 12.0, 1.7), "%d mm" % length: (length, 12.0, 1.7)}
        if length > 100:
            marks["100 mm"] = (100.0, 12.0, 1.7)
        return marks
    return build


def coin(diameter, thickness, sides=0):
    def build(bm):
        if sides:  # polygonal coin: diameter is across the corners
            _cyl(bm, diameter / 2, thickness, segs=sides)
        else:
            _cyl(bm, diameter / 2, thickness)
        r = diameter / 2
        return {"Edge left": (-r, 0.0, thickness), "Edge right": (r, 0.0, thickness)}
    return build


def cell(diameter, length, nub_d=0.0, nub_h=0.0):
    """Cylindrical battery standing on its negative end."""
    def build(bm):
        _cyl(bm, diameter / 2, length - nub_h)
        if nub_h:
            _cyl(bm, nub_d / 2, nub_h + 0.2, z0=length - nub_h - 0.2, segs=32)
        return {"- end": (0.0, 0.0, 0.0), "+ end": (0.0, 0.0, length)}
    return build


def nine_volt(bm):
    _box(bm, 26.5, 17.5, 46.4)
    _cyl(bm, 3.0, 2.3, z0=46.2, cx=-6.35, segs=32)
    _cyl(bm, 4.0, 2.3, z0=46.2, cx=6.35, segs=6)
    return {"Bottom": (0.0, 0.0, 0.0), "Top": (0.0, 0.0, 48.5),
            "Side left": (-13.25, 0.0, 23.0), "Side right": (13.25, 0.0, 23.0)}


def led(diameter, height, flange_d):
    def build(bm):
        r = diameter / 2
        _cyl(bm, flange_d / 2, 1.0, segs=32)
        _cyl(bm, r, height - r, z0=0.8, segs=32)
        dome = bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=r)["verts"]
        for v in dome:
            v.co.z = max(v.co.z, 0.0) + height - r
        for x in (-1.27, 1.27):
            _box(bm, 0.5, 0.5, 20.0, cx=x, z0=-19.8)
        return {"Base": (0.0, 0.0, 0.0), "Top": (0.0, 0.0, height)}
    return build


def board(w, h, holes=(), hole_d=0.0, parts=6.0):
    """Board lying flat, corner at the origin, components on top."""
    def build(bm):
        _box(bm, w, h, 1.6, cx=w / 2, cy=h / 2)
        _box(bm, w * 0.6, h * 0.6, parts, cx=w / 2, cy=h / 2, z0=1.5)
        pts = {"Corner 1": (0.0, 0.0, 1.6), "Corner 2": (w, 0.0, 1.6),
               "Corner 3": (w, h, 1.6), "Corner 4": (0.0, h, 1.6)}
        for i, (x, y) in enumerate(holes, start=1):
            _cyl(bm, hole_d / 2 + 0.6, 0.2, z0=1.55, cx=x, cy=y, segs=24)  # pad
            pts["Hole %d" % i] = (x, y, 1.6)
        return pts
    return build


def magnet(diameter, thickness):
    def build(bm):
        _cyl(bm, diameter / 2, thickness)
        return {"Edge left": (-diameter / 2, 0.0, thickness),
                "Edge right": (diameter / 2, 0.0, thickness)}
    return build


def base(diameter, height=4.0):
    def build(bm):
        _cyl(bm, diameter / 2, height, r2=diameter / 2 - 1.0)
        return {"Edge left": (-diameter / 2, 0.0, 0.0), "Edge right": (diameter / 2, 0.0, 0.0)}
    return build


def miniature(figure_height, base_d):
    def build(bm):
        pts = base(base_d)(bm)
        fig, _fig_pts = body.figure(figure_height)
        fig.transform(Matrix.Translation((0.0, 0.0, 4.0)))  # stand on the base
        _merge(bm, fig)
        pts["Top of head"] = (0.0, 0.0, figure_height + 4.0)
        return pts
    return build


def _merge(bm, other):
    """Copy every face of ``other`` into ``bm``."""
    vmap = {v: bm.verts.new(v.co) for v in other.verts}
    for f in other.faces:
        bm.faces.new([vmap[v] for v in f.verts])
    other.free()


# --------------------------------------------------------------------------
# Catalogue: id -> (name, note, builder)
# --------------------------------------------------------------------------

CATALOGUE = {
    # Cards & paper
    'CARD': ("Bank / ID card", "85.60 x 53.98 x 0.76 mm (ISO ID-1)", card),
    'A4': ("A4 paper", "210 x 297 mm", paper(210.0, 297.0)),
    'A5': ("A5 paper", "148 x 210 mm", paper(148.0, 210.0)),
    'LETTER': ("US Letter paper", "215.9 x 279.4 mm", paper(215.9, 279.4)),
    'RULER150': ("Ruler 150 mm", "1 mm ticks", ruler(150)),
    'RULER300': ("Ruler 300 mm", "1 mm ticks", ruler(300)),
    # Coins
    'US_QUARTER': ("US quarter", "24.26 mm across, 1.75 thick", coin(24.26, 1.75)),
    'US_PENNY': ("US penny", "19.05 mm across, 1.52 thick", coin(19.05, 1.52)),
    'EUR1': ("1 euro", "23.25 mm across, 2.33 thick", coin(23.25, 2.33)),
    'EUR2': ("2 euro", "25.75 mm across, 2.20 thick", coin(25.75, 2.20)),
    'GBP1': ("UK 1 pound", "12-sided, 23.43 mm across corners, 2.8 thick",
             coin(23.43, 2.8, sides=12)),
    # Batteries
    'AA': ("AA battery", "14.5 x 50.5 mm", cell(14.5, 50.5, 5.5, 1.0)),
    'AAA': ("AAA battery", "10.5 x 44.5 mm", cell(10.5, 44.5, 3.8, 0.8)),
    'C': ("C battery", "26.2 x 50 mm", cell(26.2, 50.0, 7.5, 1.5)),
    'D': ("D battery", "34.2 x 61.5 mm", cell(34.2, 61.5, 9.5, 1.5)),
    '9V': ("9 V battery", "26.5 x 17.5 x 48.5 mm", nine_volt),
    '18650': ("18650 cell", "18.4 x 65.2 mm (flat top)", cell(18.4, 65.2)),
    '21700': ("21700 cell", "21.1 x 70.2 mm (flat top)", cell(21.1, 70.2)),
    'CR2032': ("CR2032 coin cell", "20 x 3.2 mm", cell(20.0, 3.2)),
    'CR2025': ("CR2025 coin cell", "20 x 2.5 mm", cell(20.0, 2.5)),
    'CR2016': ("CR2016 coin cell", "20 x 1.6 mm", cell(20.0, 1.6)),
    'LR44': ("LR44 button cell", "11.6 x 5.4 mm", cell(11.6, 5.4)),
    # LEDs
    'LED5': ("5 mm LED", "5 mm body, 5.8 mm flange, 8.6 mm tall", led(5.0, 8.6, 5.8)),
    'LED3': ("3 mm LED", "3 mm body, 3.8 mm flange, 5.3 mm tall", led(3.0, 5.3, 3.8)),
    # Boards
    'UNO': ("Arduino Uno", "68.6 x 53.4 mm, 3.2 mm holes",
            board(68.6, 53.4, ((13.97, 2.54), (15.24, 50.8), (66.04, 7.62), (66.04, 35.56)),
                  3.2, 12.0)),
    'NANO': ("Arduino Nano (approx.)", "18 x 45 mm", board(18.0, 45.0, (), 0.0, 6.0)),
    'PICO': ("Raspberry Pi Pico", "21 x 51 mm, 2.1 mm holes",
             board(21.0, 51.0, ((4.8, 2.0), (16.2, 2.0), (4.8, 49.0), (16.2, 49.0)), 2.1, 3.0)),
    'ESP32': ("ESP32 DevKitC (approx.)", "28 x 55 mm", board(28.0, 55.0, (), 0.0, 5.0)),
    'PI4': ("Raspberry Pi 4 / 5", "85 x 56 mm, 2.7 mm holes",
            board(85.0, 56.0, ((3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)), 2.7, 15.0)),
    'PIZERO': ("Raspberry Pi Zero", "65 x 30 mm, 2.75 mm holes",
               board(65.0, 30.0, ((3.5, 3.5), (61.5, 3.5), (3.5, 26.5), (61.5, 26.5)),
                     2.75, 4.0)),
    # Magnets
    **{'MAG_%dx%d' % (d, t): ("Disc magnet %d x %d mm" % (d, t), "%d mm across, %d thick" % (d, t),
                              magnet(float(d), float(t)))
       for d, t in ((6, 2), (6, 3), (8, 2), (8, 3), (10, 2), (10, 3), (12, 3), (15, 3),
                    (20, 3), (20, 5))},
    # Miniatures
    **{'BASE_%d' % d: ("Miniature base %d mm" % d, "%d mm round, 4 mm tall" % d, base(float(d)))
       for d in (25, 28, 32, 40, 50, 60)},
    'MINI28': ("28 mm scale figure", "About 30 mm to the top of the head, on a 25 mm base",
               miniature(30.0, 25.0)),
    'MINI32': ("32 mm scale figure", "About 34 mm to the top of the head, on a 32 mm base",
               miniature(34.0, 32.0)),
}

_GROUPS = (
    ("Cards, paper and rulers", ('CARD', 'A4', 'A5', 'LETTER', 'RULER150', 'RULER300')),
    ("Coins", ('US_QUARTER', 'US_PENNY', 'EUR1', 'EUR2', 'GBP1')),
    ("Batteries", ('AA', 'AAA', 'C', 'D', '9V', '18650', '21700', 'CR2032', 'CR2025',
                   'CR2016', 'LR44')),
    ("LEDs and boards", ('LED5', 'LED3', 'UNO', 'NANO', 'PICO', 'ESP32', 'PI4', 'PIZERO')),
    ("Magnets", tuple(k for k in CATALOGUE if k.startswith('MAG_'))),
    ("Miniatures", tuple(k for k in CATALOGUE if k.startswith('BASE_')) + ('MINI28', 'MINI32')),
)


def enum_items():
    items = []
    for title, keys in _GROUPS:
        items.append(("", title, ""))
        for k in keys:
            name, note, _b = CATALOGUE[k]
            items.append((k, name, note))
    return items


def build(key, scale):
    """(bmesh, points) for a catalogue entry, scaled from mm to scene units."""
    _name, _note, builder = CATALOGUE[key]
    bm = bmesh.new()
    pts = builder(bm)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.transform(Matrix.Scale(scale, 4))
    bm.normal_update()
    return bm, {k: tuple(c * scale for c in v) for k, v in pts.items()}
