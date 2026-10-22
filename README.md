# Blender custom tools

Blender add-ons for 3D printing work.

## Print Splitter

Cut a model into printable pieces with a plane you can place at any angle.
Each piece gets a flat, closed face where it was cut, round holes for
registration pins, and hexagonal pins to print. A second panel builds a head
sized from three measurements and checks how a mask fits on it.

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

### Splitting a model

**Get the size right first.** Pin holes and pins are made at their real size,
so scaling pieces after cutting makes the pins stop fitting. Scaling
everything together still shrinks or grows the pins and changes the
clearance. The panel's first step shows the model's size and a **Size Is
Final** button; if you haven't clicked it, **Split** asks before cutting. The
Head Fit panel below helps you pick the size. Pieces cut from a model marked
final are marked final too.

If pieces or pins get scaled after cutting, even with the scale applied, the
panel lists them with their new hole and pin sizes. **Undo Scaling After
Cut** puts them back.

1. Select the model and click **+** next to *Cut Plane*. A grid plane appears
   through the middle of the model. Its blue Z axis is the cut direction: the
   piece on that side becomes `<name>_A`, the other one `<name>_B`.
2. Move and rotate the plane (G, R) to where you want the cut.
3. Under **Registration Pins**, set the pin size, length and clearance, then
   click **Auto Place Pins**. It finds spots on the cut with enough material
   around them and puts a wire cylinder (the hole) on each. You can drag them
   around, add one at the 3D cursor or clear them. They stay attached to the
   plane.
4. Click **Split**. The original is hidden, not deleted. You get two closed
   pieces with flat cut faces and holes, plus the pins.
5. Select the pieces and click **Cut Face Down** to rest each one on its cut
   face at Z = 0.
6. Select the pieces and pins and click **Export for Printing** (see below).

To cut again, click any piece (an original or one you already cut) and click
**+** for a new plane. The new plane goes on the selected piece, and you can
set a different angle and different pins. Repeat as many times as you like.
Pieces are named after where they came from: cutting `Mask_B` gives
`Mask_B_A` and `Mask_B_B`. Each plane keeps its own pin markers, and earlier
cuts and pins stay as they are.

#### Pin sizing

The pins are hexagonal prisms meant to be printed lying on a flat side, so
the layer lines run along the pin and it doesn't snap at a layer. They go
into round holes, with the hexagon's corners against the hole wall.

| Setting | Meaning |
|---|---|
| Pin Size | Hexagon measured corner to corner (the panel also shows across-flats) |
| Pin Length | Total length; half goes into each piece |
| Clearance | Added to the hole diameter. 0.1–0.3 mm for a glued fit, 0 or less for a press fit |
| Extra Depth | Each hole is this much deeper than half the pin, for glue and so the pieces close fully |
| Pin Chamfer | Bevel on the pin ends so they start into the hole easily |
| Min Wall | Material Auto Place keeps around each hole |

Holes are cut as true circles (the polygon sits outside the circle), so a
hole is never smaller than the size shown in the panel.

#### Methods

* **Boolean (Exact)**, the default: uses Blender's Exact boolean solver. It
  handles hollow shells, where the cut face is a ring, and multiple islands.
  The mesh should be watertight.
* **Bisect + Fill:** cuts the mesh and fills the open cut. Try it, or *Hole
  Tolerant*, if the boolean gives an empty or broken piece.

If a pin hole would break through the surface, Split still runs and warns you
which pin it was.

### Checking how a mask fits a head

Open the **Head Fit** panel.

1. Measure the head:
   * **Width:** widest point above the ears, ears not included.
   * **Length:** between the eyebrows to the furthest point at the back.
   * **Height:** chin to the top of the head. A book flat on the head makes
     this easier.

   The panel shows the head circumference those numbers imply. Check it
   against a tape measure around the forehead; the tape usually reads a few
   percent more.
2. Click **Add Head From Measurements** for a generic head of that size, which
   faces −Y with Z up. To use your own head model instead (a scan, say),
   select it and click **Scale Head Model to Measurements**. Don't use that
   button on the mask: it sizes the whole bounding box, so ears or horns
   would count toward the head's height.
3. Pick the head and the mask, then size and place the mask with
   **reference points**:
   * Shift + right-click a spot on the mask to put the 3D cursor there, then
     click **Add Point**. The point goes on whichever of mask and head is
     nearer the cursor.
   * Mark the same spot on the head, then repeat for a few more spots in the
     same order. Mask point 1 pairs with head point 1, and so on. Good spots
     are easy to find on both: crown, left and right temple, chin, back of
     the head.
   * The panel shows how much the mask needs scaling. **Fit Mask to Points**
     applies it. *Scale only* resizes the mask in place; *Scale and move*
     also moves it onto the head (two or more pairs); *Scale, move and turn*
     also rotates it to the best fit (three or more pairs).

   Points on the outside of the mask sit a wall's thickness away from the
   head's skin, so this gets the size close, not exact. The next steps add
   the breathing room.
4. **Check Fit** colours the head:
   * red: the head goes into the mask
   * orange: the gap is less than *Min Gap*
   * green: it fits
   * grey: the mask is further away than *Check Range*

   In Solid shading the view switches to show these colours.
5. **Scale Mask to Fit** scales the mask about the head's centre until the
   closest gap equals *Min Gap*. It enlarges a tight mask and shrinks a loose
   one. *Scale* chooses uniform scaling, width and depth only, or width only.
   Only the object's scale changes, so you can undo it or apply it with
   Ctrl+A.

Scale the mask, then click **Size Is Final** before you split it.

### Exporting for the slicer

**Export for Printing** (under Split) writes the selected pieces and pins at
their true size in millimetres:

* **3MF** (default): one file holding every piece. The file states that it's
  in millimetres, and Bambu Studio, OrcaSlicer, PrusaSlicer and Cura load
  each piece as its own object.
* **STL**: one file per piece, named after it (`mask_Mask_A.stl`, ...). STL
  has no units; slicers read it as millimetres.

Sizes come from the same unit setting the pins and holes were made with, so
the scene's unit settings and other exporters' options can't change them.
Cut planes and hole markers are left out even if selected. The status bar
shows the size, and the system console (Window > Toggle System Console on
Windows) lists every piece.

Set **Bed** to your printer's build volume (256 × 256 × 256 mm suits Bambu
X1, P1 and A1). Export warns about any piece too big for it in every
orientation, which is when the slicer will offer to shrink it. Cut those
pieces again.

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
