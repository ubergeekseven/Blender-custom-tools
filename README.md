# Blender custom tools

Blender add-ons for 3D printing work.

## Print Splitter

Get a model to the right real-world size, then cut it into printable pieces.

* **Scale & Fit:** size models against a head, a body part, a real-world
  object (card, battery, board…), a scan or photo with a known distance, or
  the print bed.
* **Split:** cut with planes at any angle. Every piece gets a flat, closed cut
  face and pins, magnet pockets or screw holes to join it back up. It can also
  work out the cuts that make a big model fit your bed, and hollow pieces.
* **Export:** 3MF or STL at true millimetre size for the slicer.

Works with Blender 4.2 and newer as an extension, and should also work as a
legacy add-on in 3.6 to 4.1 (only 5.1 is tested).

### Install

Download `print_splitter-<version>.zip` from the
[Releases](https://github.com/ubergeekseven/Blender-custom-tools/releases)
page; don't unzip it. Or build it yourself:

```
python tools/build_zip.py        # writes dist/print_splitter-<version>.zip
```

* **Blender 4.2+:** Edit > Preferences > Get Extensions > ⌄ (top right) >
  Install from Disk… and pick the zip.
* **Blender 3.6–4.1:** Edit > Preferences > Add-ons > Install… and pick the zip.

The tools are in the 3D Viewport sidebar (press **N**), on the **Print Split** tab.

### Scale & Fit

Pick what you're sizing at the top of the panel; the panel then shows the
tools for that job. Every workflow has a **reference** (what you measure
against) and an **item** (what you're sizing), named for the job: head and
mask, hand and glove, finger and ring…

#### Matching points

Most workflows size the item by **matching points**. A point marks the same
spot on both, such as the crown of the head on the head and on the mask.

* Shift + right-click a surface to put the 3D cursor there, then click
  **Add on …**. In Edit Mode, the point goes at the centre of the selected
  vertices instead. Select an eye hole's rim to mark the hole's centre.
* Points have names and pair up by name. Built-in references come with their
  points already placed; the panel lists them, and **Mark on …** adds the
  matching one to the item. Points you place yourself are called Point 1,
  Point 2…, and Point 1 on one pairs with Point 1 on the other.
* The panel shows how much the item needs scaling. **Fit … to Points** then:
  * **Scale only:** resizes evenly; the item stays where it is (2+ pairs).
  * **Scale and move:** also moves it onto the reference (2+ pairs).
  * **Scale, move and turn:** best fit of size, position and rotation (3+ pairs).
  * **Stretch per axis:** resizes X, Y and Z separately. This changes the
    shape, so only use it when you mean to; it needs points spread out in
    every direction.

**Clearance** (head and body workflows):
* **Check Fit** colours the reference: red where it goes into the item,
  orange where the gap is under *Min Gap*, green where it fits, grey where the
  item is out of range.
* **Scale to Clearance** grows or shrinks the item about the reference's
  centre until the closest gap is exactly *Min Gap*.

#### Head: masks, helmets, hats

1. Measure the head:
   * **Width:** widest point above the ears, ears not included.
   * **Length:** between the eyebrows to the furthest point at the back.
   * **Height:** chin to the top of the head (a book flat on the head helps).
   * **Pupil distance:** centre to centre, looking into the distance (adults
     about 54–74 mm, children often 48–56). An optician has this number, or
     measure it in a mirror with a ruler.

   The panel shows the circumference those numbers imply; check it against a
   tape measure. Or enter a hat size (US/UK like 7¼, or EU in cm) to set width
   and length.
2. **Add Head From Measurements** builds a head with eyes at the pupil
   distance, a neck, and named points: crown, eyes, nose tip, chin, ears and
   back of head.
3. Pick the mask as the item and mark its matching spots: the crown, the
   centre of each eye hole (select the hole's rim in Edit Mode, then
   **Mark on Mask**), the chin…
4. **Fit Mask to Points**, then **Check Fit** and **Scale to Clearance**.
5. **Check Eyes** reports, for each eye, how many degrees are clear outward,
   inward, up and down through the mask, whether straight ahead is clear, and
   how far each marked eye hole is from the line of sight. It draws the
   limits as sight lines.

**Your own head scan** is the most accurate reference. A phone app
(Polycam, KIRI Engine, Scaniverse) can make one. Open *Imported reference*:
**Import Scan or Model** brings it in at real size, guessing metres for
scans. Then calibrate it with a known distance (below), and mark the eyes and
other points on it with **Add on Head** using the same names.
**Scale Head Model to Measurements** stretches a head model's whole bounding
box to your three measurements. Don't use it on a mask: ears or horns would
count toward its size.

#### Body part: gloves, bracers, rings, armour, props

Choose a part, enter its measurements and click **Add …**. Each comes with
named points:

| Part | Measurements | Points |
|---|---|---|
| Hand (left/right) | length (wrist crease to middle fingertip), width across the knuckles, or glove size | wrist, each fingertip, thumb tip |
| Grip | diameter, length | top, bottom |
| Wrist and forearm | wrist and forearm circumference, wrist to elbow | wrist, elbow, outsides |
| Finger | ring size: US/Canada, EU/ISO (inside circumference) or diameter | base, tip |
| Foot (left/right) | length, width at the ball | heel, toe tip, ball inside/outside |
| Torso | chest, waist and neck circumference, shoulder width, waist to neck | neck front/back, shoulders, chest, waist |
| Whole body | height | top of head, chin, shoulders, hands, heels |

#### Real-world object

Add an object at its real size with named points: an ID/bank card,
A4/A5/Letter paper, 150/300 mm rulers, coins, batteries (AA to D, 9 V,
18650, 21700, coin cells), 3 and 5 mm LEDs, Arduino Uno/Nano, Raspberry Pi
Pico, 4/5 and Zero and ESP32 boards, disc magnets, miniature bases and
28/32 mm scale figures. Board sizes marked *approx.* vary by maker.

A typical use: photograph something next to a bank card, bring the photo in
with **Image**, add the card, mark its four corners on the photo and **Fit to
Points**. The photo is now true size.

#### Known distance: scans, photos, any model

**Import Scan or Model** (STL, OBJ, PLY, glTF, FBX, with a units choice) or
**Image** (a photo on a plane, facing front, side or top). Then:

1. Select the object, put the cursor on a spot whose position you know and
   click **Set A**; do the same for **Set B**. The panel shows the current
   distance.
2. Type the **Real Distance** and click **Scale to Match**. **Uniform** keeps
   the shape; **Along A-B only** stretches just in that direction.

#### Fit the print bed

Scales the selection evenly to fill the bed (with a margin). *Allow turning*
sizes for the best orientation.

### Splitting a model

**Get the size right first.** Holes, pins, pockets and screw holes are made at
their real size, so scaling pieces after cutting makes them stop fitting. The
Split panel shows the model's size with a **Size Is Final** button; if you
haven't clicked it, **Split** asks before cutting. If pieces or pins are
scaled after cutting, even with the scale applied, the panel lists them with
their new sizes, and **Undo Scaling After Cut** puts them back.

1. Select the model and click **+** next to *Cut Plane*. A grid plane appears
   through the middle. Its blue Z axis is the cut direction: the piece on that
   side becomes `<name>_A`, the other `<name>_B`.
2. Move and rotate the plane (G, R) to where you want the cut.
3. Under **Connectors**, choose how the pieces join, then **Auto Place**. It
   finds spots on the cut with enough material and marks each with a wire
   cylinder. Drag them around, add one at the 3D cursor, or clear them.
4. **Split**. The original is hidden, not deleted.
5. Select the pieces and **Cut Face Down** to rest each on its cut face at Z = 0.
6. **Export for Printing** (see below).

To cut again, click any piece and add a new plane; it goes on the selected
piece. Cutting `Mask_B` gives `Mask_B_A` and `Mask_B_B`.

#### Connectors

* **Pins:** hexagonal pins printed lying on a flat side, so layer lines run
  along the pin, in round holes with the corners against the wall.
  * *Pin Size* is corner to corner, and *Pin Length* is the total; half goes
    into each piece.
  * *Clearance* is added to the hole: 0.1–0.3 mm for a glued fit, 0 or less to
    press fit.
  * *Extra Depth* leaves room for glue, and *Pin Chamfer* bevels the ends.
* **Magnets:** a pocket for a disc magnet on each side, so the pieces come
  apart (detachable ears, lids). Check the polarity before gluing magnets in.
* **Screws** (M2–M5):
  * Piece A gets a clearance hole out to its outer surface, with a recess for
    the head and *Under Head* mm of material left above the cut. *Head on
    Piece B* swaps the sides.
  * Piece B gets a hole for a brass heat-set insert, or a pilot hole the screw
    taps into.
  * Split tells you the screw length to buy, e.g. "use M3 x 8 mm screws".
  * Sizes come from a table of typical values; check them against your
    inserts' datasheet.

Holes are cut as true circles (the polygon sits outside the circle), so a hole
is never smaller than the size shown.

#### Auto split and hollow

* **Suggest Cuts to Fit Bed** adds the fewest evenly spaced cut planes that
  make every piece fit the bed (with the *Fill* margin). They're ordinary cut
  planes: move or turn them, or add your own.
* **Split at All Planes** cuts at every visible plane in the order they were
  added, splitting each piece a plane crosses. With *Auto Place Connectors* on,
  every cut gets connectors; markers you placed on a plane are used where
  they fall inside a piece. Pieces are named `<name>_part_01`, `_02`…
* **Hollow** turns the selected object into a shell with *Wall* thickness,
  with an optional drain hole through its lowest point. Hollow after
  splitting, so connector holes keep a wall round them.

#### Methods

* **Boolean (Exact)**, the default: Blender's Exact boolean solver. It handles
  hollow shells (where the cut face is a ring) and multiple islands. The mesh
  should be watertight.
* **Bisect + Fill:** cuts the mesh and fills the open cut. Try it, or *Hole
  Tolerant*, if the boolean gives an empty or broken piece.

### Exporting for the slicer

**Export for Printing** (under Split) writes the selected pieces and pins at
true size in millimetres:

* **3MF** (default): one file holding every piece, stating it's in
  millimetres. Bambu Studio, OrcaSlicer, PrusaSlicer and Cura load each piece
  as its own object.
* **STL:** one file per piece, named after it. STL has no units; slicers read
  it as millimetres.

Cut planes and hole markers are left out even if selected. The status bar
shows the size, and the system console lists every piece. Set **Bed** to your
printer's build volume (256 × 256 × 256 mm suits Bambu X1, P1 and A1). Export
warns about pieces too big for it in every orientation.

### Units

Settings are in millimetres. By default one Blender unit is one millimetre,
which is what STL, 3MF and OBJ files from printing sites use. Choose *Scene
units* if your scene uses Metric with a unit scale.

With the default, Blender's own panels may label sizes in metres (a 150 mm
head shows as "150 m") when the scene is Metric at Unit Scale 1. The model is
fine; only the label is off. Export for Printing always writes true
millimetres. Other exporters may apply the scene's unit scale and write the
wrong size, so check sizes in the slicer if you use them.

### Releasing

1. Bump `version` in `print_splitter/blender_manifest.toml` (and `bl_info` in
   `print_splitter/__init__.py`).
2. On GitHub: Releases > Draft a new release > create tag `v<version>` >
   Publish. The Release workflow runs the tests, builds the zip and attaches
   it to the release.

### Tests

Tests run in real Blender, without a window:

```
blender -b --factory-startup --python tests/test_print_splitter.py
# or, with the PyPI module (pip install bpy):
python tests/test_print_splitter.py
```
