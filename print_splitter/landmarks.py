"""Matching reference points on the item and the reference.

Points have names. A point on the item pairs with the reference's point of
the same name, so built-in references can come with named points already
placed (Crown, Left eye...) and the user only marks the matching spots.
Points added by hand are called "Point 1", "Point 2"... on each object, so
the Nth hand-placed point on one pairs with the Nth on the other.

Fitting uses only those points, so ears, horns, teeth or fur on an item
don't throw the size off the way a bounding box does. With three or more
pairs, the best scale, rotation and position come from a least-squares
similarity fit (Umeyama's method).
"""

import bmesh
import bpy
import numpy as np
from bpy.props import EnumProperty, StringProperty
from mathutils import Matrix, Vector

from .units import bu_to_mm, mm_to_bu

POINT_KEY = "ps_landmark"  # order the point was added in
LABEL_KEY = "ps_label"


def points(obj):
    """Point empties on ``obj``, in the order they were added."""
    if obj is None:
        return []
    found = [c for c in obj.children if c.get(POINT_KEY)]
    return sorted(found, key=lambda c: c[POINT_KEY])


def label(point):
    return point.get(LABEL_KEY) or "Point %d" % point[POINT_KEY]


def labels(obj):
    return [label(p) for p in points(obj)]


def matched_labels(item, reference):
    """Names on both, in the reference's order."""
    on_item = set(labels(item))
    return [n for n in labels(reference) if n in on_item]


def pairs(item, reference):
    """World positions of matched points as two (N, 3) arrays:
    (item points, reference points)."""
    by_item = {label(p): p for p in points(item)}
    by_ref = {label(p): p for p in points(reference)}
    names = matched_labels(item, reference)
    ip = np.array([by_item[n].matrix_world.translation[:] for n in names]).reshape(-1, 3)
    rp = np.array([by_ref[n].matrix_world.translation[:] for n in names]).reshape(-1, 3)
    return ip, rp


def spread_ratio(ip, rp):
    """How much more spread out the reference's points are than the item's."""
    di = np.sqrt(((ip - ip.mean(0)) ** 2).sum())
    dr = np.sqrt(((rp - rp.mean(0)) ** 2).sum())
    return dr / di if di > 0.0 else None


def fit_transform(ip, rp, mode):
    """World-space 4x4 matrix moving the item's points onto the reference's.

    'SCALE' scales evenly about the item points' centre; 'SCALE_MOVE' also
    moves them onto the reference points; 'ALIGN' also rotates; 'AXES'
    scales X, Y and Z separately and moves.
    """
    s = spread_ratio(ip, rp)
    if s is None:
        return None
    ic, rc = Vector(ip.mean(0)), Vector(rp.mean(0))
    if mode == 'AXES':
        di = ((ip - ip.mean(0)) ** 2).sum(0)
        dr = ((rp - rp.mean(0)) ** 2).sum(0)
        floor = di.sum() * 1e-4
        # Axes the points barely spread along can't be measured: use the
        # overall ratio there.
        k = [float(np.sqrt(dr[i] / di[i])) if di[i] > floor else s for i in range(3)]
        lin = Matrix.Diagonal((*k, 1.0))
        return Matrix.Translation(rc) @ lin @ Matrix.Translation(-ic)
    rot = Matrix.Identity(3)
    if mode == 'ALIGN':
        if len(ip) == 2:
            # Two points only fix a direction; take the smallest turn.
            a, b = Vector(ip[1] - ip[0]), Vector(rp[1] - rp[0])
            rot = a.rotation_difference(b).to_matrix()
        else:
            xc, yc = ip - ip.mean(0), rp - rp.mean(0)
            u, d, vt = np.linalg.svd(yc.T @ xc / len(ip))
            fix = np.diag([1.0, 1.0, np.sign(np.linalg.det(u) * np.linalg.det(vt)) or 1.0])
            rot = Matrix((u @ fix @ vt).tolist())
            s = float((d * np.diag(fix)).sum() / ((xc ** 2).sum() / len(ip)))
    lin = (rot * s).to_4x4()
    if mode == 'SCALE':
        return Matrix.Translation(ic) @ lin @ Matrix.Translation(-ic)
    return Matrix.Translation(rc) @ lin @ Matrix.Translation(-ic)


def rms_error(ip, rp):
    if len(ip) == 0:
        return 0.0
    return float(np.sqrt(((ip - rp) ** 2).sum(1).mean()))


def edit_selection_center(context):
    """(object, world centre) of the selected vertices in Edit Mode, or
    (None, None)."""
    obj = context.edit_object
    if obj is None or obj.type != 'MESH':
        return None, None
    bm = bmesh.from_edit_mesh(obj.data)
    sel = [v.co for v in bm.verts if v.select]
    if not sel:
        return obj, None
    centre = sum(sel, Vector()) / len(sel)
    return obj, obj.matrix_world @ centre


def add_point(context, obj, location, name=None, display_mm=3.0):
    """Add a named point empty on ``obj`` at world ``location``."""
    existing = points(obj)
    order = (existing[-1][POINT_KEY] + 1) if existing else 1
    if not name:
        taken = {label(p) for p in existing}
        n = 1
        while "Point %d" % n in taken:
            n += 1
        name = "Point %d" % n
    empty = bpy.data.objects.new("%s: %s" % (obj.name, name), None)
    empty[POINT_KEY] = order
    empty[LABEL_KEY] = name
    empty.empty_display_type = 'SPHERE'
    empty.empty_display_size = display_mm * mm_to_bu(context)
    empty.show_in_front = True
    empty.show_name = True
    (obj.users_collection[0] if obj.users_collection
     else context.scene.collection).objects.link(empty)
    empty.parent = obj
    empty.matrix_world = Matrix.Translation(location)
    return empty


def next_label(item, reference):
    """The first reference point the item doesn't have yet."""
    have = set(labels(item))
    for n in labels(reference):
        if n not in have:
            return n
    return None


class PRINTSPLIT_OT_add_point(bpy.types.Operator):
    """Add a reference point at the 3D cursor (Shift + right-click puts it on
    a surface), or in Edit Mode at the centre of the selected vertices, e.g.
    an eye hole's rim. On the item it takes the name of the next reference
    point it doesn't have yet"""
    bl_idname = "print_splitter.add_point"
    bl_label = "Add Point"
    bl_options = {'REGISTER', 'UNDO'}

    target: EnumProperty(
        name="On",
        items=[('AUTO', "Nearest", "Whichever of reference and item is closer to the cursor"),
               ('ITEM', "Item", ""),
               ('REFERENCE', "Reference", "")],
        default='AUTO')
    name: StringProperty(
        name="Name", default="",
        description="Point name. Empty: the next unmatched reference point, or Point N")

    def execute(self, context):
        s = context.scene.print_splitter
        choices = {'ITEM': s.item, 'REFERENCE': s.reference}
        obj, loc = edit_selection_center(context)
        if obj is not None:
            if loc is None:
                self.report({'ERROR'}, "Select some vertices first")
                return {'CANCELLED'}
            if obj not in choices.values():
                self.report({'ERROR'}, "%s isn't the reference or the item" % obj.name)
                return {'CANCELLED'}
        else:
            loc = context.scene.cursor.location.copy()
            if self.target == 'AUTO':
                best_d = float("inf")
                for cand in choices.values():
                    if cand is None:
                        continue
                    inv = cand.matrix_world.inverted_safe()
                    ok, co, _n, _i = cand.closest_point_on_mesh(inv @ loc)
                    if ok:
                        d = ((cand.matrix_world @ co) - loc).length
                        if d < best_d:
                            obj, best_d = cand, d
            else:
                obj = choices[self.target]
        if obj is None:
            self.report({'ERROR'}, "Pick the reference and the item first")
            return {'CANCELLED'}

        name = self.name
        if not name and obj is s.item and s.reference is not None:
            name = next_label(s.item, s.reference)
        if name and name in labels(obj):
            self.report({'ERROR'}, "%s already has %s" % (obj.name, name))
            return {'CANCELLED'}
        point = add_point(context, obj, loc, name)
        self.report({'INFO'}, "Added %s on %s" % (label(point), obj.name))
        return {'FINISHED'}


class PRINTSPLIT_OT_remove_point(bpy.types.Operator):
    """Remove this point"""
    bl_idname = "print_splitter.remove_point"
    bl_label = "Remove Point"
    bl_options = {'REGISTER', 'UNDO'}

    target: EnumProperty(items=[('ITEM', "Item", ""), ('REFERENCE', "Reference", "")])
    name: StringProperty()

    def execute(self, context):
        s = context.scene.print_splitter
        obj = s.item if self.target == 'ITEM' else s.reference
        for p in points(obj):
            if label(p) == self.name:
                bpy.data.objects.remove(p)
                return {'FINISHED'}
        return {'CANCELLED'}


class PRINTSPLIT_OT_clear_points(bpy.types.Operator):
    """Remove the points you placed on the item and the reference"""
    bl_idname = "print_splitter.clear_points"
    bl_label = "Clear Points"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.print_splitter
        for obj in (s.item, s.reference):
            for p in points(obj):
                if not p.get("ps_builtin"):
                    bpy.data.objects.remove(p)
        return {'FINISHED'}


class PRINTSPLIT_OT_fit_to_points(bpy.types.Operator):
    """Scale (and optionally move, turn or stretch) the item so its points
    match the reference's. Afterwards, Scale to Clearance adds breathing room"""
    bl_idname = "print_splitter.fit_to_points"
    bl_label = "Fit to Points"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.print_splitter
        if s.item is None or s.reference is None:
            self.report({'ERROR'}, "Pick the reference and the item first")
            return {'CANCELLED'}
        ip, rp = pairs(s.item, s.reference)
        need = 3 if s.point_fit in ('ALIGN', 'AXES') else 2
        if len(ip) < need:
            self.report({'ERROR'}, "Needs at least %d matching pairs of points" % need)
            return {'CANCELLED'}
        m = fit_transform(ip, rp, s.point_fit)
        if m is None:
            self.report({'ERROR'}, "The item's points are all in the same place")
            return {'CANCELLED'}
        before = s.item.matrix_world.to_scale()
        s.item.matrix_world = m @ s.item.matrix_world
        after = s.item.matrix_world.to_scale()
        ratios = [after[i] / before[i] if before[i] else 1.0 for i in range(3)]
        if s.point_fit == 'AXES':
            msg = "Scaled item to X %.1f%%, Y %.1f%%, Z %.1f%%" % tuple(r * 100 for r in ratios)
        else:
            msg = "Scaled item to %.1f%%" % (ratios[0] * 100.0)
        if s.point_fit != 'SCALE':
            ip2, rp2 = pairs(s.item, s.reference)
            msg += "; points are off by %.1f mm on average" % (
                rms_error(ip2, rp2) * bu_to_mm(context))
        self.report({'INFO'}, msg)
        return {'FINISHED'}


classes = (PRINTSPLIT_OT_add_point, PRINTSPLIT_OT_remove_point, PRINTSPLIT_OT_clear_points,
           PRINTSPLIT_OT_fit_to_points)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
