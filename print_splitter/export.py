"""Export pieces for a slicer at true millimetre size.

STL files carry no units; slicers read their numbers as millimetres. 3MF
files say their unit, and Print Splitter always writes millimetres. Either
way the numbers come from the add-on's own unit setting, the same one its
pins and holes were made with, whatever other exporters do with the scene's
unit settings. The report lists each piece's size and flags pieces that
won't fit the print bed.
"""

import os
import struct
import zipfile
from xml.sax.saxutils import quoteattr

import bpy
import numpy as np
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy_extras.io_utils import ExportHelper

from .units import bu_to_mm

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="model" '
    'ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
    '</Types>')
_RELS = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
    'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
    '</Relationships>')


def printable_objects(objects):
    out = []
    for obj in objects:
        if obj.type != 'MESH' or obj.get("ps_pin_marker"):
            continue
        if obj.display_type == 'WIRE' and obj.hide_render:  # cut planes
            continue
        out.append(obj)
    return out


def world_triangles(context, obj, scale):
    """(vertices (V, 3), triangles (T, 3)) of the evaluated mesh, in world
    space multiplied by ``scale``."""
    depsgraph = context.evaluated_depsgraph_get()
    ob_eval = obj.evaluated_get(depsgraph)
    me = ob_eval.to_mesh()
    try:
        me.calc_loop_triangles()
        verts = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", verts)
        tris = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", tris)
    finally:
        ob_eval.to_mesh_clear()
    verts = verts.reshape(-1, 3)
    m = np.array(obj.matrix_world)
    verts = verts @ m[:3, :3].T + m[:3, 3]
    if np.linalg.det(m[:3, :3]) < 0.0:  # mirrored: keep normals pointing out
        tris = tris.reshape(-1, 3)[:, ::-1].ravel()
    return verts * scale, tris.reshape(-1, 3)


def write_stl(path, verts, tris):
    v = verts[tris]  # (T, 3, 3)
    n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    length = np.linalg.norm(n, axis=1)
    length[length == 0.0] = 1.0
    n /= length[:, None]
    rec = np.zeros(len(tris), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"] = n
    rec["v"] = v
    with open(path, "wb") as f:
        f.write(b"Print Splitter binary STL, millimetres".ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        f.write(rec.tobytes())


def write_3mf(path, parts):
    """``parts`` is a list of (name, verts, tris)."""
    out = ['<?xml version="1.0" encoding="UTF-8"?>\n'
           '<model unit="millimeter" xml:lang="en-US" '
           'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
           '<resources>']
    for i, (name, verts, tris) in enumerate(parts, start=1):
        out.append('<object id="%d" name=%s type="model"><mesh><vertices>'
                   % (i, quoteattr(name)))
        out.extend('<vertex x="%.6g" y="%.6g" z="%.6g"/>' % tuple(v) for v in verts)
        out.append('</vertices><triangles>')
        out.extend('<triangle v1="%d" v2="%d" v3="%d"/>' % tuple(t) for t in tris)
        out.append('</triangles></mesh></object>')
    out.append('</resources><build>')
    out.extend('<item objectid="%d"/>' % i for i in range(1, len(parts) + 1))
    out.append('</build></model>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("_rels/.rels", _RELS)
        zf.writestr("3D/3dmodel.model", "".join(out))


def _safe(name):
    keep = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    return keep or "part"


class PRINTSPLIT_OT_export(bpy.types.Operator, ExportHelper):
    """Export the selected pieces and pins for a slicer at true size in
    millimetres, whatever the scene's unit settings say"""
    bl_idname = "print_splitter.export"
    bl_label = "Export for Printing"
    bl_options = {'REGISTER'}

    filename_ext = ".3mf"
    filter_glob: StringProperty(default="*.3mf;*.stl", options={'HIDDEN'})

    file_format: EnumProperty(
        name="Format",
        items=[('3MF', "3MF (one file)",
                "All pieces in one file that says it's in millimetres. Best for "
                "Bambu Studio, OrcaSlicer, PrusaSlicer and Cura"),
               ('STL', "STL (file per piece)",
                "One STL per piece, named after the piece. STL has no units; "
                "slicers read it as millimetres")],
        default='3MF')
    selected_only: BoolProperty(
        name="Selected Only", default=True,
        description="Export only selected objects; otherwise every visible mesh")

    def check(self, context):
        ext = ".3mf" if self.file_format == '3MF' else ".stl"
        changed = self.filename_ext != ext
        self.filename_ext = ext
        root, old = os.path.splitext(self.filepath)
        if old.lower() in (".3mf", ".stl") and old.lower() != ext:
            self.filepath = root + ext
            changed = True
        return changed or super().check(context)

    def execute(self, context):
        source = (context.selected_objects if self.selected_only
                  else [o for o in context.view_layer.objects if o.visible_get()])
        objects = printable_objects(source)
        if not objects:
            self.report({'ERROR'}, "Select the pieces (and pins) to export")
            return {'CANCELLED'}
        scale = bu_to_mm(context)
        parts = []
        for obj in objects:
            verts, tris = world_triangles(context, obj, scale)
            if len(tris):
                parts.append((obj.name, verts, tris))
        if not parts:
            self.report({'ERROR'}, "The selected objects have no faces")
            return {'CANCELLED'}

        root, _ext = os.path.splitext(bpy.path.abspath(self.filepath))
        try:
            if self.file_format == '3MF':
                path = root + ".3mf"
                write_3mf(path, parts)
                written = [path]
            else:
                written = []
                for name, verts, tris in parts:
                    path = root + ".stl" if len(parts) == 1 \
                        else "%s_%s.stl" % (root, _safe(name))
                    write_stl(path, verts, tris)
                    written.append(path)
        except OSError as e:
            self.report({'ERROR'}, "Couldn't write the file: %s" % e)
            return {'CANCELLED'}

        s = context.scene.print_splitter
        bed = sorted((s.bed_x, s.bed_y, s.bed_z))
        too_big = []
        for name, verts, _tris in parts:
            size = verts.max(0) - verts.min(0)
            print("Print Splitter export: %s %.1f x %.1f x %.1f mm" % (name, *size))
            # Allow any orientation of the piece's box: compare sorted sizes.
            if any(a > b for a, b in zip(sorted(size), bed)):
                too_big.append("%s (%.0f x %.0f x %.0f)" % (name, *size))
        where = (os.path.basename(written[0]) if len(written) == 1
                 else "%d files" % len(written))
        if too_big:
            self.report({'WARNING'}, "Wrote %s. Bigger than the %.0f x %.0f x %.0f mm bed: %s"
                        % (where, s.bed_x, s.bed_y, s.bed_z, ", ".join(too_big)))
        elif len(parts) == 1:
            size = parts[0][1].max(0) - parts[0][1].min(0)
            self.report({'INFO'}, "Wrote %s: %.1f x %.1f x %.1f mm" % (where, *size))
        else:
            self.report({'INFO'}, "Wrote %d pieces to %s; all fit the bed (sizes in the "
                        "system console)" % (len(parts), where))
        return {'FINISHED'}


classes = (PRINTSPLIT_OT_export,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
