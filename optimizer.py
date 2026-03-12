"""Core route optimization engine using Google OR-Tools VRP solver.

Dynamic clustering: urgency-first spatial clustering groups orders by
SLA pressure + proximity + round-trip feasibility, then OR-Tools
optimizes sequence within each cluster.
"""

import math
import time
import logging
from datetime import datetime
from ortools.constraint_solver import routing_enums_pb2, pywrapcp

from models import (
    Order, Driver, Vehicle, Route, RouteStop, OptimizationResult, Priority,
)
from config import (
    STORE_LAT, STORE_LNG, MAX_ORDERS_PER_ROUTE, MAX_ROUTE_DURATION_MIN,
    OPTIMIZATION_TIME_LIMIT_SEC, AVERAGE_SPEED_KMPH, DETOUR_FACTOR,
    PRIORITY_PENALTIES, ROUTING_COSTING, ROUTING_ENABLE_TRAFFIC,
    ROUTING_COMPARE_PATHS, COMPATIBLE_DIRECTION_MAX_ANGLE,
    DIRECTION_CLUSTERING_ENABLED, MAX_CLUSTER_PROXIMITY_KM,
)
from routing_client import get_matrix, compare_routes, haversine_km

logger = logging.getLogger(__name__)

# Priority urgency weights — higher = more urgent, used as sort tiebreaker
_PRIORITY_URGENCY = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return haversine_km(lat1, lon1, lat2, lon2)


def _bearing(lat1, lon1, lat2, lon2) -> float:
    dlon = math.radians(lon2 - lon1)
    lat1r, lat2r = math.radians(lat1), math.radians(lat2)
    x = math.sin(dlon) * math.cos(lat2r)
    y = (math.cos(lat1r) * math.sin(lat2r)
         - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlon))
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _direction_label(bearing: float) -> str:
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[int((bearing + 22.5) / 45) % 8]


def _angular_diff(a: float, b: float) -> float:
    diff = abs(a - b) % 360
    return min(diff, 360 - diff)


# ---------------------------------------------------------------------------
# Dynamic clustering — urgency + proximity + round-trip feasibility
# ---------------------------------------------------------------------------

def _nn_route_time(
    depot_idx: int,
    order_indices: list[int],
    time_matrix: list[list[int]],
) -> float:
    """Estimate round-trip time using nearest-neighbor heuristic (minutes)."""
    if not order_indices:
        return 0.0
    # depot_idx is typically 0 in the time_matrix
    # order_indices are 1-based (order i → matrix index i+1)
    nodes = [idx + 1 for idx in order_indices]  # matrix indices
    visited = []
    current = depot_idx
    remaining = set(nodes)

    while remaining:
        nearest = min(remaining, key=lambda n: time_matrix[current][n])
        visited.append(nearest)
        current = nearest
        remaining.remove(nearest)

    # Total: depot → stops → depot
    total = time_matrix[depot_idx][visited[0]]
    for i in range(len(visited) - 1):
        total += time_matrix[visited[i]][visited[i + 1]]
    total += time_matrix[visited[-1]][depot_idx]
    return float(total)


def dynamic_cluster(
    eligible: list[Order],
    time_matrix: list[list[int]],
    bearings: list[float],
    reference_time: datetime,
    num_vehicles: int,
    max_orders: int = MAX_ORDERS_PER_ROUTE,
    max_route_min: int = MAX_ROUTE_DURATION_MIN,
    max_angle: float = COMPATIBLE_DIRECTION_MAX_ANGLE,
    max_proximity_km: float = MAX_CLUSTER_PROXIMITY_KM,
) -> tuple[list[list[int]], list[int]]:
    """
    Dynamic urgency-aware clustering.

    Algorithm:
    1. Score each order by urgency: SLA slack / priority weight
    2. Pick the most urgent unassigned order as cluster seed
    3. Expand by greedily adding nearest compatible orders that keep the
       round-trip feasible within SLA (with 15% buffer for OR-Tools to
       find a better sequence than nearest-neighbor)
    4. Direction compatibility enforced (max_angle threshold)
    5. Orders that can't fit any cluster are returned as "floaters" — they
       get no hard vehicle constraint so OR-Tools can place them anywhere

    Returns: (clusters, floaters)
        clusters: list of order index lists (hard-constrained to vehicles)
        floaters: list of order indices (no vehicle constraint, may be dropped)
    """
    n = len(eligible)
    if n == 0:
        return [], []

    NN_BUFFER = 0.85  # NN overestimates — allow 15% slack for OR-Tools

    # SLA slack in minutes
    sla_slacks = []
    for o in eligible:
        slack = (o.sla_deadline - reference_time).total_seconds() / 60.0
        sla_slacks.append(max(0, slack))

    # Urgency: lower = more urgent
    urgency = []
    for i, o in enumerate(eligible):
        pw = _PRIORITY_URGENCY.get(o.priority.value, 1)
        urgency.append(sla_slacks[i] / pw)

    sorted_indices = sorted(range(n), key=lambda i: urgency[i])

    assigned = set()
    clusters: list[list[int]] = []

    for seed_idx in sorted_indices:
        if seed_idx in assigned:
            continue
        if len(clusters) >= num_vehicles:
            break

        # Check seed feasibility: can a single round trip reach this order?
        seed_rt = _nn_route_time(0, [seed_idx], time_matrix)
        if seed_rt * NN_BUFFER > sla_slacks[seed_idx]:
            continue  # this order is unreachable within SLA — skip as seed

        cluster = [seed_idx]
        assigned.add(seed_idx)

        # Greedily expand
        for _ in range(max_orders - 1):
            best_candidate = None
            best_cost = float('inf')

            for c in sorted_indices:
                if c in assigned:
                    continue

                # Direction compatibility
                cluster_bearings = [bearings[i] for i in cluster]
                avg_bearing = sum(cluster_bearings) / len(cluster_bearings)
                if _angular_diff(bearings[c], avg_bearing) > max_angle:
                    continue

                # Proximity: candidate must be within max distance of every order in cluster
                too_far = False
                for ci_idx in cluster:
                    dist_km = haversine_km(
                        eligible[c].latitude, eligible[c].longitude,
                        eligible[ci_idx].latitude, eligible[ci_idx].longitude,
                    )
                    if dist_km > max_proximity_km:
                        too_far = True
                        break
                if too_far:
                    continue

                # Round-trip feasibility (with buffer)
                trial = cluster + [c]
                route_time = _nn_route_time(0, trial, time_matrix) * NN_BUFFER
                trial_sla = min(sla_slacks[i] for i in trial)

                if route_time > trial_sla or route_time > max_route_min:
                    continue

                # Cost: travel time increase, prefer nearby + high margin
                prev_time = _nn_route_time(0, cluster, time_matrix) * NN_BUFFER
                added_time = route_time - prev_time
                sla_margin = trial_sla - route_time
                cost = added_time - (sla_margin * 0.1)

                if cost < best_cost:
                    best_cost = cost
                    best_candidate = c

            if best_candidate is None:
                break

            cluster.append(best_candidate)
            assigned.add(best_candidate)

        clusters.append(cluster)

    # Try to fit remaining orders into existing clusters
    remaining = [i for i in range(n) if i not in assigned]
    for r in remaining[:]:
        best_ci = None
        best_cost = float('inf')

        for ci, cluster in enumerate(clusters):
            if len(cluster) >= max_orders:
                continue

            cluster_bearings = [bearings[i] for i in cluster]
            avg_bearing = sum(cluster_bearings) / len(cluster_bearings)
            if _angular_diff(bearings[r], avg_bearing) > max_angle:
                continue

            # Proximity check
            too_far = False
            for ci_idx in cluster:
                if haversine_km(
                    eligible[r].latitude, eligible[r].longitude,
                    eligible[ci_idx].latitude, eligible[ci_idx].longitude,
                ) > max_proximity_km:
                    too_far = True
                    break
            if too_far:
                continue

            trial = cluster + [r]
            route_time = _nn_route_time(0, trial, time_matrix) * NN_BUFFER
            trial_sla = min(sla_slacks[i] for i in trial)

            if route_time > trial_sla or route_time > max_route_min:
                continue

            added = route_time - _nn_route_time(0, cluster, time_matrix) * NN_BUFFER
            if added < best_cost:
                best_cost = added
                best_ci = ci

        if best_ci is not None:
            clusters[best_ci].append(r)
            assigned.add(r)
            remaining.remove(r)

    # Remaining = floaters (no hard constraint, OR-Tools decides)
    floaters = [i for i in range(n) if i not in assigned]

    # Log
    for ci, cluster in enumerate(clusters):
        cb = [bearings[i] for i in cluster]
        avg_b = sum(cb) / len(cb)
        tightest = min(sla_slacks[i] for i in cluster)
        rt = _nn_route_time(0, cluster, time_matrix)
        high_c = sum(1 for i in cluster if eligible[i].priority.value == "HIGH")
        logger.info(
            "Cluster %d (%s): %d orders (%d HIGH), route≈%.0fmin, "
            "SLA=%.0fmin, margin=%.0fmin",
            ci, _direction_label(avg_b), len(cluster), high_c,
            rt, tightest, tightest - rt * NN_BUFFER,
        )
    if floaters:
        logger.info(
            "Floaters: %d orders (no hard constraint, OR-Tools decides)",
            len(floaters),
        )

    return clusters, floaters


# ---------------------------------------------------------------------------
# Route Optimizer
# ---------------------------------------------------------------------------

class RouteOptimizer:
    def __init__(
        self,
        orders: list[Order],
        drivers: list[Driver],
        vehicles: list[Vehicle],
        reference_time: datetime,
    ):
        self.orders = orders
        self.drivers = drivers
        self.vehicles = vehicles
        self.reference_time = reference_time
        self.store_lat = STORE_LAT
        self.store_lng = STORE_LNG

    def optimize(self) -> OptimizationResult:
        start = time.time()

        ready = [o for o in self.orders if o.status.value == "READY"]

        # During peak: exclude LOW priority orders — defer them
        is_peak = any(o.is_peak for o in ready)
        if is_peak:
            eligible = [o for o in ready if o.priority != Priority.LOW]
            peak_deferred = [o for o in ready if o.priority == Priority.LOW]
            if peak_deferred:
                logger.info(
                    "Peak mode: deferring %d LOW priority orders",
                    len(peak_deferred),
                )
        else:
            eligible = ready
            peak_deferred = []

        self._peak_deferred = peak_deferred
        available_drivers = [d for d in self.drivers if d.available]
        available_vehicles = [v for v in self.vehicles if v.available]
        num_vehicles = min(len(available_drivers), len(available_vehicles))

        if not eligible or num_vehicles == 0:
            return self._empty_result(eligible, time.time() - start)

        # Build location list: index 0 = depot, 1..N = orders
        locations = [(self.store_lat, self.store_lng)]
        for o in eligible:
            locations.append((o.latitude, o.longitude))

        n = len(locations)

        # Compute bearings
        bearings = [
            _bearing(self.store_lat, self.store_lng, o.latitude, o.longitude)
            for o in eligible
        ]

        # --- Distance/time matrices ---
        departure_iso = None
        if ROUTING_ENABLE_TRAFFIC and self.reference_time:
            departure_iso = self.reference_time.isoformat()

        matrix_result = get_matrix(
            locations,
            costing=ROUTING_COSTING,
            departure_time=departure_iso,
            detour_factor=DETOUR_FACTOR,
            avg_speed_kmph=AVERAGE_SPEED_KMPH,
        )
        self._routing_source = matrix_result.source
        logger.info("Routing source: %s", matrix_result.source)

        dist_matrix = matrix_result.distance_matrix  # meters
        time_matrix = [[0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                travel_min = matrix_result.time_matrix[i][j] / 60.0
                svc = eligible[j - 1].service_time_min if j > 0 else 0
                time_matrix[i][j] = int(travel_min + svc)

        # --- Dynamic clustering ---
        if DIRECTION_CLUSTERING_ENABLED and num_vehicles > 1:
            clusters, floaters = dynamic_cluster(
                eligible, time_matrix, bearings,
                self.reference_time, num_vehicles,
            )

            # Allocate vehicles to clusters proportionally
            zone_vehicle_map = {}
            vehicle_cursor = 0
            remaining_v = num_vehicles - len(clusters)

            for ci, cluster in enumerate(clusters):
                count = 1
                if remaining_v > 0:
                    total_orders = sum(len(c) for c in clusters)
                    extra = round(remaining_v * len(cluster) / max(total_orders, 1))
                    extra = min(extra, remaining_v)
                    count += extra
                    remaining_v -= extra
                zone_vehicle_map[ci] = list(range(vehicle_cursor, vehicle_cursor + count))
                vehicle_cursor += count

            while vehicle_cursor < num_vehicles:
                largest = max(range(len(clusters)), key=lambda i: len(clusters[i]))
                zone_vehicle_map[largest].append(vehicle_cursor)
                vehicle_cursor += 1

            # Build order→allowed vehicles (floaters get no constraint)
            order_allowed_vehicles = [None] * len(eligible)
            for ci, cluster in enumerate(clusters):
                for order_idx in cluster:
                    order_allowed_vehicles[order_idx] = zone_vehicle_map[ci]
            # Floaters: order_allowed_vehicles[i] stays None → no constraint
        else:
            order_allowed_vehicles = None

        # --- OR-Tools VRP setup ---
        manager = pywrapcp.RoutingIndexManager(n, num_vehicles, 0)
        routing = pywrapcp.RoutingModel(manager)

        def time_cb(from_idx, to_idx):
            return time_matrix[manager.IndexToNode(from_idx)][manager.IndexToNode(to_idx)]

        time_cb_idx = routing.RegisterTransitCallback(time_cb)
        routing.SetArcCostEvaluatorOfAllVehicles(time_cb_idx)
        routing.AddDimension(
            time_cb_idx,
            60,  # max waiting
            MAX_ROUTE_DURATION_MIN,
            False,
            "Time",
        )
        time_dim = routing.GetDimensionOrDie("Time")

        # Time windows
        for i, order in enumerate(eligible):
            idx = manager.NodeToIndex(i + 1)
            sla_min = int(
                (order.sla_deadline - self.reference_time).total_seconds() / 60
            )
            sla_min = max(1, min(sla_min, MAX_ROUTE_DURATION_MIN))
            time_dim.CumulVar(idx).SetRange(0, sla_min)

        for v in range(num_vehicles):
            time_dim.CumulVar(routing.Start(v)).SetRange(0, MAX_ROUTE_DURATION_MIN)
            time_dim.CumulVar(routing.End(v)).SetRange(0, MAX_ROUTE_DURATION_MIN)
            time_dim.SetSpanCostCoefficientForVehicle(1, v)

        # Capacity
        def demand_cb(idx):
            node = manager.IndexToNode(idx)
            return 1 if node > 0 else 0

        demand_cb_idx = routing.RegisterUnaryTransitCallback(demand_cb)
        routing.AddDimensionWithVehicleCapacity(
            demand_cb_idx, 0,
            [MAX_ORDERS_PER_ROUTE] * num_vehicles,
            True, "Capacity",
        )

        # Hard cluster constraints (floaters have None → no constraint)
        if order_allowed_vehicles is not None:
            solver = routing.solver()
            for i in range(len(eligible)):
                allowed = order_allowed_vehicles[i]
                if allowed is not None:
                    node_idx = manager.NodeToIndex(i + 1)
                    solver.Add(routing.VehicleVar(node_idx).Member(allowed))

        # Priority drop penalties
        for i, order in enumerate(eligible):
            penalty = PRIORITY_PENALTIES.get(order.priority.value, 50000)
            routing.AddDisjunction([manager.NodeToIndex(i + 1)], penalty)

        # Search
        search_params = pywrapcp.DefaultRoutingSearchParameters()
        search_params.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_params.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        search_params.time_limit.FromSeconds(OPTIMIZATION_TIME_LIMIT_SEC)

        solution = routing.SolveWithParameters(search_params)
        opt_time = time.time() - start

        if solution:
            return self._extract_solution(
                solution, routing, manager, eligible,
                available_drivers, available_vehicles,
                dist_matrix, time_matrix, opt_time,
            )
        return self._empty_result(eligible, opt_time)

    def _extract_solution(
        self, solution, routing, manager, orders,
        drivers, vehicles, dist_matrix, time_matrix, opt_time,
    ) -> OptimizationResult:
        time_dim = routing.GetDimensionOrDie("Time")
        num_vehicles = routing.vehicles()
        routes = []
        assigned_ids = set()

        for v in range(num_vehicles):
            stops = []
            index = routing.Start(v)
            route_dist = 0

            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                next_index = solution.Value(routing.NextVar(index))
                next_node = manager.IndexToNode(next_index)

                if node > 0:
                    order = orders[node - 1]
                    arrival = solution.Value(time_dim.CumulVar(index))
                    sla_min = int(
                        (order.sla_deadline - self.reference_time).total_seconds() / 60
                    )
                    stops.append(RouteStop(
                        order_id=order.order_id,
                        sequence=len(stops) + 1,
                        latitude=order.latitude,
                        longitude=order.longitude,
                        address=order.address,
                        arrival_time_min=arrival,
                        departure_time_min=arrival + order.service_time_min,
                        sla_deadline_min=sla_min,
                        sla_met=arrival <= sla_min,
                        is_return_trip=False,
                        priority=order.priority.value,
                        customer_name=order.customer_name,
                    ))
                    assigned_ids.add(order.order_id)

                route_dist += dist_matrix[node][next_node]
                index = next_index

            if not stops:
                continue

            # Mark return-trip stops
            for i in range(1, len(stops)):
                d_curr = haversine(
                    stops[i].latitude, stops[i].longitude,
                    self.store_lat, self.store_lng,
                )
                d_prev = haversine(
                    stops[i - 1].latitude, stops[i - 1].longitude,
                    self.store_lat, self.store_lng,
                )
                if d_curr < d_prev and i > len(stops) // 2:
                    stops[i].is_return_trip = True

            dep_time = solution.Value(time_dim.CumulVar(routing.Start(v)))
            end_time = solution.Value(time_dim.CumulVar(routing.End(v)))

            # Direction coherence
            stop_bearings = [
                _bearing(self.store_lat, self.store_lng, s.latitude, s.longitude)
                for s in stops
            ]
            avg_bearing = sum(stop_bearings) / len(stop_bearings) if stop_bearings else 0

            if len(stop_bearings) > 1:
                compat = sum(
                    1 for si in range(len(stop_bearings))
                    for sj in range(si + 1, len(stop_bearings))
                    if _angular_diff(stop_bearings[si], stop_bearings[sj]) <= COMPATIBLE_DIRECTION_MAX_ANGLE
                )
                total_p = len(stop_bearings) * (len(stop_bearings) - 1) // 2
                direction_coherence = round(compat / total_p * 100, 1) if total_p else 100.0
            else:
                direction_coherence = 100.0

            sla_ok = sum(1 for s in stops if s.sla_met)

            logger.info(
                "Route %s: %d stops, dir=%s, coherence=%.0f%%, "
                "duration=%.0fmin, SLA=%.0f%%",
                f"R-{v + 1:03d}", len(stops), _direction_label(avg_bearing),
                direction_coherence, end_time - dep_time,
                sla_ok / len(stops) * 100,
            )

            # Fastest vs shortest comparison
            path_type = "fastest"
            path_reason = ""
            route_shape = ""
            has_restrictions = has_tolls = has_ferry = False

            if ROUTING_COMPARE_PATHS and stops:
                route_locs = [(self.store_lat, self.store_lng)]
                route_locs += [(s.latitude, s.longitude) for s in stops]
                route_locs.append((self.store_lat, self.store_lng))

                sla_budget = min(s.sla_deadline_min for s in stops) * 60
                dep_iso = (
                    self.reference_time.isoformat()
                    if ROUTING_ENABLE_TRAFFIC and self.reference_time else None
                )
                comparison = compare_routes(route_locs, sla_budget, dep_iso)
                path_type = comparison.recommended
                path_reason = comparison.reason
                chosen = comparison.fastest if path_type == "fastest" else comparison.shortest
                if chosen:
                    route_shape = chosen.shape
                    has_restrictions = chosen.has_restrictions
                    has_tolls = chosen.has_tolls
                    has_ferry = chosen.has_ferry

            routes.append(Route(
                route_id=f"R-{v + 1:03d}",
                driver_id=drivers[v].driver_id if v < len(drivers) else f"DRV-{v + 1}",
                vehicle_id=vehicles[v].vehicle_id if v < len(vehicles) else f"VEH-{v + 1}",
                stops=stops,
                departure_time_min=dep_time,
                total_distance_km=round(route_dist / 1000, 2),
                total_duration_min=end_time - dep_time,
                orders_count=len(stops),
                sla_compliance=round(sla_ok / len(stops) * 100, 1),
                direction_label=_direction_label(avg_bearing),
                path_type=path_type,
                path_reason=path_reason,
                routing_source=getattr(self, '_routing_source', 'haversine'),
                shape=route_shape,
                has_road_restrictions=has_restrictions,
                has_tolls=has_tolls,
                has_ferry=has_ferry,
                direction_coherence_pct=direction_coherence,
            ))

        unassigned = [o.order_id for o in orders if o.order_id not in assigned_ids]
        deferred = [
            o.order_id for o in orders
            if o.order_id in unassigned and o.can_defer
        ]

        total_stops = sum(len(r.stops) for r in routes)
        sla_ok_total = sum(1 for r in routes for s in r.stops if s.sla_met)

        return OptimizationResult(
            routes=routes,
            assigned_orders=len(assigned_ids),
            unassigned_orders=unassigned,
            deferred_orders=deferred,
            total_distance_km=round(sum(r.total_distance_km for r in routes), 2),
            total_duration_min=round(sum(r.total_duration_min for r in routes), 2),
            sla_compliance_pct=round(
                sla_ok_total / total_stops * 100, 1
            ) if total_stops > 0 else 100.0,
            optimization_time_sec=round(opt_time, 2),
            driver_utilization_pct=round(
                len(routes) / len(self.drivers) * 100, 1
            ) if self.drivers else 0,
            vehicle_utilization_pct=round(
                len(routes) / len(self.vehicles) * 100, 1
            ) if self.vehicles else 0,
            routing_source=getattr(self, '_routing_source', 'haversine'),
        )

    def _empty_result(self, orders, opt_time) -> OptimizationResult:
        return OptimizationResult(
            routes=[],
            assigned_orders=0,
            unassigned_orders=[o.order_id for o in orders],
            deferred_orders=[o.order_id for o in orders if o.can_defer],
            total_distance_km=0,
            total_duration_min=0,
            sla_compliance_pct=0,
            optimization_time_sec=round(opt_time, 2),
            driver_utilization_pct=0,
            vehicle_utilization_pct=0,
        )
