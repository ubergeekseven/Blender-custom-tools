"""Print Splitter: cut models with a plane for 3D printing, fill the cut flat,
add hexagonal registration pins and check how a mask fits a head."""

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
    for _m in (units, geometry, head, props, sizing, ops_split, ops_fit, landmarks,  # noqa: F821
               export, ui):  # noqa: F821
        importlib.reload(_m)

import bpy  # noqa: E402,F401

from . import (export, geometry, head, landmarks, ops_fit, ops_split, props,  # noqa: E402
               sizing, ui, units)

_modules = (props, sizing, ops_split, ops_fit, landmarks, export, ui)


def register():
    for m in _modules:
        m.register()


def unregister():
    for m in reversed(_modules):
        m.unregister()
