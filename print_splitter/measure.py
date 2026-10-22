"""Scale anything from a known distance, fit the print bed, and bring in
references: scans, models from elsewhere and photos on a plane."""

import math
import os

import bpy
import numpy as np
from bpy.props import EnumProperty, FloatProperty, StringProperty
from bpy_extras.io_utils import ImportHelper
from mathutils import Matrix, Vector

from .landmarks import edit_selection_center
from .units import bu_to_mm, mm_to_bu

MEASURE_KEY = "ps_measure"


# --------------------------------------------------------------------------
# Known distance
# --------------------------------------------------------------------------

def measure_owner(context):
    """The object whose A/B points the panel shows: the edited or active
    object, or the parent of a selected measure point."""
    obj = context.edit_object or context.active_object
    if obj is not None and obj.get(MEASURE_KEY) and obj.parent is not None:
        return obj.parent
    return obj


def measure_points(obj):
    """{'A': empty, 'B': empty} on ``obj`` (either may be missing)."""
    if obj is None:
        return {}
    return {c[MEASURE_KEY]: c for c in obj.children if c.get(MEASURE_KEY) in ('A', 'B')}


def measured(obj):
    """(A, B, distance) in world space, or None until both are placed."""
    pts = measure_points(obj)
    if 'A' not in pts or 'B' not in pts:
        return None
    a = pts['A'].matrix_world.translation.copy()
    b = pts['B'].matrix_world.translation.copy()
    return a, b, (b - a).length


def scale_matrix(a, b, factor, mode):
    """World matrix scaling by ``factor`` about the midpoint of A-B, evenly
    or only along A-B."""
    mid = (a + b) * 0.5
    if mode == 'ALONG':
        d = (b - a).normalized()
        lin = Matrix.Identity(3)
        for i in range(3):
            for j in range(3):
                lin[i][j] += (factor - 1.0) * d[i] * d[j]
        lin = lin.to_4x4()
    else:
        lin = Matrix.Scale(factor, 4)
    return Matrix.Translation(mid) @ lin @ Matrix.Translation(-mid)


class PRINTSPLIT_OT_measure_point(bpy.types.Operator):
    """Put measuring point A or B at the 3D cursor (Shift + right-click puts
    it on a surface), or in Edit Mode at the centre of the selected vertices"""
    bl_idname = "print_splitter.measure_point"
    bl_label = "Set Measuring Point"
    bl_options = {'REGISTER', 'UNDO'}

    which: EnumProperty(items=[('A', "A", ""), ('B', "B", "")])

    def execute(self, context):
        obj, loc = edit_selection_center(context)
        if obj is not None and loc is None:
            self.report({'ERROR'}, "Select some vertices first")
            return {'CANCELLED'}
        if obj is None:
            obj = measure_owner(context)
            loc = context.scene.cursor.location.copy()
        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, "Select the object to measure first")
            return {'CANCELLED'}
        old = measure_points(obj).get(self.which)
        if old is not None:
            bpy.data.objects.remove(old)
        empty = bpy.data.objects.new("%s: %s" % (obj.name, self.which), None)
        empty[MEASURE_KEY] = self.which
        empty.empty_display_type = 'PLAIN_AXES'
        empty.empty_display_size = 4.0 * mm_to_bu(context)
        empty.show_in_front = True
        empty.show_name = True
        (obj.users_collection[0] if obj.users_collection
         else context.scene.collection).objects.link(empty)
        empty.parent = obj
        empty.matrix_world = Matrix.Translation(loc)
        return {'FINISHED'}


class PRINTSPLIT_OT_scale_to_distance(bpy.types.Operator):
    """Scale the measured object so A to B is the real distance. Uniform keeps
    the shape; Along A-B only stretches in that direction"""
    bl_idname = "print_splitter.scale_to_distance"
    bl_label = "Scale to Match"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.print_splitter
        obj = measure_owner(context)
        m = measured(obj)
        if m is None:
            self.report({'ERROR'}, "Place points A and B on the object first")
            return {'CANCELLED'}
        a, b, dist = m
        if dist <= 0.0:
            self.report({'ERROR'}, "A and B are in the same place")
            return {'CANCELLED'}
        factor = s.known_distance * mm_to_bu(context) / dist
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        obj.matrix_world = scale_matrix(a, b, factor, s.measure_mode) @ obj.matrix_world
        self.report({'INFO'}, "Scaled %s by %.2f%%%s" % (
            obj.name, factor * 100.0, "" if s.measure_mode == 'UNIFORM' else " along A-B"))
        return {'FINISHED'}


# --------------------------------------------------------------------------
# Fit the bed
# --------------------------------------------------------------------------

def _world_extent(objects):
    pts = []
    for obj in objects:
        mw = np.array(obj.matrix_world)
        co = np.empty(len(obj.data.vertices) * 3)
        obj.data.vertices.foreach_get("co", co)
        pts.append(co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3])
    pts = np.vstack(pts)
    return pts.min(0), pts.max(0)


def bed_factor(size, bed, fill, allow_turn):
    """Uniform scale making a box of ``size`` fill ``fill`` of the bed."""
    size = [max(x, 1e-12) for x in size]
    if allow_turn:
        return min(b / x for b, x in zip(sorted(bed), sorted(size))) * fill
    return min(b / x for b, x in zip(bed, size)) * fill


class PRINTSPLIT_OT_scale_to_bed(bpy.types.Operator):
    """Scale the selected objects together, evenly, to the biggest size that
    fits the print bed (with the Fill margin)"""
    bl_idname = "print_splitter.scale_to_bed"
    bl_label = "Scale to Fit Bed"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.print_splitter
        objects = [o for o in context.selected_objects
                   if o.type == 'MESH' and len(o.data.vertices)]
        if not objects:
            self.report({'ERROR'}, "Select what to scale")
            return {'CANCELLED'}
        lo, hi = _world_extent(objects)
        size_mm = (hi - lo) * bu_to_mm(context)
        bed = (s.bed_x, s.bed_y, s.bed_z)
        k = bed_factor(size_mm, bed, s.bed_fill / 100.0, s.bed_allow_turn)
        pivot = Vector(((lo + hi) * 0.5).tolist())
        m = Matrix.Translation(pivot) @ Matrix.Scale(k, 4) @ Matrix.Translation(-pivot)
        for obj in objects:
            if obj.parent in objects:
                continue  # moves with its parent
            obj.matrix_world = m @ obj.matrix_world
        new = size_mm * k
        turn = s.bed_allow_turn and any(n > b for n, b in zip(new, bed))
        self.report({'INFO'}, "Scaled by %.1f%% to %.1f x %.1f x %.1f mm%s" % (
            k * 100.0, *new, "; turn it in the slicer to fit" if turn else ""))
        return {'FINISHED'}


# --------------------------------------------------------------------------
# Import a scan or model
# --------------------------------------------------------------------------

UNIT_MM = {'MM': 1.0, 'CM': 10.0, 'M': 1000.0, 'IN': 25.4}
_IMPORTERS = {
    ".stl": (("wm", "stl_import"), ("import_mesh", "stl")),
    ".obj": (("wm", "obj_import"), ("import_scene", "obj")),
    ".ply": (("wm", "ply_import"), ("import_mesh", "ply")),
    ".glb": (("import_scene", "gltf"),),
    ".gltf": (("import_scene", "gltf"),),
    ".fbx": (("import_scene", "fbx"),),
}
# glTF and FBX importers already convert to Blender's metre convention.
_FILE_IN_METRES = {".glb", ".gltf", ".fbx"}


def _run_importer(ext, path):
    for module, name in _IMPORTERS[ext]:
        op = getattr(getattr(bpy.ops, module), name)
        try:
            return op(filepath=path)
        except (AttributeError, RuntimeError, TypeError, KeyError):
            continue
    return None


class PRINTSPLIT_OT_import_model(bpy.types.Operator, ImportHelper):
    """Import a scan or a model from elsewhere at real size (STL, OBJ, PLY,
    glTF, FBX). Phone scanning apps usually export metres"""
    bl_idname = "print_splitter.import_model"
    bl_label = "Import Scan or Model"
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: StringProperty(default="*.stl;*.obj;*.ply;*.glb;*.gltf;*.fbx",
                                options={'HIDDEN'})
    file_units: EnumProperty(
        name="File Units",
        items=[('AUTO', "Guess", "glTF/FBX: metres. STL/OBJ/PLY: millimetres, or metres "
                                 "if the model is under 10 units across (typical of scans)"),
               ('MM', "Millimetres", ""), ('CM', "Centimetres", ""),
               ('M', "Metres", ""), ('IN', "Inches", "")],
        default='AUTO')
    use_as: EnumProperty(
        name="Use As",
        items=[('REFERENCE', "Reference", "Something to size against, e.g. a head scan"),
               ('ITEM', "Item", "Something to size, e.g. a mask"),
               ('NONE', "Nothing", "Just import it")],
        default='REFERENCE')

    def execute(self, context):
        path = self.filepath
        ext = os.path.splitext(path)[1].lower()
        if ext not in _IMPORTERS:
            self.report({'ERROR'}, "Can't import %s files" % ext)
            return {'CANCELLED'}
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        before = set(bpy.data.objects)
        if _run_importer(ext, path) is None:
            self.report({'ERROR'}, "Blender's importer for %s isn't available" % ext)
            return {'CANCELLED'}
        new = [o for o in bpy.data.objects if o not in before]
        meshes = [o for o in new if o.type == 'MESH' and len(o.data.vertices)]
        if not meshes:
            self.report({'ERROR'}, "Nothing to use in that file")
            return {'CANCELLED'}

        units = self.file_units
        guessed = ""
        if units == 'AUTO':
            if ext in _FILE_IN_METRES:
                units = 'M'
            else:
                lo, hi = _world_extent(meshes)
                units = 'M' if float((hi - lo).max()) < 10.0 else 'MM'
                guessed = " (guessed %s)" % ("metres" if units == 'M' else "millimetres")
        k = UNIT_MM[units] * mm_to_bu(context)
        if ext in _FILE_IN_METRES and units != 'M':
            k /= 1000.0  # the importer already treated the numbers as metres
        roots = [o for o in new if o.parent not in new]
        scale = Matrix.Scale(k, 4)
        for obj in roots:
            obj.matrix_world = scale @ obj.matrix_world

        s = context.scene.print_splitter
        main = max(meshes, key=lambda o: len(o.data.vertices))
        if self.use_as == 'REFERENCE':
            s.reference = main
        elif self.use_as == 'ITEM':
            s.item = main
        lo, hi = _world_extent(meshes)
        size = (hi - lo) * bu_to_mm(context)
        self.report({'INFO'}, "Imported %s: %.1f x %.1f x %.1f mm%s. Check a known "
                    "distance to be sure" % (main.name, *size, guessed))
        return {'FINISHED'}


# --------------------------------------------------------------------------
# Reference image
# --------------------------------------------------------------------------

class PRINTSPLIT_OT_add_reference_image(bpy.types.Operator, ImportHelper):
    """Put a photo or drawing on a plane. Then mark two points on it whose
    real distance you know and Scale to Match"""
    bl_idname = "print_splitter.add_reference_image"
    bl_label = "Add Reference Image"
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: StringProperty(default="*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tif;*.tiff",
                                options={'HIDDEN'})
    facing: EnumProperty(
        name="Facing",
        items=[('FRONT', "Front", "Upright, seen from the front view"),
               ('SIDE', "Side", "Upright, seen from the side view"),
               ('TOP', "Top", "Lying flat, seen from the top view")],
        default='FRONT')
    width: FloatProperty(name="Starting Width (mm)", min=1.0, default=200.0,
                         description="Size before calibrating with two known points")

    def execute(self, context):
        try:
            img = bpy.data.images.load(self.filepath, check_existing=True)
        except RuntimeError as e:
            self.report({'ERROR'}, "Couldn't open the image: %s" % e)
            return {'CANCELLED'}
        w_px, h_px = img.size
        if w_px == 0 or h_px == 0:
            self.report({'ERROR'}, "The image is empty")
            return {'CANCELLED'}
        w = self.width * mm_to_bu(context)
        h = w * h_px / w_px
        me = bpy.data.meshes.new(img.name)
        me.from_pydata([(-w / 2, -h / 2, 0), (w / 2, -h / 2, 0), (w / 2, h / 2, 0),
                        (-w / 2, h / 2, 0)], [], [(0, 1, 2, 3)])
        uv = me.uv_layers.new(name="UVMap")
        for loop, co in zip(uv.data, ((0, 0), (1, 0), (1, 1), (0, 1))):
            loop.uv = co
        mat = bpy.data.materials.new(img.name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = img
        bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if bsdf is not None:
            mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        me.materials.append(mat)
        obj = bpy.data.objects.new("Reference image", me)
        obj.hide_render = True
        rot = {'FRONT': Matrix.Rotation(math.radians(90), 4, 'X'),
               'SIDE': Matrix.Rotation(math.radians(90), 4, 'Z')
               @ Matrix.Rotation(math.radians(90), 4, 'X'),
               'TOP': Matrix.Identity(4)}[self.facing]
        obj.matrix_world = Matrix.Translation(context.scene.cursor.location) @ rot
        context.collection.objects.link(obj)
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        screen = getattr(context, "screen", None)
        for area in (screen.areas if screen else ()):
            for space in area.spaces:
                if space.type == 'VIEW_3D' and space.shading.type == 'SOLID':
                    space.shading.color_type = 'TEXTURE'
        return {'FINISHED'}


classes = (PRINTSPLIT_OT_measure_point, PRINTSPLIT_OT_scale_to_distance,
           PRINTSPLIT_OT_scale_to_bed, PRINTSPLIT_OT_import_model,
           PRINTSPLIT_OT_add_reference_image)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
