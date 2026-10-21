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

```
python tools/build_zip.py        # writes dist/print_splitter-<version>.zip
```

* **Blender 4.2+:** Edit > Preferences > Get Extensions > ⌄ (top right) >
  Install from Disk… and pick the zip.
* **Blender 3.6–4.1:** Edit > Preferences > Add-ons > Install… and pick the zip.

The tools are in the 3D Viewport sidebar (press **N**), on the **Print Split** tab.

### Splitting a model

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
   face at Z = 0, ready to export.

Cut a piece again by choosing it as the object and adding another plane.

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
   select it and click **Scale Active to Measurements**.
3. Pick the head and the mask, then move the head to where it will sit in the
   mask.
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

Scale the mask before you split it, so the pins and holes keep their sizes.

### Units

Settings are in millimetres. By default one Blender unit is one millimetre,
which is what STL, 3MF and OBJ files from printing sites use. Choose *Scene
units* if your scene uses Metric with a unit scale.

### Tests

Tests run in real Blender, without a window:

```
blender -b --factory-startup --python tests/test_print_splitter.py
# or, with the PyPI module (pip install bpy):
python tests/test_print_splitter.py
```
