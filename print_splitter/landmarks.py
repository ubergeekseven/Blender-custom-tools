"""Matching reference points on the mask and the head.

The user marks the same spots on both (top of the head, temples, chin...).
Point N on the mask pairs with point N on the head. Fitting uses only those
points, so ears, horns, teeth or fur on the mask don't throw the size off the
way a bounding box does.

With three or more pairs the best scale, rotation and position come from a
least-squares similarity fit (Umeyama's method).
"""

import bpy
import numpy as np
from bpy.props import EnumProperty
from mathutils import Matrix, Vector

from .units import bu_to_mm, mm_to_bu

POINT_KEY = "ps_landmark"


def points(obj):
    """Landmark empties on ``obj``, in the order they were added."""
    if obj is None:
        return []
    found = [c for c in obj.children if c.get(POINT_KEY)]
    return sorted(found, key=lambda c: c[POINT_KEY])


def pairs(mask, head):
    """World positions of matched points as two (N, 3) arrays."""
    m, h = points(mask), points(head)
    n = min(len(m), len(h))
    mp = np.array([p.matrix_world.translation[:] for p in m[:n]]).reshape(-1, 3)
    hp = np.array([p.matrix_world.translation[:] for p in h[:n]]).reshape(-1, 3)
    return mp, hp


def spread_ratio(mp, hp):
    """How much bigger the head's points are spread than the mask's."""
    dm = np.sqrt(((mp - mp.mean(0)) ** 2).sum())
    dh = np.sqrt(((hp - hp.mean(0)) ** 2).sum())
    return dh / dm if dm > 0.0 else None


def fit_transform(mp, hp, mode):
    """World-space 4x4 matrix moving the mask's points onto the head's.

    mode: 'SCALE' scales about the mask points' centre; 'SCALE_MOVE' also
    moves them onto the head points; 'ALIGN' also rotates.
    """
    s = spread_ratio(mp, hp)
    if s is None:
        return None
    mc, hc = Vector(mp.mean(0)), Vector(hp.mean(0))
    rot = Matrix.Identity(3)
    if mode == 'ALIGN':
        if len(mp) == 2:
            # Two points only fix a direction; take the smallest turn.
            a, b = Vector(mp[1] - mp[0]), Vector(hp[1] - hp[0])
            rot = a.rotation_difference(b).to_matrix()
        else:
            xc, yc = mp - mp.mean(0), hp - hp.mean(0)
            u, d, vt = np.linalg.svd(yc.T @ xc / len(mp))
            fix = np.diag([1.0, 1.0, np.sign(np.linalg.det(u) * np.linalg.det(vt)) or 1.0])
            rot = Matrix((u @ fix @ vt).tolist())
            s = float((d * np.diag(fix)).sum() / ((xc ** 2).sum() / len(mp)))
    lin = (rot * s).to_4x4()
    if mode == 'SCALE':
        return Matrix.Translation(mc) @ lin @ Matrix.Translation(-mc)
    return Matrix.Translation(hc) @ lin @ Matrix.Translation(-mc)


def rms_error(mp, hp):
    if len(mp) == 0:
        return 0.0
    return float(np.sqrt(((mp - hp) ** 2).sum(1).mean()))


class PRINTSPLIT_OT_add_point(bpy.types.Operator):
    """Add a reference point at the 3D cursor (Shift + right-click puts the
    cursor on a surface). Point 1 on the mask pairs with point 1 on the head,
    and so on"""
    bl_idname = "print_splitter.add_point"
    bl_label = "Add Point at Cursor"
    bl_options = {'REGISTER', 'UNDO'}

    target: EnumProperty(
        name="On",
        items=[('AUTO', "Nearest", "Whichever of head and mask is closer to the cursor"),
               ('MASK', "Mask", ""),
               ('HEAD', "Head", "")],
        default='AUTO')

    def execute(self, context):
        s = context.scene.print_splitter
        loc = context.scene.cursor.location.copy()
        choices = {'MASK': s.mask, 'HEAD': s.head}
        if self.target == 'AUTO':
            best, best_d = None, float("inf")
            for obj in choices.values():
                if obj is None:
                    continue
                inv = obj.matrix_world.inverted_safe()
                ok, co, _n, _i = obj.closest_point_on_mesh(inv @ loc)
                if ok:
                    d = ((obj.matrix_world @ co) - loc).length
                    if d < best_d:
                        best, best_d = obj, d
            obj = best
        else:
            obj = choices[self.target]
        if obj is None:
            self.report({'ERROR'}, "Pick the head and the mask first")
            return {'CANCELLED'}

        existing = points(obj)
        index = (existing[-1][POINT_KEY] + 1) if existing else 1
        role = "Mask" if obj is s.mask else "Head"
        empty = bpy.data.objects.new("%s point %d" % (role, index), None)
        empty[POINT_KEY] = index
        empty.empty_display_type = 'SPHERE'
        empty.empty_display_size = 3.0 * mm_to_bu(context)
        empty.show_in_front = True
        empty.show_name = True
        (obj.users_collection[0] if obj.users_collection
         else context.scene.collection).objects.link(empty)
        empty.parent = obj
        empty.matrix_world = Matrix.Translation(loc)

        partner = points(s.head if obj is s.mask else s.mask)
        self.report({'INFO'}, "%s point %d%s" % (
            role, index, "" if len(partner) >= len(existing) + 1
            else " - now add point %d on the %s" % (index, "head" if obj is s.mask else "mask")))
        return {'FINISHED'}


class PRINTSPLIT_OT_clear_points(bpy.types.Operator):
    """Remove all reference points from the head and the mask"""
    bl_idname = "print_splitter.clear_points"
    bl_label = "Clear Points"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.print_splitter
        for obj in (s.mask, s.head):
            for p in points(obj):
                bpy.data.objects.remove(p)
        return {'FINISHED'}


class PRINTSPLIT_OT_fit_to_points(bpy.types.Operator):
    """Scale (and optionally move and turn) the mask so its reference points
    match the head's. Afterwards, Scale Mask to Fit adds breathing room"""
    bl_idname = "print_splitter.fit_to_points"
    bl_label = "Fit Mask to Points"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.print_splitter
        if s.mask is None or s.head is None:
            self.report({'ERROR'}, "Pick the head and the mask first")
            return {'CANCELLED'}
        mp, hp = pairs(s.mask, s.head)
        need = 3 if s.point_fit == 'ALIGN' else 2
        if len(mp) < need:
            self.report({'ERROR'}, "Needs at least %d matching pairs of points" % need)
            return {'CANCELLED'}
        m = fit_transform(mp, hp, s.point_fit)
        if m is None:
            self.report({'ERROR'}, "The mask's points are all in the same place")
            return {'CANCELLED'}
        before = s.mask.matrix_world.to_scale()
        s.mask.matrix_world = m @ s.mask.matrix_world
        ratio = s.mask.matrix_world.to_scale().x / before.x if before.x else 1.0
        mp2, hp2 = pairs(s.mask, s.head)
        msg = "Scaled mask to %.1f%%" % (ratio * 100.0)
        if s.point_fit != 'SCALE':
            msg += "; points are off by %.1f mm on average" % (
                rms_error(mp2, hp2) * bu_to_mm(context))
        self.report({'INFO'}, msg)
        return {'FINISHED'}


classes = (PRINTSPLIT_OT_add_point, PRINTSPLIT_OT_clear_points, PRINTSPLIT_OT_fit_to_points)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
