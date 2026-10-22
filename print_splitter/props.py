import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, IntProperty,
                       PointerProperty)


def _is_mesh(_self, obj):
    return obj.type == 'MESH'


def _update_previews(self, context):
    # Imported lazily: ops_split imports this module.
    from . import ops_split
    ops_split.refresh_hole_previews(context)


class PrintSplitterSettings(bpy.types.PropertyGroup):
    units: EnumProperty(
        name="Units",
        description="How millimetre values below map to Blender units",
        items=[
            ('MM', "1 unit = 1 mm",
             "Typical for STL/3MF/OBJ models: one Blender unit is one millimetre"),
            ('SCENE', "Scene units",
             "Follow the scene's unit system and unit scale"),
        ],
        default='MM',
        update=_update_previews,
    )

    # ---- cutting ---------------------------------------------------------
    target: PointerProperty(
        name="Object", type=bpy.types.Object, poll=_is_mesh,
        description="Mesh to split. Leave empty to use the active object")
    cut_plane: PointerProperty(
        name="Cut Plane", type=bpy.types.Object,
        description="Object whose position and rotation define the cut. Its local Z "
                    "axis is the cut normal; part A is on that side")
    method: EnumProperty(
        name="Method",
        items=[
            ('BOOLEAN', "Boolean (Exact)",
             "Robust caps for closed meshes, including hollow shells"),
            ('BISECT', "Bisect + Fill",
             "Bisect the mesh and fill the open cut. Use when the mesh is not "
             "watertight and the boolean result is empty or broken"),
        ],
        default='BOOLEAN')
    hole_tolerant: BoolProperty(
        name="Hole Tolerant",
        description="Exact boolean option for meshes with small holes or "
                    "non-manifold edges (slower)",
        default=False)
    separate: FloatProperty(
        name="Pull Apart (mm)", min=0.0, soft_max=200.0, default=0.0,
        description="Move the two parts apart along the cut normal after splitting")

    # ---- registration pins -------------------------------------------------
    use_pins: BoolProperty(name="Registration Pins", default=True)
    pin_count: IntProperty(
        name="Pin Count", min=1, max=32, default=3,
        description="How many pins Auto Place looks for")
    pin_diameter: FloatProperty(
        name="Pin Size (mm)", min=0.5, soft_max=20.0, default=5.0, update=_update_previews,
        description="Hexagon pin size measured corner to corner. It is the "
                    "diameter of the round hole before clearance")
    pin_length: FloatProperty(
        name="Pin Length (mm)", min=1.0, soft_max=60.0, default=12.0,
        update=_update_previews,
        description="Total pin length; half of it goes into each part")
    hole_clearance: FloatProperty(
        name="Clearance (mm)", min=-1.0, soft_max=1.0, default=0.2, update=_update_previews,
        description="Added to the hole diameter. ~0.1-0.3 mm for a glued slip "
                    "fit, 0 or less for a press fit")
    hole_extra_depth: FloatProperty(
        name="Extra Depth (mm)", min=0.0, soft_max=5.0, default=0.6,
        update=_update_previews,
        description="Each hole is this much deeper than half the pin, leaving "
                    "room for glue and so the parts close fully")
    pin_chamfer: FloatProperty(
        name="Pin Chamfer (mm)", min=0.0, soft_max=2.0, default=0.4,
        description="Bevel on the pin ends to help them slide in")
    min_wall: FloatProperty(
        name="Min Wall (mm)", min=0.0, soft_max=10.0, default=1.2,
        description="Material Auto Place keeps around each hole")
    hole_segments: IntProperty(
        name="Hole Segments", min=8, max=256, default=48,
        description="Number of sides of the round holes")
    pin_layout: EnumProperty(
        name="Pins",
        items=[
            ('FLAT', "Lay flat for printing",
             "Pins lie on a flat side in a row next to the parts"),
            ('IN_HOLES', "In the holes", "Preview the pins sitting in the holes"),
            ('NONE', "Don't create", "Only cut the holes"),
        ],
        default='FLAT')

    bed_x: FloatProperty(name="Bed X (mm)", min=10.0, soft_max=1000.0, default=256.0,
                         description="Printer's build width; export warns about pieces that "
                                     "won't fit. 256 suits Bambu X1, P1 and A1")
    bed_y: FloatProperty(name="Bed Y (mm)", min=10.0, soft_max=1000.0, default=256.0,
                         description="Printer's build depth")
    bed_z: FloatProperty(name="Bed Z (mm)", min=10.0, soft_max=1000.0, default=256.0,
                         description="Printer's build height")

    # ---- head fit --------------------------------------------------------
    head_width: FloatProperty(
        name="Width (mm)", min=50.0, soft_max=250.0, default=150.0,
        description="Widest point of the head above the ears, ears not included")
    head_length: FloatProperty(
        name="Length (mm)", min=50.0, soft_max=300.0, default=190.0,
        description="Between the eyebrows to the back of the head, nose not included")
    head_height: FloatProperty(
        name="Height (mm)", min=50.0, soft_max=350.0, default=225.0,
        description="Chin to the top of the head")
    flow: EnumProperty(
        name="Sizing",
        description="What you're sizing. The panel shows the tools for it",
        items=[
            ('HEAD', "Head: mask, helmet, hat", "Fit something worn on the head"),
            ('DISTANCE', "Known distance: scan, photo, any model",
             "Scale anything from two points and the real distance between them"),
            ('BED', "Fit the print bed", "Scale to fill the printer's build volume"),
        ],
        default='HEAD')
    reference: PointerProperty(
        name="Reference", type=bpy.types.Object, poll=_is_mesh,
        description="What you measure against: a head, a body part, a real-world object "
                    "or a calibrated scan")
    item: PointerProperty(
        name="Item", type=bpy.types.Object, poll=_is_mesh,
        description="What you're sizing to the reference, e.g. a mask")
    show_calibrate: BoolProperty(
        name="Imported reference", default=False,
        description="Import a scan or model as the reference and calibrate its size")
    min_clearance: FloatProperty(
        name="Min Gap (mm)", min=0.0, soft_max=30.0, default=3.0,
        description="Smallest gap wanted between reference and item (padding, hair)")
    fit_range: FloatProperty(
        name="Check Range (mm)", min=1.0, soft_max=200.0, default=40.0,
        description="Reference areas further than this from the item are not checked "
                    "(e.g. the neck below a mask)")
    point_fit: EnumProperty(
        name="Fit",
        items=[
            ('SCALE', "Scale only",
             "Resize evenly; the item stays where it is (2+ point pairs)"),
            ('SCALE_MOVE', "Scale and move",
             "Resize evenly and move onto the reference (2+ point pairs)"),
            ('ALIGN', "Scale, move and turn",
             "Best even resize, position and rotation (3+ point pairs)"),
            ('AXES', "Stretch per axis",
             "Resize X, Y and Z separately and move onto the reference. Changes the "
             "shape; needs points spread out in each direction"),
        ],
        default='SCALE_MOVE')
    # ---- known distance ----------------------------------------------------
    known_distance: FloatProperty(
        name="Real Distance (mm)", min=0.001, soft_max=2000.0, default=100.0,
        description="What the distance between points A and B should be")
    measure_mode: EnumProperty(
        name="Scale",
        items=[('UNIFORM', "Uniform", "Scale evenly in every direction: shape stays the same"),
               ('ALONG', "Along A-B only",
                "Stretch or squash only in the direction from A to B")],
        default='UNIFORM')
    # ---- fit the bed -------------------------------------------------------
    bed_fill: FloatProperty(
        name="Fill (%)", min=1.0, max=100.0, default=95.0,
        description="How much of the bed the selection may use, leaving a margin")
    bed_allow_turn: BoolProperty(
        name="Allow turning", default=True,
        description="Size for the best orientation; you may need to turn the "
                    "model in the slicer")
    fit_axes: EnumProperty(
        name="Scale",
        items=[
            ('XYZ', "Uniform", "Scale equally in all directions"),
            ('XY', "Width + Depth", "Keep the height"),
            ('X', "Width only", ""),
        ],
        default='XYZ')


classes = (PrintSplitterSettings,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.print_splitter = PointerProperty(type=PrintSplitterSettings)


def unregister():
    del bpy.types.Scene.print_splitter
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
