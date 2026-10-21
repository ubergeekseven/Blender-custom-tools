import bpy

from . import head as head_mod
from .ops_split import get_target, pin_markers


class _Panel:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Print Split"


class PRINTSPLIT_PT_split(_Panel, bpy.types.Panel):
    bl_label = "Split for Printing"

    def draw(self, context):
        s = context.scene.print_splitter
        layout = self.layout

        col = layout.column(align=True)
        col.prop(s, "target")
        if s.target is None:
            target = get_target(context)
            col.label(text="Using: %s" % (target.name if target else "nothing selected"),
                      icon='INFO')
        row = col.row(align=True)
        row.prop(s, "cut_plane")
        row.operator("print_splitter.add_cut_plane", text="", icon='ADD')

        col = layout.column(align=True)
        col.prop(s, "method")
        if s.method == 'BOOLEAN':
            col.prop(s, "hole_tolerant")
        col.prop(s, "separate")

        layout.prop(s, "units")


class PRINTSPLIT_PT_pins(_Panel, bpy.types.Panel):
    bl_label = "Registration Pins"
    bl_parent_id = "PRINTSPLIT_PT_split"

    def draw_header(self, context):
        self.layout.prop(context.scene.print_splitter, "use_pins", text="")

    def draw(self, context):
        s = context.scene.print_splitter
        layout = self.layout
        layout.active = s.use_pins

        col = layout.column(align=True)
        col.prop(s, "pin_diameter")
        col.prop(s, "pin_length")
        col.prop(s, "hole_clearance")
        col.prop(s, "hole_extra_depth")
        col.prop(s, "pin_chamfer")
        hole = s.pin_diameter + s.hole_clearance
        flats = s.pin_diameter * 0.8660254
        col.label(text="Hole Ø %.2f, %.2f deep each side" %
                  (hole, s.pin_length * 0.5 + s.hole_extra_depth))
        col.label(text="Pin across flats %.2f" % flats)

        col = layout.column(align=True)
        col.prop(s, "pin_count")
        col.prop(s, "min_wall")
        col.operator("print_splitter.auto_place_pins", icon='SNAP_FACE_CENTER')
        row = col.row(align=True)
        row.operator("print_splitter.add_pin", icon='PIVOT_CURSOR')
        row.operator("print_splitter.clear_pins", icon='X')
        col.label(text="%d pin markers" % len(pin_markers(s.cut_plane)))

        col = layout.column(align=True)
        col.prop(s, "pin_layout")
        col.prop(s, "hole_segments")


class PRINTSPLIT_PT_do_split(_Panel, bpy.types.Panel):
    bl_label = "Cut"
    bl_parent_id = "PRINTSPLIT_PT_split"
    bl_options = {'HIDE_HEADER'}

    def draw(self, context):
        col = self.layout.column(align=True)
        col.scale_y = 1.4
        col.operator("print_splitter.split", icon='MOD_BOOLEAN')
        self.layout.operator("print_splitter.cut_face_down", icon='TRIA_DOWN_BAR')


class PRINTSPLIT_PT_fit(_Panel, bpy.types.Panel):
    bl_label = "Head Fit"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        s = context.scene.print_splitter
        layout = self.layout

        col = layout.column(align=True)
        col.label(text="Head measurements")
        col.prop(s, "head_width")
        col.prop(s, "head_length")
        col.prop(s, "head_height")
        col.label(text="≈ %.0f mm around (tape check)"
                  % head_mod.head_circumference(s.head_width, s.head_length))
        col.operator("print_splitter.add_head", icon='USER')
        col.operator("print_splitter.scale_to_measurements", icon='FULLSCREEN_ENTER')

        col = layout.column(align=True)
        col.prop(s, "head")
        col.prop(s, "mask")
        col.prop(s, "min_clearance")
        col.prop(s, "fit_range")
        col.operator("print_splitter.check_fit", icon='VIEWZOOM')
        col.prop(s, "fit_axes")
        col.operator("print_splitter.scale_mask_to_fit", icon='FULLSCREEN_EXIT')

        obj = context.active_object
        if obj is not None and obj.type == 'MESH':
            from .units import bu_to_mm
            d = obj.dimensions * bu_to_mm(context)
            box = layout.box()
            box.label(text=obj.name, icon='OBJECT_DATA')
            box.label(text="%.1f × %.1f × %.1f mm" % (d.x, d.y, d.z))


classes = (
    PRINTSPLIT_PT_split,
    PRINTSPLIT_PT_pins,
    PRINTSPLIT_PT_do_split,
    PRINTSPLIT_PT_fit,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
