"""Copy the newest live forecast into data/ for the app.

    python publish.py                                    # newest archive per city
    python publish.py --boston path/to/2026_27/boston/2026-10-04

Reads the frozen forecast folders that areaFluForecast's scripts/live_forecast.py
writes (forecast.csv, rates_asof.csv, backtest_*.csv, trust.md, meta.json), plus
the season's scores.csv once forecasts start meeting real numbers. Boundaries are
projected and simplified here, once, into ready-to-draw SVG paths, so the app
needs neither geopandas nor the raw GeoJSON at runtime.

Only public numbers leave this script: BPHC and CDPH dashboard values and our
forecasts of them. No model code, no weights.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).parent
HOME = Path.home()
LIVE = HOME / "Developer" / "areaFluForecast" / "live"
RESEARCH = HOME / "GNN-Influenza-Boston"

# BPHC reports 14 areas; the City's official layer has 26 named neighborhoods.
# Same crosswalk as the research repo (Code/influenza/cities/boston.py
# GEOID_TO_IDX, plus derive_boston_adjacency.EXTRA_MEMBERS). Harbor Islands is
# water, not a BPHC area, and is drawn as context only.
BOSTON_AREA_OF = {
    "Allston": "Allston/Brighton", "Brighton": "Allston/Brighton",
    **{n: "Back Bay/Beacon Hill/Downtown/North End/West End"
       for n in ("Back Bay", "Beacon Hill", "Downtown", "North End", "West End", "Bay Village")},
    "Charlestown": "Charlestown", "Dorchester": "Dorchester", "East Boston": "East Boston",
    "Fenway": "Fenway", "Longwood": "Fenway", "Hyde Park": "Hyde Park",
    "Jamaica Plain": "Jamaica Plain", "Mattapan": "Mattapan", "Roslindale": "Roslindale",
    "Mission Hill": "Roxbury", "Roxbury": "Roxbury",
    "South Boston": "South Boston", "South Boston Waterfront": "South Boston",
    "Chinatown": "South End", "Leather District": "South End", "South End": "South End",
    "West Roxbury": "West Roxbury",
}
GEO = {
    "boston": (RESEARCH / "Data" / "Neighborhood Data" / "boston_polygons_official_neighborhoods.geojson",
               lambda p: BOSTON_AREA_OF.get(p["name"])),
    "chicago": (HOME / "Developer" / "areaFluForecast" / "examples" / "data" / "chicago_cache"
                / "unjd-c2ca.geojson", lambda p: str(p["zip"])),
}
WIDTH = 600.0
TOLERANCE = 0.7  # px after projection


# --- geometry ----------------------------------------------------------------

def _rings(geometry: dict):
    if geometry["type"] == "Polygon":
        yield from geometry["coordinates"]
    elif geometry["type"] == "MultiPolygon":
        for polygon in geometry["coordinates"]:
            yield from polygon


def _simplify(points: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Douglas-Peucker, iterative."""
    if len(points) < 4:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = points[a], points[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy) or 1e-12
        best, index = -1.0, None
        for i in range(a + 1, b):
            px, py = points[i]
            d = abs(dy * (px - ax) - dx * (py - ay)) / norm
            if d > best:
                best, index = d, i
        if index is not None and best > tol:
            keep[index] = True
            stack += [(a, index), (index, b)]
    return [p for p, k in zip(points, keep) if k]


def _simplify_ring(ring: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """A closed ring starts and ends on the same point, which gives Douglas-Peucker a
    zero-length base line; split it at the point farthest from the start instead."""
    if len(ring) < 5:
        return ring
    x0, y0 = ring[0]
    far = max(range(len(ring)), key=lambda i: (ring[i][0] - x0) ** 2 + (ring[i][1] - y0) ** 2)
    return _simplify(ring[:far + 1], tol) + _simplify(ring[far:], tol)[1:]


def build_geo(city: str, areas: list[str]) -> dict:
    path, area_of = GEO[city]
    features = json.loads(path.read_text())["features"]
    lons = [x for f in features for r in _rings(f["geometry"]) for x, _ in r]
    lats = [y for f in features for r in _rings(f["geometry"]) for _, y in r]
    lat0 = (min(lats) + max(lats)) / 2
    kx = math.cos(math.radians(lat0))
    span = (max(lons) - min(lons)) * kx
    scale = WIDTH / span
    height = (max(lats) - min(lats)) * scale

    def project(lon, lat):
        return ((lon - min(lons)) * kx * scale, (max(lats) - lat) * scale)

    shapes: dict[str, list[str]] = {a: [] for a in areas}
    sums: dict[str, list[float]] = {}
    context: list[str] = []
    for f in features:
        area = area_of(f["properties"])
        parts = []
        for ring in _rings(f["geometry"]):
            pts = _simplify_ring([project(x, y) for x, y in ring], TOLERANCE)[:-1]
            if len(pts) < 3:
                continue
            parts.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
            if area in areas:
                # Area-weighted centroid of the ring (shoelace), for labels and the network.
                a = cx = cy = 0.0
                for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
                    cross = x1 * y2 - x2 * y1
                    a += cross
                    cx += (x1 + x2) * cross
                    cy += (y1 + y2) * cross
                s = sums.setdefault(area, [0.0, 0.0, 0.0])
                s[0] += a
                s[1] += cx
                s[2] += cy
        if area in areas:
            shapes[area].extend(parts)
        else:
            context.extend(parts)
    missing = sorted(a for a in areas if not shapes[a])
    if missing:
        raise SystemExit(f"{city}: no boundary for {missing}")
    centroids = {a: (round(s[1] / (3 * s[0]), 1), round(s[2] / (3 * s[0]), 1))
                 for a, s in sums.items() if s[0]}
    return {"viewBox": f"0 0 {WIDTH:.0f} {math.ceil(height)}",
            "areas": {a: {"d": "".join(p), "c": centroids[a]} for a, p in shapes.items()},
            "context": "".join(context)}


# --- copying -------------------------------------------------------------------

def newest_archive(city: str) -> Path:
    folders = sorted(p.parent for p in LIVE.glob(f"[0-9][0-9][0-9][0-9]_[0-9][0-9]/{city}/*/meta.json"))
    if not folders:
        raise SystemExit(f"No archived {city} forecast under {LIVE}. Run live_forecast.py first, "
                         f"or pass --{city} <folder>.")
    return folders[-1]


def publish(city: str, folder: Path, data_folder: Path | None) -> None:
    out = APP_DIR / "data" / city
    out.mkdir(parents=True, exist_ok=True)
    meta = json.loads((folder / "meta.json").read_text())
    for name in ("forecast.csv", "backtest_comparison.csv", "backtest_scores.csv", "trust.md"):
        shutil.copy(folder / name, out / name)
    history = pd.read_csv(folder / "rates_asof.csv", index_col=0)
    history.index.name = "week"
    history.round(3).to_csv(out / "history.csv")
    scores = folder.parent / "scores.csv"
    if scores.exists():
        shutil.copy(scores, out / "live_scores.csv")
    elif (out / "live_scores.csv").exists():
        (out / "live_scores.csv").unlink()
    data_folder = data_folder or LIVE / city
    edges = pd.read_csv(data_folder / "edges.csv", dtype=str)
    areas = list(history.columns)
    edges = edges[edges["a"].isin(areas) & edges["b"].isin(areas)]
    edges.to_csv(out / "edges.csv", index=False)
    (out / "geo.json").write_text(json.dumps(build_geo(city, areas), separators=(",", ":")))
    # Every archived origin, newest last, so the app can show how many weeks are on record.
    origins = sorted(p.name for p in folder.parent.iterdir() if (p / "meta.json").exists())
    meta["archived_origins"] = origins
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"{city}: origin {meta['origin']} -> {out}"
          + ("  (QUICK smoke-test numbers: the app will say so)" if meta.get("quick") else ""))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    for city in GEO:
        parser.add_argument(f"--{city}", type=Path, help="archived forecast folder")
        parser.add_argument(f"--{city}-data", type=Path,
                            help="city data folder with edges.csv (default live/<city>)")
    parser.add_argument("--only", nargs="+", choices=list(GEO), default=list(GEO))
    args = parser.parse_args()
    for city in args.only:
        folder = getattr(args, city) or newest_archive(city)
        publish(city, folder, getattr(args, f"{city}_data"))


if __name__ == "__main__":
    main()
