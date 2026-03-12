"""Data models for the Route Optimizer POC."""

from enum import Enum
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class OrderStatus(str, Enum):
    INVOICE = "INVOICE"
    READY = "READY"
    ROUTING = "ROUTING"
    ROUTE_AGENT_IN_PROGRESS = "ROUTE_AGENT_IN_PROGRESS"
    DELIVERED = "DELIVERED"
    DELAYED = "DELAYED"
    DEFERRED = "DEFERRED"
    CANCELLED = "CANCELLED"


class Priority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Order(BaseModel):
    order_id: str
    priority: Priority
    status: OrderStatus
    created_at: datetime
    ready_at: Optional[datetime] = None
    sla_deadline: datetime
    customer_name: str
    address: str
    latitude: float
    longitude: float
    service_time_min: int = 5
    weight_kg: float = 1.0
    is_peak: bool = False
    can_defer: bool = False
    return_trip_eligible: bool = False


class Driver(BaseModel):
    driver_id: str
    available: bool = True
    shift_start: datetime
    shift_end: datetime
    current_lat: float
    current_lng: float


class Vehicle(BaseModel):
    vehicle_id: str
    available: bool = True
    capacity: int = 20
    vehicle_type: str = "van"
    current_lat: float
    current_lng: float


class RouteStop(BaseModel):
    order_id: str
    sequence: int
    latitude: float
    longitude: float
    address: str
    arrival_time_min: float
    departure_time_min: float
    sla_deadline_min: float
    sla_met: bool
    is_return_trip: bool = False
    priority: str = "MEDIUM"
    customer_name: str = ""


class Route(BaseModel):
    route_id: str
    driver_id: str
    vehicle_id: str
    stops: List[RouteStop]
    departure_time_min: float
    total_distance_km: float
    total_duration_min: float
    orders_count: int
    sla_compliance: float
    direction_label: str = ""
    # Routing metadata
    path_type: str = "fastest"           # "fastest" or "shortest"
    path_reason: str = ""                # why this path was chosen
    routing_source: str = "haversine"    # "valhalla" or "haversine"
    shape: str = ""                      # encoded polyline from Valhalla
    has_road_restrictions: bool = False
    has_tolls: bool = False
    has_ferry: bool = False
    # Direction clustering
    direction_coherence_pct: float = 100.0  # % of stop pairs in compatible direction


class OptimizationResult(BaseModel):
    routes: List[Route]
    assigned_orders: int
    unassigned_orders: List[str]
    deferred_orders: List[str]
    total_distance_km: float
    total_duration_min: float
    sla_compliance_pct: float
    optimization_time_sec: float
    driver_utilization_pct: float
    vehicle_utilization_pct: float
    routing_source: str = "haversine"    # "valhalla" or "haversine"
