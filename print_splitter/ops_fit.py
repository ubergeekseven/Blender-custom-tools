"""Head proxy, scale-to-measurement and mask fit operators."""

import bpy
import numpy as np
from bpy.props import EnumProperty
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from . import geometry as geo
from . import head as head_mod
from .units import bu_to_mm, mm_to_bu

FIT_ATTR = "Fit Check"
COLORS = {
    'HIT': (1.0, 0.08, 0.05, 1.0),
    'TIGHT': (1.0, 0.55, 0.0, 1.0),
    'OK': (0.15, 0.75, 0.3, 1.0),
    'FAR': (0.55, 0.55, 0.55, 1.0),
}


def _world_bbox_center(obj):
    mw = obj.matrix_world
    pts = [mw @ Vector(c) for c in obj.bound_box]
    return sum(pts, Vector()) / len(pts)


def _world_dims(obj):
    mw = obj.matrix_world
    pts = np.array([(mw @ v.co)[:] for v in obj.data.vertices])
    if len(pts) == 0:
        return Vector((0.0, 0.0, 0.0)), Vector((0.0, 0.0, 0.0))
    lo, hi = pts.min(0), pts.max(0)
    return Vector(hi - lo), Vector((lo + hi) * 0.5)


def scale_about(obj, pivot, factors):
    """Scale ``obj`` along the world axes about ``pivot``."""
    s = Matrix.Diagonal((*factors, 1.0))
    obj.matrix_world = Matrix.Translation(pivot) @ s @ Matrix.Translation(-pivot) \
        @ obj.matrix_world


class FitChecker:
    """Measures the gap between a head and a mask, optionally as if the mask
    were scaled by ``factors`` about ``pivot`` (without moving it)."""

    def __init__(self, context, head, mask):
        self.points = [head.matrix_world @ v.co for v in head.data.vertices]
        bm = geo.world_bmesh(context, mask)
        self.bvh = BVHTree.FromBMesh(bm)
        bm.free()

    def measure(self, check_range, pivot=None, factors=(1.0, 1.0, 1.0)):
        """Returns (classes, distances, worst_overlap, min_gap) in scene units.
        ``classes`` holds 'HIT', 'GAP' or 'FAR' per head vertex."""
        inv = Vector([1.0 / f for f in factors])
        dist_scale = min(factors)
        classes = []
        dists = []
        worst_overlap = 0.0
        min_gap = float("inf")
        for p in self.points:
            q = p if pivot is None else pivot + (p - pivot) * inv
            loc, normal, _i, dist = self.bvh.find_nearest(q)
            if loc is None:
                classes.append('FAR')
                dists.append(float("inf"))
                continue
            dist *= dist_scale
            dists.append(dist)
            if dist > check_range:
                classes.append('FAR')
            elif (q - loc).dot(normal) < 0.0:
                classes.append('HIT')
                worst_overlap = max(worst_overlap, dist)
            else:
                classes.append('GAP')
                min_gap = min(min_gap, dist)
        return classes, dists, worst_overlap, min_gap


def _paint(head, classes, dists, min_gap_bu):
    me = head.data
    attr = me.color_attributes.get(FIT_ATTR)
    if attr is None or attr.domain != 'POINT':
        if attr is not None:
            me.color_attributes.remove(attr)
        attr = me.color_attributes.new(FIT_ATTR, 'BYTE_COLOR', 'POINT')
    colors = []
    for cls, gap in zip(classes, dists):
        if cls == 'GAP':
            cls = 'TIGHT' if gap < min_gap_bu else 'OK'
        colors.extend(COLORS[cls])
    attr.data.foreach_set("color", colors)
    try:
        me.color_attributes.active_color = attr
        me.color_attributes.render_color_index = me.color_attributes.find(FIT_ATTR)
    except (AttributeError, TypeError):
        pass
    me.update()


def _show_attribute_colors(context):
    screen = getattr(context, "screen", None)
    if screen is None:
        return
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D' and space.shading.type == 'SOLID':
                    space.shading.color_type = 'VERTEX'


def _head_and_mask(op, context):
    s = context.scene.print_splitter
    if s.head is None or s.mask is None:
        op.report({'ERROR'}, "Pick both a head and a mask")
        return None, None
    if s.head is s.mask:
        op.report({'ERROR'}, "Head and mask must be different objects")
        return None, None
    return s.head, s.mask


class PRINTSPLIT_OT_add_head(bpy.types.Operator):
    """Add a generic head sized to the measurements, at the 3D cursor"""
    bl_idname = "print_splitter.add_head"
    bl_label = "Add Head From Measurements"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.print_splitter
        mm = mm_to_bu(context)
        bm = head_mod.head_bmesh(s.head_width * mm, s.head_length * mm, s.head_height * mm)
        me = geo.mesh_from_bmesh("Head", bm)
        for poly in me.polygons:
            poly.use_smooth = True
        obj = bpy.data.objects.new("Head", me)
        obj.location = context.scene.cursor.location
        context.collection.objects.link(obj)
        s.head = obj
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {'FINISHED'}


class PRINTSPLIT_OT_scale_to_measurements(bpy.types.Operator):
    """Scale an imported head model to the measured width, length and height
    (its whole bounding box, along world X, Y and Z). Not for masks: ears or
    horns would count toward the size. Use reference points for a mask"""
    bl_idname = "print_splitter.scale_to_measurements"
    bl_label = "Scale Head Model to Measurements"
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(
        name="Match",
        items=[('ALL', "Width, length and height", "Stretch to match all three"),
               ('HEIGHT', "Height, keep proportions", ""),
               ('WIDTH', "Width, keep proportions", ""),
               ('LENGTH', "Length, keep proportions", "")],
        default='ALL')

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        s = context.scene.print_splitter
        mm = mm_to_bu(context)
        dims, center = _world_dims(obj)
        want = Vector((s.head_width, s.head_length, s.head_height)) * mm
        if min(dims) <= 0.0:
            self.report({'ERROR'}, "Object is flat or empty")
            return {'CANCELLED'}
        f = [want[i] / dims[i] for i in range(3)]
        if self.mode != 'ALL':
            k = f[{'WIDTH': 0, 'LENGTH': 1, 'HEIGHT': 2}[self.mode]]
            f = [k, k, k]
        scale_about(obj, center, f)
        return {'FINISHED'}


class PRINTSPLIT_OT_check_fit(bpy.types.Operator):
    """Colour the head by how it sits in the mask: red where it pokes into the
    mask, orange where the gap is under Min Gap, green where it fits, grey
    where the mask is out of range"""
    bl_idname = "print_splitter.check_fit"
    bl_label = "Check Fit"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        head, mask = _head_and_mask(self, context)
        if head is None:
            return {'CANCELLED'}
        s = context.scene.print_splitter
        mm = mm_to_bu(context)
        checker = FitChecker(context, head, mask)
        classes, dists, overlap, min_gap = checker.measure(s.fit_range * mm)
        _paint(head, classes, dists, s.min_clearance * mm)
        _show_attribute_colors(context)
        to_mm = bu_to_mm(context)
        hits = classes.count('HIT')
        if hits:
            self.report({'WARNING'}, "Head goes into the mask at %d points, up to %.1f mm"
                        % (hits, overlap * to_mm))
        elif min_gap == float("inf"):
            self.report({'WARNING'}, "The mask is not within Check Range of the head")
        else:
            level = 'INFO' if min_gap >= s.min_clearance * mm else 'WARNING'
            self.report({level}, "No contact; smallest gap %.1f mm" % (min_gap * to_mm))
        return {'FINISHED'}


class PRINTSPLIT_OT_scale_mask_to_fit(bpy.types.Operator):
    """Scale the mask about the head's centre until the closest gap is Min
    Gap: grows a mask that is too tight, shrinks one that is too loose. Put
    the head where it will sit inside the mask first"""
    bl_idname = "print_splitter.scale_mask_to_fit"
    bl_label = "Scale Mask to Fit"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        head, mask = _head_and_mask(self, context)
        if head is None:
            return {'CANCELLED'}
        s = context.scene.print_splitter
        mm = mm_to_bu(context)
        need = s.min_clearance * mm
        rng = max(s.fit_range * mm, need * 2.0)
        axes = {'XYZ': (1, 1, 1), 'XY': (1, 1, 0), 'X': (1, 0, 0)}[s.fit_axes]
        pivot = _world_bbox_center(head)
        checker = FitChecker(context, head, mask)

        def factors(k):
            return tuple(k if a else 1.0 for a in axes)

        def fits(k):
            classes, _dists, _overlap, gap = checker.measure(rng, pivot, factors(k))
            return 'HIT' not in classes and gap >= need

        # Walk from the current size in 1% steps (small enough that the head
        # can't jump through the mask wall between steps), then refine.
        step = 1.01
        if fits(1.0):
            good, k = 1.0, 1.0 / step
            while k >= 0.5 and fits(k):
                good, k = k, k / step
            if k < 0.5:
                self.report({'ERROR'}, "The mask doesn't come near the head. Move the "
                                       "head into the mask first")
                return {'CANCELLED'}
            bad = k
        else:
            bad, k = 1.0, step
            while k <= 3.0 and not fits(k):
                bad, k = k, k * step
            if k > 3.0:
                self.report({'ERROR'}, "Couldn't find a fit up to 3x. Check that the "
                                       "head is positioned inside the mask")
                return {'CANCELLED'}
            good = k
        for _ in range(16):
            mid = (good + bad) * 0.5
            if fits(mid):
                good = mid
            else:
                bad = mid
        hi = good
        scale_about(mask, pivot, factors(hi))
        self.report({'INFO'}, "Scaled mask by %.1f%%" % (hi * 100.0))
        return {'FINISHED'}


classes = (
    PRINTSPLIT_OT_add_head,
    PRINTSPLIT_OT_scale_to_measurements,
    PRINTSPLIT_OT_check_fit,
    PRINTSPLIT_OT_scale_mask_to_fit,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
