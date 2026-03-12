"""Configuration and business rules for the Route Optimizer POC."""

# Store / Depot location (Alpharetta, GA)
STORE_LAT = 34.0401
STORE_LNG = -84.3234
STORE_ADDRESS = "1535 Mansell Rd, Alpharetta, GA 30009"

# Business rules
MAX_ORDERS_PER_ROUTE = 20
MAX_ROUTE_DURATION_MIN = 300  # 5 hours
OPTIMIZATION_TIME_LIMIT_SEC = 10  # 10s for POC speed; increase to 25 for production
AVERAGE_SPEED_KMPH = 25
DETOUR_FACTOR = 1.3
DEFAULT_SERVICE_TIME_MIN = 5

# Priority penalties for OR-Tools (higher = harder to drop)
PRIORITY_PENALTIES = {
    "HIGH": 100000,
    "MEDIUM": 50000,
    "LOW": 10000,
}

# SLA windows by priority (hours from order creation)
SLA_WINDOW_HOURS = {
    "HIGH": 1.5,
    "MEDIUM": 3.0,
    "LOW": 5.0,
}

# Defaults
DEFAULT_NUM_ORDERS = 15
DEFAULT_NUM_DRIVERS = 3
DEFAULT_NUM_VEHICLES = 3
DELIVERY_RADIUS_KM = 12

# Operating hours
OPERATING_START_HOUR = 9
OPERATING_END_HOUR = 21

# Routing engine
ROUTING_COSTING = "auto"              # "auto" (fastest), "auto_shorter" (shortest)
ROUTING_ENABLE_TRAFFIC = True         # use time-dependent routing when departure time known
ROUTING_COMPARE_PATHS = True          # compare fastest vs shortest per route

# Direction clustering
COMPATIBLE_DIRECTION_MAX_ANGLE = 90   # degrees — orders within this angle are "same direction"
DIRECTION_CLUSTERING_ENABLED = True   # enable dynamic urgency-first clustering
MAX_CLUSTER_PROXIMITY_KM = 16.09     # 10 miles — max distance between any two orders in a cluster
