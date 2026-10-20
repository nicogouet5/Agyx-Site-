"""
app/api/__init__.py
Modular API routers re-export package.
"""
from app.api.routes_dispatch import router as dispatch_router
from app.api.routes_r4r import router as r4r_router
from app.api.routes_memory import router as memory_router
from app.api.routes_fleet import router as fleet_router
from app.api.routes_demo import router as demo_router

__all__ = [
    "dispatch_router",
    "r4r_router",
    "memory_router",
    "fleet_router",
    "demo_router",
]
