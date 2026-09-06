#!/usr/bin/env python3
"""Export raw mesh vertex positions from Blender without applying modifiers.

Run inside Blender, e.g.:
blender --background file.blend --python tools/export_vertex_positions.py -- \
  --object SK_HMA_Coen_Head_A --out edited_positions.csv
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import bpy


def argv_after_double_dash():
    if "--" in sys.argv:
        return sys.argv[sys.argv.index("--") + 1 :]
    return []


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--object", dest="object_name", default=None)
    p.add_argument("--out", required=True)
    return p.parse_args(argv_after_double_dash())


def main():
    args = parse_args()

    if args.object_name:
        obj = bpy.data.objects.get(args.object_name)
        if obj is None:
            raise SystemExit(f"Object not found: {args.object_name}")
    else:
        obj = bpy.context.active_object

    if obj is None or obj.type != "MESH":
        raise SystemExit("Active/selected object must be a MESH")

    mesh = obj.data
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["index", "x", "y", "z"])
        for v in mesh.vertices:
            co = v.co
            w.writerow([v.index, repr(float(co.x)), repr(float(co.y)), repr(float(co.z))])

    metadata = {
        "object": obj.name,
        "mesh": mesh.name,
        "vertex_count": len(mesh.vertices),
        "polygon_count": len(mesh.polygons),
        "edge_count": len(mesh.edges),
        "matrix_world": [[float(x) for x in row] for row in obj.matrix_world],
        "modifiers": [
            {
                "name": m.name,
                "type": m.type,
                "show_viewport": bool(m.show_viewport),
                "show_render": bool(m.show_render),
            }
            for m in obj.modifiers
        ],
        "shape_keys": [kb.name for kb in mesh.shape_keys.key_blocks] if mesh.shape_keys else [],
        "note": "Coordinates are raw obj.data vertex positions. Modifiers are NOT applied.",
    }
    out.with_suffix(out.suffix + ".json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    print(f"[PASS] exported {len(mesh.vertices)} vertices -> {out}")
    print(f"[INFO] metadata -> {out.with_suffix(out.suffix + '.json')}")


if __name__ == "__main__":
    main()
