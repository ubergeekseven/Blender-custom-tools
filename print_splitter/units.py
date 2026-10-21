"""Millimetre <-> Blender unit conversion.

All lengths in the add-on's settings are entered in millimetres. STL/3MF/OBJ
files carry no units and are almost always in millimetres, so the default
treats one Blender unit as one millimetre. "Scene units" follows the scene's
unit settings instead (e.g. Metric with Unit Scale 0.001).
"""


def mm_to_bu(context):
    settings = context.scene.print_splitter
    if settings.units == 'MM':
        return 1.0
    unit = context.scene.unit_settings
    if unit.system == 'NONE' or unit.scale_length <= 0.0:
        return 1.0
    # Metric and imperial lengths are both stored as metres * scale_length.
    return 0.001 / unit.scale_length


def bu_to_mm(context):
    return 1.0 / mm_to_bu(context)
