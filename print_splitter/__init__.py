"""Print Splitter: size models against heads, body parts, real-world objects
or known distances, then cut them with planes for 3D printing, fill the cuts
flat and add registration pins."""

# Read by Blender 4.1 and older; 4.2+ uses blender_manifest.toml.
bl_info = {
    "name": "Print Splitter",
    "author": "ubergeekseven",
    "version": (0, 3, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > Print Split",
    "description": "Split models with a plane, cap the cut and add pin registration holes",
    "category": "Mesh",
}

if "bpy" in locals():
    import importlib
    for _m in (units, geometry, head, body, library, props, sizing, ops_split,  # noqa: F821
               ops_fit, landmarks, measure, eyes, references, export, ui):  # noqa: F821
        importlib.reload(_m)

import bpy  # noqa: E402,F401

from . import (body, export, eyes, geometry, head, landmarks, library,  # noqa: E402
               measure, ops_fit, ops_split, props, references, sizing, ui, units)

_modules = (props, sizing, ops_split, ops_fit, landmarks, measure, eyes, references,
            export, ui)


def register():
    for m in _modules:
        m.register()


def unregister():
    for m in reversed(_modules):
        m.unregister()
