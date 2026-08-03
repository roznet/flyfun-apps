#!/usr/bin/env python3

"""
Starlink coastal-coverage limit as a ForeFlight map layer.

Why
---
Starlink's land/Roam service reaches territorial waters out to 12 NM from the
coast; past that the link drops unless the aircraft is on a maritime/aviation
plan. (Roam additionally caps coastal water at 5 consecutive / 60 annual days.)
For flight planning the useful question is simply "where does the link stop?",
so this tool draws that one line.

What it builds
--------------
  layers/<Name>Limit.kml    the offshore limit as LineStrings. Islands and
                            enclosed water — mid Irish Sea, mid Adriatic — fall
                            out naturally as their own closed rings.
  layers/<Name>Beyond.kml   optional translucent wash over the water beyond the
                            limit, as a separate toggle.

Both go in layers/, so ForeFlight lists them as two independent map layers and
the wash can be switched off without losing the line.

Emitting the limit as lines rather than a filled polygon is deliberate: a line
does not hide the weather and airspace underneath it, and nothing depends on
how ForeFlight handles polygon fill or ring winding order.

Choosing a coastline resolution — read this before switching --source
--------------------------------------------------------------------
The buffer distance sets how much coastline detail can possibly matter. At
12 NM (22.2 km) any wiggle below a few hundred metres is erased by the buffer
itself, so a generalized coastline gives the same answer as a full-resolution
one for far less work. This is not a minor tuning knob: the full-resolution OSM
land polygons carry 5.3 million vertices for the British Isles alone, and
GEOS union/buffer over that allocates tens of GB. Hence the defaults here are
a generalized source plus simplification applied as each polygon is read, so
full-resolution geometry never accumulates in memory.

Two guards keep a bad combination from taking the machine down rather than just
failing: --max-vertices refuses to start the expensive stage on an oversized
input, and --memory-limit-mb runs a watchdog that aborts the process if its own
memory use runs away. The watchdog polls RSS rather than calling setrlimit
because macOS refuses to lower RLIMIT_AS/DATA/RSS, so an address-space cap here
would silently do nothing.

How the geometry is built
-------------------------
1. Land polygons are read for the region, clipped and simplified on the way in.
2. Land is binned into a coarse grid and each cell is buffered by the coverage
   distance in an azimuthal-equidistant projection centred on that cell.
   Minkowski dilation distributes over union — buffer(A u B) == buffer(A) u
   buffer(B) — so buffering per cell and then unioning is exact rather than an
   approximation, while keeping every buffer within the few hundred km where
   AEQD stays metrically faithful. A single projection spanning Europe and the
   Atlantic islands would not.
3. The boundary of that union is the coverage limit.
4. A verification pass resamples the emitted boundary and measures the true
   geodesic distance from each sample back to the land it came from. Note this
   validates the buffer and projection maths, not the fidelity of the source
   coastline — a 1 km-generalized source verifies clean while still sitting
   ~1 km off the real shore.

This buffers the *physical* shoreline, which is deliberately conservative.
Starlink describes the limit in terms of territorial waters, and legal
territorial seas are drawn from straight baselines that close bays and
skerries, so off Norway or the French Biscay coast the legal 12 NM limit lies
further out than 12 NM from the shoreline. Where this layer says "dark" you may
still have signal; where it says "covered" you should have it.

Usage:
  python tools/starlink.py [NAME]
      [-r REGION | --bbox=W,S,E,N]
      [--distance-nm NM] [--source SOURCE]
      [--land-simplify-m M] [--simplify-m M]
      [--no-fill] [--out-dir DIR] [--kmz FILE] [--geojson FILE]
      [--next-version] [--expiration DAYS]
      [--cache-dir DIR] [--max-vertices N] [--memory-limit-mb MB]
      [--verify-report] [--skip-verify] [-v|--verbose]

Examples:
  # Default: all of Europe — Azores to the Black Sea, North Cape to the
  # Canaries. ~30 s, ~350 MB peak, ~270 kB packed.
  python tools/starlink.py

  # Just the British Isles, line only, bumped version
  python tools/starlink.py Starlink12NM -r uk-ireland --no-fill -n

  # A different rule (e.g. a plan with a wider coastal allowance)
  python tools/starlink.py Starlink20NM --distance-nm 20

  # The old default, if a smaller pack is wanted
  python tools/starlink.py Starlink12NM -r western-europe

  # Build into out/ and also emit a KMZ to eyeball in Google Earth first
  python tools/starlink.py Starlink12NM --out-dir out --kmz out/preview.kmz

  # Custom area, and dump GeoJSON to inspect in QGIS/geojson.io
  # Note the '=': a bbox starting with a negative longitude looks like an option
  # to argparse, so --bbox=-15,... works where --bbox -15,... does not.
  python tools/starlink.py --bbox=-15,45,10,60 --geojson /tmp/limit.geojson
"""

import argparse
import json
import logging
import math
import os
import sys
import threading
import time
import zipfile
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.request import urlopen

import pyproj
import shapefile  # pyshp
import shapely
import simplekml
from shapely.errors import GEOSException
from shapely.geometry import Point, box, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree

from ffpack import ContentPack

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

NM_IN_M = 1852.0
M_PER_DEG_LAT = 111320.0

REGIONS: Dict[str, Tuple[float, float, float, float]] = {
    # The default, and wide enough that the edges are chosen rather than
    # inherited. West reaches Flores (-31.3), the last land before
    # Newfoundland; south clears the Canaries and, because the Gulf of Sirte
    # only dips to 30.2 N, the whole North African shore with it; east covers
    # the Black Sea to Batumi (41.6 E); north takes in the North Cape (71.2 N)
    # and Jan Mayen, while leaving out Svalbard.
    #
    # Both shores of every crossing have to be inside the box or the layer goes
    # quiet exactly when you are committed over water — the old western-europe
    # default cut Tunisia in half at 35 N and dropped Libya altogether, so a
    # Sicily -> Tunis leg showed the link dying and never showed it coming back.
    'europe':           (-32.0, 26.0, 45.0, 72.0),
    # The previous default. Far enough south for the Balearics (Mallorca is at
    # 39.6 N) so a UK -> France -> Spain -> Mallorca trip fits in one layer.
    'western-europe':   (-13.0, 35.0, 20.0, 62.0),
    'uk-ireland':       (-13.0, 47.0,  4.0, 62.0),
    'mediterranean':    ( -7.0, 29.0, 37.0, 47.0),
    'atlantic-islands': (-32.0, 26.0, -12.0, 41.0),
    'scandinavia':      ( -2.0, 53.0, 33.0, 72.0),
}

# Land beyond the region still shapes the limit inside it, so read a margin far
# wider than any sane coverage distance.
REGION_MARGIN_DEG = 3.0

# Cell size for per-cell buffering. 5 degrees keeps every point within roughly
# 300 km of its projection centre, where AEQD tangential scale error is well
# under 0.1% — a few metres on a 22 km buffer.
CELL_DEG = 5.0

# How many polygons to hand to a single buffer call. Peak memory in GEOS scales
# with the number of parts noded together, not with vertex count, so this is the
# knob that keeps archipelagos affordable. See _dilate.
BUFFER_BATCH = 64

# Watchdog poll interval. Deliberately short: the archipelago failure mode grew
# from 133 MB to 30 GB inside two seconds, so a lazy poll never sees it coming.
WATCHDOG_INTERVAL_S = 0.25


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------

def peak_rss_mb() -> float:
    """Peak resident set size of this process, in MB."""
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # ru_maxrss is bytes on macOS/BSD, kilobytes on Linux.
    return peak / (1024 * 1024) if sys.platform == 'darwin' else peak / 1024


def start_memory_watchdog(megabytes: int) -> None:
    """
    Abort the process if its own memory use runs away.

    setrlimit is not an option here: macOS refuses to lower RLIMIT_AS, DATA or
    RSS, so a runaway buffer operation would take the whole machine into swap
    before Python ever saw a MemoryError. Watching our own peak RSS and bailing
    out is crude but it is enforced, and dying is much cheaper than wedging the
    user's laptop. --max-vertices is the guard that normally prevents ever
    getting here; this is the backstop for when an estimate is wrong.
    """
    if not megabytes or megabytes <= 0:
        logger.warning('Memory watchdog disabled — a detailed --source can exhaust the machine')
        return

    def watch():
        while True:
            used = peak_rss_mb()
            if used > megabytes:
                logger.error(
                    'Aborting: memory use %.0f MB exceeded --memory-limit-mb %d. '
                    'Raise --land-simplify-m, pick a coarser --source, or shrink the region.'
                    % (used, megabytes)
                )
                os._exit(2)
            time.sleep(WATCHDOG_INTERVAL_S)

    threading.Thread(target=watch, daemon=True, name='memory-watchdog').start()
    logger.debug(f'Memory watchdog armed at {megabytes} MB')


# ---------------------------------------------------------------------------
# projection helpers
# ---------------------------------------------------------------------------

@lru_cache(maxsize=512)
def _aeqd(lat0: float, lon0: float):
    """Forward/inverse transforms for an AEQD frame centred on (lat0, lon0)."""
    crs = pyproj.CRS.from_proj4(
        f'+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m +no_defs'
    )
    fwd = pyproj.Transformer.from_crs('EPSG:4326', crs, always_xy=True).transform
    inv = pyproj.Transformer.from_crs(crs, 'EPSG:4326', always_xy=True).transform
    return fwd, inv


GEOD = pyproj.Geod(ellps='WGS84')


def _cell_of(lon: float, lat: float, cell_deg: float = CELL_DEG) -> Tuple[int, int]:
    return (math.floor(lon / cell_deg), math.floor(lat / cell_deg))


def _cell_centre(cell: Tuple[int, int], cell_deg: float = CELL_DEG) -> Tuple[float, float]:
    ix, iy = cell
    return ((ix + 0.5) * cell_deg, (iy + 0.5) * cell_deg)


def _parts(geom: Optional[BaseGeometry], types: Sequence[str]) -> List[BaseGeometry]:
    """Flatten a geometry down to the requested primitive types."""
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type in types:
        return [geom]
    if hasattr(geom, 'geoms'):
        out: List[BaseGeometry] = []
        for g in geom.geoms:
            out.extend(_parts(g, types))
        return out
    return []


def polygons_of(geom: Optional[BaseGeometry]) -> List[BaseGeometry]:
    return _parts(geom, ('Polygon',))


def lines_of(geom: Optional[BaseGeometry]) -> List[BaseGeometry]:
    return _parts(geom, ('LineString', 'LinearRing'))


def count_vertices(geom) -> int:
    if isinstance(geom, (list, tuple)):
        return int(sum(shapely.get_num_coordinates(g) for g in geom))
    return int(shapely.get_num_coordinates(geom))


# ---------------------------------------------------------------------------
# coastline sources
# ---------------------------------------------------------------------------

class CoastlineSource:
    """
    A cached coastline dataset, read back as land polygons for a bounding box.

    Subclasses stream features and hand each one to _accept, which clips and
    simplifies immediately — the point being that full-resolution geometry is
    never held in memory all at once.
    """

    #: Nominal positional accuracy, for logging so the choice is visible.
    accuracy_note = ''

    def __init__(self, cache_dir):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _fetch(self, url: str, filename: Optional[str] = None) -> Path:
        dest = self.cache_dir / (filename or os.path.basename(url))
        if dest.exists() and dest.stat().st_size > 0:
            logger.debug(f'Using cached {dest}')
            return dest
        logger.info(f'Downloading {url}')
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(url) as response, open(dest, 'wb') as out:
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
        logger.info(f'Cached {dest} ({dest.stat().st_size / 1e6:.1f} MB)')
        return dest

    def _unzip(self, url: str, expect: Optional[str] = None) -> Path:
        """
        Download and extract into the cache, unless what we need is already there.

        Keyed on the wanted file rather than on the target directory existing.
        These archives carry several resolutions, and a directory extracted for
        one of them would otherwise permanently mask the rest — asking for a
        resolution that had not been unpacked yet failed with "not found" while
        the archive holding it sat right there in the cache.

        When the wanted file is named exactly, only its own sidecars are
        unpacked: a shapefile needs its .shx/.dbf/.prj, but there is no reason to
        spill every other resolution across the disk to read one of them.

        A truncated archive is discarded and fetched again. _fetch only knows
        whether a cached file is non-empty, so an interrupted download would
        otherwise be trusted forever and fail on every subsequent run.
        """
        archive = self._fetch(url)
        target = self.cache_dir / archive.stem
        if expect:
            if any(target.glob(f'**/{expect}')):
                return target
        elif target.exists():
            return target

        for attempt in (1, 2):
            try:
                logger.info(f'Extracting {archive}')
                with zipfile.ZipFile(archive) as zf:
                    members = None
                    if expect and not any(ch in expect for ch in '*?['):
                        stem = Path(expect).stem
                        members = [n for n in zf.namelist() if Path(n).stem == stem] or None
                    zf.extractall(target, members)
                return target
            except zipfile.BadZipFile:
                if attempt == 2:
                    raise
                logger.warning(
                    f'{archive.name} is not a valid zip — most likely a truncated '
                    f'download. Discarding and fetching it again.'
                )
                archive.unlink()
                archive = self._fetch(url)
        return target

    @staticmethod
    def _accept(geom: BaseGeometry, clip, simplify_deg: float, out: List[BaseGeometry]) -> None:
        """Clip, simplify and stash a single feature, discarding the original."""
        if not geom.is_valid:
            geom = geom.buffer(0)
        geom = geom.intersection(clip)
        if geom.is_empty:
            return
        if simplify_deg > 0:
            # preserve_topology keeps small islands from collapsing to nothing —
            # they are the whole reason for using a multipart source.
            geom = geom.simplify(simplify_deg, preserve_topology=True)
            if geom.is_empty:
                return
            # Simplification is per-feature, so it can leave a ring crossing
            # itself or a neighbour. Repair here or the union downstream throws
            # "side location conflict".
            if not geom.is_valid:
                geom = shapely.make_valid(geom)
        out.extend(polygons_of(geom))

    def polygons(self, bbox, simplify_deg: float) -> List[BaseGeometry]:
        raise NotImplementedError


class GshhgSource(CoastlineSource):
    """
    GSHHG shorelines (Wessel & Smith) — the standard hierarchical coastline.

    Level 1 is the land/ocean boundary. Resolutions run c/l/i/h/f from crude to
    full; 'h' is roughly 200 m and is ample under a 12 NM buffer.
    """

    URL = 'https://www.soest.hawaii.edu/pwessel/gshhg/gshhg-shp-2.3.7.zip'
    ACCURACY = {'c': '~25 km', 'l': '~5 km', 'i': '~1 km', 'h': '~200 m', 'f': 'full'}

    def __init__(self, cache_dir, resolution: str = 'h'):
        super().__init__(cache_dir)
        self.resolution = resolution
        self.accuracy_note = f'GSHHG-{resolution} ({self.ACCURACY.get(resolution, "?")})'

    def shapefile_path(self) -> Path:
        wanted = f'GSHHS_{self.resolution}_L1.shp'
        root = self._unzip(self.URL, expect=wanted)
        for candidate in root.glob(f'**/{wanted}'):
            return candidate
        raise ValueError(f'{wanted} not found under {root}')

    def polygons(self, bbox, simplify_deg: float) -> List[BaseGeometry]:
        west, south, east, north = bbox
        clip = box(west, south, east, north)
        shp = self.shapefile_path()
        logger.info(f'Reading {shp.name} for bbox {bbox}')

        kept: List[BaseGeometry] = []
        with shapefile.Reader(str(shp)) as reader:
            for record in reader.iterShapes(bbox=(west, south, east, north)):
                if record is None:
                    continue
                self._accept(shape(record.__geo_interface__), clip, simplify_deg, kept)
        return kept


class NaturalEarthSource(CoastlineSource):
    """
    Natural Earth 1:10m land plus minor islands.

    Coarser than GSHHG-h (roughly 1 km) but tiny and dependency-free, and the
    minor-islands file has to be loaded alongside the main one or the Channel
    Islands and similar disappear.
    """

    BASE = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/'
    FILES = ('ne_10m_land.geojson', 'ne_10m_minor_islands.geojson')
    accuracy_note = 'Natural Earth 10m (~1 km)'

    def polygons(self, bbox, simplify_deg: float) -> List[BaseGeometry]:
        west, south, east, north = bbox
        clip = box(west, south, east, north)
        kept: List[BaseGeometry] = []
        for filename in self.FILES:
            path = self._fetch(self.BASE + filename, f'naturalearth/{filename}')
            logger.info(f'Reading {filename} for bbox {bbox}')
            with open(path) as f:
                collection = json.load(f)
            for feature in collection['features']:
                geom = shape(feature['geometry'])
                if not geom.intersects(clip):
                    continue
                self._accept(geom, clip, simplify_deg, kept)
            del collection
        return kept


class OsmSource(CoastlineSource):
    """
    OSM land polygons — full resolution, best fidelity, and heavy.

    870k features globally and 5.3M vertices for the British Isles alone, so
    simplification on read is not optional here. Kept available because it is
    the only source that is current to the week.
    """

    URL = 'https://osmdata.openstreetmap.de/download/land-polygons-split-4326.zip'
    accuracy_note = 'OSM land polygons (full resolution)'

    def shapefile_path(self) -> Path:
        root = self._unzip(self.URL, expect='*.shp')
        for candidate in sorted(root.glob('**/*.shp')):
            return candidate
        raise ValueError(f'No .shp found under {root}')

    def polygons(self, bbox, simplify_deg: float) -> List[BaseGeometry]:
        west, south, east, north = bbox
        clip = box(west, south, east, north)
        shp = self.shapefile_path()
        logger.info(f'Reading {shp.name} for bbox {bbox} (full-resolution source)')
        if simplify_deg <= 0:
            logger.warning(
                'Reading OSM land polygons without simplification — this can need '
                'tens of GB downstream. Use --land-simplify-m 300 or more.'
            )

        kept: List[BaseGeometry] = []
        with shapefile.Reader(str(shp)) as reader:
            # pyshp's bbox filter reads each record's stored bounding box and
            # seeks past the rest, so the features outside the region are cheap.
            for record in reader.iterShapes(bbox=(west, south, east, north)):
                if record is None:
                    continue
                self._accept(shape(record.__geo_interface__), clip, simplify_deg, kept)
        return kept


SOURCES = {
    'gshhg-i': lambda cache: GshhgSource(cache, 'i'),
    'gshhg-h': lambda cache: GshhgSource(cache, 'h'),
    'gshhg-f': lambda cache: GshhgSource(cache, 'f'),
    'ne10m':   NaturalEarthSource,
    'osm':     OsmSource,
}


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------

def _safe_union(geoms: Sequence[BaseGeometry]) -> BaseGeometry:
    """Union, repairing inputs and retrying if GEOS rejects them."""
    try:
        return unary_union(geoms)
    except GEOSException as exc:
        logger.debug(f'union failed ({exc}); repairing inputs and retrying')
        return unary_union([shapely.make_valid(g) for g in geoms])


def _dilate(
    members: Sequence[BaseGeometry],
    distance_m: float,
    quad_segs: int,
    batch_size: int = BUFFER_BATCH,
) -> BaseGeometry:
    """
    Dilate a group of projected polygons, in batches.

    The trap this avoids: calling buffer() once on a MultiPolygon with thousands
    of parts. GEOS generates the offset curves for every part and nodes them in
    a single pass, so the Åland/Turku archipelago — 6,905 islands but only 35k
    vertices — needs 30 GB and two minutes to yield a 525-vertex result. Peak
    memory there is driven by the number of parts handed to one buffer call, not
    by the vertex count, which is why an innocuous-looking input explodes.

    Buffering small batches and unioning progressively keeps every intermediate
    small. The result is identical because dilation distributes over union, and
    overlapping buffers collapse into few components as they accumulate.
    """
    accumulated: Optional[BaseGeometry] = None
    for start in range(0, len(members), batch_size):
        chunk = list(members[start:start + batch_size])
        try:
            grown = unary_union(chunk).buffer(distance_m, quad_segs=quad_segs)
        except GEOSException as exc:
            # A union of independently simplified coastline can trip GEOS
            # robustness ("side location conflict"); buffering each member is
            # slower but far more forgiving.
            logger.debug(f'union-before-buffer failed ({exc}); buffering members individually')
            grown = _safe_union([m.buffer(distance_m, quad_segs=quad_segs) for m in chunk])
        accumulated = grown if accumulated is None else _safe_union([accumulated, grown])
    return accumulated


def grid_land(
    land: Sequence[BaseGeometry],
    bbox,
    cell_deg: float = CELL_DEG,
) -> Dict[Tuple[int, int], List[BaseGeometry]]:
    """
    Clip land into grid cells so every piece lies inside the cell that holds it.

    Binning whole polygons by centroid is not good enough: one polygon can be a
    whole continent, which would then be projected in a frame centred thousands
    of km from most of it, and would be invisible to any lookup that only
    consults neighbouring cells. Cutting the land on the grid keeps both the
    projection and the nearest-land search honestly local.

    The cuts are safe. They add edges along cell borders, but those edges are
    interior to the union of all the pieces, so the buffer union absorbs them —
    the same reason buffering per cell and unioning is exact.
    """
    west, south, east, north = bbox
    tree = STRtree(list(land))
    cells: Dict[Tuple[int, int], List[BaseGeometry]] = {}
    for ix in range(math.floor(west / cell_deg), math.floor(east / cell_deg) + 1):
        for iy in range(math.floor(south / cell_deg), math.floor(north / cell_deg) + 1):
            cell_box = box(ix * cell_deg, iy * cell_deg,
                           (ix + 1) * cell_deg, (iy + 1) * cell_deg)
            pieces: List[BaseGeometry] = []
            for index in tree.query(cell_box):
                clipped = land[index].intersection(cell_box)
                if not clipped.is_empty:
                    pieces.extend(polygons_of(clipped))
            if pieces:
                cells[(ix, iy)] = pieces
    logger.info(
        'Gridded %d land polygons into %d cells (%d pieces)'
        % (len(land), len(cells), sum(len(v) for v in cells.values()))
    )
    return cells


def buffer_land(
    cells: Dict[Tuple[int, int], List[BaseGeometry]],
    distance_nm: float,
    cell_deg: float = CELL_DEG,
    quad_segs: int = 8,
) -> BaseGeometry:
    """
    Dilate land by distance_nm, cell by cell in local equidistant frames.

    Exact rather than approximate: dilation distributes over union, so the union
    of per-cell buffers is the buffer of the union. Each cell is projected to
    its own AEQD frame so no part of the buffer is measured far from its
    projection centre.
    """
    total = sum(len(v) for v in cells.values())
    logger.info(f'Buffering {total} land pieces by {distance_nm} NM across {len(cells)} cells')
    distance_m = distance_nm * NM_IN_M
    buffered: List[BaseGeometry] = []
    for cell, members in sorted(cells.items()):
        lon0, lat0 = _cell_centre(cell, cell_deg)
        fwd, inv = _aeqd(lat0, lon0)
        projected = [transform(fwd, poly) for poly in members]
        grown = _dilate(projected, distance_m, quad_segs)
        del projected
        buffered.append(transform(inv, grown))
        logger.debug(f'  cell {cell}: {len(members)} polygons -> {count_vertices(buffered[-1])} vertices')

    logger.info('Merging buffered cells')
    union = _safe_union(buffered)
    if not union.is_valid:
        union = shapely.make_valid(union)
    return union


def simplify_geographic(geom: BaseGeometry, tolerance_m: float) -> BaseGeometry:
    """
    Simplify with a tolerance in metres, part by part in local frames.

    Applied after the union so the artificial edges where source tiles were cut
    are already gone and cannot be simplified into visible kinks.
    """
    if tolerance_m <= 0:
        return geom
    simplified: List[BaseGeometry] = []
    for part in polygons_of(geom):
        centre = part.representative_point()
        fwd, inv = _aeqd(centre.y, centre.x)
        reduced = transform(fwd, part).simplify(tolerance_m)
        if reduced.is_empty:
            continue
        if not reduced.is_valid:
            reduced = shapely.make_valid(reduced)
        simplified.append(transform(inv, reduced))
    out = _safe_union(simplified)
    return out if out.is_valid else shapely.make_valid(out)


def limit_lines(coverage: BaseGeometry, region) -> List[BaseGeometry]:
    """Coverage boundary, trimmed to the region so the read margin is not drawn."""
    west, south, east, north = region
    clipped = coverage.boundary.intersection(box(west, south, east, north))
    lines = [line for line in lines_of(clipped) if line.length > 0]
    logger.info(f'Coverage limit: {len(lines)} line strings, {count_vertices(lines)} vertices')
    return lines


def beyond_limit(coverage: BaseGeometry, region) -> List[BaseGeometry]:
    """Water outside the coverage limit, inside the region."""
    west, south, east, north = region
    return polygons_of(box(west, south, east, north).difference(coverage))


# ---------------------------------------------------------------------------
# verification
# ---------------------------------------------------------------------------

def verify_limit(
    lines: Sequence[BaseGeometry],
    land_cells: Dict[Tuple[int, int], List[BaseGeometry]],
    distance_nm: float,
    cell_deg: float = CELL_DEG,
) -> dict:
    """
    Measure the true geodesic distance from the emitted limit back to land.

    Samples every vertex plus each segment midpoint — vertices catch systematic
    offset error, midpoints catch corners cut inward by simplification. Work is
    binned by cell so each measurement happens in a local metric frame, and the
    reported number is a geodesic distance on the ellipsoid.
    """
    sample_cells: Dict[Tuple[int, int], List[Tuple[float, float]]] = defaultdict(list)
    for line in lines:
        coords = list(line.coords)
        for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
            sample_cells[_cell_of(x1, y1, cell_deg)].append((x1, y1))
            mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            sample_cells[_cell_of(mx, my, cell_deg)].append((mx, my))
        if coords:
            x, y = coords[-1]
            sample_cells[_cell_of(x, y, cell_deg)].append((x, y))

    distances: List[float] = []
    unmeasured = 0
    for cell, samples in sorted(sample_cells.items()):
        ix, iy = cell
        nearby: List[BaseGeometry] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nearby.extend(land_cells.get((ix + dx, iy + dy), []))
        if not nearby:
            unmeasured += len(samples)
            continue

        lon0, lat0 = _cell_centre(cell, cell_deg)
        fwd, inv = _aeqd(lat0, lon0)
        projected = [transform(fwd, poly) for poly in nearby]
        tree = STRtree(projected)

        for lon, lat in samples:
            point = transform(fwd, Point(lon, lat))
            nearest = projected[tree.nearest(point)]
            ring = nearest.exterior
            back = transform(inv, ring.interpolate(ring.project(point)))
            _, _, metres = GEOD.inv(lon, lat, back.x, back.y)
            distances.append(metres / NM_IN_M)

    if not distances:
        return {'samples': 0, 'unmeasured': unmeasured}

    distances.sort()
    n = len(distances)
    within = sum(1 for d in distances if abs(d - distance_nm) <= 0.5)
    return {
        'samples': n,
        'unmeasured': unmeasured,
        'target_nm': distance_nm,
        'min': distances[0],
        'p05': distances[int(0.05 * n)],
        'median': distances[n // 2],
        'p95': distances[int(0.95 * n)],
        'max': distances[-1],
        'within_half_nm_pct': 100.0 * within / n,
    }


def log_verification(stats: dict) -> None:
    if not stats.get('samples'):
        logger.warning('Verification produced no measurable samples')
        return
    logger.info(
        'Limit vs land (target %.1f NM): min %.2f  p05 %.2f  median %.2f  p95 %.2f  max %.2f NM'
        % (stats['target_nm'], stats['min'], stats['p05'], stats['median'],
           stats['p95'], stats['max'])
    )
    logger.info(
        'Within 0.5 NM of target: %.1f%% of %d samples'
        % (stats['within_half_nm_pct'], stats['samples'])
    )
    if stats['within_half_nm_pct'] < 95.0:
        logger.warning('Less than 95%% of the limit sits within 0.5 NM of target — inspect the output')


# ---------------------------------------------------------------------------
# KML output
# ---------------------------------------------------------------------------

def add_polygon(multi, poly) -> None:
    """
    Add a polygon to a MultiGeometry, emitting one <innerBoundaryIs> per hole.

    Not a style preference — simplekml gets this wrong. Its innerboundaryis
    setter concatenates every hole into a single element (featgeom.py:
    `self._kml['innerBoundaryIs'] += LinearRing(ring)`), producing one
    <innerBoundaryIs> wrapping N <LinearRing>s. KML allows one ring per
    <innerBoundaryIs>, and Google Earth honours only the first, so every hole
    after the first was silently filled in.

    That mattered here more than it sounds. Along a mainland coast the covered
    band lies *outside* the beyond-limit polygon and draws correctly, but every
    island's coverage ring is a hole — so Mallorca, the Azores, Madeira,
    Iceland and the Faroes were all washed over as if they had no coverage,
    which is precisely backwards for the features this layer exists to show.

    A trailing underscore is simplekml's own convention for a value emitted
    verbatim rather than wrapped in <key> (base.py: `if var.endswith("_")`),
    so the repeated elements go in without post-processing the saved file.
    """
    kml_poly = multi.newpolygon(outerboundaryis=list(poly.exterior.coords))
    if not poly.interiors:
        return
    kml_poly._kml['innerBoundaryIs'] = None
    kml_poly._kml['innerboundaryis_'] = ''.join(
        f'<innerBoundaryIs>{simplekml.LinearRing(list(ring.coords))}</innerBoundaryIs>'
        for ring in poly.interiors
    )


def write_limit_kml(dest: Path, lines, distance_nm: float, colour: str) -> None:
    """
    One placemark holding a MultiGeometry of every boundary line.

    Collapsing thousands of rings into a single placemark keeps one inline style
    for the whole layer instead of one per ring, which matters for both file
    size and how quickly ForeFlight draws it.
    """
    kml = simplekml.Kml(name=f'Starlink {distance_nm:g} NM limit')
    multi = kml.newmultigeometry(name=f'Starlink {distance_nm:g} NM coverage limit')
    multi.description = (
        f'Seaward limit of Starlink land/Roam coverage, {distance_nm:g} NM from the '
        'shoreline. Beyond this line the link drops without a maritime or aviation '
        'plan. Buffered from the physical coast, so it is conservative where '
        'territorial sea baselines close a bay.'
    )
    for line in lines:
        multi.newlinestring(coords=list(line.coords))
    multi.style.linestyle.color = colour
    multi.style.linestyle.width = 2

    logger.info(f'Writing {dest}')
    kml.save(str(dest))


def write_beyond_kml(dest: Path, water, distance_nm: float, colour: str) -> None:
    """Translucent wash over the water beyond the limit, outline suppressed."""
    kml = simplekml.Kml(name=f'Beyond Starlink {distance_nm:g} NM')
    multi = kml.newmultigeometry(name=f'No Starlink coverage (beyond {distance_nm:g} NM)')
    multi.description = (
        f'Water more than {distance_nm:g} NM from the shoreline — outside Starlink '
        'land/Roam coverage.'
    )
    for poly in water:
        add_polygon(multi, poly)
    multi.style.polystyle.color = colour
    multi.style.polystyle.outline = 0
    multi.style.linestyle.width = 0

    logger.info(f'Writing {dest}')
    kml.save(str(dest))


def write_preview_kmz(dest: Path, lines, water, distance_nm: float,
                      line_colour: str, fill_colour: str) -> None:
    """
    Both layers in one KMZ, as separate folders, for desktop preview.

    ForeFlight wants the layers as separate files in the pack; Google Earth is
    happier with a single file, and its web importer only takes one. A KMZ needs
    doc.kml at the archive root, so the content pack zip cannot be reused for
    this — it holds manifest.json and layers/ instead.
    """
    kml = simplekml.Kml(name=f'Starlink {distance_nm:g} NM preview')

    limit_folder = kml.newfolder(name=f'{distance_nm:g} NM coverage limit')
    multi = limit_folder.newmultigeometry(name='Coverage limit')
    for line in lines:
        multi.newlinestring(coords=list(line.coords))
    multi.style.linestyle.color = line_colour
    multi.style.linestyle.width = 2

    if water:
        water_folder = kml.newfolder(name=f'No coverage (beyond {distance_nm:g} NM)')
        wash = water_folder.newmultigeometry(name='Beyond limit')
        for poly in water:
            add_polygon(wash, poly)
        wash.style.polystyle.color = fill_colour
        wash.style.polystyle.outline = 0
        wash.style.linestyle.width = 0

    logger.info(f'Writing {dest}')
    kml.savekmz(str(dest))


def _dms(value: float, hemispheres: str, degree_width: int) -> str:
    """Format a coordinate as SkyDemon's packed DMS, e.g. N583553.97 / W0023842.28."""
    hemisphere = hemispheres[0] if value >= 0 else hemispheres[1]
    remainder = abs(value)
    degrees = int(remainder)
    remainder = (remainder - degrees) * 60.0
    minutes = int(remainder)
    seconds = round((remainder - minutes) * 60.0, 2)
    # Rounding can carry: 59.999 s becomes 60.00 and must roll up.
    if seconds >= 60.0:
        seconds -= 60.0
        minutes += 1
    if minutes >= 60:
        minutes -= 60
        degrees += 1
    return f'{hemisphere}{degrees:0{degree_width}d}{minutes:02d}{seconds:05.2f}'


def _skydemon_block(title: str, ring) -> List[str]:
    """One airspace definition. Header repeated per block so each is self-contained."""
    lines = ['#', 'TYPE=OTHER', 'SUBTYPE=Starlink', '#', '#',
             f'TITLE={title}', 'REF=STARLINK', 'BASE=MSL', 'TOPS=UNL']
    coords = list(ring.coords)
    # Close the ring explicitly. His Europe file did not, leaving SkyDemon to
    # join the Barents coast to the Black Sea with a 1,516 NM straight line.
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    for lon, lat in coords:
        lines.append(f'POINT={_dms(lat, "NS", 2)} {_dms(lon, "EW", 3)}')
    return lines


def _ring_area_nm2(ring) -> float:
    """Geodesic area enclosed by a ring, in square nautical miles."""
    area_m2, _ = GEOD.geometry_area_perimeter(ring)
    return abs(area_m2) / (NM_IN_M ** 2)


def _coord_label(point) -> str:
    return (f'{abs(point.y):.1f}{"N" if point.y >= 0 else "S"} '
            f'{abs(point.x):06.2f}{"E" if point.x >= 0 else "W"}')


def write_skydemon(dest: Path, polygons: Sequence[BaseGeometry], distance_nm: float,
                   split: bool = False, min_gap_nm2: float = 25.0) -> None:
    """
    Write the same boundary in SkyDemon's custom-airspace format.

    The format holds one closed ring per block, with no holes and no multipart
    geometry — which is what cost the original files every offshore island. The
    workaround is one ring per block: each landmass group gets its own, and each
    enclosed gap gets one labelled GAP so it is not mistaken for coverage.

    The format is not publicly documented, so the layout mirrors the observed
    files byte for byte, CRLF endings included. Evidence suggests SkyDemon takes
    one airspace per file (the source files were split that way), so split=True
    writes one file per ring — drop them all in SkyDemon's CustomData folder.

    Gaps below min_gap_nm2 are dropped: a hole a couple of NM across is noise
    under a 12 NM rule and would just add clutter. The count is logged, never
    silently discarded.
    """
    ordered = sorted(polygons, key=lambda g: -g.area)
    blocks: List[Tuple[str, List[str]]] = []
    area_no = gap_no = 0
    dropped = 0
    for poly in ordered:
        area_no += 1
        title = (f'STARLINK {distance_nm:g}NM AREA {area_no:02d} '
                 f'{_coord_label(poly.representative_point())}')
        blocks.append((f'area{area_no:02d}', _skydemon_block(title, poly.exterior)))
        for ring in poly.interiors:
            if _ring_area_nm2(ring) < min_gap_nm2:
                dropped += 1
                continue
            gap_no += 1
            gap_title = (f'STARLINK {distance_nm:g}NM GAP {gap_no:02d} '
                         f'{_coord_label(ring.centroid)}')
            blocks.append((f'gap{gap_no:02d}', _skydemon_block(gap_title, ring)))
    if dropped:
        logger.info(f'Dropped {dropped} enclosed gaps smaller than {min_gap_nm2:g} NM2')

    # newline='' plus explicit \r\n keeps the CRLF endings the observed files use.
    with open(dest, 'w', newline='') as f:
        for _, block in blocks:
            f.write('\r\n'.join(block) + '\r\n')
    points = sum(len(b) for _, b in blocks)
    logger.info(
        f'Writing {dest}: {len(blocks)} blocks ({area_no} areas, {gap_no} gaps), ~{points} lines'
    )

    if split:
        for name, block in blocks:
            part = dest.with_name(f'{dest.stem}_{name}{dest.suffix}')
            with open(part, 'w', newline='') as f:
                f.write('\r\n'.join(block) + '\r\n')
        logger.info(f'Also wrote {len(blocks)} single-block files next to {dest.name}')


def write_geojson(dest: Path, lines) -> None:
    collection = {
        'type': 'FeatureCollection',
        'features': [
            {'type': 'Feature', 'properties': {}, 'geometry': mapping(line)}
            for line in lines
        ],
    }
    logger.info(f'Writing {dest}')
    with open(dest, 'w') as f:
        json.dump(collection, f)


# ---------------------------------------------------------------------------
# command
# ---------------------------------------------------------------------------

class Command:
    """Command-line interface for the Starlink coverage layer."""

    def __init__(self, args):
        self.args = args
        self.region = self._resolve_region()

    def _resolve_region(self):
        if self.args.bbox:
            parts = [float(v) for v in self.args.bbox.split(',')]
            if len(parts) != 4:
                raise ValueError('--bbox needs four comma-separated values: W,S,E,N')
            west, south, east, north = parts
            if west >= east or south >= north:
                raise ValueError(f'--bbox is not a valid box: {self.args.bbox}')
            return (west, south, east, north)
        return REGIONS[self.args.region]

    def load_land(self) -> List[BaseGeometry]:
        west, south, east, north = self.region
        margin = REGION_MARGIN_DEG
        read_bbox = (west - margin, south - margin, east + margin, north + margin)

        source = SOURCES[self.args.source](self.args.cache_dir)
        # Simplify in degrees on the way in. Using the latitude scale for both
        # axes under-simplifies in longitude away from the equator, which errs
        # towards keeping detail rather than losing it.
        simplify_deg = self.args.land_simplify_m / M_PER_DEG_LAT
        logger.info(
            'Coastline source: %s, simplified on read at %.0f m'
            % (source.accuracy_note or self.args.source, self.args.land_simplify_m)
        )
        land = source.polygons(read_bbox, simplify_deg)
        if not land:
            raise ValueError(f'No land found in {read_bbox} — check the region')

        vertices = count_vertices(land)
        logger.info(f'Land: {len(land)} polygons, {vertices} vertices')
        if vertices > self.args.max_vertices:
            raise ValueError(
                f'Land geometry has {vertices} vertices, above --max-vertices '
                f'({self.args.max_vertices}). Buffering this much detail can need '
                f'tens of GB and is pointless under a {self.args.distance_nm:g} NM '
                f'buffer. Raise --land-simplify-m, choose a coarser --source, or '
                f'shrink the region.'
            )
        return land

    def run(self):
        start_memory_watchdog(self.args.memory_limit_mb)

        west, south, east, north = self.region
        logger.info(
            'Region %s: %.1f..%.1f E, %.1f..%.1f N'
            % (self.args.bbox or self.args.region, west, east, south, north)
        )

        land = self.load_land()
        margin = REGION_MARGIN_DEG
        cells = grid_land(land, (west - margin, south - margin, east + margin, north + margin))
        del land

        coverage = buffer_land(cells, self.args.distance_nm)
        if self.args.simplify_m > 0:
            before = count_vertices(coverage)
            coverage = simplify_geographic(coverage, self.args.simplify_m)
            logger.info(
                'Simplified output at %.0f m: %d -> %d vertices'
                % (self.args.simplify_m, before, count_vertices(coverage))
            )

        lines = limit_lines(coverage, self.region)

        if not self.args.skip_verify:
            stats = verify_limit(lines, cells, self.args.distance_nm)
            log_verification(stats)
            if self.args.verify_report:
                for key, value in stats.items():
                    logger.info(f'  {key}: {value}')

        name = self.args.name
        pack = ContentPack(
            Path(self.args.out_dir) / name,
            name=f'Starlink {self.args.distance_nm:g} NM',
            abbreviation=f'{name}.V1',
            version=1,
        )
        if pack.adopt_version(self.args.next_version):
            pack.abbreviation = f'{name}.V{pack.version}'
        pack.write_manifest(self.args.expiration)
        layers = pack.subdir(ContentPack.LAYERS)

        write_limit_kml(layers / f'{name}Limit.kml', lines, self.args.distance_nm,
                        self.args.line_color)
        water = [] if self.args.no_fill else beyond_limit(coverage, self.region)
        if not self.args.no_fill:
            write_beyond_kml(layers / f'{name}Beyond.kml', water,
                             self.args.distance_nm, self.args.fill_color)

        if self.args.skydemon:
            # Deliberately NOT clipped to the region. An airspace must be a closed
            # ring, so wherever the data stops the ring closes with a straight leg
            # along the cut. Clipping to the region puts those legs right through
            # the area of interest — a ~1000 NM straight line across the Med,
            # indistinguishable from the artefact this export exists to avoid.
            # Using the unclipped coverage pushes them out to the read margin
            # instead, and keeps island groups near the region edge (the Faroes)
            # whole. Inside the region the boundary is identical to the KML.
            write_skydemon(Path(self.args.skydemon), polygons_of(coverage),
                           self.args.distance_nm,
                           split=self.args.skydemon_split,
                           min_gap_nm2=self.args.min_gap_nm2)

        if self.args.kmz:
            write_preview_kmz(Path(self.args.kmz), lines, water, self.args.distance_nm,
                              self.args.line_color, self.args.fill_color)

        if self.args.geojson:
            write_geojson(Path(self.args.geojson), lines)

        logger.info(f'Content pack ready: {pack.path} (version {pack.version})')
        logger.info('Install: AirDrop or copy the folder (or a zip of it) into ForeFlight')


def main():
    parser = argparse.ArgumentParser(
        description='Build a ForeFlight content pack with the Starlink coastal coverage limit'
    )
    parser.add_argument('name', nargs='?', default='Starlink12NM',
                        help='Name of the content pack (default: Starlink12NM)')
    parser.add_argument('-r', '--region', choices=sorted(REGIONS), default='europe',
                        help='Predefined area to cover (default: europe)')
    parser.add_argument('--bbox', help='Explicit area as W,S,E,N in degrees (overrides --region)')
    parser.add_argument('--distance-nm', type=float, default=12.0,
                        help='Coverage distance from the coast in NM (default: 12)')
    parser.add_argument('--source', choices=sorted(SOURCES), default='gshhg-h',
                        help='Coastline dataset (default: gshhg-h, ~200 m)')
    parser.add_argument('--land-simplify-m', type=float, default=300.0,
                        help='Simplify land on read, in metres (default: 300). Detail below '
                             'this cannot survive a 12 NM buffer anyway.')
    parser.add_argument('--simplify-m', type=float, default=500.0,
                        help='Simplify the output limit, in metres, 0 to disable (default: 500)')
    parser.add_argument('--no-fill', action='store_true',
                        help='Emit only the limit line, no shaded beyond-limit layer')
    parser.add_argument('--line-color', default=simplekml.Color.magenta,
                        help='KML aabbggrr colour for the limit line')
    parser.add_argument('--fill-color', default='40ff00ff',
                        help='KML aabbggrr colour for the beyond-limit wash')
    parser.add_argument('--out-dir', default='.',
                        help='Directory to build the pack in (default: current directory). '
                             'The pack name stays clean, so use this rather than a path in NAME.')
    parser.add_argument('--kmz', help='Also write a single-file KMZ (both layers as folders) '
                                      'for previewing in Google Earth')
    parser.add_argument('--skydemon', help='Also write the same boundary as a SkyDemon '
                                           'custom-airspace file (.airspace)')
    parser.add_argument('--skydemon-split', action='store_true',
                        help='With --skydemon, also write one file per area/gap, since SkyDemon '
                             'appears to take a single airspace per file')
    parser.add_argument('--min-gap-nm2', type=float, default=25.0,
                        help='Skip enclosed no-coverage gaps smaller than this, in square NM '
                             '(default: 25)')
    parser.add_argument('--geojson', help='Also write the limit lines to this GeoJSON file')
    parser.add_argument('-n', '--next-version', action='store_true', help='Increment pack version')
    parser.add_argument('-e', '--expiration', type=int, default=365, help='Expiration in days')
    parser.add_argument('--cache-dir', default='cache/coastline',
                        help='Where to cache coastline downloads (default: cache/coastline)')
    parser.add_argument('--max-vertices', type=int, default=600_000,
                        help='Refuse to buffer land with more vertices than this (default: 600000)')
    parser.add_argument('--memory-limit-mb', type=int, default=6000,
                        help='Abort if own memory use exceeds this many MB, 0 to disable '
                             '(default: 6000)')
    parser.add_argument('--verify-report', action='store_true',
                        help='Log the full verification breakdown')
    parser.add_argument('--skip-verify', action='store_true',
                        help='Skip the geodesic check of the emitted limit')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    Command(args).run()


if __name__ == '__main__':
    main()
