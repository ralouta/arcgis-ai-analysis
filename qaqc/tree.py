"""
QA/QC tool: Tree Points
~~~~~~~~~~~~~~~~~~~~~~~~
Converts raw DL polygon detections into clean **point** features representing
the trunk base of each tree.

Shadow-direction estimation
----------------------------
For elongated detections (shadow + trunk), the tool estimates a **global shadow
azimuth** from the collection of all elongated shapes.  Each elongated polygon
has a *wider* end (canopy) and a *narrower* end (shadow tip).  The vector from
narrow → wide end approximates the sun direction.  The median of these vectors
gives a robust shadow azimuth for the entire scene.

The trunk-base point is placed at the **shadow-near edge** of the canopy — i.e.
walking from the polygon centroid **opposite to the shadow direction** by a
fraction of the major-axis length.  For circular (non-elongated) detections,
the point is placed at the polygon centroid.

``canopy_width_m`` (= minor axis) and ``radius_m`` (= minor / 2) are preserved
as attributes for downstream use.

API
---
``run(features, spatial_reference, **params) -> (FeatureSet, info_dict)``
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from arcgis.features import Feature, FeatureSet


# ── default parameters (overridable via **params) ────────────────────────
DEFAULTS = {
    "cluster_dist": 5.0,
    "elongation_threshold": 1.8,
    "min_radius": 1.0,
    "max_radius": 15.0,
    "canopy_shift": 0.30,       # fraction of major axis to shift toward trunk base
}

PARAM_INFO = [
    {"name": "cluster_dist", "label": "Cluster distance (m)", "type": "float",
     "description": "Centroids within this distance are merged into one tree."},
    {"name": "elongation_threshold", "label": "Elongation threshold", "type": "float",
     "description": "Major/minor ratio above this → shadow+trunk."},
    {"name": "min_radius", "label": "Min radius (m)", "type": "float",
     "description": "Discard circles smaller than this."},
    {"name": "max_radius", "label": "Max radius (m)", "type": "float",
     "description": "Cap circles larger than this."},
    {"name": "canopy_shift", "label": "Canopy shift fraction", "type": "float",
     "description": "How far (0-0.5) to shift centre from centroid toward canopy end."},
]


# ── geometry helpers ─────────────────────────────────────────────────────

def _ring_area(ring: list) -> float:
    pts = np.array(ring)
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _ring_centroid(ring: list) -> tuple[float, float]:
    pts = np.array(ring)
    x, y = pts[:, 0], pts[:, 1]
    cross = x * np.roll(y, -1) - np.roll(x, -1) * y
    area6 = 3.0 * float(np.sum(cross))
    if abs(area6) < 1e-10:
        return float(x.mean()), float(y.mean())
    return (float(np.sum((x + np.roll(x, -1)) * cross) / area6),
            float(np.sum((y + np.roll(y, -1)) * cross) / area6))


def _convex_hull(points: list) -> list:
    pts = sorted(set(map(tuple, points)))
    if len(pts) <= 2:
        return pts

    def _cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and _cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and _cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def _min_rotated_rect(ring: list) -> tuple[float, float, float]:
    """Return (major, minor, angle_of_major_axis)."""
    hull = _convex_hull(ring)
    if len(hull) < 3:
        return 0.0, 0.0, 0.0
    h = np.array(hull)
    edges = np.diff(np.vstack([h, h[:1]]), axis=0)
    angles = np.arctan2(edges[:, 1], edges[:, 0])
    best_area, best = float("inf"), (0.0, 0.0, 0.0)
    for a in angles:
        c, s = np.cos(a), np.sin(a)
        rot = h @ np.array([[c, s], [-s, c]])
        w = float(rot[:, 0].max() - rot[:, 0].min())
        ht = float(rot[:, 1].max() - rot[:, 1].min())
        if w * ht < best_area:
            best_area = w * ht
            best = (w, ht, a) if w >= ht else (ht, w, a + math.pi / 2)
    return best


def _shadow_direction_for_poly(ring: list, angle: float) -> float | None:
    """Return azimuth (radians, CW from +Y/North) from narrow→wide end.

    In projected coords +X = East, +Y = North.
    The vector points FROM shadow-tip TOWARD canopy (≈ toward the sun).
    """
    pts = np.array(ring)
    c, s = np.cos(angle), np.sin(angle)
    rot = pts @ np.array([[c, s], [-s, c]])
    x_rot, y_rot = rot[:, 0], rot[:, 1]

    x_min, x_max = float(x_rot.min()), float(x_rot.max())
    x_mid = (x_min + x_max) / 2.0

    left = x_rot < x_mid
    right = x_rot >= x_mid
    left_w = float(y_rot[left].max() - y_rot[left].min()) if left.sum() >= 2 else 0
    right_w = float(y_rot[right].max() - y_rot[right].min()) if right.sum() >= 2 else 0

    if abs(left_w - right_w) < 0.5:
        return None  # symmetric — can't tell direction

    # Vector from narrow end midpoint to wide end midpoint (in rotated frame)
    if left_w >= right_w:
        # Wide on left, narrow on right → shadow tip is right
        vx_rot = -1.0  # from right toward left
    else:
        vx_rot = 1.0   # from left toward right

    # Rotate vector back to original frame
    ic, is_ = np.cos(-angle), np.sin(-angle)
    v_orig = np.array([vx_rot, 0.0]) @ np.array([[ic, is_], [-is_, ic]])
    # Azimuth: angle from +Y (North) clockwise
    az = math.atan2(v_orig[0], v_orig[1])  # atan2(east, north)
    return az


def _estimate_shadow_azimuth(polys: list[dict], elong_thresh: float) -> float | None:
    """Estimate the scene-wide shadow direction from all elongated polygons.

    Returns the **median** azimuth (radians, CW from North) that points from
    shadow-tip toward canopy (≈ toward the sun).  Returns None if no elongated
    polygons are found.
    """
    azimuths = []
    for p in polys:
        if p["elong"] <= elong_thresh:
            continue
        az = _shadow_direction_for_poly(p["ring"], p["angle"])
        if az is not None:
            azimuths.append(az)

    if not azimuths:
        return None

    # Circular median: convert to unit vectors, take mean, then atan2
    vx = np.mean([math.sin(a) for a in azimuths])
    vy = np.mean([math.cos(a) for a in azimuths])
    return float(math.atan2(vx, vy))


def _shift_centroid(cx: float, cy: float, azimuth: float, distance: float) -> tuple[float, float]:
    """Shift point along azimuth (CW from North) by distance (metres)."""
    # azimuth: atan2(east, north) → dx = sin(az)*d, dy = cos(az)*d
    dx = math.sin(azimuth) * distance
    dy = math.cos(azimuth) * distance
    return cx + dx, cy + dy


# ── main entry point ─────────────────────────────────────────────────────

def run(
    features: list,
    spatial_reference: dict,
    **params: Any,
) -> tuple[FeatureSet, dict]:
    """Process raw DL polygon features into tree-circle features.

    Parameters
    ----------
    features : list[Feature]
        Raw polygon features from detect_objects_using_deep_learning.
    spatial_reference : dict
        ``{"wkid": ...}`` of the feature coordinates.
    **params
        Override any key from ``DEFAULTS``.

    Returns
    -------
    (FeatureSet, info_dict)
        The corrected FeatureSet and a dict with summary stats.
    """
    cfg = {**DEFAULTS, **params}
    cluster_dist = cfg["cluster_dist"]
    elong_thresh = cfg["elongation_threshold"]
    min_r = cfg["min_radius"]
    max_r = cfg["max_radius"]
    canopy_shift = cfg["canopy_shift"]

    # ── Extract polygon metadata ──────────────────────────────────────────
    polys: list[dict] = []
    for feat in features:
        geom = feat.geometry if isinstance(feat.geometry, dict) else dict(feat.geometry)
        rings = geom.get("rings", [])
        if not rings:
            continue
        ring = max(rings, key=lambda r: _ring_area(r))
        area = _ring_area(ring)
        if area < 0.5:
            continue
        cx, cy = _ring_centroid(ring)
        major, minor, angle = _min_rotated_rect(ring)
        elong = major / minor if minor > 0 else 999.0
        polys.append({
            "cx": cx, "cy": cy, "area": area,
            "elong": elong, "ring": ring,
            "major": major, "minor": minor, "angle": angle,
        })

    # ── Estimate global shadow direction ──────────────────────────────────
    shadow_az = _estimate_shadow_azimuth(polys, elong_thresh)
    sun_az_deg = None
    if shadow_az is not None:
        sun_az_deg = round(math.degrees(shadow_az) % 360, 1)

    # ── Cluster by centroid proximity ─────────────────────────────────────
    polys.sort(key=lambda p: -p["area"])

    clusters: list[list[int]] = []
    c_cx: list[float] = []
    c_cy: list[float] = []
    c_n: list[int] = []

    for pi, p in enumerate(polys):
        px, py = p["cx"], p["cy"]
        best_ci, best_d = -1, float("inf")
        for ci in range(len(clusters)):
            d = math.hypot(px - c_cx[ci], py - c_cy[ci])
            if d < best_d:
                best_d = d
                best_ci = ci
        if best_d < cluster_dist and best_ci >= 0:
            clusters[best_ci].append(pi)
            n = c_n[best_ci]
            c_cx[best_ci] = (c_cx[best_ci] * n + px) / (n + 1)
            c_cy[best_ci] = (c_cy[best_ci] * n + py) / (n + 1)
            c_n[best_ci] = n + 1
        else:
            clusters.append([pi])
            c_cx.append(px)
            c_cy.append(py)
            c_n.append(1)

    # ── Pick representative per cluster ───────────────────────────────────
    reps = []
    for cl in clusters:
        members = [polys[i] for i in cl]
        members.sort(key=lambda p: (p["elong"], -p["area"]))
        reps.append(members[0])

    # ── Build point features ─────────────────────────────────────────────
    point_features: list[Feature] = []
    stats = {"circular": 0, "shadow_trunk": 0}

    for i, rep in enumerate(reps):
        elong = rep["elong"]
        area = rep["area"]
        major = rep["major"]
        minor = rep["minor"]

        if elong > elong_thresh:
            kind = "shadow_trunk"
            radius = minor / 2
            cx, cy = rep["cx"], rep["cy"]

            if shadow_az is not None:
                # shadow_az points narrow→wide (toward sun); flip to place point
                # at trunk base (shadow-near edge of canopy)
                shift = canopy_shift * major
                cx, cy = _shift_centroid(cx, cy, shadow_az + math.pi, shift)
            else:
                # Fallback: per-polygon wider-end detection
                cx, cy = _fallback_canopy_center(
                    rep["ring"], rep["angle"], canopy_shift
                )
        else:
            kind = "circular"
            radius = math.sqrt(area / math.pi)
            cx, cy = rep["cx"], rep["cy"]

        radius = max(min_r, min(max_r, radius))
        stats[kind] += 1

        point_features.append(Feature(
            geometry={"x": cx, "y": cy, "spatialReference": spatial_reference},
            attributes={
                "tree_id": i + 1,
                "radius_m": round(radius, 2),
                "canopy_width_m": round(radius * 2, 2),
                "elongation": round(elong, 2),
                "det_type": kind,
                "orig_area_m2": round(area, 2),
                "cluster_size": len(clusters[i]),
            },
        ))

    fset = FeatureSet(
        features=point_features,
        geometry_type="esriGeometryPoint",
        spatial_reference=spatial_reference,
    )

    info = {
        "raw_count": len(features),
        "valid_polys": len(polys),
        "clusters": len(clusters),
        "tree_count": len(point_features),
        "circular": stats["circular"],
        "shadow_trunk": stats["shadow_trunk"],
        "shadow_azimuth_deg": sun_az_deg,
        "params": cfg,
    }
    return fset, info


def _fallback_canopy_center(
    ring: list, angle: float, shift_frac: float
) -> tuple[float, float]:
    """Per-polygon fallback when global shadow direction is unavailable."""
    pts = np.array(ring)
    c, s = np.cos(angle), np.sin(angle)
    rot = pts @ np.array([[c, s], [-s, c]])
    x_rot, y_rot = rot[:, 0], rot[:, 1]
    x_min, x_max = float(x_rot.min()), float(x_rot.max())
    x_mid = (x_min + x_max) / 2.0
    length = x_max - x_min

    left = x_rot < x_mid
    right = x_rot >= x_mid
    left_w = float(y_rot[left].max() - y_rot[left].min()) if left.sum() >= 2 else 0
    right_w = float(y_rot[right].max() - y_rot[right].min()) if right.sum() >= 2 else 0

    if left_w >= right_w:
        # Wide on left = canopy; shift target INTO that half
        target_x = x_max - length * shift_frac
        sel = right
    else:
        target_x = x_min + length * shift_frac
        sel = left

    cy_rot = (
        float((y_rot[sel].max() + y_rot[sel].min()) / 2)
        if sel.sum() >= 2
        else float(y_rot.mean())
    )

    ic, is_ = np.cos(-angle), np.sin(-angle)
    orig = np.array([target_x, cy_rot]) @ np.array([[ic, is_], [-is_, ic]])
    return float(orig[0]), float(orig[1])
