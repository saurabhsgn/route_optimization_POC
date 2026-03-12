"""
Routing client — Valhalla integration for real road-network routing.

Provides:
- Real distance/time matrices via /sources_to_targets
- Fastest path (auto costing) and shortest path (auto_shorter costing)
- Road restrictions, turn restrictions handled by Valhalla's graph
- Time-dependent routing for traffic-aware ETA
- Graceful fallback to haversine when Valhalla is unavailable
"""

import os
import math
import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

VALHALLA_URL = os.getenv("VALHALLA_URL", "http://localhost:8002")
_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MatrixResult:
    """Distance (meters) and time (seconds) matrices from routing engine."""
    distance_matrix: list[list[int]]  # meters
    time_matrix: list[list[int]]      # seconds
    source: str = "haversine"         # "valhalla" or "haversine"


@dataclass
class RoutePathResult:
    """Detailed route path between an ordered list of locations."""
    total_distance_m: float = 0.0
    total_time_sec: float = 0.0
    costing: str = ""                        # "auto" (fastest) or "auto_shorter" (shortest)
    shape: str = ""                          # encoded polyline
    legs: list[dict] = field(default_factory=list)
    maneuvers: list[dict] = field(default_factory=list)
    has_restrictions: bool = False
    has_tolls: bool = False
    has_ferry: bool = False
    source: str = "haversine"


@dataclass
class RoutingComparison:
    """Side-by-side fastest vs shortest path comparison."""
    fastest: RoutePathResult | None = None
    shortest: RoutePathResult | None = None
    recommended: str = "fastest"             # which one the system picked
    reason: str = ""


# ---------------------------------------------------------------------------
# Haversine fallback
# ---------------------------------------------------------------------------

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _haversine_matrix(
    locations: list[tuple[float, float]],
    detour_factor: float = 1.3,
    avg_speed_kmph: float = 25.0,
) -> MatrixResult:
    """Build distance/time matrices using haversine (fallback)."""
    n = len(locations)
    dist = [[0] * n for _ in range(n)]
    time_ = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                d_km = haversine_km(*locations[i], *locations[j]) * detour_factor
                dist[i][j] = int(d_km * 1000)
                time_[i][j] = int(d_km / avg_speed_kmph * 3600)
    return MatrixResult(distance_matrix=dist, time_matrix=time_, source="haversine")


# ---------------------------------------------------------------------------
# Valhalla client
# ---------------------------------------------------------------------------

def _valhalla_available() -> bool:
    """Quick health check."""
    try:
        r = httpx.get(f"{VALHALLA_URL}/status", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def _to_valhalla_locations(locations: list[tuple[float, float]]) -> list[dict]:
    return [{"lat": lat, "lon": lon} for lat, lon in locations]


def get_matrix(
    locations: list[tuple[float, float]],
    costing: str = "auto",
    departure_time: str | None = None,
    detour_factor: float = 1.3,
    avg_speed_kmph: float = 25.0,
) -> MatrixResult:
    """
    Get distance/time matrix for all location pairs.

    Uses Valhalla /sources_to_targets when available.
    Falls back to haversine otherwise.

    Args:
        locations: list of (lat, lon) tuples; index 0 is depot
        costing: "auto" (fastest) or "auto_shorter" (shortest)
        departure_time: ISO datetime for time-dependent/traffic routing
        detour_factor: multiplier for haversine fallback
        avg_speed_kmph: average speed for haversine fallback
    """
    if not _valhalla_available():
        logger.info("Valhalla unavailable — using haversine fallback")
        return _haversine_matrix(locations, detour_factor, avg_speed_kmph)

    valhalla_locs = _to_valhalla_locations(locations)
    body: dict = {
        "sources": valhalla_locs,
        "targets": valhalla_locs,
        "costing": costing,
    }

    # Time-dependent routing for traffic awareness
    if departure_time:
        body["date_time"] = {"type": 1, "value": departure_time}

    try:
        resp = httpx.post(
            f"{VALHALLA_URL}/sources_to_targets",
            json=body,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("Valhalla matrix request failed: %s — falling back to haversine", e)
        return _haversine_matrix(locations, detour_factor, avg_speed_kmph)

    # Parse Valhalla response into matrices
    n = len(locations)
    dist = [[0] * n for _ in range(n)]
    time_ = [[0] * n for _ in range(n)]

    sources_to_targets = data.get("sources_to_targets", [])
    for i, row in enumerate(sources_to_targets):
        for j, cell in enumerate(row):
            dist[i][j] = int(cell.get("distance", 0) * 1000)   # km → meters
            time_[i][j] = int(cell.get("time", 0))              # seconds

    return MatrixResult(distance_matrix=dist, time_matrix=time_, source="valhalla")


def get_route_path(
    locations: list[tuple[float, float]],
    costing: str = "auto",
    departure_time: str | None = None,
) -> RoutePathResult:
    """
    Get a detailed route path through ordered locations.

    Args:
        locations: ordered list of (lat, lon); first=origin, last=destination
        costing: "auto" (fastest), "auto_shorter" (shortest), "truck" (with restrictions)
        departure_time: ISO datetime for traffic-aware routing
    """
    if not _valhalla_available():
        # Fallback: compute haversine totals
        total_d = sum(
            haversine_km(*locations[i], *locations[i + 1])
            for i in range(len(locations) - 1)
        ) * 1.3
        return RoutePathResult(
            total_distance_m=total_d * 1000,
            total_time_sec=total_d / 25.0 * 3600,
            costing=costing,
            source="haversine",
        )

    valhalla_locs = _to_valhalla_locations(locations)
    body: dict = {
        "locations": valhalla_locs,
        "costing": costing,
        "directions_options": {"units": "kilometers"},
    }
    if departure_time:
        body["date_time"] = {"type": 1, "value": departure_time}

    try:
        resp = httpx.post(
            f"{VALHALLA_URL}/route",
            json=body,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("Valhalla route request failed: %s", e)
        total_d = sum(
            haversine_km(*locations[i], *locations[i + 1])
            for i in range(len(locations) - 1)
        ) * 1.3
        return RoutePathResult(
            total_distance_m=total_d * 1000,
            total_time_sec=total_d / 25.0 * 3600,
            costing=costing,
            source="haversine",
        )

    trip = data.get("trip", {})
    summary = trip.get("summary", {})
    legs = trip.get("legs", [])

    # Extract maneuvers and detect restrictions
    all_maneuvers = []
    has_restrictions = False
    has_tolls = False
    has_ferry = False

    for leg in legs:
        for m in leg.get("maneuvers", []):
            maneuver_info = {
                "instruction": m.get("instruction", ""),
                "distance_km": m.get("length", 0),
                "time_sec": m.get("time", 0),
                "type": m.get("type", 0),
                "street_names": m.get("street_names", []),
            }
            all_maneuvers.append(maneuver_info)

            # Detect road features
            if m.get("toll", False):
                has_tolls = True
            if m.get("ferry", False):
                has_ferry = True
            if m.get("restriction", False):
                has_restrictions = True

    shape = trip.get("shape", "") or (legs[0].get("shape", "") if legs else "")

    return RoutePathResult(
        total_distance_m=summary.get("length", 0) * 1000,
        total_time_sec=summary.get("time", 0),
        costing=costing,
        shape=shape,
        legs=[{
            "distance_km": leg.get("summary", {}).get("length", 0),
            "time_sec": leg.get("summary", {}).get("time", 0),
        } for leg in legs],
        maneuvers=all_maneuvers,
        has_restrictions=has_restrictions,
        has_tolls=has_tolls,
        has_ferry=has_ferry,
        source="valhalla",
    )


def compare_routes(
    locations: list[tuple[float, float]],
    sla_budget_sec: float | None = None,
    departure_time: str | None = None,
) -> RoutingComparison:
    """
    Compare fastest vs shortest path and recommend the best one.

    Decision logic:
    - If both meet SLA → pick shortest (saves fuel/cost)
    - If only fastest meets SLA → pick fastest
    - If neither meets SLA → pick fastest (minimizes breach)
    """
    fastest = get_route_path(locations, costing="auto", departure_time=departure_time)
    shortest = get_route_path(locations, costing="auto_shorter", departure_time=departure_time)

    if sla_budget_sec is None:
        # No SLA constraint — default to fastest
        return RoutingComparison(
            fastest=fastest,
            shortest=shortest,
            recommended="fastest",
            reason="No SLA constraint — fastest path selected",
        )

    fastest_ok = fastest.total_time_sec <= sla_budget_sec
    shortest_ok = shortest.total_time_sec <= sla_budget_sec

    if fastest_ok and shortest_ok:
        return RoutingComparison(
            fastest=fastest,
            shortest=shortest,
            recommended="shortest",
            reason="Both meet SLA — shortest path saves distance/fuel",
        )
    elif fastest_ok:
        return RoutingComparison(
            fastest=fastest,
            shortest=shortest,
            recommended="fastest",
            reason="Only fastest path meets SLA deadline",
        )
    else:
        return RoutingComparison(
            fastest=fastest,
            shortest=shortest,
            recommended="fastest",
            reason="Neither meets SLA — fastest minimizes breach",
        )
