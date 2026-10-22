"""Print Splitter: size models against heads, body parts, real-world objects
or known distances, then cut them with planes for 3D printing, fill the cuts
flat and add registration pins."""

# Read by Blender 4.1 and older; 4.2+ uses blender_manifest.toml.
bl_info = {
    "name": "Print Splitter",
    "author": "ubergeekseven",
    "version": (0, 4, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > Print Split",
    "description": "Size models to people and objects, split them for 3D printing",
    "category": "Mesh",
}

if "bpy" in locals():
    import importlib
    # Dependencies first: a module is reloaded before the ones importing it.
    for _m in (units, geometry, connectors, head, body, library, props,  # noqa: F821
               sizing, ops_split, ops_fit, landmarks, measure, eyes,  # noqa: F821
               references, autosplit, export, ui):  # noqa: F821
        importlib.reload(_m)

import bpy  # noqa: E402,F401

from . import (autosplit, body, connectors, export, eyes, geometry, head,  # noqa: E402
               landmarks, library, measure, ops_fit, ops_split, props, references,
               sizing, ui, units)

_modules = (props, sizing, ops_split, ops_fit, landmarks, measure, eyes, references,
            autosplit, export, ui)


def register():
    for m in _modules:
        m.register()


def unregister():
    for m in reversed(_modules):
        m.unregister()
