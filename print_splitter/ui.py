import bpy

from . import head as head_mod
from . import landmarks
from . import sizing
from .ops_split import get_target, pin_markers
from .units import bu_to_mm


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
        target = get_target(context)
        if s.target is None:
            col.label(text="Using: %s" % (target.name if target else "nothing selected"),
                      icon='INFO')

        _draw_resized_warning(layout, context)
        if target is not None:
            _draw_size_step(layout, context, target)
        row = col.row(align=True)
        row.prop(s, "cut_plane")
        row.operator("print_splitter.add_cut_plane", text="", icon='ADD')

        col = layout.column(align=True)
        col.prop(s, "method")
        if s.method == 'BOOLEAN':
            col.prop(s, "hole_tolerant")
        col.prop(s, "separate")

        layout.prop(s, "units")


def _draw_size_step(layout, context, target):
    box = layout.box()
    status = sizing.size_status(target)
    d = sizing.dims(target) * bu_to_mm(context)
    if status == 'OK':
        box.label(text="1. Size is final", icon='CHECKMARK')
        box.label(text="%.1f × %.1f × %.1f mm" % (d.x, d.y, d.z))
        return
    box.alert = True
    box.label(text="1. Scale before you cut!", icon='ERROR')
    col = box.column(align=True)
    col.label(text="Now %.1f × %.1f × %.1f mm" % (d.x, d.y, d.z))
    if status == 'CHANGED':
        col.label(text="Size changed since you marked it final")
    col.label(text="Pins and holes are made at real")
    col.label(text="size; scaling later breaks the fit.")
    col.label(text="Check it with Head Fit below.")
    box.alert = False
    box.operator("print_splitter.confirm_size", icon='LOCKED')


def _draw_resized_warning(layout, context):
    resized = sizing.resized_after_cut(context.scene.objects)
    if not resized:
        return
    box = layout.box()
    box.alert = True
    box.label(text="Scaled after cutting: pins won't fit", icon='ERROR')
    col = box.column(align=True)
    for obj, ratio in resized[:6]:
        if sizing.HOLE_MM_KEY in obj:
            extra = ", holes now Ø%.2f mm" % (obj[sizing.HOLE_MM_KEY] * ratio)
        elif sizing.PIN_MM_KEY in obj:
            extra = ", pin now %.2f mm" % (obj[sizing.PIN_MM_KEY] * ratio)
        else:
            extra = ""
        col.label(text="%s at %.0f%%%s" % (obj.name, ratio * 100.0, extra))
    if len(resized) > 6:
        col.label(text="…and %d more" % (len(resized) - 6))
    box.alert = False
    box.operator("print_splitter.restore_cut_size", icon='LOOP_BACK')


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
        s = context.scene.print_splitter
        col = self.layout.column(align=True)
        row = col.row(align=True)
        row.label(text="Bed (mm)")
        row.prop(s, "bed_x", text="")
        row.prop(s, "bed_y", text="")
        row.prop(s, "bed_z", text="")
        col.operator("print_splitter.export", icon='EXPORT')


def _draw_points(layout, context):
    s = context.scene.print_splitter
    box = layout.box()
    box.label(text="Reference points", icon='EMPTY_SINGLE_ARROW')
    col = box.column(align=True)
    col.label(text="Shift + right-click a spot to put the")
    col.label(text="cursor there, then Add Point. Mark the")
    col.label(text="same spots on mask and head, in the")
    col.label(text="same order (e.g. crown, temples, chin).")
    n_mask = len(landmarks.points(s.mask))
    n_head = len(landmarks.points(s.head))
    col = box.column(align=True)
    col.label(text="Mask %d points, head %d points" % (n_mask, n_head))
    mp, hp = landmarks.pairs(s.mask, s.head)
    if len(mp) >= 2:
        ratio = landmarks.spread_ratio(mp, hp)
        if ratio is not None:
            col.label(text="Mask needs scaling to %.1f%%" % (ratio * 100.0))
    row = box.row(align=True)
    row.operator("print_splitter.add_point", icon='PIVOT_CURSOR')
    row.operator("print_splitter.clear_points", text="", icon='X')
    box.prop(s, "point_fit")
    box.operator("print_splitter.fit_to_points", icon='CON_SIZELIKE')


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
        _draw_points(layout, context)

        col = layout.column(align=True)
        col.label(text="Clearance")
        col.prop(s, "min_clearance")
        col.prop(s, "fit_range")
        col.operator("print_splitter.check_fit", icon='VIEWZOOM')
        col.prop(s, "fit_axes")
        col.operator("print_splitter.scale_mask_to_fit", icon='FULLSCREEN_EXIT')

        obj = context.active_object
        if obj is not None and obj.type == 'MESH':
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
