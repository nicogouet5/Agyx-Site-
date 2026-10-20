"""
app/dependencies.py
Re-exports dependencies from app.api.dependencies for top-level convenience.
"""
from app.api.dependencies import ServiceContainer, get_services

__all__ = ["ServiceContainer", "get_services"]
