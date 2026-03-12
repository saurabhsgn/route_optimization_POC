# Route Optimizer POC — Findings & Fix Tracker

> Auto-updated as fixes are applied. Reference: `requierment.docx` Point 3 (Identified Data Points)

---

## Summary
| Category | Total | Done | Dead Code | Missing |
|---|---|---|---|---|
| Order Data | 16 | 10 | 3 | 3 |
| Status Data | 8 | 8 | 0 | 0 |
| Driver Data | 6 | 3 | 1 | 2 |
| Vehicle Data | 7 | 5 | 0 | 2 |
| Store Data | 5 | 4 | 0 | 1 |
| Routing/Map Data | 10 | 10 | 0 | 0 |
| Business Rules | 10 | 6 | 0 | 4 |
| Analytics | 11 | 6 | 0 | 5 |
| **Total** | **73** | **52** | **4** | **17** |

---

## P0 — Dead Code (exists but not wired into optimizer)

| # | Issue | Location | Status | Fixed Date |
|---|---|---|---|---|
| 1 | `weight_kg` not used in capacity constraint — optimizer uses count=1 per order | optimizer.py:132 | PENDING | |
| 2 | Driver `shift_start/end` not enforced as time constraints | optimizer.py | PENDING | |
| 3 | `is_peak` flag ignored — no peak-priority boost in optimization | optimizer.py | PENDING | |
| 4 | `return_trip_eligible` flag ignored by solver | optimizer.py | PENDING | |

## P1 — Missing Data Fields

| # | Field | Required By | Files to Update | Status | Fixed Date |
|---|---|---|---|---|---|
| 5 | `special_handling` flag on Order | Order Data Points | models.py, schema.sql, data_generator.py | PENDING | |
| 6 | `delivery_window_start/end` (promised window) | Order Data Points | models.py, schema.sql, app.py | PENDING | |
| 7 | `assigned_route_id` on Driver | Driver Data Points | models.py, schema.sql | PENDING | |
| 8 | `assigned_driver_id` on Vehicle | Vehicle Data Points | models.py, schema.sql | PENDING | |
| 9 | `fuel_range_km` on Vehicle | Vehicle Data Points | models.py, schema.sql | PENDING | |
| 10 | `store_id` in config/model | Store Data Points | config.py, models.py | PENDING | |
| 11 | `max_delay_allowed_min` config | Business Rules | config.py | PENDING | |
| 12 | `sla_breach_tolerance_min` config | Business Rules | config.py | PENDING | |
| 13 | Direction clustering thresholds | Business Rules | config.py, optimizer.py | DONE (v3) | 2026-03-11 |
| 14 | Peak-time handling rules config | Business Rules | config.py | PENDING | |
| 15 | Driver capacity/skill/restrictions | Driver Data Points | models.py, schema.sql | PENDING | |

## P2 — Missing Analytics & Outputs

| # | Metric | Required By | Files to Update | Status | Fixed Date |
|---|---|---|---|---|---|
| 16 | Delayed count (separate from unassigned) | Simulation/Analytics | optimizer.py, models.py | PENDING | |
| 17 | Average delivery delay (minutes) | Simulation/Analytics | optimizer.py, models.py | PENDING | |
| 18 | Route fill rate (orders/capacity %) | Simulation/Analytics | optimizer.py, models.py | PENDING | |
| 19 | Cost per route | Simulation/Analytics | optimizer.py, models.py, config.py | PENDING | |
| 20 | Cost per order | Simulation/Analytics | optimizer.py, models.py, config.py | PENDING | |

## P3 — Infrastructure Integration

| # | Feature | Impact | Files to Update | Status | Fixed Date |
|---|---|---|---|---|---|
| 21 | Valhalla integration for real distance/time matrices | Routing accuracy 30-50% improvement | routing_client.py, optimizer.py | DONE | 2026-03-11 |
| 22 | Traffic-aware ETA | Real-world SLA accuracy | routing_client.py, optimizer.py | DONE | 2026-03-11 |
| 23 | PostgreSQL persistence | Data durability | app.py, new db layer | PENDING | |
| 24 | Redis caching for distance matrices | Performance | optimizer.py | PENDING | |
| 25 | Kafka order streaming | Real-time intake | app.py | PENDING | |

---

## Completed Fixes

| # | Issue | Fixed Date | Notes |
|---|---|---|---|
| 21 | Valhalla integration for real distance/time matrices | 2026-03-11 | New `routing_client.py` — Valhalla `/sources_to_targets` for matrices, haversine fallback |
| 22 | Traffic-aware ETA | 2026-03-11 | Time-dependent routing via `departure_time` param in Valhalla requests |
| R1 | Fastest vs shortest path comparison | 2026-03-11 | `compare_routes()` evaluates both, picks based on SLA feasibility |
| R2 | Road/turn restrictions detection | 2026-03-11 | Valhalla handles restrictions in routing; flags exposed on Route model |
| R3 | Toll/ferry detection | 2026-03-11 | Detected from Valhalla maneuvers, exposed as `has_tolls`/`has_ferry` |
| R4 | Route shape (polyline) | 2026-03-11 | Encoded polyline from Valhalla stored on Route for map rendering |
| R5 | Routing metadata on Route model | 2026-03-11 | `path_type`, `path_reason`, `routing_source`, restriction flags |
| R6 | DB schema updated | 2026-03-11 | Added routing columns to `routes` table |
| 13 | Direction clustering thresholds | 2026-03-11 | v3: Dynamic urgency-first spatial clustering with round-trip feasibility checks + floater support |

---

## Improvement Ideas (ongoing)

- Multi-store dispatch support
- Re-optimization when new orders arrive mid-route
- Historical delivery data for better time estimates
- Split delivery support
- Real-time driver GPS tracking integration
- ML-based demand prediction for pre-positioning

---

> Last updated: 2026-03-11
