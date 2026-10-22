"""Auto-split to fit the print bed, split at every plane, and hollowing."""

import itertools
import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import geometry as geo
from .ops_split import (CUT_PLANE_KEY, SplitError, _remove_object, get_target,
                        hole_dims, make_cut_plane, pin_markers, split_object)
from .units import bu_to_mm, mm_to_bu

AUTO_KEY = "ps_auto_cut"
MAX_PER_AXIS = 8


def _world_extent(obj):
    mw = np.array(obj.matrix_world)
    co = np.empty(len(obj.data.vertices) * 3)
    obj.data.vertices.foreach_get("co", co)
    pts = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
    return pts.min(0), pts.max(0)


def fits_bed(size, bed):
    """True when a box fits the bed in some orientation."""
    return all(a <= b for a, b in zip(sorted(size), sorted(bed)))


def grid_for_bed(size, bed):
    """Fewest even cuts per axis (nx, ny, nz) so every piece's box fits the
    bed, or None when more than MAX_PER_AXIS per axis would be needed."""
    best = None
    for n in itertools.product(range(1, MAX_PER_AXIS + 1), repeat=3):
        piece = [size[i] / n[i] for i in range(3)]
        if not fits_bed(piece, bed):
            continue
        key = (n[0] * n[1] * n[2], sum(n), max(piece) - min(piece))
        if best is None or key < best[0]:
            best = (key, n)
    return None if best is None else best[1]


def cut_planes(scene):
    """Visible cut planes, in the order they were made."""
    planes = [o for o in scene.objects if o.get(CUT_PLANE_KEY) and o.visible_get()]
    return sorted(planes, key=lambda o: o.get(CUT_PLANE_KEY, 0))


class PRINTSPLIT_OT_suggest_cuts(bpy.types.Operator):
    """Add the fewest evenly spaced cut planes that make every piece fit the
    print bed. Move or turn them as you like, then Split at All Planes"""
    bl_idname = "print_splitter.suggest_cuts"
    bl_label = "Suggest Cuts to Fit Bed"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.print_splitter
        target = get_target(context)
        if target is None:
            self.report({'ERROR'}, "Pick a mesh object to split")
            return {'CANCELLED'}
        for o in [o for o in context.scene.objects if o.get(AUTO_KEY)]:
            for m in pin_markers(o):
                _remove_object(m)
            _remove_object(o)
        lo, hi = _world_extent(target)
        size_mm = (hi - lo) * bu_to_mm(context)
        fill = s.bed_fill / 100.0
        bed = [b * fill for b in (s.bed_x, s.bed_y, s.bed_z)]
        if fits_bed(size_mm, bed):
            self.report({'INFO'}, "%s already fits the bed" % target.name)
            return {'FINISHED'}
        n = grid_for_bed(size_mm, bed)
        if n is None:
            self.report({'ERROR'}, "Would need more than %d cuts per direction" % MAX_PER_AXIS)
            return {'CANCELLED'}
        centre = Vector(((lo + hi) * 0.5).tolist())
        rots = (Matrix.Rotation(math.radians(90.0), 3, 'Y'),
                Matrix.Rotation(math.radians(90.0), 3, 'X'), Matrix.Identity(3))
        made = 0
        for axis in range(3):
            for i in range(1, n[axis]):
                at = centre.copy()
                at[axis] = lo[axis] + (hi[axis] - lo[axis]) * i / n[axis]
                plane = make_cut_plane(context, target, at, rots[axis],
                                       float(np.linalg.norm(hi - lo)) * 0.75)
                plane[AUTO_KEY] = True
                made += 1
        s.target = target
        self.report({'INFO'}, "Added %d cut planes for %d pieces" % (made, n[0] * n[1] * n[2]))
        return {'FINISHED'}


def _centers_for(context, piece, frame, plane):
    """Connector positions for this piece on this plane: the plane's markers
    that fall inside the piece's cut, or automatic ones."""
    s = context.scene.print_splitter
    if not s.use_pins:
        return []
    bm = geo.world_bmesh(context, piece)
    try:
        eps = max(geo.bmesh_size(bm) * 1e-7, 1e-9)
        seg_a, seg_b = geo.section_segments(bm, frame, eps)
        if len(seg_a) == 0:
            return None  # the plane misses this piece
        markers = [frame.project(m.matrix_world.translation) for m in pin_markers(plane)]
        if markers:
            pts2 = np.array([frame.to_2d(p) for p in markers])
            inside, _d = geo.section_query(pts2, seg_a, seg_b)
            mine = [p for p, ok in zip(markers, inside) if ok]
            if mine or not s.auto_connectors:
                return mine
        if not s.auto_connectors:
            return []
        radius, depth = hole_dims(context)
        return geo.auto_pin_spots(bm, frame, s.pin_count, radius, depth,
                                  s.min_wall * mm_to_bu(context), eps)
    finally:
        bm.free()


class PRINTSPLIT_OT_split_all(bpy.types.Operator):
    """Split the object at every visible cut plane, in the order they were
    added, cutting each piece a plane crosses and joining them with the
    chosen connectors"""
    bl_idname = "print_splitter.split_all"
    bl_label = "Split at All Planes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.print_splitter
        target = get_target(context)
        if target is None:
            self.report({'ERROR'}, "Pick a mesh object to split")
            return {'CANCELLED'}
        planes = cut_planes(context.scene)
        if not planes:
            self.report({'ERROR'}, "Add cut planes first (or Suggest Cuts to Fit Bed)")
            return {'CANCELLED'}
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        pieces, pins, notes, connectors_made = [target], [], [], 0
        for plane in planes:
            frame = geo.PlaneFrame(plane.matrix_world)
            next_pieces = []
            for piece in pieces:
                centers = _centers_for(context, piece, frame, plane)
                if centers is None:
                    next_pieces.append(piece)
                    continue
                try:
                    res = split_object(context, piece, frame, centers)
                except SplitError as e:
                    notes.append(str(e))
                    next_pieces.append(piece)
                    continue
                connectors_made += len(centers)
                pins.extend(res.pins)
                notes.extend(n for n in res.notes if n not in notes)
                next_pieces.extend(res.parts)
                if piece is target:
                    target.hide_set(True)
                else:
                    _remove_object(piece)  # an in-between piece
            pieces = next_pieces
            plane.hide_set(True)
            for m in pin_markers(plane):
                m.hide_set(True)
        if pieces == [target]:
            self.report({'ERROR'}, "None of the planes cross %s" % target.name)
            return {'CANCELLED'}

        base = target.name
        for i, piece in enumerate(pieces, start=1):
            piece.name = "%s_part_%02d" % (base, i)
        _lay_out_pins(context, pins, pieces)
        for i, pin in enumerate(pins, start=1):
            pin.name = "%s_pin_%02d" % (base, i)
        for o in context.selected_objects:
            o.select_set(False)
        for o in pieces + pins:
            o.select_set(True)
        context.view_layer.objects.active = pieces[0]
        s.target = pieces[0]

        bed = (s.bed_x, s.bed_y, s.bed_z)
        to_mm = bu_to_mm(context)
        big = []
        for p in pieces:
            lo, hi = _world_extent(p)
            if not fits_bed((hi - lo) * to_mm, bed):
                big.append(p.name)
        msg = "%d pieces, %d connectors" % (len(pieces), connectors_made)
        if big:
            notes.append("still bigger than the bed: %s" % ", ".join(big))
        if notes:
            msg += "; " + "; ".join(notes)
        self.report({'WARNING'} if big else {'INFO'}, msg)
        return {'FINISHED'}


def _lay_out_pins(context, pins, pieces):
    """Line the pins up beside all the pieces."""
    if not pins or context.scene.print_splitter.pin_layout != 'FLAT':
        return
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    for p in pieces:
        a, b = _world_extent(p)
        lo, hi = np.minimum(lo, a), np.maximum(hi, b)
    mm = mm_to_bu(context)
    gap = max(context.scene.print_splitter.pin_diameter * 2.0 * mm, 5.0 * mm)
    for i, pin in enumerate(pins):
        plo, _phi = _world_extent(pin)
        shift = Vector((hi[0] + gap - plo[0], lo[1] + i * gap - plo[1], lo[2] - plo[2]))
        pin.matrix_world = Matrix.Translation(shift) @ pin.matrix_world


class PRINTSPLIT_OT_hollow(bpy.types.Operator):
    """Make the object a shell with the set wall thickness, optionally with a
    drain hole through its lowest point. Hollow after splitting so the
    connector holes keep a wall round them"""
    bl_idname = "print_splitter.hollow"
    bl_label = "Hollow"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.print_splitter
        obj = get_target(context)
        if obj is None:
            self.report({'ERROR'}, "Pick a mesh object to hollow")
            return {'CANCELLED'}
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        mm = mm_to_bu(context)
        mod = obj.modifiers.new("PS_Hollow", 'SOLIDIFY')
        mod.thickness = s.hollow_wall * mm
        mod.offset = -1.0  # add the thickness inside the surface
        mod.use_even_offset = True
        mod.use_quality_normals = True
        drain = None
        if s.hollow_drain > 0.0:
            co = np.empty(len(obj.data.vertices) * 3)
            obj.data.vertices.foreach_get("co", co)
            mw = np.array(obj.matrix_world)
            pts = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
            low = pts[int(np.argmin(pts[:, 2]))]
            me = geo.cylinder_mesh("PS_drain", s.hollow_drain * 0.5 * mm,
                                   (s.hollow_wall * 2.0 + 1.0) * mm)
            drain = bpy.data.objects.new("PS_drain", me)
            drain.matrix_world = Matrix.Translation(Vector(low.tolist()))
            context.scene.collection.objects.link(drain)
            bmod = obj.modifiers.new("PS_Drain", 'BOOLEAN')
            bmod.operation = 'DIFFERENCE'
            bmod.object = drain
            bmod.solver = 'EXACT'
        try:
            depsgraph = context.evaluated_depsgraph_get()
            depsgraph.update()
            new_mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
        finally:
            for m in [m for m in obj.modifiers if m.name in ("PS_Hollow", "PS_Drain")]:
                obj.modifiers.remove(m)
            if drain is not None:
                _remove_object(drain)
        old = obj.data
        new_mesh.name = old.name
        obj.data = new_mesh
        if old.users == 0:
            bpy.data.meshes.remove(old)
        self.report({'INFO'}, "Hollowed %s with %.1f mm walls%s" % (
            obj.name, s.hollow_wall, " and a drain hole" if drain is not None else ""))
        return {'FINISHED'}


classes = (PRINTSPLIT_OT_suggest_cuts, PRINTSPLIT_OT_split_all, PRINTSPLIT_OT_hollow)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
