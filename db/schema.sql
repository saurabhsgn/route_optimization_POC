-- Route Optimizer POC — Database Schema (PostgreSQL + PostGIS)

CREATE EXTENSION IF NOT EXISTS postgis;

-- Orders
CREATE TABLE IF NOT EXISTS orders (
    order_id          VARCHAR(20) PRIMARY KEY,
    priority          VARCHAR(10) NOT NULL,
    status            VARCHAR(30) NOT NULL DEFAULT 'READY',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ready_at          TIMESTAMPTZ,
    sla_deadline      TIMESTAMPTZ NOT NULL,
    customer_name     VARCHAR(200),
    address           TEXT,
    latitude          DOUBLE PRECISION NOT NULL,
    longitude         DOUBLE PRECISION NOT NULL,
    location          GEOMETRY(Point, 4326),
    service_time_min  INT DEFAULT 5,
    weight_kg         DOUBLE PRECISION DEFAULT 1.0,
    is_peak           BOOLEAN DEFAULT FALSE,
    can_defer         BOOLEAN DEFAULT FALSE,
    return_trip_eligible BOOLEAN DEFAULT FALSE,
    batch_id          VARCHAR(40),
    created_ts        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_orders_location ON orders USING GIST(location);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_batch ON orders(batch_id);

-- Drivers
CREATE TABLE IF NOT EXISTS drivers (
    driver_id         VARCHAR(20) PRIMARY KEY,
    available         BOOLEAN DEFAULT TRUE,
    shift_start       TIMESTAMPTZ,
    shift_end         TIMESTAMPTZ,
    current_lat       DOUBLE PRECISION,
    current_lng       DOUBLE PRECISION,
    location          GEOMETRY(Point, 4326)
);

-- Vehicles
CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id        VARCHAR(20) PRIMARY KEY,
    available         BOOLEAN DEFAULT TRUE,
    capacity          INT DEFAULT 20,
    vehicle_type      VARCHAR(20) DEFAULT 'van',
    current_lat       DOUBLE PRECISION,
    current_lng       DOUBLE PRECISION,
    location          GEOMETRY(Point, 4326)
);

-- Optimized routes
CREATE TABLE IF NOT EXISTS routes (
    route_id          VARCHAR(20) PRIMARY KEY,
    driver_id         VARCHAR(20),
    vehicle_id        VARCHAR(20),
    departure_time_min DOUBLE PRECISION,
    total_distance_km  DOUBLE PRECISION,
    total_duration_min DOUBLE PRECISION,
    orders_count      INT,
    sla_compliance    DOUBLE PRECISION,
    direction_label   VARCHAR(5),
    route_shape       GEOMETRY(LineString, 4326),
    path_type         VARCHAR(10) DEFAULT 'fastest',
    path_reason       TEXT,
    routing_source    VARCHAR(20) DEFAULT 'haversine',
    has_road_restrictions BOOLEAN DEFAULT FALSE,
    has_tolls         BOOLEAN DEFAULT FALSE,
    has_ferry         BOOLEAN DEFAULT FALSE,
    batch_id          VARCHAR(40),
    optimized_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Route stops (delivery sequence)
CREATE TABLE IF NOT EXISTS route_stops (
    id                SERIAL PRIMARY KEY,
    route_id          VARCHAR(20) REFERENCES routes(route_id) ON DELETE CASCADE,
    order_id          VARCHAR(20),
    sequence          INT NOT NULL,
    latitude          DOUBLE PRECISION,
    longitude         DOUBLE PRECISION,
    location          GEOMETRY(Point, 4326),
    address           TEXT,
    arrival_time_min  DOUBLE PRECISION,
    departure_time_min DOUBLE PRECISION,
    sla_deadline_min  DOUBLE PRECISION,
    sla_met           BOOLEAN,
    is_return_trip    BOOLEAN DEFAULT FALSE,
    priority          VARCHAR(10),
    customer_name     VARCHAR(200)
);
CREATE INDEX IF NOT EXISTS idx_stops_route ON route_stops(route_id);
CREATE INDEX IF NOT EXISTS idx_stops_location ON route_stops USING GIST(location);
