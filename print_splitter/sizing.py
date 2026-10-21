"""Guards against scaling at the wrong time.

Pin holes and pins are made at their real size, so the model has to be at its
final size before it's cut. Before a cut, the user marks the size as final
(Split asks if they haven't). After a cut, pieces and pins remember their
size, so the panel can flag ones that were scaled afterwards and put them
back.
"""

import bpy
import numpy as np
from mathutils import Matrix, Vector

from .units import bu_to_mm

SIZE_OK_KEY = "ps_size_ok"
MADE_DIMS_KEY = "ps_made_dims"
HOLE_MM_KEY = "ps_hole_mm"
PIN_MM_KEY = "ps_pin_mm"
TOLERANCE = 0.002


def _local_box(obj):
    """(min, max) of the mesh's vertices in object space."""
    verts = obj.data.vertices
    if len(verts) == 0:
        return Vector(), Vector()
    co = np.empty(len(verts) * 3)
    verts.foreach_get("co", co)
    co = co.reshape(-1, 3)
    return Vector(co.min(0)), Vector(co.max(0))


def dims(obj):
    """Size along the object's own axes, including its scale. Unchanged by
    moving or rotating the object and by applying its scale."""
    lo, hi = _local_box(obj)
    scale = obj.matrix_world.to_scale()
    return Vector([(hi[i] - lo[i]) * abs(scale[i]) for i in range(3)])


def _ratios(obj, key):
    stored = obj.get(key)
    if stored is None or len(stored) != 3:
        return None
    now = dims(obj)
    return [now[i] / stored[i] if stored[i] > 0.0 else 1.0 for i in range(3)]


def _changed(ratios):
    return ratios is not None and max(abs(r - 1.0) for r in ratios) > TOLERANCE


def confirm_size(obj):
    obj[SIZE_OK_KEY] = dims(obj)[:]


def size_status(obj):
    """'OK' when the size was marked final and hasn't changed since,
    'CHANGED' when it has, 'UNCONFIRMED' when it was never marked."""
    ratios = _ratios(obj, SIZE_OK_KEY)
    if ratios is None:
        return 'UNCONFIRMED'
    return 'CHANGED' if _changed(ratios) else 'OK'


def stamp_made(obj, hole_mm=None, pin_mm=None):
    obj[MADE_DIMS_KEY] = dims(obj)[:]
    if hole_mm is not None:
        obj[HOLE_MM_KEY] = hole_mm
    if pin_mm is not None:
        obj[PIN_MM_KEY] = pin_mm


def resized_after_cut(objects):
    """[(obj, average ratio)] for pieces and pins scaled after they were made."""
    out = []
    for obj in objects:
        if obj.type != 'MESH' or MADE_DIMS_KEY not in obj:
            continue
        ratios = _ratios(obj, MADE_DIMS_KEY)
        if _changed(ratios):
            out.append((obj, sum(ratios) / 3.0))
    return out


def restore_made_size(obj):
    """Scale ``obj`` back to the size it was made at, about its own centre."""
    ratios = _ratios(obj, MADE_DIMS_KEY)
    if ratios is None:
        return False
    lo, hi = _local_box(obj)
    c = (lo + hi) * 0.5
    s = Matrix.Diagonal((*[1.0 / r if r > 0.0 else 1.0 for r in ratios], 1.0))
    obj.matrix_world = obj.matrix_world @ Matrix.Translation(c) @ s @ Matrix.Translation(-c)
    return True


class PRINTSPLIT_OT_confirm_size(bpy.types.Operator):
    """Mark the object's current size as final. Pin holes and pins are made
    at real size, so scale first (Head Fit helps), then cut"""
    bl_idname = "print_splitter.confirm_size"
    bl_label = "Size Is Final"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .ops_split import get_target
        obj = get_target(context)
        if obj is None:
            self.report({'ERROR'}, "Pick a mesh object")
            return {'CANCELLED'}
        confirm_size(obj)
        d = dims(obj) * bu_to_mm(context)
        self.report({'INFO'}, "%s: %.1f x %.1f x %.1f mm" % (obj.name, d.x, d.y, d.z))
        return {'FINISHED'}


class PRINTSPLIT_OT_restore_cut_size(bpy.types.Operator):
    """Scale pieces and pins that were resized after cutting back to the size
    they were made at, so the pins fit the holes again"""
    bl_idname = "print_splitter.restore_cut_size"
    bl_label = "Undo Scaling After Cut"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        done = 0
        for obj, _ratio in resized_after_cut(context.scene.objects):
            done += restore_made_size(obj)
        self.report({'INFO'}, "Restored %d objects" % done)
        return {'FINISHED'} if done else {'CANCELLED'}


classes = (PRINTSPLIT_OT_confirm_size, PRINTSPLIT_OT_restore_cut_size)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
