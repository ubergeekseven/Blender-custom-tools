"""Build an installable zip of the add-on into dist/.

    python tools/build_zip.py

Install it in Blender 4.2+ with Edit > Preferences > Get Extensions >
(menu) Install from Disk, or in older versions with Preferences > Add-ons >
Install.
"""

import os
import re
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = "print_splitter"


def main():
    src = os.path.join(ROOT, PKG)
    with open(os.path.join(src, "blender_manifest.toml"), encoding="utf-8") as f:
        version = re.search(r'^version = "([^"]+)"', f.read(), re.M).group(1)
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    out = os.path.join(ROOT, "dist", "%s-%s.zip" % (PKG, version))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(os.listdir(src)):
            if name.endswith((".py", ".toml")):
                zf.write(os.path.join(src, name), "%s/%s" % (PKG, name))
    print(out)


if __name__ == "__main__":
    main()
