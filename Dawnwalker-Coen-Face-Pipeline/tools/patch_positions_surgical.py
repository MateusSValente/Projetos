#!/usr/bin/env python3
"""Patch ONLY selected vertex-position bytes in a vanilla .uexp.

The script fits an affine transform from Blender vanilla coordinates to the
positions decoded from the original game buffer. It then applies that same
transform only to vertices that changed in the edited Blender mesh.

Everything outside those position bytes is preserved byte-for-byte.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import struct
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def load_csv(path: Path):
    rows = []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        required = {"index", "x", "y", "z"}
        if not required.issubset(set(r.fieldnames or [])):
            raise ValueError(f"{path}: expected columns {sorted(required)}")
        for row in r:
            idx = int(row["index"])
            if idx != len(rows):
                raise ValueError(f"{path}: vertex order broken at row {len(rows)} (index={idx})")
            p = (float(row["x"]), float(row["y"]), float(row["z"]))
            if not all(math.isfinite(v) for v in p):
                raise ValueError(f"{path}: NaN/Inf at vertex {idx}")
            rows.append(p)
    return rows


def solve4(a, b):
    # Gaussian elimination with partial pivoting on a 4x4 system.
    m = [list(map(float, a[i])) + [float(b[i])] for i in range(4)]
    for col in range(4):
        pivot = max(range(col, 4), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-18:
            raise ValueError("Singular affine-fit system")
        m[col], m[pivot] = m[pivot], m[col]
        div = m[col][col]
        for j in range(col, 5):
            m[col][j] /= div
        for r in range(4):
            if r == col:
                continue
            factor = m[r][col]
            if factor == 0:
                continue
            for j in range(col, 5):
                m[r][j] -= factor * m[col][j]
    return [m[i][4] for i in range(4)]


def fit_affine(src, dst):
    # dst_coord = c0*x + c1*y + c2*z + c3
    ata = [[0.0] * 4 for _ in range(4)]
    atb = [[0.0] * 4 for _ in range(3)]
    for s, d in zip(src, dst):
        x = (s[0], s[1], s[2], 1.0)
        for i in range(4):
            for j in range(4):
                ata[i][j] += x[i] * x[j]
            for axis in range(3):
                atb[axis][i] += x[i] * d[axis]
    coeff = [solve4(ata, atb[axis]) for axis in range(3)]
    return coeff


def apply_affine(coeff, p):
    x = (p[0], p[1], p[2], 1.0)
    return tuple(sum(coeff[axis][i] * x[i] for i in range(4)) for axis in range(3))


def dist(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def format_spec(name: str):
    specs = {
        "float32x3_le": ("<fff", 12),
        "float16x3_le": ("<eee", 6),
    }
    if name not in specs:
        raise ValueError(f"Unsupported position format: {name}")
    return specs[name]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--vanilla-csv", type=Path, required=True)
    ap.add_argument("--edited-csv", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--unsafe-no-hash", action="store_true")
    ap.add_argument("--allow-large-delta", action="store_true")
    args = ap.parse_args()

    cfg = json.loads(args.manifest.read_text(encoding="utf-8"))
    expected_n = int(cfg["vertex_count"])
    base = args.base.read_bytes()
    actual_hash = sha256_bytes(base)
    expected_hash = str(cfg.get("base_sha256", "")).strip().upper()

    if not expected_hash and not args.unsafe_no_hash:
        raise SystemExit("FAIL: manifest base_sha256 is empty. Refusing unsafe patch.")
    if expected_hash and actual_hash != expected_hash:
        raise SystemExit(f"FAIL: base SHA256 mismatch\nexpected={expected_hash}\nactual  ={actual_hash}")

    vanilla = load_csv(args.vanilla_csv)
    edited = load_csv(args.edited_csv)
    if len(vanilla) != expected_n or len(edited) != expected_n:
        raise SystemExit(
            f"FAIL: vertex count mismatch. expected={expected_n} vanilla={len(vanilla)} edited={len(edited)}"
        )

    buf = cfg["buffer"]
    byte_offset = int(buf["byte_offset"])
    stride = int(buf["stride"])
    pos_off = int(buf.get("position_offset", 0))
    fmt, pos_size = format_spec(buf["format"])
    if stride < pos_off + pos_size:
        raise SystemExit("FAIL: stride is smaller than position field")

    final_needed = byte_offset + (expected_n - 1) * stride + pos_off + pos_size
    if final_needed > len(base):
        raise SystemExit(f"FAIL: configured position buffer exceeds file size ({final_needed} > {len(base)})")

    game_original = []
    for i in range(expected_n):
        off = byte_offset + i * stride + pos_off
        p = struct.unpack_from(fmt, base, off)
        if not all(math.isfinite(v) for v in p):
            raise SystemExit(f"FAIL: decoded NaN/Inf at game vertex {i}")
        game_original.append(tuple(map(float, p)))

    coeff = fit_affine(vanilla, game_original)
    fit_errors = [dist(apply_affine(coeff, vanilla[i]), game_original[i]) for i in range(expected_n)]
    rmse = math.sqrt(sum(e * e for e in fit_errors) / expected_n)
    max_fit = max(fit_errors) if fit_errors else 0.0

    fit_cfg = cfg.get("fit", {})
    max_rmse = float(fit_cfg.get("max_rmse", 1e-4))
    max_abs = float(fit_cfg.get("max_abs_error", 1e-3))
    if rmse > max_rmse or max_fit > max_abs:
        raise SystemExit(
            f"FAIL: Blender->game affine fit is not trustworthy. rmse={rmse:.9g} max={max_fit:.9g} "
            f"limits=({max_rmse},{max_abs})"
        )

    edit_cfg = cfg.get("edit", {})
    blender_eps = float(edit_cfg.get("blender_unchanged_epsilon", 1e-9))
    changed = [i for i in range(expected_n) if dist(vanilla[i], edited[i]) > blender_eps]
    max_changed = int(edit_cfg.get("max_changed_vertices", 0))
    if max_changed > 0 and len(changed) > max_changed and not args.allow_large_delta:
        raise SystemExit(
            f"FAIL: changed vertices {len(changed)} exceeds safety limit {max_changed}. "
            "Use --allow-large-delta only after reviewing the edit."
        )

    target_game = {}
    game_deltas = []
    for i in changed:
        p = apply_affine(coeff, edited[i])
        if not all(math.isfinite(v) for v in p):
            raise SystemExit(f"FAIL: transformed NaN/Inf at vertex {i}")
        d = dist(p, game_original[i])
        game_deltas.append(d)
        target_game[i] = p

    max_game_delta = max(game_deltas) if game_deltas else 0.0
    safety_delta = float(edit_cfg.get("max_game_delta", 0.0))
    if safety_delta > 0 and max_game_delta > safety_delta and not args.allow_large_delta:
        raise SystemExit(
            f"FAIL: max game-space delta {max_game_delta:.9g} exceeds limit {safety_delta}. "
            "Use --allow-large-delta only after reviewing the edit."
        )

    patched = bytearray(base)
    allowed_bytes = set()
    for i in changed:
        off = byte_offset + i * stride + pos_off
        struct.pack_into(fmt, patched, off, *target_game[i])
        allowed_bytes.update(range(off, off + pos_size))

    # Hard safety gate: no changed byte may exist outside the configured position fields.
    unexpected = []
    actual_changed_bytes = 0
    for i, (a, b) in enumerate(zip(base, patched)):
        if a != b:
            actual_changed_bytes += 1
            if i not in allowed_bytes:
                unexpected.append(i)
                if len(unexpected) >= 20:
                    break
    if unexpected:
        raise SystemExit(f"FAIL: bytes changed outside position buffer: {unexpected}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(patched)

    report = {
        "status": "PASS",
        "base_file": str(args.base),
        "base_sha256": actual_hash,
        "output_file": str(args.out),
        "output_sha256": sha256_bytes(bytes(patched)),
        "vertex_count": expected_n,
        "changed_vertices": len(changed),
        "changed_vertex_ratio": len(changed) / expected_n if expected_n else 0.0,
        "actual_changed_bytes": actual_changed_bytes,
        "position_format": buf["format"],
        "buffer": {
            "byte_offset": byte_offset,
            "stride": stride,
            "position_offset": pos_off,
            "position_size": pos_size,
        },
        "affine_coefficients": coeff,
        "fit_rmse": rmse,
        "fit_max_error": max_fit,
        "max_game_delta": max_game_delta,
        "mean_game_delta_changed": (sum(game_deltas) / len(game_deltas)) if game_deltas else 0.0,
        "safety": {
            "outside_position_bytes_changed": 0,
            "unchanged_vertices_preserved_byte_exact": True,
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"PASS: {len(changed)}/{expected_n} vertices patched")
    print(f"fit rmse={rmse:.9g} max={max_fit:.9g}")
    print(f"max game delta={max_game_delta:.9g}")
    print(f"changed bytes={actual_changed_bytes}")
    print(f"output={args.out}")
    print(f"report={args.report}")


if __name__ == "__main__":
    main()
