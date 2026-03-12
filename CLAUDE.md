# Route Optimizer POC — Claude Code Instructions

## Project Overview
- FastAPI delivery route optimization app using OR-Tools
- Store/depot: Alpharetta, GA (34.0401, -84.3234)
- Run with: `python run.py` → http://localhost:8000
- Docker services: PostgreSQL+PostGIS, Redis, Kafka, Valhalla

## Key Files
- `app.py` — FastAPI endpoints (dashboard, generate, optimize, upload, simulate)
- `optimizer.py` — OR-Tools CVRPTW solver
- `visualizer.py` — Folium map + chart data
- `data_generator.py` — random order/driver/vehicle generation
- `models.py` — Pydantic models (Order, Driver, Vehicle, Route, etc.)
- `config.py` — business rules, constants
- `geocoder.py` — Nominatim geocoding
- `templates/dashboard.html` — single-page UI
- `docker-compose.yml` — infrastructure services
- `db/schema.sql` — PostgreSQL schema

## Rules for Token Efficiency
1. **Do NOT re-read files** already read in this session unless edited
2. **Skip explanations** — go straight to code changes
3. **No summaries** of what was done unless asked
4. **No repeating** file contents back to the user
5. **Batch edits** — combine multiple edits to the same file in one step
6. **Minimal output** — only show what changed or what's needed
7. **No docstrings/comments** unless the user asks for them
8. **No type annotations** on unchanged code
9. **Ask before exploring** — don't read 10 files to answer a simple question

## Tech Stack
- Python 3.12+, FastAPI, Pydantic v2, OR-Tools, Folium, openpyxl
- Geocoding: Nominatim (free, no API key)
- No git repo initialized yet

## User Preferences
- Windows 11, PyCharm IDE, bash shell via Claude Code
- Prefers concise communication
- Token-conscious — avoid unnecessary reads/writes