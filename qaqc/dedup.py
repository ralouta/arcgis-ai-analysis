"""
Spatial deduplication utilities.

Provides a grid-based spatial index for fast nearest-neighbor duplicate
detection on feature centroids.  Used by both ``create-field-collection-layer``
(seed step) and ``update-field-collection-layer`` (append step).
"""

from __future__ import annotations

import math
from typing import Sequence


# ── geometry helpers ─────────────────────────────────────────────────────

def centroid(geom: dict) -> tuple[float, float]:
    """Extract centroid (x, y) from an ArcGIS geometry dict."""
    if "x" in geom and "y" in geom:
        return (geom["x"], geom["y"])
    if "rings" in geom:
        xs, ys = [], []
        for ring in geom["rings"]:
            for pt in ring:
                xs.append(pt[0])
                ys.append(pt[1])
        return (sum(xs) / len(xs), sum(ys) / len(ys)) if xs else (0.0, 0.0)
    if "paths" in geom:
        xs, ys = [], []
        for path in geom["paths"]:
            for pt in path:
                xs.append(pt[0])
                ys.append(pt[1])
        return (sum(xs) / len(xs), sum(ys) / len(ys)) if xs else (0.0, 0.0)
    return (0.0, 0.0)


def _distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """Euclidean distance between two (x, y) tuples."""
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def is_geographic(wkid: int) -> bool:
    """Check if WKID is a geographic (degree-based) coordinate system."""
    return wkid in (4326, 4269, 4267, 4230, 4258, 4283, 4167)


def meters_to_coord_units(
    distance_m: float,
    wkid: int,
    reference_centroids: Sequence[tuple[float, float]] | None = None,
) -> float:
    """Convert a meter distance to coordinate units for the given SR.

    For projected systems the value is returned as-is.  For geographic
    systems an equirectangular approximation is used, with the median
    latitude taken from *reference_centroids* (or the equator if none).
    """
    if not is_geographic(wkid) or distance_m <= 0:
        return distance_m

    med_lat = 0.0
    if reference_centroids:
        lats = sorted(c[1] for c in reference_centroids)
        med_lat = lats[len(lats) // 2]

    m_per_deg_lon = 111_320 * math.cos(math.radians(med_lat))
    m_per_deg_lat = 111_320
    m_per_deg = (m_per_deg_lon + m_per_deg_lat) / 2
    return distance_m / m_per_deg


# ── SpatialDedupIndex ────────────────────────────────────────────────────

class SpatialDedupIndex:
    """Grid-based spatial index for O(1) amortized duplicate checking.

    Parameters
    ----------
    distance : float
        Dedup threshold in **coordinate units** (use ``meters_to_coord_units``
        to convert from metres first).
    seed_centroids : list[(x, y)], optional
        Pre-existing centroids to load into the index.
    """

    def __init__(
        self,
        distance: float,
        seed_centroids: Sequence[tuple[float, float]] | None = None,
    ):
        self.distance = distance
        self._cell_size = distance * 2 if distance > 0 else 1.0
        self._grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
        self.total_checked = 0
        self.total_duplicates = 0

        if seed_centroids:
            for c in seed_centroids:
                self._insert(c)

    # ── internal ──────────────────────────────────────────────────────

    def _cell(self, x: float, y: float) -> tuple[int, int]:
        return int(x / self._cell_size), int(y / self._cell_size)

    def _insert(self, pt: tuple[float, float]) -> None:
        gx, gy = self._cell(pt[0], pt[1])
        self._grid.setdefault((gx, gy), []).append(pt)

    # ── public API ────────────────────────────────────────────────────

    def has_nearby(self, x: float, y: float) -> bool:
        """Return True if (x, y) is within *distance* of any indexed point."""
        if self.distance <= 0:
            return False
        gx, gy = self._cell(x, y)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for ec in self._grid.get((gx + dx, gy + dy), []):
                    if _distance((x, y), ec) <= self.distance:
                        return True
        return False

    def check_and_insert(self, x: float, y: float) -> bool:
        """Check for duplicate and, if unique, add to the index.

        Returns ``True`` if the point is a **duplicate** (should be skipped).
        Returns ``False`` if the point is unique (was added to the index).
        """
        self.total_checked += 1
        if self.has_nearby(x, y):
            self.total_duplicates += 1
            return True  # duplicate
        self._insert((x, y))
        return False  # unique

    @property
    def unique_count(self) -> int:
        return self.total_checked - self.total_duplicates

    def summary(self) -> str:
        return (
            f"Checked: {self.total_checked}  |  "
            f"Duplicates: {self.total_duplicates}  |  "
            f"Unique: {self.unique_count}"
        )


def deduplicate_features(
    new_features: list,
    existing_centroids: Sequence[tuple[float, float]],
    distance_m: float,
    wkid: int,
) -> tuple[list, list, SpatialDedupIndex]:
    """Partition *new_features* into unique and duplicate lists.

    Parameters
    ----------
    new_features : list[Feature]
        Features to check (must have ``.geometry``).
    existing_centroids : list[(x, y)]
        Centroids of already-existing features.
    distance_m : float
        Dedup threshold in metres.
    wkid : int
        Spatial reference WKID of all geometries.

    Returns
    -------
    (unique, duplicates, index)
        *unique* — features that passed dedup.
        *duplicates* — features that were skipped.
        *index* — the ``SpatialDedupIndex`` (for stats / further use).
    """
    ref = existing_centroids or []
    dist_units = meters_to_coord_units(distance_m, wkid, ref if ref else None)

    if is_geographic(wkid) and distance_m > 0:
        print(f"Geographic SR (WKID {wkid}): {distance_m} m ≈ {dist_units:.8f}°")
    elif distance_m > 0:
        print(f"Projected SR (WKID {wkid}): dedup distance = {dist_units} map units")

    idx = SpatialDedupIndex(dist_units, seed_centroids=ref)

    unique, duplicates = [], []
    for feat in new_features:
        geom = feat.geometry if isinstance(feat.geometry, dict) else dict(feat.geometry)
        cx, cy = centroid(geom)
        if idx.check_and_insert(cx, cy):
            duplicates.append(feat)
        else:
            unique.append(feat)

    return unique, duplicates, idx
