"""Generate realistic US-based test data for the Route Optimizer POC."""

import random
from datetime import datetime, timedelta
from models import Order, Driver, Vehicle, OrderStatus, Priority
from config import (
    STORE_LAT, STORE_LNG, SLA_WINDOW_HOURS, OPERATING_START_HOUR,
)

# Alpharetta / North Metro Atlanta area locations (within ~10 miles of store)
LOCAL_AREAS = [
    ("North Point Mall, Alpharetta", 34.0595, -84.2717),
    ("Old Milton Pkwy, Alpharetta", 34.0750, -84.3050),
    ("Windward Pkwy, Alpharetta", 34.0985, -84.2645),
    ("Brookside Pkwy, Alpharetta", 34.0612, -84.2350),
    ("Haynes Bridge Rd, Alpharetta", 34.0521, -84.2870),
    ("North Point Pkwy, Alpharetta", 34.0520, -84.2630),
    ("Holcomb Bridge Rd, Roswell", 34.0280, -84.2940),
    ("Alpharetta Hwy, Roswell", 34.0350, -84.3200),
    ("Mansell Rd, Roswell", 34.0730, -84.2950),
    ("Avalon Blvd, Alpharetta", 34.0709, -84.2654),
    ("Holcomb Bridge, Roswell", 34.0280, -84.2830),
    ("McGinnis Ferry Rd, Alpharetta", 34.0800, -84.2100),
    ("Crabapple Rd, Roswell", 34.0867, -84.3150),
    ("Old Alabama Rd, Johns Creek", 34.0395, -84.2050),
    ("State Bridge Rd, Johns Creek", 34.0200, -84.1900),
    ("Alpharetta Hwy, Roswell", 34.0450, -84.3100),
    ("Premiere Pkwy, Duluth", 34.0050, -84.1450),
    ("State Bridge Rd, Alpharetta", 34.0440, -84.2260),
    ("Old Milton Pkwy W, Alpharetta", 34.0750, -84.2900),
    ("Windward Pkwy N, Alpharetta", 34.0950, -84.2400),
    ("Kimball Bridge Rd, Alpharetta", 34.0430, -84.2650),
    ("Webb Bridge Rd, Alpharetta", 34.0612, -84.2350),
    ("Medlock Bridge Rd, Johns Creek", 34.0289, -84.1991),
    ("Milton Pkwy, Milton", 34.0867, -84.3000),
    ("Deerfield Pkwy, Alpharetta", 34.0888, -84.2455),
    ("Encore Pkwy, Alpharetta", 34.0680, -84.2700),
    ("Marconi Dr, Alpharetta", 34.0770, -84.2780),
    ("Westside Pkwy, Alpharetta", 34.0650, -84.3100),
    ("Northwinds Pkwy, Alpharetta", 34.0920, -84.2550),
    ("Peachtree Pkwy, Suwanee", 34.0515, -84.0713),
]

CUSTOMER_NAMES = [
    "James Smith", "Maria Garcia", "Robert Johnson", "Jennifer Williams",
    "Michael Brown", "Linda Jones", "David Miller", "Patricia Davis",
    "William Wilson", "Elizabeth Moore", "Richard Taylor", "Barbara Anderson",
    "Joseph Thomas", "Susan Jackson", "Charles White", "Jessica Harris",
    "Thomas Martin", "Sarah Thompson", "Christopher Lee", "Karen Robinson",
    "Daniel Clark", "Nancy Lewis", "Matthew Walker", "Lisa Hall",
    "Anthony Allen", "Betty Young", "Mark King", "Dorothy Wright",
    "Steven Lopez", "Sandra Hill", "Paul Scott", "Ashley Green",
    "Andrew Adams", "Emily Baker", "Joshua Nelson", "Megan Carter",
    "Kevin Mitchell", "Amanda Perez", "Brian Roberts", "Stephanie Turner",
]


def _jitter(lat: float, lng: float, km_radius: float = 1.0) -> tuple:
    """Add random jitter to coordinates within a radius."""
    delta = km_radius * 0.009
    return (
        lat + random.uniform(-delta, delta),
        lng + random.uniform(-delta, delta),
    )


def generate_orders(
    n: int = 15,
    reference_time: datetime | None = None,
    scenario: str = "normal",
) -> list[Order]:
    """Generate n random orders in the NYC metro area."""
    if reference_time is None:
        reference_time = datetime.now().replace(
            hour=OPERATING_START_HOUR, minute=0, second=0, microsecond=0
        )

    orders = []
    areas = random.sample(LOCAL_AREAS, min(n, len(LOCAL_AREAS)))
    if n > len(LOCAL_AREAS):
        areas += random.choices(LOCAL_AREAS, k=n - len(LOCAL_AREAS))

    names = random.sample(CUSTOMER_NAMES, min(n, len(CUSTOMER_NAMES)))
    if n > len(CUSTOMER_NAMES):
        names += random.choices(CUSTOMER_NAMES, k=n - len(CUSTOMER_NAMES))

    for i in range(n):
        area_name, area_lat, area_lng = areas[i]
        lat, lng = _jitter(area_lat, area_lng, km_radius=0.5)

        if scenario == "peak":
            priority = random.choices(
                [Priority.HIGH, Priority.MEDIUM, Priority.LOW],
                weights=[40, 40, 20], k=1
            )[0]
        else:
            priority = random.choices(
                [Priority.HIGH, Priority.MEDIUM, Priority.LOW],
                weights=[20, 50, 30], k=1
            )[0]

        created_offset_min = random.randint(0, 60)
        created_at = reference_time + timedelta(minutes=created_offset_min)
        ready_at = created_at + timedelta(minutes=random.randint(5, 30))

        sla_hours = SLA_WINDOW_HOURS[priority.value]
        sla_deadline = created_at + timedelta(hours=sla_hours)

        can_defer = priority == Priority.LOW and random.random() < 0.5
        return_eligible = random.random() < 0.3

        order = Order(
            order_id=f"ORD-{i + 1:04d}",
            priority=priority,
            status=OrderStatus.READY,
            created_at=created_at,
            ready_at=ready_at,
            sla_deadline=sla_deadline,
            customer_name=names[i],
            address=f"{random.randint(1, 999)} {area_name}",
            latitude=round(lat, 6),
            longitude=round(lng, 6),
            service_time_min=random.choice([3, 5, 5, 7, 10]),
            weight_kg=round(random.uniform(0.5, 15.0), 1),
            is_peak=scenario == "peak",
            can_defer=can_defer,
            return_trip_eligible=return_eligible,
        )
        orders.append(order)

    return orders


def generate_drivers(
    n: int = 3,
    reference_time: datetime | None = None,
) -> list[Driver]:
    """Generate n available drivers at the store location."""
    if reference_time is None:
        reference_time = datetime.now().replace(
            hour=OPERATING_START_HOUR, minute=0, second=0, microsecond=0
        )

    drivers = []
    for i in range(n):
        lat, lng = _jitter(STORE_LAT, STORE_LNG, km_radius=0.3)
        drivers.append(Driver(
            driver_id=f"DRV-{i + 1:03d}",
            available=True,
            shift_start=reference_time,
            shift_end=reference_time + timedelta(hours=10),
            current_lat=round(lat, 6),
            current_lng=round(lng, 6),
        ))
    return drivers


def generate_vehicles(
    n: int = 3,
) -> list[Vehicle]:
    """Generate n available vehicles at the store location."""
    vehicles = []
    for i in range(n):
        lat, lng = _jitter(STORE_LAT, STORE_LNG, km_radius=0.1)
        vehicles.append(Vehicle(
            vehicle_id=f"VEH-{i + 1:03d}",
            available=True,
            capacity=20,
            vehicle_type=random.choice(["van", "bike", "truck"]),
            current_lat=round(lat, 6),
            current_lng=round(lng, 6),
        ))
    return vehicles
