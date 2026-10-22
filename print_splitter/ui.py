import bpy

from . import head as head_mod
from . import landmarks
from . import body, library, measure, references
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


# Labels for the reference and the item in each sizing flow.
ROLES = {
    'HEAD': ("Head", "Mask"),
    'DISTANCE': ("Reference", "Item"),
    'BED': ("Reference", "Item"),
}


def _roles(s):
    if s.flow == 'BODY':
        return references.BODY_ROLES[s.body_part]
    if s.flow == 'OBJECT':
        return ("Reference", "Model")
    return ROLES.get(s.flow, ("Reference", "Item"))


def _draw_points(layout, context):
    s = context.scene.print_splitter
    ref_name, item_name = _roles(s)
    box = layout.box()
    box.label(text="Matching points", icon='EMPTY_SINGLE_ARROW')
    col = box.column(align=True)
    col.label(text="Shift + right-click a spot to put the")
    col.label(text="cursor there, or select vertices in Edit")
    col.label(text="Mode (e.g. an eye hole's rim), then Add.")

    ref_labels = landmarks.labels(s.reference)
    item_labels = landmarks.labels(s.item)
    if ref_labels or item_labels:
        col = box.column(align=True)
        for name in ref_labels:
            row = col.row(align=True)
            have = name in item_labels
            row.label(text=name, icon='CHECKBOX_HLT' if have else 'CHECKBOX_DEHLT')
            if have:
                op = row.operator("print_splitter.remove_point", text="", icon='X')
                op.target, op.name = 'ITEM', name
            else:
                op = row.operator("print_splitter.add_point", text="Mark on %s" % item_name)
                op.target, op.name = 'ITEM', name
        for name in item_labels:
            if name not in ref_labels:
                row = col.row(align=True)
                row.label(text="%s (%s only)" % (name, item_name.lower()), icon='ERROR')
                op = row.operator("print_splitter.remove_point", text="", icon='X')
                op.target, op.name = 'ITEM', name

    ip, rp = landmarks.pairs(s.item, s.reference)
    if len(ip) >= 2:
        ratio = landmarks.spread_ratio(ip, rp)
        if ratio is not None:
            box.label(text="%d pairs: %s needs scaling to %.1f%%"
                      % (len(ip), item_name, ratio * 100.0))
    row = box.row(align=True)
    op = row.operator("print_splitter.add_point", text="Add on %s" % ref_name,
                      icon='PIVOT_CURSOR')
    op.target, op.name = 'REFERENCE', ""
    op = row.operator("print_splitter.add_point", text="Add on %s" % item_name)
    op.target, op.name = 'ITEM', ""
    row.operator("print_splitter.clear_points", text="", icon='X')
    box.prop(s, "point_fit")
    box.operator("print_splitter.fit_to_points", text="Fit %s to Points" % item_name,
                 icon='CON_SIZELIKE')


def _draw_measure(layout, context, title="Known distance"):
    s = context.scene.print_splitter
    box = layout.box()
    box.label(text=title, icon='DRIVER_DISTANCE')
    obj = measure.measure_owner(context)
    if obj is None or obj.type != 'MESH':
        box.label(text="Select the object to measure")
        return
    col = box.column(align=True)
    col.label(text="On: %s" % obj.name, icon='OBJECT_DATA')
    col.label(text="Put the cursor on a spot (Shift +")
    col.label(text="right-click) or select vertices, then:")
    row = col.row(align=True)
    row.operator("print_splitter.measure_point", text="Set A").which = 'A'
    row.operator("print_splitter.measure_point", text="Set B").which = 'B'
    m = measure.measured(obj)
    if m is not None:
        col.label(text="A to B now: %.2f mm" % (m[2] * bu_to_mm(context)))
    col = box.column(align=True)
    col.prop(s, "known_distance")
    col.prop(s, "measure_mode", expand=True)
    col.operator("print_splitter.scale_to_distance", icon='FULLSCREEN_ENTER')


def _draw_head_reference(layout, context):
    s = context.scene.print_splitter
    col = layout.column(align=True)
    col.label(text="Head measurements")
    col.prop(s, "head_width")
    col.prop(s, "head_length")
    col.prop(s, "head_height")
    col.label(text="≈ %.0f mm around (tape check)"
              % head_mod.head_circumference(s.head_width, s.head_length))
    row = col.row(align=True)
    row.prop(s, "hat_system", text="")
    row.prop(s, "hat_size")
    row.operator("print_splitter.head_from_hat_size", text="", icon='CHECKMARK')
    col.prop(s, "head_ipd")
    col.prop(s, "head_neck")
    col.operator("print_splitter.add_head", icon='USER')
    col.operator("print_splitter.scale_to_measurements", icon='FULLSCREEN_ENTER')


BODY_FIELDS = {
    'HAND': ("hand_length", "hand_breadth"), 'GRIP': ("grip_diameter", "grip_length"),
    'ARM': ("wrist_circ", "forearm_circ", "forearm_length"), 'FINGER': (),
    'FOOT': ("foot_length", "foot_width"),
    'TORSO': ("chest_circ", "waist_circ", "shoulder_width", "torso_length", "neck_circ"),
    'FIGURE': ("figure_height",),
}


def _draw_body_reference(layout, context):
    s = context.scene.print_splitter
    col = layout.column(align=True)
    col.prop(s, "body_part", text="")
    if s.body_part in ('HAND', 'FOOT'):
        col.prop(s, "body_side", expand=True)
    for field in BODY_FIELDS[s.body_part]:
        col.prop(s, field)
    if s.body_part == 'HAND':
        row = col.row(align=True)
        row.prop(s, "glove_size")
        row.operator("print_splitter.hand_from_glove_size", text="", icon='CHECKMARK')
    if s.body_part == 'FINGER':
        col.prop(s, "ring_system", text="")
        col.prop(s, "ring_size")
        d = body.ring_size_to_diameter(s.ring_system, s.ring_size)
        col.label(text="Inside Ø %.2f mm" % d)
    col.operator("print_splitter.add_body_part",
                 text="Add %s" % references.BODY_NAMES[s.body_part], icon='ADD')


def _draw_object_reference(layout, context):
    s = context.scene.print_splitter
    col = layout.column(align=True)
    col.prop(s, "library_item", text="")
    col.label(text=library.CATALOGUE[s.library_item][1])
    col.operator("print_splitter.add_library_item", icon='ADD')


def _draw_import(layout, context, use_as='REFERENCE'):
    row = layout.row(align=True)
    row.operator("print_splitter.import_model", icon='IMPORT').use_as = use_as
    row.operator("print_splitter.add_reference_image", text="Image", icon='IMAGE_DATA')


def _draw_match(layout, context, clearance=True):
    s = context.scene.print_splitter
    ref_name, item_name = _roles(s)
    col = layout.column(align=True)
    col.prop(s, "reference", text=ref_name)
    col.prop(s, "item", text=item_name)
    _draw_points(layout, context)
    if not clearance:
        return
    col = layout.column(align=True)
    col.label(text="Clearance")
    col.prop(s, "min_clearance")
    col.prop(s, "fit_range")
    col.operator("print_splitter.check_fit", icon='VIEWZOOM')
    col.prop(s, "fit_axes")
    col.operator("print_splitter.scale_mask_to_fit", icon='FULLSCREEN_EXIT')
    if s.flow == 'HEAD':
        col = layout.column(align=True)
        col.label(text="Eyes")
        col.operator("print_splitter.check_eyes", icon='HIDE_OFF')


class PRINTSPLIT_PT_fit(_Panel, bpy.types.Panel):
    bl_label = "Scale & Fit"

    def draw(self, context):
        s = context.scene.print_splitter
        layout = self.layout
        layout.prop(s, "flow", text="")

        if s.flow == 'HEAD':
            _draw_head_reference(layout, context)
            layout.prop(s, "show_calibrate",
                        icon='TRIA_DOWN' if s.show_calibrate else 'TRIA_RIGHT')
            if s.show_calibrate:
                box = layout.box()
                box.label(text="Use a head scan or model instead:")
                _draw_import(box, context)
                _draw_measure(box, context, "Calibrate it")
            _draw_match(layout, context)
        elif s.flow in ('BODY', 'OBJECT'):
            if s.flow == 'BODY':
                _draw_body_reference(layout, context)
            else:
                _draw_object_reference(layout, context)
            _draw_match(layout, context)
        elif s.flow == 'DISTANCE':
            layout.label(text="Bring in a model, scan or photo:")
            _draw_import(layout, context, 'NONE')
            _draw_measure(layout, context)
        elif s.flow == 'BED':
            col = layout.column(align=True)
            row = col.row(align=True)
            row.label(text="Bed (mm)")
            row.prop(s, "bed_x", text="")
            row.prop(s, "bed_y", text="")
            row.prop(s, "bed_z", text="")
            col.prop(s, "bed_fill")
            col.prop(s, "bed_allow_turn")
            col.operator("print_splitter.scale_to_bed", icon='FULLSCREEN_ENTER')

        obj = context.active_object
        if obj is not None and obj.type == 'MESH':
            d = obj.dimensions * bu_to_mm(context)
            box = layout.box()
            box.label(text=obj.name, icon='OBJECT_DATA')
            box.label(text="%.1f × %.1f × %.1f mm" % (d.x, d.y, d.z))


classes = (
    PRINTSPLIT_PT_fit,
    PRINTSPLIT_PT_split,
    PRINTSPLIT_PT_pins,
    PRINTSPLIT_PT_do_split,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
