"""Map and chart visualization for route optimization results."""

import folium
from models import OptimizationResult, Order
from config import STORE_LAT, STORE_LNG, STORE_ADDRESS

# Bold, high-contrast route colors
ROUTE_COLORS = [
    "#FF0000",  # Red
    "#0000FF",  # Blue
    "#008800",  # Green
    "#FF8C00",  # Dark Orange
    "#9400D3",  # Purple
    "#00CED1",  # Turquoise
    "#FF1493",  # Deep Pink
    "#228B22",  # Forest Green
    "#FFD700",  # Gold
    "#4B0082",  # Indigo
]


def generate_route_map(
    result: OptimizationResult,
    orders: list[Order],
) -> str:
    """Generate a Folium map HTML string with optimized routes."""
    m = folium.Map(
        location=[STORE_LAT, STORE_LNG],
        zoom_start=12,
        tiles="OpenStreetMap",
    )

    # Store marker (large, distinct)
    folium.Marker(
        [STORE_LAT, STORE_LNG],
        popup=f"<b>Store / Depot</b><br>{STORE_ADDRESS}",
        tooltip="STORE (Depot)",
        icon=folium.Icon(color="black", icon="home", prefix="fa"),
    ).add_to(m)

    order_map = {o.order_id: o for o in orders}

    # Draw each route with a unique color
    for i, route in enumerate(result.routes):
        color = ROUTE_COLORS[i % len(ROUTE_COLORS)]

        # Split into outbound and return segments
        outbound_stops = [s for s in route.stops if not s.is_return_trip]
        return_stops = [s for s in route.stops if s.is_return_trip]

        # --- Outbound polyline (solid, thick) ---
        outbound_coords = [[STORE_LAT, STORE_LNG]]
        for s in outbound_stops:
            outbound_coords.append([s.latitude, s.longitude])
        # If there are return stops, connect outbound to first return stop
        if return_stops:
            outbound_coords.append([return_stops[0].latitude, return_stops[0].longitude])
        elif outbound_stops:
            # No return stops: go back to store
            outbound_coords.append([STORE_LAT, STORE_LNG])

        # Shadow line for depth
        folium.PolyLine(
            outbound_coords, weight=9, color="#000000", opacity=0.15,
        ).add_to(m)
        # Main outbound line
        folium.PolyLine(
            outbound_coords, weight=5, color=color, opacity=0.9,
            tooltip=f"{route.route_id} OUTBOUND ({route.direction_label}) - {route.orders_count} orders",
        ).add_to(m)

        # --- Return polyline (dashed, same color) ---
        if return_stops:
            return_coords = []
            if outbound_stops:
                return_coords.append([outbound_stops[-1].latitude, outbound_stops[-1].longitude])
            else:
                return_coords.append([STORE_LAT, STORE_LNG])
            for s in return_stops:
                return_coords.append([s.latitude, s.longitude])
            return_coords.append([STORE_LAT, STORE_LNG])

            folium.PolyLine(
                return_coords, weight=5, color=color, opacity=0.7,
                dash_array="12 8",
                tooltip=f"{route.route_id} RETURN - {len(return_stops)} deliveries on return",
            ).add_to(m)

        # --- Stop markers ---
        for stop in route.stops:
            sla_color = "#22c55e" if stop.sla_met else "#ef4444"
            trip_type = "RETURN" if stop.is_return_trip else "OUTBOUND"
            border_style = "dashed" if stop.is_return_trip else "solid"

            popup_html = f"""
            <div style="min-width:220px;font-family:sans-serif">
                <div style="background:{color};color:white;padding:6px 10px;border-radius:6px 6px 0 0;font-weight:bold">
                    {route.route_id} &rarr; Stop #{stop.sequence}
                </div>
                <div style="padding:8px 10px;font-size:13px">
                    <b>{stop.order_id}</b><br>
                    <b>Customer:</b> {stop.customer_name}<br>
                    <b>Address:</b> {stop.address}<br>
                    <b>Priority:</b> <span style="font-weight:bold">{stop.priority}</span><br>
                    <hr style="margin:4px 0">
                    <b>ETA:</b> {stop.arrival_time_min:.0f} min<br>
                    <b>SLA Deadline:</b> {stop.sla_deadline_min:.0f} min<br>
                    <b>SLA:</b> <span style="color:{sla_color};font-weight:bold">
                        {"MET" if stop.sla_met else "MISSED"}</span><br>
                    <b>Trip:</b> {trip_type}<br>
                    <b>Driver:</b> {route.driver_id} |
                    <b>Vehicle:</b> {route.vehicle_id}
                </div>
            </div>
            """

            # Return stops get a square shape, outbound get circles
            if stop.is_return_trip:
                marker_html = f"""
                    <div style="
                        background:{color};color:white;
                        border-radius:4px;
                        width:28px;height:28px;
                        display:flex;align-items:center;justify-content:center;
                        font-weight:bold;font-size:12px;
                        border:3px {border_style} white;
                        box-shadow:0 2px 6px rgba(0,0,0,0.5);
                    ">{stop.sequence}</div>
                """
            else:
                marker_html = f"""
                    <div style="
                        background:{color};color:white;
                        border-radius:50%;
                        width:30px;height:30px;
                        display:flex;align-items:center;justify-content:center;
                        font-weight:bold;font-size:13px;
                        border:3px solid white;
                        box-shadow:0 2px 6px rgba(0,0,0,0.5);
                    ">{stop.sequence}</div>
                """

            folium.Marker(
                [stop.latitude, stop.longitude],
                popup=folium.Popup(popup_html, max_width=320),
                tooltip=f"{route.route_id} #{stop.sequence} - {stop.order_id} ({stop.priority}) {'[RETURN]' if stop.is_return_trip else ''}",
                icon=folium.DivIcon(html=marker_html),
            ).add_to(m)

    # Unassigned orders (grey markers)
    for oid in result.unassigned_orders:
        order = order_map.get(oid)
        if order:
            folium.Marker(
                [order.latitude, order.longitude],
                popup=f"<b>{oid}</b> — UNASSIGNED<br>{order.address}<br>Priority: {order.priority.value}",
                tooltip=f"{oid} (UNASSIGNED)",
                icon=folium.Icon(color="gray", icon="times", prefix="fa"),
            ).add_to(m)

    # Legend
    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
        background:white;padding:14px 18px;border-radius:10px;
        box-shadow:0 3px 12px rgba(0,0,0,0.25);font-size:13px;
        font-family:sans-serif;max-width:300px;">
        <div style="font-weight:bold;font-size:15px;margin-bottom:6px;
            border-bottom:2px solid #e5e7eb;padding-bottom:4px">Route Legend</div>
    """
    for i, route in enumerate(result.routes):
        c = ROUTE_COLORS[i % len(ROUTE_COLORS)]
        return_count = sum(1 for s in route.stops if s.is_return_trip)
        return_info = f" | {return_count} return" if return_count else ""
        legend_html += (
            f'<div style="margin:3px 0">'
            f'<span style="display:inline-block;width:30px;height:4px;'
            f'background:{c};vertical-align:middle;margin-right:6px;'
            f'border-radius:2px"></span>'
            f'<b>{route.route_id}</b> [{route.direction_label}] — '
            f'{route.orders_count} orders{return_info}'
            f'</div>'
        )
    if result.unassigned_orders:
        legend_html += (
            f'<div style="margin:3px 0;color:#888">'
            f'<span style="font-size:16px;margin-right:4px">&#9679;</span>'
            f'Unassigned: {len(result.unassigned_orders)} orders'
            f'</div>'
        )
    legend_html += (
        '<div style="margin-top:6px;font-size:11px;color:#999;'
        'border-top:1px solid #eee;padding-top:4px">'
        '&#9679; Circle = Outbound &nbsp; &#9632; Square = Return trip<br>'
        '&#8212; Solid = Outbound &nbsp; - - - Dashed = Return'
        '</div>'
    )
    legend_html += "</div>"
    m.get_root().html.add_child(folium.Element(legend_html))

    return m._repr_html_()


def generate_chart_data(result: OptimizationResult) -> dict:
    """Prepare chart-ready data from optimization results."""
    sla_met = sum(1 for r in result.routes for s in r.stops if s.sla_met)
    sla_missed = sum(1 for r in result.routes for s in r.stops if not s.sla_met)

    priority_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for r in result.routes:
        for s in r.stops:
            priority_counts[s.priority] = priority_counts.get(s.priority, 0) + 1

    route_stats = []
    for r in result.routes:
        route_stats.append({
            "route_id": r.route_id,
            "orders": r.orders_count,
            "distance_km": r.total_distance_km,
            "duration_min": r.total_duration_min,
            "sla_pct": r.sla_compliance,
            "direction": r.direction_label,
            "driver": r.driver_id,
            "vehicle": r.vehicle_id,
        })

    timeline = []
    for r in result.routes:
        for s in r.stops:
            timeline.append({
                "route": r.route_id,
                "order": s.order_id,
                "arrival": s.arrival_time_min,
                "departure": s.departure_time_min,
                "sla_deadline": s.sla_deadline_min,
                "sla_met": s.sla_met,
            })

    return {
        "sla": {"met": sla_met, "missed": sla_missed},
        "priority": priority_counts,
        "routes": route_stats,
        "timeline": timeline,
        "summary": {
            "total_routes": len(result.routes),
            "assigned": result.assigned_orders,
            "unassigned": len(result.unassigned_orders),
            "deferred": len(result.deferred_orders),
            "total_distance_km": result.total_distance_km,
            "total_duration_min": result.total_duration_min,
            "sla_pct": result.sla_compliance_pct,
            "opt_time_sec": result.optimization_time_sec,
            "driver_util_pct": result.driver_utilization_pct,
            "vehicle_util_pct": result.vehicle_utilization_pct,
        },
    }
