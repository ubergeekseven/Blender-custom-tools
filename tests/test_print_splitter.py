"""Headless tests for the Print Splitter add-on.

Run with either
    blender -b --factory-startup --python tests/test_print_splitter.py
or, with the ``bpy`` module from PyPI installed,
    python tests/test_print_splitter.py
"""

import math
import os
import sys
import traceback

import bpy  # first: the PyPI bpy module provides bmesh/mathutils
import bmesh  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import print_splitter  # noqa: E402
from print_splitter import geometry as geo  # noqa: E402


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    try:
        print_splitter.unregister()
    except Exception:
        pass
    print_splitter.register()
    return bpy.context


def shell(name, outer, inner, segments=64, rings=32):
    """Closed hollow sphere: a stand-in for a helmet-style mask."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=outer)
    inner_bm = bmesh.new()
    bmesh.ops.create_uvsphere(inner_bm, u_segments=segments, v_segments=rings, radius=inner)
    bmesh.ops.reverse_faces(inner_bm, faces=inner_bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    tmp = bpy.data.meshes.new("tmp")
    inner_bm.to_mesh(tmp)
    bm.from_mesh(tmp)
    bm.to_mesh(me)
    bm.free()
    inner_bm.free()
    bpy.data.meshes.remove(tmp)
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def non_manifold_edges(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    n = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    return n


def world_z_range(obj):
    zs = [(obj.matrix_world @ v.co).z for v in obj.data.vertices]
    return min(zs), max(zs)


def box_centre(obj):
    """World position of the centre of the object's own bounding box."""
    lo = [min(v.co[i] for v in obj.data.vertices) for i in range(3)]
    hi = [max(v.co[i] for v in obj.data.vertices) for i in range(3)]
    return obj.matrix_world @ Matrix.Translation([(lo[i] + hi[i]) / 2
                                                  for i in range(3)]).to_translation()


def close(a, b, tol):
    assert abs(a - b) <= tol, "%r != %r (tol %r)" % (a, b, tol)


def setup_split(method):
    ctx = reset()
    s = ctx.scene.print_splitter
    obj = shell("Mask", 100.0, 88.0)
    ctx.view_layer.objects.active = obj
    obj.select_set(True)
    s.target = obj
    s.method = method
    s.pin_diameter = 5.0
    s.pin_length = 12.0
    s.pin_count = 4
    assert bpy.ops.print_splitter.add_cut_plane(axis='Z') == {'FINISHED'}
    plane = s.cut_plane
    # Tilt the plane so the cut isn't axis aligned.
    plane.matrix_world = Matrix.Translation((0, 0, 10)) @ \
        Matrix.Rotation(math.radians(20), 4, 'X')
    return ctx, s, obj, plane


def test_auto_place_pins():
    ctx, s, obj, plane = setup_split('BOOLEAN')
    assert bpy.ops.print_splitter.auto_place_pins() == {'FINISHED'}
    markers = [c for c in plane.children if c.get("ps_pin_marker")]
    assert len(markers) == 4, len(markers)
    frame = geo.PlaneFrame(plane.matrix_world)
    for m in markers:
        p = m.matrix_world.translation
        close((p - frame.origin).dot(frame.n), 0.0, 1e-4)
        # The cut through the shell is a ring; pins must sit in the wall.
        r = p.length
        assert 88.0 + 2.6 < r < 100.0 - 2.6, r
    pts = [m.matrix_world.translation for m in markers]
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            assert (pts[i] - pts[j]).length > 40.0, "pins bunched together"


def test_too_thin_for_pins():
    ctx, s, obj, plane = setup_split('BOOLEAN')
    s.pin_diameter = 12.0
    assert bpy.ops.print_splitter.auto_place_pins() == {'CANCELLED'}
    assert not [c for c in plane.children if c.get("ps_pin_marker")]


def _check_split(method):
    ctx, s, obj, plane = setup_split(method)
    vol_before = geo.mesh_volume(obj)
    bpy.ops.print_splitter.auto_place_pins()
    assert bpy.ops.print_splitter.split() == {'FINISHED'}
    a = bpy.data.objects["Mask_A"]
    b = bpy.data.objects["Mask_B"]
    assert obj.hide_get()
    for part in (a, b):
        assert non_manifold_edges(part) == 0, (method, part.name, non_manifold_edges(part))
        assert geo.mesh_volume(part) > 0.0
    hole_r = (s.pin_diameter + s.hole_clearance) / 2.0
    hole_depth = s.pin_length / 2.0 + s.hole_extra_depth
    holes = 4 * math.pi * hole_r ** 2 * hole_depth
    total = geo.mesh_volume(a) + geo.mesh_volume(b)
    close(total, vol_before - 2 * holes, vol_before * 0.002)
    pins = [o for o in bpy.data.objects if o.name.startswith("Mask_pin_")]
    assert len(pins) == 4
    for pin in pins:
        assert non_manifold_edges(pin) == 0
    # Pins lie flat: their lowest face is horizontal and they are no taller
    # than the hexagon's width across flats.
    pin = pins[0]
    lo, hi = world_z_range(pin)
    close(hi - lo, s.pin_diameter * math.cos(math.radians(30)), 1e-3)

    # Cut face down: part A's cut face ends on Z=0 and the part sits above it.
    for o in ctx.selected_objects:
        o.select_set(False)
    a.select_set(True)
    b.select_set(True)
    assert bpy.ops.print_splitter.cut_face_down() == {'FINISHED'}
    for part in (a, b):
        lo, _hi = world_z_range(part)
        close(lo, 0.0, 1e-4)
        n = sum(1 for v in part.data.vertices
                if abs((part.matrix_world @ v.co).z) < 1e-3)
        assert n > 20, (part.name, n)


def test_split_boolean():
    _check_split('BOOLEAN')


def test_split_bisect():
    _check_split('BISECT')


def test_second_cut_on_other_piece():
    ctx, s, obj, plane = setup_split('BOOLEAN')
    bpy.ops.print_splitter.auto_place_pins()
    bpy.ops.print_splitter.split()
    b = bpy.data.objects["Mask_B"]
    vol_b = geo.mesh_volume(b)
    # Click piece B, add a new plane at another angle and cut it again.
    for o in ctx.selected_objects:
        o.select_set(False)
    b.select_set(True)
    ctx.view_layer.objects.active = b
    assert bpy.ops.print_splitter.add_cut_plane(axis='X') == {'FINISHED'}
    assert s.target is b and s.cut_plane is not plane
    s.cut_plane.matrix_world = Matrix.Translation((20, 0, -30)) @ \
        Matrix.Rotation(math.radians(25), 4, 'Y') @ Matrix.Rotation(math.radians(90), 4, 'Y')
    s.pin_count = 2
    assert bpy.ops.print_splitter.auto_place_pins() == {'FINISHED'}
    assert bpy.ops.print_splitter.split() == {'FINISHED'}
    ba, bb = bpy.data.objects["Mask_B_A"], bpy.data.objects["Mask_B_B"]
    for part in (ba, bb):
        assert non_manifold_edges(part) == 0, part.name
    hole_r = (s.pin_diameter + s.hole_clearance) / 2.0
    hole_depth = s.pin_length / 2.0 + s.hole_extra_depth
    holes = 2 * math.pi * hole_r ** 2 * hole_depth
    close(geo.mesh_volume(ba) + geo.mesh_volume(bb), vol_b - 2 * holes, vol_b * 0.003)
    # The first cut's pins are untouched and piece A is still there.
    assert len([o for o in bpy.data.objects if o.name.startswith("Mask_pin_")]) == 4
    assert "Mask_A" in bpy.data.objects


def test_size_guards():
    ctx, s, obj, plane = setup_split('BOOLEAN')
    from print_splitter import sizing
    assert sizing.size_status(obj) == 'UNCONFIRMED'
    assert bpy.ops.print_splitter.confirm_size() == {'FINISHED'}
    assert sizing.size_status(obj) == 'OK'
    obj.scale = (1.1, 1.1, 1.1)
    bpy.context.view_layer.update()
    assert sizing.size_status(obj) == 'CHANGED'
    obj.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()
    assert sizing.size_status(obj) == 'OK'

    bpy.ops.print_splitter.auto_place_pins()
    bpy.ops.print_splitter.split()
    a = bpy.data.objects["Mask_A"]
    pins = [o for o in bpy.data.objects if o.name.startswith("Mask_pin_")]
    # Pieces of a confirmed object are confirmed too; rotating doesn't count
    # as resizing.
    assert sizing.size_status(a) == 'OK'
    for o in ctx.selected_objects:
        o.select_set(False)
    a.select_set(True)
    bpy.ops.print_splitter.cut_face_down()
    assert sizing.resized_after_cut(ctx.scene.objects) == []

    # "Select all, scale 80%": everything gets flagged, with the new sizes.
    for o in (a, bpy.data.objects["Mask_B"], *pins):
        o.matrix_world = Matrix.Scale(0.8, 4) @ o.matrix_world
    resized = dict(sizing.resized_after_cut(ctx.scene.objects))
    assert len(resized) == 2 + len(pins)
    close(resized[a], 0.8, 1e-4)
    close(a[sizing.HOLE_MM_KEY] * resized[a], 5.2 * 0.8, 1e-3)
    close(pins[0][sizing.PIN_MM_KEY] * resized[pins[0]], 4.0, 1e-3)

    # Applying the scale doesn't hide it.
    a.data.transform(Matrix.Diagonal((*a.matrix_world.to_scale(), 1.0)))
    loc, rot, _sc = a.matrix_world.decompose()
    a.matrix_world = Matrix.LocRotScale(loc, rot, None)
    assert a in dict(sizing.resized_after_cut(ctx.scene.objects))

    centre_before = box_centre(a)
    assert bpy.ops.print_splitter.restore_cut_size() == {'FINISHED'}
    assert sizing.resized_after_cut(ctx.scene.objects) == []
    centre_after = box_centre(a)
    assert (centre_after - centre_before).length < 1e-3


def _point_fit_scene(mask_matrix):
    ctx = reset()
    s = ctx.scene.print_splitter
    bpy.ops.print_splitter.add_head()
    head = s.reference
    for child in list(head.children):  # these tests place their own points
        bpy.data.objects.remove(child)
    mask = bpy.data.objects.new("Mask", head.data.copy())
    ctx.scene.collection.objects.link(mask)
    mask.matrix_world = mask_matrix
    s.item = mask
    return ctx, s, head, mask


def _add_pairs(ctx, head, mask, vert_ids, target='AUTO'):
    for i in vert_ids:
        for obj, role in ((mask, 'ITEM'), (head, 'REFERENCE')):
            ctx.scene.cursor.location = obj.matrix_world @ obj.data.vertices[i].co
            assert bpy.ops.print_splitter.add_point(
                target=role if target != 'AUTO' else 'AUTO') == {'FINISHED'}


SPOTS = (1, 2000, 3500, 5200)  # crown and three spots round the head


def test_point_fit_align():
    m = Matrix.Translation((300, 40, -20)) @ Matrix.Rotation(math.radians(25), 4, 'Z') \
        @ Matrix.Rotation(math.radians(10), 4, 'X') @ Matrix.Scale(1.25, 4)
    ctx, s, head, mask = _point_fit_scene(m)
    _add_pairs(ctx, head, mask, SPOTS)  # far apart, so Nearest picks right
    from print_splitter import landmarks
    assert len(landmarks.points(mask)) == 4 and len(landmarks.points(head)) == 4
    s.point_fit = 'ALIGN'
    assert bpy.ops.print_splitter.fit_to_points() == {'FINISHED'}
    for i in (0, 777, 4000):
        a = mask.matrix_world @ mask.data.vertices[i].co
        b = head.matrix_world @ head.data.vertices[i].co
        assert (a - b).length < 1e-3, (a - b).length


def test_point_fit_scale_only_and_move():
    m = Matrix.Translation((300, 0, 0)) @ Matrix.Scale(0.8, 4)
    ctx, s, head, mask = _point_fit_scene(m)
    _add_pairs(ctx, head, mask, SPOTS[:2], target='EXPLICIT')
    from print_splitter import landmarks
    mp, _hp = landmarks.pairs(mask, head)
    centre = Vector(mp.mean(0))
    s.point_fit = 'SCALE'
    assert bpy.ops.print_splitter.fit_to_points() == {'FINISHED'}
    close(mask.matrix_world.to_scale().x, 1.0, 1e-4)
    mp, hp = landmarks.pairs(mask, head)
    assert (Vector(mp.mean(0)) - centre).length < 1e-3  # stayed put

    mask.matrix_world = m
    s.point_fit = 'SCALE_MOVE'
    assert bpy.ops.print_splitter.fit_to_points() == {'FINISHED'}
    mp, hp = landmarks.pairs(mask, head)
    assert landmarks.rms_error(mp, hp) < 1e-3

    s.point_fit = 'ALIGN'  # needs 3 pairs
    try:
        bpy.ops.print_splitter.fit_to_points()
        raise AssertionError("should need 3 pairs")
    except RuntimeError as e:
        assert "at least 3" in str(e)
    assert bpy.ops.print_splitter.clear_points() == {'FINISHED'}
    assert not landmarks.points(mask) and not landmarks.points(head)


def _read_stl(path):
    import numpy as np
    with open(path, "rb") as f:
        data = f.read()
    n = int.from_bytes(data[80:84], "little")
    rec = np.frombuffer(data[84:84 + 50 * n], dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)),
                                                      ("a", "<u2")])
    return rec["v"].reshape(-1, 3)


def _read_3mf(path):
    import zipfile
    import xml.etree.ElementTree as ET
    ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("3D/3dmodel.model"))
    assert root.get("unit") == "millimeter"
    objects = {}
    for obj in root.findall("m:resources/m:object", ns):
        verts = [[float(v.get(k)) for k in "xyz"]
                 for v in obj.findall("m:mesh/m:vertices/m:vertex", ns)]
        tris = obj.findall("m:mesh/m:triangles/m:triangle", ns)
        assert tris and all(int(t.get(k)) < len(verts) for t in tris for k in ("v1", "v2", "v3"))
        objects[obj.get("name")] = verts
    assert len(root.findall("m:build/m:item", ns)) == len(objects)
    return objects


def _extent(points):
    return [max(p[i] for p in points) - min(p[i] for p in points) for i in range(3)]


def _export_head(tmpdir, units, system, scale_length):
    ctx = reset()
    s = ctx.scene.print_splitter
    s.units = units
    ctx.scene.unit_settings.system = system
    ctx.scene.unit_settings.scale_length = scale_length
    bpy.ops.print_splitter.add_head()
    head = s.reference
    head.rotation_euler = (0.3, 0.0, 0.5)  # export uses the world placement
    ctx.view_layer.update()
    from print_splitter.units import bu_to_mm
    world = [head.matrix_world @ v.co for v in head.data.vertices]
    want = [d * bu_to_mm(ctx) for d in _extent(world)]
    path3 = os.path.join(tmpdir, "head.3mf")
    assert bpy.ops.print_splitter.export(filepath=path3, file_format='3MF') == {'FINISHED'}
    got3 = _extent(_read_3mf(path3)["Head"])
    paths = os.path.join(tmpdir, "head.stl")
    assert bpy.ops.print_splitter.export(filepath=paths, file_format='STL') == {'FINISHED'}
    gots = _extent(_read_stl(paths))
    for a, b, c in zip(want, got3, gots):
        close(b, a, 1e-3)
        close(c, a, 1e-2)
    return want


def test_export_true_size_whatever_the_scene_units():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        # 1 unit = 1 mm in the add-on, scene left at metres (the reported setup).
        a = _export_head(d, 'MM', 'METRIC', 1.0)
        # Scene set to millimetres.
        b = _export_head(d, 'SCENE', 'METRIC', 0.001)
        # Scene in metres and the add-on following it: head built 0.15 units wide.
        c = _export_head(d, 'SCENE', 'METRIC', 1.0)
        for x, y, z in zip(a, b, c):
            close(x, y, 1e-3)
            close(x, z, 1e-2)
        assert 150.0 < a[0] < 200.0  # a head, in millimetres


def test_export_pieces_and_pins():
    import tempfile
    ctx, s, obj, plane = setup_split('BOOLEAN')
    bpy.ops.print_splitter.auto_place_pins()
    bpy.ops.print_splitter.split()
    # Selection includes things that must not be printed.
    plane.hide_set(False)
    plane.select_set(True)
    marker = [c for c in plane.children if c.get("ps_pin_marker")][0]
    marker.hide_set(False)
    marker.select_set(True)
    with tempfile.TemporaryDirectory() as d:
        path3 = os.path.join(d, "mask.3mf")
        assert bpy.ops.print_splitter.export(filepath=path3, file_format='3MF') == {'FINISHED'}
        objects = _read_3mf(path3)
        assert set(objects) == {"Mask_A", "Mask_B", "Mask_pin_01", "Mask_pin_02",
                                "Mask_pin_03", "Mask_pin_04"}, set(objects)
        close(_extent(objects["Mask_pin_01"])[0], s.pin_length, 1e-3)
        assert bpy.ops.print_splitter.export(filepath=os.path.join(d, "mask.stl"),
                                             file_format='STL') == {'FINISHED'}
        assert sorted(os.listdir(d)) == sorted(
            ["mask.3mf", "mask_Mask_A.stl", "mask_Mask_B.stl"]
            + ["mask_Mask_pin_%02d.stl" % i for i in range(1, 5)])
    for o in ctx.selected_objects:
        o.select_set(False)
    try:
        bpy.ops.print_splitter.export(filepath="/nonexistent.3mf")
        raise AssertionError("export with nothing selected should fail")
    except RuntimeError as e:
        assert "Select the pieces" in str(e)


def _cube(name, size, location=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    return obj


def _cursor(p):
    bpy.context.scene.cursor.location = p


def test_named_points_pair_by_name():
    ctx = reset()
    s = ctx.scene.print_splitter
    ref = _cube("Ref", 100.0)
    item = _cube("Item", 80.0, (300, 0, 0))
    s.reference, s.item = ref, item
    from print_splitter import landmarks
    for name, p in (("Crown", (0, 0, 50)), ("Left eye", (-30, -50, 0)),
                    ("Right eye", (30, -50, 0))):
        _cursor(p)
        assert bpy.ops.print_splitter.add_point(target='REFERENCE', name=name) == {'FINISHED'}
    # Unnamed points on the item take the next reference name: mark in a
    # different order by naming one explicitly first.
    _cursor((300 + 24, -40, 0))
    bpy.ops.print_splitter.add_point(target='ITEM', name="Right eye")
    _cursor((300, 0, 40))
    bpy.ops.print_splitter.add_point(target='ITEM')
    _cursor((300 - 24, -40, 0))
    bpy.ops.print_splitter.add_point(target='ITEM')
    assert landmarks.labels(item) == ["Right eye", "Crown", "Left eye"]
    assert landmarks.matched_labels(item, ref) == ["Crown", "Left eye", "Right eye"]
    ip, rp = landmarks.pairs(item, ref)
    close(landmarks.spread_ratio(ip, rp), 100.0 / 80.0, 1e-6)
    # Duplicate names are refused; hand-placed points are numbered.
    try:
        bpy.ops.print_splitter.add_point(target='ITEM', name="Crown")
        raise AssertionError("duplicate accepted")
    except RuntimeError:
        pass
    bpy.ops.print_splitter.add_point(target='REFERENCE')
    bpy.ops.print_splitter.add_point(target='REFERENCE')
    assert landmarks.labels(ref)[-2:] == ["Point 1", "Point 2"]
    bpy.ops.print_splitter.remove_point(target='REFERENCE', name="Point 1")
    bpy.ops.print_splitter.add_point(target='REFERENCE')
    assert sorted(landmarks.labels(ref)[-2:]) == ["Point 1", "Point 2"]

    s.point_fit = 'SCALE_MOVE'
    assert bpy.ops.print_splitter.fit_to_points() == {'FINISHED'}
    ip, rp = landmarks.pairs(item, ref)
    assert landmarks.rms_error(ip, rp) < 1e-3


def test_point_at_edit_mode_selection():
    ctx = reset()
    s = ctx.scene.print_splitter
    ref = _cube("Ref", 100.0)
    s.reference = ref
    ctx.view_layer.objects.active = ref
    ref.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ref.data)
    for v in bm.verts:
        v.select = v.co.z > 0  # top face: centre at (0, 0, 50)
    bmesh.update_edit_mesh(ref.data)
    assert bpy.ops.print_splitter.add_point(target='AUTO', name="Top") == {'FINISHED'}
    bpy.ops.object.mode_set(mode='OBJECT')
    from print_splitter import landmarks
    p = landmarks.points(ref)[0].matrix_world.translation
    assert (p - Vector((0, 0, 50))).length < 1e-4, p


def test_stretch_per_axis():
    m = Matrix.Translation((300, 0, 0)) @ Matrix.Diagonal((1.2, 0.9, 1.1, 1.0))
    ctx, s, head, mask = _point_fit_scene(m)
    _add_pairs(ctx, head, mask, (1, 700, 2000, 3500, 4400, 5200))
    s.point_fit = 'AXES'
    assert bpy.ops.print_splitter.fit_to_points() == {'FINISHED'}
    sc = mask.matrix_world.to_scale()
    for got in sc:
        close(got, 1.0, 1e-3)


def test_known_distance_uniform_and_along():
    ctx = reset()
    s = ctx.scene.print_splitter
    cube = _cube("Box", 20.0)
    ctx.view_layer.objects.active = cube
    cube.select_set(True)
    _cursor((-10, 0, 0))
    assert bpy.ops.print_splitter.measure_point(which='A') == {'FINISHED'}
    _cursor((10, 0, 0))
    bpy.ops.print_splitter.measure_point(which='B')
    from print_splitter import measure
    close(measure.measured(cube)[2], 20.0, 1e-6)
    s.known_distance = 50.0
    s.measure_mode = 'ALONG'
    assert bpy.ops.print_splitter.scale_to_distance() == {'FINISHED'}
    ctx.view_layer.update()
    for got, want in zip(cube.dimensions, (50.0, 20.0, 20.0)):
        close(got, want, 1e-3)
    close(measure.measured(cube)[2], 50.0, 1e-4)
    # Re-measure across Y and scale evenly: the shape is kept.
    _cursor((0, -10, 0))
    bpy.ops.print_splitter.measure_point(which='A')
    _cursor((0, 10, 0))
    bpy.ops.print_splitter.measure_point(which='B')
    s.known_distance = 10.0
    s.measure_mode = 'UNIFORM'
    bpy.ops.print_splitter.scale_to_distance()
    ctx.view_layer.update()
    for got, want in zip(cube.dimensions, (25.0, 10.0, 10.0)):
        close(got, want, 1e-3)


def test_scale_to_bed():
    ctx = reset()
    s = ctx.scene.print_splitter
    a = _cube("A", 100.0)
    a.scale = (5.0, 1.0, 0.5)  # 500 x 100 x 50
    b = _cube("B", 10.0, (300, 0, 0))
    ctx.view_layer.update()
    for o in (a, b):
        o.select_set(True)
    s.bed_fill = 90.0
    s.bed_allow_turn = False
    assert bpy.ops.print_splitter.scale_to_bed() == {'FINISHED'}
    from print_splitter import measure
    lo, hi = measure._world_extent([a, b])
    close(float((hi - lo).max()), 256.0 * 0.9, 1e-3)


def test_import_scan_units():
    import tempfile
    ctx = reset()
    s = ctx.scene.print_splitter
    with tempfile.TemporaryDirectory() as d:
        scan = _cube("Scan", 0.2)  # a 200 mm head scanned "in metres"
        part = _cube("Part", 150.0, (500, 0, 0))
        for obj, name in ((scan, "scan.obj"), (part, "part.stl")):
            for o in ctx.selected_objects:
                o.select_set(False)
            obj.select_set(True)
            if name.endswith(".obj"):
                bpy.ops.wm.obj_export(filepath=os.path.join(d, name), export_selected_objects=True,
                                      export_materials=False)
            else:
                bpy.ops.wm.stl_export(filepath=os.path.join(d, name), export_selected_objects=True)
        bpy.data.objects.remove(scan)
        bpy.data.objects.remove(part)
        assert bpy.ops.print_splitter.import_model(filepath=os.path.join(d, "scan.obj")) \
            == {'FINISHED'}
        ctx.view_layer.update()
        assert s.reference is not None
        close(max(s.reference.dimensions), 200.0, 1e-3)
        assert bpy.ops.print_splitter.import_model(filepath=os.path.join(d, "part.stl"),
                                                   use_as='ITEM') == {'FINISHED'}
        ctx.view_layer.update()
        close(max(s.item.dimensions), 150.0, 1e-3)
        assert bpy.ops.print_splitter.import_model(filepath=os.path.join(d, "part.stl"),
                                                   file_units='IN', use_as='NONE') == {'FINISHED'}
        ctx.view_layer.update()
        newest = [o for o in ctx.selected_objects if o.type == 'MESH'][0]  # just imported
        close(max(newest.dimensions), 150.0 * 25.4, 1e-2)


def test_reference_image_calibration():
    import tempfile
    ctx = reset()
    s = ctx.scene.print_splitter
    with tempfile.TemporaryDirectory() as d:
        img = bpy.data.images.new("photo", 400, 200)
        path = os.path.join(d, "photo.png")
        img.filepath_raw = path
        img.file_format = 'PNG'
        img.save()
        assert bpy.ops.print_splitter.add_reference_image(filepath=path, facing='FRONT',
                                                          width=100.0) == {'FINISHED'}
    plane = ctx.active_object
    ctx.view_layer.update()
    close(plane.dimensions.x, 100.0, 1e-4)
    close(plane.dimensions.y, 50.0, 1e-4)  # keeps the photo's aspect ratio
    # Upright in the front view: spans X and Z.
    zs = [(plane.matrix_world @ v.co).z for v in plane.data.vertices]
    close(max(zs) - min(zs), 50.0, 1e-4)
    # Something in the photo known to be 85.6 mm wide spans 40 % of it.
    _cursor((-20, 0, 0))
    bpy.ops.print_splitter.measure_point(which='A')
    _cursor((20, 0, 0))
    bpy.ops.print_splitter.measure_point(which='B')
    s.known_distance = 85.6
    bpy.ops.print_splitter.scale_to_distance()
    ctx.view_layer.update()
    close(plane.dimensions.x, 214.0, 1e-3)


class _Layout:
    """Stand-in for a panel layout that records labels and buttons, so panel
    drawing code runs without a window."""

    def __init__(self, log=None):
        self.log = log if log is not None else []

    def __getattr__(self, name):
        return _Layout(self.log)

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)

    def __call__(self, *args, **kwargs):
        if args and isinstance(args[0], str):
            self.log.append((args[0], kwargs.get("text")))
        elif "text" in kwargs:
            self.log.append(("label", kwargs["text"]))
        return _Layout(self.log)


def _draw_panel(name, ctx):
    from print_splitter import ui
    panel = next(c for c in ui.classes if c.__name__ == name)
    holder = type("Holder", (), {})()
    holder.layout = _Layout()
    panel.draw(holder, ctx)
    return holder.layout.log


def test_panels_draw_for_every_flow():
    ctx = reset()
    s = ctx.scene.print_splitter
    bpy.ops.print_splitter.add_head()
    s.item = _cube("Mask", 200.0)
    _cursor((0, 0, 112))
    bpy.ops.print_splitter.add_point(target='ITEM')  # takes the head's first name
    s.show_calibrate = True
    seen = {}
    for flow in [i.identifier for i in s.bl_rna.properties["flow"].enum_items]:
        s.flow = flow
        seen[flow] = _draw_panel("PRINTSPLIT_PT_fit", ctx)
    ops = lambda log: {a for a, _t in log if a.startswith("print_splitter.")}
    assert "print_splitter.fit_to_points" in ops(seen['HEAD'])
    assert ("print_splitter.add_point", "Mark on Mask") in seen['HEAD']
    assert "print_splitter.check_eyes" in ops(seen['HEAD'])
    assert "print_splitter.add_body_part" in ops(seen['BODY'])
    assert "print_splitter.add_library_item" in ops(seen['OBJECT'])
    for part in [i.identifier for i in s.bl_rna.properties["body_part"].enum_items]:
        s.flow, s.body_part = 'BODY', part
        _draw_panel("PRINTSPLIT_PT_fit", ctx)
    assert "print_splitter.scale_to_distance" in ops(seen['DISTANCE'])
    assert "print_splitter.scale_to_bed" in ops(seen['BED'])
    for connector in ('PINS', 'MAGNETS', 'SCREWS'):
        s.connector = connector
        for name in ("PRINTSPLIT_PT_split", "PRINTSPLIT_PT_pins", "PRINTSPLIT_PT_do_split",
                     "PRINTSPLIT_PT_auto"):
            _draw_panel(name, ctx)
    log = _draw_panel("PRINTSPLIT_PT_auto", ctx)
    assert {"print_splitter.suggest_cuts", "print_splitter.split_all",
            "print_splitter.hollow"} <= ops(log)


HEAD_POINTS = {"Crown", "Left eye", "Right eye", "Nose tip", "Chin", "Back of head",
               "Left ear", "Right ear"}


def test_head_v2_points_eyes_and_neck():
    ctx = reset()
    s = ctx.scene.print_splitter
    s.head_ipd = 58.0
    assert bpy.ops.print_splitter.add_head() == {'FINISHED'}
    head = s.reference
    from print_splitter import landmarks
    assert set(landmarks.labels(head)) == HEAD_POINTS
    pts = {landmarks.label(p): p.matrix_world.translation for p in landmarks.points(head)}
    close((pts["Left eye"] - pts["Right eye"]).length, 58.0, 0.05)
    assert pts["Left eye"].x > 0 > pts["Right eye"].x  # facing -Y, its left is +X
    assert pts["Nose tip"].y < pts["Left eye"].y < 0 < pts["Back of head"].y
    close(pts["Crown"].z, s.head_height / 2, 1e-3)
    assert pts["Left ear"].x > s.head_width / 2  # ears stick out past the skull
    names = {c.name for c in head.children}
    assert {"Left eyeball", "Right eyeball", "Neck"} <= names
    assert non_manifold_edges(head) == 0
    # Clear Points keeps a reference's own points.
    bpy.ops.print_splitter.clear_points()
    assert set(landmarks.labels(head)) == HEAD_POINTS


def test_hat_size():
    ctx = reset()
    s = ctx.scene.print_splitter
    ratio = s.head_length / s.head_width
    s.hat_system, s.hat_size = 'US', 7.25
    assert bpy.ops.print_splitter.head_from_hat_size() == {'FINISHED'}
    from print_splitter import head as head_mod
    close(head_mod.head_circumference(s.head_width, s.head_length), 7.25 * math.pi * 25.4, 0.01)
    close(s.head_length / s.head_width, ratio, 1e-6)
    s.hat_system, s.hat_size = 'EU', 56
    bpy.ops.print_splitter.head_from_hat_size()
    close(head_mod.head_circumference(s.head_width, s.head_length), 560.0, 0.01)


def _helmet(ctx, head, holes):
    """Hollow ball round the head, with eye holes at the head's pupils."""
    from print_splitter import landmarks
    helmet = shell("Helmet", 160.0, 150.0)
    if holes:
        pts = {landmarks.label(p): p.matrix_world.translation for p in landmarks.points(head)}
        cutters = []
        for side in ("Left", "Right"):
            me = geo.cylinder_mesh("hole", 16.0, 60.0)
            cyl = bpy.data.objects.new("hole", me)
            cyl.matrix_world = Matrix.Translation((pts["%s eye" % side].x, -150.0,
                                                   pts["%s eye" % side].z)) \
                @ Matrix.Rotation(math.radians(90), 4, 'X')
            ctx.scene.collection.objects.link(cyl)
            cutters.append(('DIFFERENCE', cyl))
        geo.apply_booleans(ctx, helmet, cutters)
        for _op, c in cutters:
            bpy.data.objects.remove(c)
    return helmet


def test_eye_check():
    ctx = reset()
    s = ctx.scene.print_splitter
    bpy.ops.print_splitter.add_head()
    head = s.reference
    from print_splitter import eyes
    s.item = _helmet(ctx, head, holes=False)
    view = eyes.eye_view(ctx, head, s.item)
    assert not view["Left"]["ahead"] and view["Left"]["out"] == 0

    s.item = _helmet(ctx, head, holes=True)
    view = eyes.eye_view(ctx, head, s.item)
    for side in ("Left", "Right"):
        v = view[side]
        assert v["ahead"] and not v["inside"]
        # The 16 mm radius hole's outer rim limits the view.
        p = v["pupil"]
        rim = math.sqrt(160.0 ** 2 - p.x ** 2 - p.z ** 2) - abs(p.y)
        want = math.degrees(math.atan(16.0 / rim))
        for key in ("out", "in", "up", "down"):
            assert abs(v[key] - want) <= 1.5, (side, key, v[key], want)
    # Mark the left hole's centre 5 mm outward of where it really is.
    pupil = view["Left"]["pupil"]
    _cursor((pupil.x + 5.0, -150.0, pupil.z))
    bpy.ops.print_splitter.add_point(target='ITEM', name="Left eye")
    view = eyes.eye_view(ctx, head, s.item)
    ox, oy = view["Left"]["offset"]
    close(ox, 5.0, 1e-3)
    close(oy, 0.0, 1e-3)
    assert bpy.ops.print_splitter.check_eyes() == {'FINISHED'}
    assert any(o.get("ps_sight_lines") for o in bpy.data.objects)


def test_body_parts():
    ctx = reset()
    s = ctx.scene.print_splitter
    from print_splitter import landmarks
    for part in [i.identifier for i in s.bl_rna.properties["body_part"].enum_items]:
        s.body_part = part
        assert bpy.ops.print_splitter.add_body_part() == {'FINISHED'}, part
        obj = s.reference
        assert non_manifold_edges(obj) == 0, part
        assert geo.mesh_volume(obj) > 0.0, part
        assert len(landmarks.points(obj)) >= 2, part
    # Ring size: US 7 is 17.32 mm inside.
    s.body_part, s.ring_system, s.ring_size = 'FINGER', 'US', 7.0
    bpy.ops.print_splitter.add_body_part()
    ctx.view_layer.update()
    close(s.reference.dimensions.x, 17.32, 0.01)
    s.glove_size = 9.0
    bpy.ops.print_splitter.hand_from_glove_size()
    close(s.hand_breadth, 9.0 * 25.4 / 2.5, 1e-4)
    s.body_part, s.figure_height = 'FIGURE', 1600.0
    bpy.ops.print_splitter.add_body_part()
    ctx.view_layer.update()
    close(s.reference.dimensions.z, 1600.0, 0.5)


def test_library_card_calibrates_a_photo():
    ctx = reset()
    s = ctx.scene.print_splitter
    s.library_item = 'CARD'
    assert bpy.ops.print_splitter.add_library_item() == {'FINISHED'}
    card = s.reference
    ctx.view_layer.update()
    close(card.dimensions.x, 85.60, 1e-3)
    close(card.dimensions.y, 53.98, 1e-3)
    # A "photo" in which the card is 40 mm wide, lying flat elsewhere.
    photo = _cube("Photo", 1.0, (500, 0, 0))
    photo.scale = (200.0, 150.0, 0.01)
    ctx.view_layer.update()
    s.item = photo
    k = 40.0 / 85.6
    for name, (x, y) in (("Corner 1", (-42.8, 26.99)), ("Corner 2", (42.8, 26.99)),
                         ("Corner 3", (42.8, -26.99)), ("Corner 4", (-42.8, -26.99))):
        _cursor((500 + 10 + x * k, 20 + y * k, 0))
        bpy.ops.print_splitter.add_point(target='ITEM', name=name)
    s.point_fit = 'ALIGN'
    assert bpy.ops.print_splitter.fit_to_points() == {'FINISHED'}
    close(photo.matrix_world.to_scale().x, 200.0 / k, 0.01)
    from print_splitter import landmarks
    ip, rp = landmarks.pairs(photo, card)
    assert landmarks.rms_error(ip, rp) < 1e-3


def test_every_library_object():
    ctx = reset()
    s = ctx.scene.print_splitter
    from print_splitter import library
    for key in library.CATALOGUE:
        s.library_item = key
        assert bpy.ops.print_splitter.add_library_item() == {'FINISHED'}, key
        assert non_manifold_edges(s.reference) == 0, key


def _block(name, x, y, z):
    obj = _cube(name, 1.0)
    obj.data.transform(Matrix.Diagonal((x, y, z, 1.0)))
    bpy.context.view_layer.update()
    return obj


def test_magnet_pockets():
    ctx, s, obj, plane = setup_split('BOOLEAN')
    s.connector = 'MAGNETS'
    s.magnet_diameter, s.magnet_thickness = 6.0, 3.0
    vol = geo.mesh_volume(obj)
    bpy.ops.print_splitter.auto_place_pins()
    n = len([c for c in plane.children if c.get("ps_pin_marker")])
    assert n >= 3
    assert bpy.ops.print_splitter.split() == {'FINISHED'}
    a, b = bpy.data.objects["Mask_A"], bpy.data.objects["Mask_B"]
    r, depth = (6.0 + s.magnet_clearance) / 2, 3.0 + s.magnet_depth_extra
    pocket = math.pi * r * r * depth
    close(geo.mesh_volume(a) + geo.mesh_volume(b), vol - 2 * n * pocket, vol * 0.002)
    assert not [o for o in bpy.data.objects if "_pin_" in o.name]  # no pins for magnets
    for part in (a, b):
        assert non_manifold_edges(part) == 0


def test_screws_with_inserts():
    ctx = reset()
    s = ctx.scene.print_splitter
    blk = _block("Block", 60.0, 60.0, 100.0)  # z from -50 to 50
    s.target = blk
    ctx.view_layer.objects.active = blk
    blk.select_set(True)
    bpy.ops.print_splitter.add_cut_plane(axis='Z')
    s.cut_plane.location = (0, 0, 0)
    s.connector = 'SCREWS'
    s.screw_size, s.screw_anchor = 'M3', 'INSERT'
    assert abs(s.screw_anchor_d - 4.0) < 1e-6 and abs(s.screw_clearance - 3.4) < 1e-6
    ctx.scene.cursor.location = (0, 0, 0)
    bpy.ops.print_splitter.add_pin()
    vol = geo.mesh_volume(blk)
    try:
        bpy.ops.print_splitter.split()
    except RuntimeError:
        pass
    a, b = bpy.data.objects["Block_A"], bpy.data.objects["Block_B"]
    seg = s.hole_segments
    k = (1.0 / math.cos(math.pi / seg)) ** 2 * seg * math.sin(2 * math.pi / seg) / (2 * math.pi)
    area = lambda d: math.pi * (d / 2) ** 2 * k  # the circumscribed polygon's area
    floor = s.screw_floor
    want_a = 0.5 * vol - area(3.4) * floor - area(s.screw_head_d) * (50.0 - floor)
    want_b = 0.5 * vol - area(4.0) * s.screw_anchor_depth
    close(geo.mesh_volume(a), want_a, 1.0)
    close(geo.mesh_volume(b), want_b, 1.0)
    for part in (a, b):
        assert non_manifold_edges(part) == 0
    from print_splitter import connectors
    from print_splitter import geometry
    frame = geometry.PlaneFrame(Matrix.Identity(4))
    bm = geometry.world_bmesh(ctx, blk)
    from mathutils.bvhtree import BVHTree
    _a, _b, notes = connectors.cutters(ctx, frame, [Vector((0, 0, 0))], BVHTree.FromBMesh(bm))
    bm.free()
    assert notes[0] == "use M3 x 8 mm screws", notes  # 3 under the head + 5.7 insert


def test_suggest_cuts_and_split_all():
    ctx = reset()
    s = ctx.scene.print_splitter
    bar = _block("Bar", 600.0, 100.0, 100.0)
    s.target = bar
    ctx.view_layer.objects.active = bar
    bar.select_set(True)
    vol = geo.mesh_volume(bar)
    s.pin_count = 2
    s.pin_diameter, s.pin_length = 5.0, 12.0
    assert bpy.ops.print_splitter.suggest_cuts() == {'FINISHED'}
    from print_splitter import autosplit
    planes = autosplit.cut_planes(ctx.scene)
    assert len(planes) == 2, len(planes)  # 600 mm on a 256 mm bed: 3 pieces
    assert bpy.ops.print_splitter.split_all() == {'FINISHED'}
    pieces = [o for o in bpy.data.objects if o.name.startswith("Bar_part_")]
    pins = [o for o in bpy.data.objects if o.name.startswith("Bar_pin_")]
    assert len(pieces) == 3 and len(pins) == 4, ([p.name for p in pieces], len(pins))
    hole = math.pi * ((5.0 + s.hole_clearance) / 2) ** 2 * (6.0 + s.hole_extra_depth)
    close(sum(geo.mesh_volume(p) for p in pieces), vol - 4 * 2 * hole, vol * 0.001)
    for p in pieces:
        assert non_manifold_edges(p) == 0
        lo, hi = autosplit._world_extent(p)
        assert autosplit.fits_bed(hi - lo, (256, 256, 256))
    # No leftover in-between pieces.
    assert not [o for o in bpy.data.objects if o.name.startswith("Bar_A") or
                o.name.startswith("Bar_B")]


def test_grid_for_bed():
    from print_splitter import autosplit
    assert autosplit.grid_for_bed((200, 200, 200), (256, 256, 256)) == (1, 1, 1)
    assert sorted(autosplit.grid_for_bed((400, 400, 100), (256, 256, 256))) == [1, 2, 2]
    # A long thin piece fits lying diagonally? No: boxes only turn by 90 degrees.
    assert autosplit.grid_for_bed((300, 100, 100), (256, 256, 256)) in [(2, 1, 1)]


def test_hollow():
    ctx = reset()
    s = ctx.scene.print_splitter
    bpy.ops.mesh.primitive_uv_sphere_add(radius=50.0, segments=96, ring_count=48)
    ball = ctx.active_object
    s.hollow_wall, s.hollow_drain = 2.0, 0.0
    assert bpy.ops.print_splitter.hollow() == {'FINISHED'}
    want = 4.0 / 3.0 * math.pi * (50.0 ** 3 - 48.0 ** 3)
    close(geo.mesh_volume(ball), want, want * 0.01)
    assert non_manifold_edges(ball) == 0
    bpy.ops.mesh.primitive_uv_sphere_add(radius=50.0, segments=96, ring_count=48,
                                         location=(200, 0, 0))
    ball2 = ctx.active_object
    s.hollow_drain = 5.0
    bpy.ops.print_splitter.hollow()
    assert geo.mesh_volume(ball2) < geo.mesh_volume(ball)
    assert non_manifold_edges(ball2) == 0


def test_plane_misses():
    ctx, s, obj, plane = setup_split('BOOLEAN')
    plane.location = (0, 0, 500)
    try:
        bpy.ops.print_splitter.split()
        raise AssertionError("split should fail")
    except RuntimeError as e:
        assert "doesn't cross" in str(e)
    assert "Mask_A" not in bpy.data.objects


def test_pin_breakout_warning_still_splits():
    ctx, s, obj, plane = setup_split('BOOLEAN')
    plane.matrix_world = Matrix.Identity(4)
    bpy.context.scene.cursor.location = (0, 0, 0)  # centre of the hollow: no material
    bpy.ops.print_splitter.add_pin()
    assert bpy.ops.print_splitter.split() == {'FINISHED'}


def test_scene_units():
    ctx = reset()
    s = ctx.scene.print_splitter
    s.units = 'SCENE'
    ctx.scene.unit_settings.system = 'METRIC'
    ctx.scene.unit_settings.scale_length = 1.0
    from print_splitter.units import mm_to_bu
    close(mm_to_bu(ctx), 0.001, 1e-12)
    ctx.scene.unit_settings.scale_length = 0.001
    close(mm_to_bu(ctx), 1.0, 1e-6)


def test_head_dimensions():
    ctx = reset()
    s = ctx.scene.print_splitter
    s.head_width, s.head_length, s.head_height = 140.0, 180.0, 210.0
    assert bpy.ops.print_splitter.add_head() == {'FINISHED'}
    head = s.reference
    assert non_manifold_edges(head) == 0
    d = head.dimensions
    close(d.z, 210.0, 0.5)
    assert 140.0 < d.x < 140.0 * 1.3, d.x  # ears stick out
    assert 180.0 < d.y < 180.0 * 1.25, d.y  # nose sticks out
    # Nose is at the front (-Y).
    ys = [v.co.y for v in head.data.vertices]
    assert -min(ys) > max(ys) + 10.0
    assert geo.mesh_volume(head) > 0.0


def test_scale_to_measurements():
    ctx = reset()
    s = ctx.scene.print_splitter
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0)
    obj = ctx.active_object
    s.head_width, s.head_length, s.head_height = 150.0, 190.0, 225.0
    assert bpy.ops.print_splitter.scale_to_measurements(mode='ALL') == {'FINISHED'}
    bpy.context.view_layer.update()
    for got, want in zip(obj.dimensions, (150.0, 190.0, 225.0)):
        close(got, want, 0.01)


def test_fit_and_scale_mask():
    ctx = reset()
    s = ctx.scene.print_splitter
    s.head_width, s.head_length, s.head_height = 150.0, 190.0, 225.0
    bpy.ops.print_splitter.add_head()
    head = s.reference
    mask = shell("Mask", 115.0, 105.0)  # inner Ø210: too small for this head
    s.item = mask
    s.min_clearance = 3.0
    s.fit_range = 60.0
    assert bpy.ops.print_splitter.check_fit() == {'FINISHED'}
    attr = head.data.color_attributes.get("Fit Check")
    assert attr is not None
    reds = sum(1 for c in attr.data if c.color[0] > 0.9 and c.color[1] < 0.2)
    assert reds > 0

    assert bpy.ops.print_splitter.scale_mask_to_fit() == {'FINISHED'}
    from print_splitter.ops_fit import FitChecker
    classes, dists, overlap, gap = FitChecker(ctx, head, mask).measure(60.0)
    assert 'HIT' not in classes
    assert 3.0 <= gap < 3.3, gap
    k = mask.matrix_world.to_scale().x
    assert k > 1.0

    # A loose mask shrinks back down to the same snug size.
    from print_splitter.ops_fit import _world_bbox_center, scale_about
    scale_about(mask, _world_bbox_center(head), (1.3, 1.3, 1.3))
    assert bpy.ops.print_splitter.scale_mask_to_fit() == {'FINISHED'}
    close(mask.matrix_world.to_scale().x, k, 0.01)


def test_hole_preview_follows_settings():
    ctx, s, obj, plane = setup_split('BOOLEAN')
    bpy.ops.print_splitter.auto_place_pins()
    marker = [c for c in plane.children if c.get("ps_pin_marker")][0]
    s.pin_diameter = 3.0
    xs = [v.co.x for v in marker.data.vertices]
    close(max(xs) - min(xs), 3.2, 0.05)


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception:
            failed += 1
            print("FAIL", name)
            traceback.print_exc()
    print("%d passed, %d failed" % (len(tests) - failed, failed))
    return failed


if __name__ == "__main__":
    code = main()
    if bpy.app.background and not hasattr(sys, "ps1"):
        sys.exit(1 if code else 0)
