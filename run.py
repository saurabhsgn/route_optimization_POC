"""
Route Optimizer POC — Single entry point.

Usage:
    python run.py

Then open http://localhost:8000 in your browser.
"""

import subprocess
import sys


def ensure_dependencies():
    """Install missing packages from requirements.txt."""
    required = ["ortools", "fastapi", "uvicorn", "folium", "jinja2", "pydantic"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Installing missing packages: {', '.join(missing)}")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            stdout=subprocess.DEVNULL,
        )
        print("Dependencies installed.")


if __name__ == "__main__":
    ensure_dependencies()

    import uvicorn
    print("\n" + "=" * 50)
    print("  Route Optimizer POC")
    print("  Open http://localhost:8000 in your browser")
    print("=" * 50 + "\n")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
