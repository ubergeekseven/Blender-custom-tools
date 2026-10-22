import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, IntProperty,
                       PointerProperty)

from . import library


def _is_mesh(_self, obj):
    return obj.type == 'MESH'


def _update_previews(self, context):
    # Imported lazily: ops_split imports this module.
    from . import ops_split
    ops_split.refresh_hole_previews(context)


def _update_screw(self, context):
    from . import connectors
    connectors.apply_screw_defaults(self)
    _update_previews(self, context)


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

    # ---- connectors --------------------------------------------------------
    connector: EnumProperty(
        name="Join With",
        items=[('PINS', "Pins", "Hexagonal pins in round holes, glued"),
               ('MAGNETS', "Magnets", "A pocket for a disc magnet on each side, so the "
                                      "pieces come apart"),
               ('SCREWS', "Screws", "A screw through piece A into a heat-set insert or "
                                    "tapped hole in piece B")],
        default='PINS', update=_update_previews)
    magnet_diameter: FloatProperty(name="Magnet Ø (mm)", min=1.0, soft_max=30.0, default=6.0,
                                   update=_update_previews)
    magnet_thickness: FloatProperty(name="Magnet Thickness (mm)", min=0.5, soft_max=10.0,
                                    default=3.0, update=_update_previews)
    magnet_clearance: FloatProperty(
        name="Clearance (mm)", min=-0.5, soft_max=1.0, default=0.2, update=_update_previews,
        description="Added to the pocket diameter. Around 0.1-0.2 for a press fit")
    magnet_depth_extra: FloatProperty(
        name="Extra Depth (mm)", min=0.0, soft_max=2.0, default=0.2, update=_update_previews,
        description="Pocket depth beyond the magnet's thickness, for glue")
    screw_size: EnumProperty(
        name="Screw", items=[(k, k, "") for k in ('M2', 'M2.5', 'M3', 'M4', 'M5')],
        default='M3', update=_update_screw)
    screw_anchor: EnumProperty(
        name="Into",
        items=[('INSERT', "Heat-set insert", "A hole sized for a brass insert"),
               ('TAP', "Tapped plastic", "A pilot hole the screw cuts its own thread in")],
        default='INSERT', update=_update_screw)
    screw_clearance: FloatProperty(name="Clearance Hole Ø (mm)", min=0.5, soft_max=10.0,
                                   default=3.4, update=_update_previews)
    screw_head_d: FloatProperty(name="Head Recess Ø (mm)", min=1.0, soft_max=15.0, default=5.9,
                                description="Counterbore for the screw head")
    screw_anchor_d: FloatProperty(name="Insert/Pilot Hole Ø (mm)", min=0.5, soft_max=10.0,
                                  default=4.0, update=_update_previews)
    screw_anchor_depth: FloatProperty(name="Insert/Pilot Depth (mm)", min=1.0, soft_max=30.0,
                                      default=6.7, update=_update_previews)
    screw_floor: FloatProperty(
        name="Under Head (mm)", min=0.5, soft_max=20.0, default=3.0,
        description="Material left between the screw head and the cut")
    screw_from_b: BoolProperty(name="Head on Piece B", default=False,
                               description="Put the screw heads on piece B instead of A")
    auto_connectors: BoolProperty(
        name="Auto Place Connectors", default=True,
        description="When splitting at all planes, place connectors on every cut")
    hollow_wall: FloatProperty(name="Wall (mm)", min=0.4, soft_max=10.0, default=2.0,
                               description="Wall thickness left when hollowing")
    hollow_drain: FloatProperty(
        name="Drain Hole Ø (mm)", min=0.0, soft_max=15.0, default=0.0,
        description="Hole through the lowest point, e.g. for resin printing. 0: none")

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
    head_ipd: FloatProperty(
        name="Pupil Distance (mm)", min=30.0, soft_max=85.0, default=63.0,
        description="Centre of one pupil to the other, looking into the distance. "
                    "Adults are about 54-74 mm, children often 48-56")
    head_neck: BoolProperty(name="Neck", default=True,
                            description="Add a neck under the head")
    hat_system: EnumProperty(
        name="Hat Size",
        items=[('US', "US/UK", "Hat sizes like 7 1/4 (enter 7.25)"),
               ('EU', "EU (cm)", "Hat sizes like 58: the circumference in cm")],
        default='US')
    hat_size: FloatProperty(name="Size", min=1.0, soft_max=70.0, default=7.25,
                            description="The hat size to set the head from")
    # ---- body parts --------------------------------------------------------
    body_part: EnumProperty(
        name="Body Part",
        items=[('HAND', "Hand", "Gloves, gauntlets, claws"),
               ('GRIP', "Grip", "Handles for props, tools and swords"),
               ('ARM', "Wrist and forearm", "Bracers, cuffs, watch bands"),
               ('FINGER', "Finger", "Rings"),
               ('FOOT', "Foot", "Shoe parts, insoles, costume feet"),
               ('TORSO', "Torso", "Armour, chest pieces"),
               ('FIGURE', "Whole body", "Size props against a person")],
        default='HAND')
    body_side: EnumProperty(name="Side", items=[('RIGHT', "Right", ""), ('LEFT', "Left", "")],
                            default='RIGHT')
    hand_length: FloatProperty(
        name="Hand Length (mm)", min=50.0, soft_max=260.0, default=180.0,
        description="Wrist crease to the tip of the middle finger")
    hand_breadth: FloatProperty(
        name="Hand Width (mm)", min=30.0, soft_max=130.0, default=84.0,
        description="Across the knuckles, thumb not included")
    glove_size: FloatProperty(
        name="Glove Size", min=4.0, soft_max=13.0, default=8.5,
        description="Glove size: the hand's circumference round the knuckles in inches")
    grip_diameter: FloatProperty(name="Grip Diameter (mm)", min=5.0, soft_max=80.0,
                                 default=35.0, description="Comfortable handle thickness")
    grip_length: FloatProperty(name="Grip Length (mm)", min=10.0, soft_max=400.0,
                               default=100.0)
    wrist_circ: FloatProperty(name="Wrist Around (mm)", min=50.0, soft_max=300.0,
                              default=165.0, description="Circumference at the wrist bone")
    forearm_circ: FloatProperty(name="Forearm Around (mm)", min=80.0, soft_max=450.0,
                                default=260.0, description="Circumference at the widest point")
    forearm_length: FloatProperty(name="Forearm Length (mm)", min=80.0, soft_max=450.0,
                                  default=260.0, description="Wrist to elbow")
    ring_system: EnumProperty(
        name="Ring Size",
        items=[('US', "US/Canada", "Sizes like 7 or 7.5"),
               ('EU', "EU / ISO", "The inside circumference in mm, like 54"),
               ('DIAMETER', "Diameter (mm)", "The inside diameter")],
        default='US')
    ring_size: FloatProperty(name="Size", min=0.0, soft_max=80.0, default=7.0)
    foot_length: FloatProperty(name="Foot Length (mm)", min=60.0, soft_max=350.0,
                               default=260.0, description="Heel to the longest toe")
    foot_width: FloatProperty(name="Foot Width (mm)", min=30.0, soft_max=150.0,
                              default=100.0, description="Widest point, across the ball")
    chest_circ: FloatProperty(name="Chest Around (mm)", min=300.0, soft_max=1600.0,
                              default=960.0)
    waist_circ: FloatProperty(name="Waist Around (mm)", min=300.0, soft_max=1600.0,
                              default=820.0)
    shoulder_width: FloatProperty(name="Shoulder Width (mm)", min=150.0, soft_max=600.0,
                                  default=400.0, description="Shoulder tip to shoulder tip")
    torso_length: FloatProperty(name="Torso Length (mm)", min=150.0, soft_max=800.0,
                                default=450.0, description="Waist to the base of the neck")
    neck_circ: FloatProperty(name="Neck Around (mm)", min=150.0, soft_max=600.0, default=380.0)
    figure_height: FloatProperty(name="Height (mm)", min=10.0, soft_max=2500.0, default=1700.0)
    # ---- real-world objects ------------------------------------------------
    library_item: EnumProperty(name="Object", items=library.enum_items(), default='CARD')
    flow: EnumProperty(
        name="Sizing",
        description="What you're sizing. The panel shows the tools for it",
        items=[
            ('HEAD', "Head: mask, helmet, hat", "Fit something worn on the head"),
            ('BODY', "Body part: glove, bracer, ring, armour",
             "Fit something worn on the body, or size a prop to a person"),
            ('OBJECT', "Real-world object: card, battery, board",
             "Size against something with known measurements"),
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
