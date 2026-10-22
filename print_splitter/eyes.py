"""Eye check: how much of each eye's view the mask leaves clear, and how far
each eye hole is from the line of sight."""

import math

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import geometry as geo
from . import landmarks
from .units import bu_to_mm, mm_to_bu

SIGHT_KEY = "ps_sight_lines"
# Roughly how far a person sees from straight ahead with one eye.
NATURAL = {"out": 95, "in": 60, "up": 50, "down": 70}


def _point(obj, name):
    for p in landmarks.points(obj):
        if landmarks.label(p) == name:
            return p.matrix_world.translation.copy()
    return None


def _rotate(forward, toward, deg):
    a = math.radians(deg)
    return (forward * math.cos(a) + toward * math.sin(a)).normalized()


def clear_angle(bvh, origin, forward, toward, limit, reach, step=1.0):
    """Degrees from straight ahead toward ``toward`` that stay clear before
    the first ray that hits the mask (0 when straight ahead is blocked)."""
    clear = 0.0
    deg = 0.0
    while deg <= limit:
        d = _rotate(forward, toward, deg)
        hit = bvh.ray_cast(origin, d, reach)[0]
        if hit is not None:
            return clear
        clear = deg
        deg += step
    return clear


def eye_view(context, head, mask):
    """Per eye ("Left"/"Right"): degrees clear "out", "in", "up" and "down",
    "ahead" (straight ahead clear), "inside" (pupil inside the item),
    "offset" (hole centre's (outward, up) offset from the line of sight, when
    the item has that eye's point), the "pupil" and the "dir_*" directions."""
    m3 = head.matrix_world.to_3x3()
    forward = (m3 @ Vector((0.0, -1.0, 0.0))).normalized()
    up = (m3 @ Vector((0.0, 0.0, 1.0))).normalized()
    left = (m3 @ Vector((1.0, 0.0, 0.0))).normalized()
    bm = geo.world_bmesh(context, mask)
    try:
        bvh = BVHTree.FromBMesh(bm)
    finally:
        bm.free()
    reach = 500.0 * mm_to_bu(context)
    out = {}
    for side, outward in (("Left", left), ("Right", -left)):
        pupil = _point(head, "%s eye" % side)
        if pupil is None:
            continue
        res = {
            "out": clear_angle(bvh, pupil, forward, outward, NATURAL["out"], reach),
            "in": clear_angle(bvh, pupil, forward, -outward, NATURAL["in"], reach),
            "up": clear_angle(bvh, pupil, forward, up, NATURAL["up"], reach),
            "down": clear_angle(bvh, pupil, forward, -up, NATURAL["down"], reach),
            "ahead": bvh.ray_cast(pupil, forward, reach)[0] is None,
            "inside": geo.is_inside(bvh, pupil),
            "pupil": pupil, "dir_ahead": forward, "dir_out": outward, "dir_up": up,
        }
        hole = _point(mask, "%s eye" % side)
        if hole is not None:
            v = hole - pupil
            lateral = v - forward * v.dot(forward)
            res["offset"] = (lateral.dot(outward), lateral.dot(up))
        out[side] = res
    return out


def _sight_lines(context, views):
    """Wire object showing straight ahead and each clear limit per eye."""
    old = [o for o in bpy.data.objects if o.get(SIGHT_KEY)]
    for o in old:
        me = o.data
        bpy.data.objects.remove(o)
        if me.users == 0:
            bpy.data.meshes.remove(me)
    length = 150.0 * mm_to_bu(context)
    verts, edges = [], []
    for v in views.values():
        dirs = [v["dir_ahead"]]
        for key, toward in (("out", v["dir_out"]), ("in", -v["dir_out"]),
                            ("up", v["dir_up"]), ("down", -v["dir_up"])):
            dirs.append(_rotate(v["dir_ahead"], toward, v[key]))
        base = len(verts)
        verts.append(v["pupil"][:])
        for i, d in enumerate(dirs):
            verts.append((v["pupil"] + d * length)[:])
            edges.append((base, base + 1 + i))
    me = bpy.data.meshes.new("Sight lines")
    me.from_pydata(verts, edges, [])
    obj = bpy.data.objects.new("Sight lines", me)
    obj[SIGHT_KEY] = True
    obj.show_in_front = True
    obj.hide_render = True
    context.collection.objects.link(obj)
    return obj


class PRINTSPLIT_OT_check_eyes(bpy.types.Operator):
    """Check what each eye can see through the mask: degrees clear outward,
    inward, up and down, and how far each eye hole is from the line of sight
    (mark the holes' centres as Left eye / Right eye on the mask). Draws the
    clear limits as sight lines"""
    bl_idname = "print_splitter.check_eyes"
    bl_label = "Check Eyes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.print_splitter
        if s.reference is None or s.item is None:
            self.report({'ERROR'}, "Pick the head and the mask")
            return {'CANCELLED'}
        views = eye_view(context, s.reference, s.item)
        if not views:
            self.report({'ERROR'}, "The head has no Left eye / Right eye points. Add a "
                                   "head from measurements, or mark them on your head model")
            return {'CANCELLED'}
        _sight_lines(context, views)
        to_mm = bu_to_mm(context)
        parts = []
        for side, v in views.items():
            if v["inside"]:
                parts.append("%s eye is inside the mask's material" % side)
                continue
            text = "%s eye: %s; %d° out, %d° in, %d° up, %d° down" % (
                side, "clear ahead" if v["ahead"] else "BLOCKED ahead",
                v["out"], v["in"], v["up"], v["down"])
            if "offset" in v:
                ox, oy = v["offset"]
                text += "; hole %.1f mm %s, %.1f mm %s of the eye" % (
                    abs(ox) * to_mm, "out" if ox >= 0 else "in",
                    abs(oy) * to_mm, "above" if oy >= 0 else "below")
            parts.append(text)
            print("Print Splitter eye check:", text)
        blocked = any(not v["ahead"] or v["inside"] for v in views.values())
        self.report({'WARNING'} if blocked else {'INFO'}, " | ".join(parts))
        return {'FINISHED'}


classes = (PRINTSPLIT_OT_check_eyes,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
