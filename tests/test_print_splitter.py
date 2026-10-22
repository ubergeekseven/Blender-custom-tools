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
    head = s.head
    mask = bpy.data.objects.new("Mask", head.data.copy())
    ctx.scene.collection.objects.link(mask)
    mask.matrix_world = mask_matrix
    s.mask = mask
    return ctx, s, head, mask


def _add_pairs(ctx, head, mask, vert_ids, target='AUTO'):
    for i in vert_ids:
        for obj, role in ((mask, 'MASK'), (head, 'HEAD')):
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
    head = s.head
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
    head = s.head
    mask = shell("Mask", 115.0, 105.0)  # inner Ø210: too small for this head
    s.mask = mask
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
