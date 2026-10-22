"""Cut plane, registration pin and split operators."""

import math

import bmesh
import bpy
from bpy.props import EnumProperty
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from . import connectors
from . import geometry as geo
from . import sizing
from .units import mm_to_bu

PREVIEW_MESH = "PS Hole Preview"
MARKER_KEY = "ps_pin_marker"
CUT_NORMAL_KEY = "ps_cut_normal"
CUT_PLANE_KEY = "ps_cut_plane"  # order the plane was added in


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def get_target(context):
    s = context.scene.print_splitter
    obj = s.target or context.active_object
    if obj is not None and obj.type == 'MESH' and obj is not s.cut_plane \
            and not obj.get(MARKER_KEY) and not obj.get(CUT_PLANE_KEY):
        return obj
    return None


def pin_markers(plane):
    if plane is None:
        return []
    return [c for c in plane.children if c.get(MARKER_KEY)]


def hole_dims(context):
    """(radius, depth per side) in Blender units of the chosen connector."""
    return connectors.connector_dims(context)


def _preview_mesh(context):
    radius, depth = hole_dims(context)
    s = context.scene.print_splitter
    new = geo.cylinder_mesh(PREVIEW_MESH, max(radius, 1e-6), max(depth, 1e-6),
                            min(s.hole_segments, 32))
    old = bpy.data.meshes.get(PREVIEW_MESH)
    if old is not None and old is not new:
        old.user_remap(new)
        bpy.data.meshes.remove(old)
        new.name = PREVIEW_MESH
    return new


def refresh_hole_previews(context):
    """Rebuild the hole preview cylinders after a pin setting changed."""
    if bpy.data.meshes.get(PREVIEW_MESH) is not None:
        _preview_mesh(context)


def _link(obj, like):
    cols = like.users_collection if like is not None else ()
    (cols[0] if cols else bpy.context.scene.collection).objects.link(obj)


def add_marker(context, plane, location):
    me = bpy.data.meshes.get(PREVIEW_MESH) or _preview_mesh(context)
    marker = bpy.data.objects.new("Pin Hole", me)
    marker[MARKER_KEY] = True
    marker.display_type = 'WIRE'
    marker.show_in_front = True
    marker.hide_render = True
    _link(marker, plane)
    frame = geo.PlaneFrame(plane.matrix_world)
    marker.parent = plane
    marker.matrix_world = Matrix.Translation(frame.project(location)) @ frame.rot.to_4x4()
    return marker


def _set_active(context, obj):
    for o in context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _world_bbox(obj):
    mw = obj.matrix_world
    pts = [mw @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def cut_normal_world(obj):
    """World-space outward normal of the cut face stored on a split part."""
    n = obj.get(CUT_NORMAL_KEY)
    if n is None or len(n) != 3:
        return None
    m3 = obj.matrix_world.to_3x3()
    try:
        return (m3.inverted().transposed() @ Vector(n)).normalized()
    except ValueError:
        return None


def _store_cut_normal(obj, world_normal):
    local = obj.matrix_world.to_3x3().transposed() @ world_normal
    obj[CUT_NORMAL_KEY] = local.normalized()[:]


def _remove_object(obj):
    me = obj.data if obj.type == 'MESH' else None
    bpy.data.objects.remove(obj)
    if me is not None and me.users == 0:
        bpy.data.meshes.remove(me)


def make_cut_plane(context, near, center, rot, size):
    """Grid plane at ``center`` with rotation ``rot`` (its Z is the cut
    normal), numbered so Split at All Planes cuts in the order added."""
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=8, y_segments=8, size=size * 0.5)
    me = geo.mesh_from_bmesh("Cut Plane", bm)
    plane = bpy.data.objects.new("Cut Plane", me)
    plane.display_type = 'WIRE'
    plane.show_axis = True
    plane.show_in_front = True
    plane.hide_render = True
    plane[CUT_PLANE_KEY] = 1 + max((o.get(CUT_PLANE_KEY, 0) for o in context.scene.objects),
                                   default=0)
    plane.matrix_world = Matrix.Translation(center) @ rot.to_4x4()
    _link(plane, near)
    return plane


# --------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------

class PRINTSPLIT_OT_add_cut_plane(bpy.types.Operator):
    """Add a cut plane through the middle of the object. Move and rotate it
    freely; its blue Z axis points to part A"""
    bl_idname = "print_splitter.add_cut_plane"
    bl_label = "Add Cut Plane"
    bl_options = {'REGISTER', 'UNDO'}

    axis: EnumProperty(
        name="Normal",
        items=[('Z', "Z (horizontal cut)", ""),
               ('Y', "Y (front/back cut)", ""),
               ('X', "X (left/right cut)", "")],
        default='Z')

    def execute(self, context):
        s = context.scene.print_splitter
        # A selected mesh wins over the remembered target, so after a split you
        # can click the piece you want to cut next and add a plane for it.
        active = context.active_object
        if active is not None and active.type == 'MESH' and active.select_get() \
                and not active.get(MARKER_KEY) and not active.get(CUT_PLANE_KEY):
            s.target = active
        target = get_target(context)
        if target is not None:
            lo, hi = _world_bbox(target)
            center = (lo + hi) * 0.5
            size = max((hi - lo).length * 0.75, 1e-3)
        else:
            center = context.scene.cursor.location.copy()
            size = 100.0 * mm_to_bu(context)

        rot = {'Z': Matrix.Identity(3),
               'Y': Matrix.Rotation(math.radians(90.0), 3, 'X'),
               'X': Matrix.Rotation(math.radians(90.0), 3, 'Y')}[self.axis]
        plane = make_cut_plane(context, target, center, rot, size)
        if target is not None:
            s.target = target
        s.cut_plane = plane
        _set_active(context, plane)
        return {'FINISHED'}


class PRINTSPLIT_OT_auto_place_pins(bpy.types.Operator):
    """Find spots on the cut with enough material for the pin holes and put a
    hole marker on each. Drag markers around afterwards if you like"""
    bl_idname = "print_splitter.auto_place_pins"
    bl_label = "Auto Place Pins"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.print_splitter
        target, plane = get_target(context), s.cut_plane
        if target is None or plane is None:
            self.report({'ERROR'}, "Pick the object to split and a cut plane first")
            return {'CANCELLED'}
        mm = mm_to_bu(context)
        radius, depth = hole_dims(context)
        frame = geo.PlaneFrame(plane.matrix_world)
        bm = geo.world_bmesh(context, target)
        try:
            eps = max(geo.bmesh_size(bm) * 1e-7, 1e-9)
            spots = geo.auto_pin_spots(bm, frame, s.pin_count, radius, depth,
                                       s.min_wall * mm, eps)
        finally:
            bm.free()
        for m in pin_markers(plane):
            _remove_object(m)
        _preview_mesh(context)
        for p in spots:
            add_marker(context, plane, p)
        if not spots:
            self.report({'WARNING'},
                        "No room for %.1f mm holes on this cut. Try a smaller pin, a "
                        "shorter pin or less wall, or place pins by hand"
                        % (s.pin_diameter + s.hole_clearance))
            return {'CANCELLED'}
        if len(spots) < s.pin_count:
            self.report({'WARNING'}, "Only room for %d of %d pins"
                        % (len(spots), s.pin_count))
        else:
            self.report({'INFO'}, "Placed %d pins" % len(spots))
        return {'FINISHED'}


class PRINTSPLIT_OT_add_pin(bpy.types.Operator):
    """Add a pin hole marker on the cut plane at the 3D cursor (projected onto
    the plane). Move it with G; it stays on the plane when you split"""
    bl_idname = "print_splitter.add_pin"
    bl_label = "Add Pin at Cursor"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        plane = context.scene.print_splitter.cut_plane
        if plane is None:
            self.report({'ERROR'}, "Add or pick a cut plane first")
            return {'CANCELLED'}
        marker = add_marker(context, plane, context.scene.cursor.location)
        _set_active(context, marker)
        return {'FINISHED'}


class PRINTSPLIT_OT_clear_pins(bpy.types.Operator):
    """Remove all pin hole markers from the cut plane"""
    bl_idname = "print_splitter.clear_pins"
    bl_label = "Clear Pins"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for m in pin_markers(context.scene.print_splitter.cut_plane):
            _remove_object(m)
        return {'FINISHED'}


class PRINTSPLIT_OT_split(bpy.types.Operator):
    """Split the object with the cut plane, fill both cut faces flat and cut
    pin holes at the markers. The original is hidden, not deleted"""
    bl_idname = "print_splitter.split"
    bl_label = "Split"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        target = get_target(context)
        if target is None or sizing.size_status(target) == 'OK':
            return self.execute(context)
        message = ("Pin holes and pins are made at real size. Scaling after the "
                   "cut makes them stop fitting. Is %s at its final size?" % target.name)
        try:
            return context.window_manager.invoke_confirm(
                self, event, title="Size not marked final", message=message,
                confirm_text="Split Anyway", icon='WARNING')
        except TypeError:  # Blender 4.0 and older: no custom text
            return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        s = context.scene.print_splitter
        target, plane = get_target(context), s.cut_plane
        if target is None:
            self.report({'ERROR'}, "Pick a mesh object to split")
            return {'CANCELLED'}
        if plane is None:
            self.report({'ERROR'}, "Add or pick a cut plane first")
            return {'CANCELLED'}
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        frame = geo.PlaneFrame(plane.matrix_world)
        markers = pin_markers(plane) if s.use_pins else []
        centers = [frame.project(m.matrix_world.translation) for m in markers]
        try:
            res = split_object(context, target, frame, centers)
        except SplitError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        part_a, part_b = res.parts

        target.hide_set(True)
        plane.hide_set(True)
        for m in markers:
            m.hide_set(True)
        for o in context.selected_objects:
            o.select_set(False)
        for o in (part_a, part_b, *res.pins):
            o.select_set(True)
        context.view_layer.objects.active = part_a
        s.target = part_a

        msg = "Split into %s and %s" % (part_a.name, part_b.name)
        if centers:
            msg += " with %d %s" % (len(centers), CONNECTOR_NOUN[s.connector])
        notes = list(res.notes)
        if res.bad:
            notes.append("connector %s may break through the surface"
                         % ", ".join(str(b) for b in res.bad))
        if notes:
            msg += "; " + "; ".join(notes)
        self.report({'WARNING'} if res.bad or len(notes) > (s.connector == 'SCREWS')
                    else {'INFO'}, msg)
        return {'FINISHED'}


CONNECTOR_NOUN = {'PINS': "pin holes", 'MAGNETS': "magnet pockets", 'SCREWS': "screws"}


class SplitError(Exception):
    pass


class SplitResult:
    def __init__(self, parts, pins, bad, notes):
        self.parts, self.pins, self.bad, self.notes = parts, pins, bad, notes


def split_object(context, target, frame, centers):
    """Cut ``target`` with the plane ``frame`` into two capped pieces with
    connectors at ``centers`` (world points on the plane). The original is
    left untouched. Raises SplitError when the cut can't be made."""
    s = context.scene.print_splitter
    mm = mm_to_bu(context)
    radius, depth = hole_dims(context)

    bm = geo.world_bmesh(context, target)
    try:
        size = geo.bmesh_size(bm)
        eps = max(size * 1e-7, 1e-9)
        seg_a, _seg_b = geo.section_segments(bm, frame, eps)
        if len(seg_a) == 0:
            raise SplitError("The cut plane doesn't cross %s" % target.name)
        bvh = BVHTree.FromBMesh(bm)
        bad = [i + 1 for i, c in enumerate(centers)
               if not geo.hole_fits(bvh, frame, c, radius, depth, 0.0)]
        holes_a, holes_b, notes = connectors.cutters(context, frame, centers, bvh)
        world_bm = bm.copy() if s.method == 'BISECT' else None
    finally:
        bm.free()

    tmp = bpy.data.collections.new("PS_tmp")
    context.scene.collection.children.link(tmp)
    temp_objects = []
    try:
        part_a, part_b = _make_parts(context, target, frame, size, eps, world_bm, tmp,
                                     temp_objects)
        for part, holes in ((part_a, holes_a), (part_b, holes_b)):
            steps = []
            for i, (me, m) in enumerate(holes):
                hole = bpy.data.objects.new("PS_hole_%d" % i, me)
                hole.matrix_world = m
                tmp.objects.link(hole)
                temp_objects.append(hole)
                steps.append(('DIFFERENCE', hole))
            if steps:
                geo.apply_booleans(context, part, steps, s.hole_tolerant)
    finally:
        for o in temp_objects:
            _remove_object(o)
        bpy.data.collections.remove(tmp)

    size_ok = sizing.size_status(target) == 'OK'
    hole_mm = connectors.connector_size_mm(s) if centers else None
    for part, sign in ((part_a, 1.0), (part_b, -1.0)):
        _store_cut_normal(part, frame.n * -sign)
        sizing.stamp_made(part, hole_mm=hole_mm)
        if size_ok:
            sizing.confirm_size(part)
        if s.separate > 0.0:
            part.matrix_world = Matrix.Translation(frame.n * (sign * s.separate * mm)) \
                @ part.matrix_world

    pins = []
    if centers and s.connector == 'PINS' and s.pin_layout != 'NONE':
        pins = _make_pins(context, target, frame, centers, (part_a, part_b))
    return SplitResult((part_a, part_b), pins, bad, notes)


def _make_parts(context, target, frame, size, eps, world_bm, tmp, temp_objects):
    s = context.scene.print_splitter
    depsgraph = context.evaluated_depsgraph_get()
    parts = []
    for suffix, keep_positive in (("A", True), ("B", False)):
        if s.method == 'BISECT':
            bm = world_bm.copy()
            geo.cap_by_bisect(bm, frame, keep_positive, eps)
            bm.transform(target.matrix_world.inverted_safe())
            me = geo.mesh_from_bmesh("%s_%s" % (target.data.name, suffix), bm)
            for mat in target.data.materials:
                me.materials.append(mat)
        else:
            me = bpy.data.meshes.new_from_object(target.evaluated_get(depsgraph))
            me.name = "%s_%s" % (target.data.name, suffix)
        part = bpy.data.objects.new("%s_%s" % (target.name, suffix), me)
        part.matrix_world = target.matrix_world.copy()
        _link(part, target)
        parts.append(part)
    if world_bm is not None:
        world_bm.free()

    if s.method == 'BOOLEAN':
        half = bpy.data.objects.new("PS_half", geo.halfspace_mesh("PS_half", size * 2.0))
        half.matrix_world = frame.matrix()
        tmp.objects.link(half)
        temp_objects.append(half)
        geo.apply_booleans(context, parts[0], [('INTERSECT', half)], s.hole_tolerant)
        geo.apply_booleans(context, parts[1], [('DIFFERENCE', half)], s.hole_tolerant)

    if any(len(p.data.polygons) == 0 for p in parts):
        for p in parts:
            _remove_object(p)
        raise SplitError("The cut produced an empty part. If the plane crosses the "
                         "object, the mesh probably isn't watertight: try Hole Tolerant "
                         "or the Bisect + Fill method")
    return parts


def _make_pins(context, target, frame, centers, parts):
    s = context.scene.print_splitter
    mm = mm_to_bu(context)
    length = s.pin_length * mm
    diameter = s.pin_diameter * mm
    pins = []
    if s.pin_layout == 'FLAT':
        lo = Vector((math.inf,) * 3)
        hi = Vector((-math.inf,) * 3)
        for p in parts:
            plo, phi = _world_bbox(p)
            lo = Vector(map(min, lo, plo))
            hi = Vector(map(max, hi, phi))
        gap = max(diameter * 2.0, 5.0 * mm)
        # Rotating about Y lays the pin along X with a flat side down.
        lay = Matrix.Rotation(math.radians(90.0), 4, 'Y')
        flat_h = diameter * 0.5 * math.cos(math.radians(30.0))
    for i, c in enumerate(centers):
        bm = geo.hex_pin_bmesh(diameter, length, s.pin_chamfer * mm)
        me = geo.mesh_from_bmesh("%s_pin" % target.name, bm)
        pin = bpy.data.objects.new("%s_pin_%02d" % (target.name, i + 1), me)
        if s.pin_layout == 'FLAT':
            pos = Vector((hi.x + gap, lo.y + i * gap, lo.z + flat_h))
            pin.matrix_world = Matrix.Translation(pos) @ lay
        else:
            pin.matrix_world = Matrix.Translation(c - frame.n * (length * 0.5)) \
                @ frame.rot.to_4x4()
        _link(pin, target)
        sizing.stamp_made(pin, pin_mm=s.pin_diameter)
        pins.append(pin)
    return pins


class PRINTSPLIT_OT_cut_face_down(bpy.types.Operator):
    """Turn each selected split part so its cut face lies flat on the print
    bed (Z = 0)"""
    bl_idname = "print_splitter.cut_face_down"
    bl_label = "Cut Face Down"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        done = 0
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            n = cut_normal_world(obj)
            if n is None:
                continue
            q = n.rotation_difference(Vector((0.0, 0.0, -1.0)))
            lo, hi = _world_bbox(obj)
            c = (lo + hi) * 0.5
            obj.matrix_world = Matrix.Translation(c) @ q.to_matrix().to_4x4() \
                @ Matrix.Translation(-c) @ obj.matrix_world
            mw = obj.matrix_world
            min_z = min((mw @ v.co).z for v in obj.data.vertices)
            obj.matrix_world = Matrix.Translation((0.0, 0.0, -min_z)) @ mw
            done += 1
        if not done:
            self.report({'WARNING'}, "Select parts made with Split")
            return {'CANCELLED'}
        return {'FINISHED'}


classes = (
    PRINTSPLIT_OT_add_cut_plane,
    PRINTSPLIT_OT_auto_place_pins,
    PRINTSPLIT_OT_add_pin,
    PRINTSPLIT_OT_clear_pins,
    PRINTSPLIT_OT_split,
    PRINTSPLIT_OT_cut_face_down,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
