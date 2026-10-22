"""Operators adding body-part and real-world references to the scene."""

import bpy

from . import body, library
from .ops_fit import make_reference
from .units import mm_to_bu

# What the reference and the item are called for each body part.
BODY_ROLES = {
    'HAND': ("Hand", "Glove"), 'GRIP': ("Grip", "Handle"), 'ARM': ("Arm", "Bracer"),
    'FINGER': ("Finger", "Ring"), 'FOOT': ("Foot", "Shoe"), 'TORSO': ("Torso", "Armour"),
    'FIGURE': ("Person", "Prop"),
}
BODY_NAMES = {'HAND': "Hand", 'GRIP': "Grip", 'ARM': "Forearm", 'FINGER': "Finger",
              'FOOT': "Foot", 'TORSO': "Torso", 'FIGURE': "Person"}


def build_body_part(s, mm):
    right = s.body_side == 'RIGHT'
    part = s.body_part
    if part == 'HAND':
        return body.hand(s.hand_length * mm, s.hand_breadth * mm, right)
    if part == 'GRIP':
        return body.grip(s.grip_diameter * mm, s.grip_length * mm)
    if part == 'ARM':
        return body.forearm(s.wrist_circ * mm, s.forearm_circ * mm, s.forearm_length * mm)
    if part == 'FINGER':
        d = body.ring_size_to_diameter(s.ring_system, s.ring_size)
        return body.finger(d * mm, 30.0 * mm)
    if part == 'FOOT':
        return body.foot(s.foot_length * mm, s.foot_width * mm, right)
    if part == 'TORSO':
        return body.torso(s.chest_circ * mm, s.waist_circ * mm, s.shoulder_width * mm,
                          s.torso_length * mm, s.neck_circ * mm)
    return body.figure(s.figure_height * mm)


class PRINTSPLIT_OT_add_body_part(bpy.types.Operator):
    """Add the chosen body part sized to the measurements, at the 3D cursor,
    with named points ready to match"""
    bl_idname = "print_splitter.add_body_part"
    bl_label = "Add Body Part"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.print_splitter
        if s.body_part == 'FINGER':
            d = body.ring_size_to_diameter(s.ring_system, s.ring_size)
            if d <= 1.0:
                self.report({'ERROR'}, "That ring size is too small")
                return {'CANCELLED'}
        bm, points = build_body_part(s, mm_to_bu(context))
        name = BODY_NAMES[s.body_part]
        if s.body_part in ('HAND', 'FOOT'):
            name = "%s %s" % (s.body_side.title(), name.lower())
        make_reference(context, name, bm, points, smooth=s.body_part != 'GRIP')
        return {'FINISHED'}


class PRINTSPLIT_OT_hand_from_glove_size(bpy.types.Operator):
    """Set the hand width from a glove size (circumference round the knuckles
    in inches)"""
    bl_idname = "print_splitter.hand_from_glove_size"
    bl_label = "Use Glove Size"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.print_splitter
        # Round the knuckles is about 2.5 times the width across them.
        s.hand_breadth = s.glove_size * 25.4 / 2.5
        self.report({'INFO'}, "Hand width %.1f mm" % s.hand_breadth)
        return {'FINISHED'}


class PRINTSPLIT_OT_add_library_item(bpy.types.Operator):
    """Add the chosen real-world object at its real size, at the 3D cursor,
    with named points (corners, ends, holes) ready to match"""
    bl_idname = "print_splitter.add_library_item"
    bl_label = "Add Object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.print_splitter
        bm, points = library.build(s.library_item, mm_to_bu(context))
        name = library.CATALOGUE[s.library_item][0]
        make_reference(context, name, bm, points, smooth=False)
        return {'FINISHED'}


classes = (PRINTSPLIT_OT_add_body_part, PRINTSPLIT_OT_hand_from_glove_size,
           PRINTSPLIT_OT_add_library_item)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
