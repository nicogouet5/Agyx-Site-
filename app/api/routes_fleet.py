"""
app/api/routes_fleet.py
FastAPI router and controller for fleet vehicles, maintenance locks (CAM-04 brake failure),
and municipal urban restrictions.
"""
from typing import Dict, Any, Optional, Tuple
from app.api.dependencies import ServiceContainer, get_services

try:
    from fastapi import APIRouter, HTTPException, Depends
    from fastapi.responses import JSONResponse
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    class APIRouter:  # type: ignore
        def __init__(self, *args, **kwargs): pass
        def post(self, *args, **kwargs): return lambda fn: fn
        def get(self, *args, **kwargs): return lambda fn: fn
    def Depends(fn=None): return None  # type: ignore


router = APIRouter(prefix="/api", tags=["Fleet & Restrictions"])


def get_fleet_controller(
    services: Optional[ServiceContainer] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Retrieves full fleet list with maintenance and availability statuses."""
    container = services or ServiceContainer.get_instance()
    trucks = container.fleet_service.get_all_trucks()
    return 200, {
        "total": len(trucks),
        "trucks": [t.to_dict() for t in trucks],
    }


def get_truck_controller(
    truck_id: str,
    services: Optional[ServiceContainer] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Retrieves details of a specific truck by ID."""
    container = services or ServiceContainer.get_instance()
    truck = container.fleet_service.get_truck_by_id(truck_id)
    if not truck:
        return 404, {"error": "TRUCK_NOT_FOUND", "detail": f"Camión '{truck_id}' no encontrado"}
    return 200, truck.to_dict()


def get_restrictions_controller(
    services: Optional[ServiceContainer] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Retrieves all municipal road restrictions and daytime bans."""
    container = services or ServiceContainer.get_instance()
    restrictions = container.restriction_service.get_all_restrictions()
    return 200, {
        "total": len(restrictions),
        "restrictions": [r.to_dict() for r in restrictions],
    }


def get_zone_restriction_controller(
    zone: str,
    services: Optional[ServiceContainer] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Retrieves restriction details for a specific zone or comuna."""
    container = services or ServiceContainer.get_instance()
    rst = container.restriction_service.get_restriction_for_zone(zone)
    if not rst:
        return 404, {"error": "RESTRICTION_NOT_FOUND", "detail": f"Restricción para zona '{zone}' no encontrada"}
    return 200, rst.to_dict()


from app.services.geo_service import get_network_telemetry


def get_tactical_network_controller(
    hora: str = "14:00",
    services: Optional[ServiceContainer] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Retrieves full Santiago tactical network telemetry, corridors, and live fleet markers."""
    container = services or ServiceContainer.get_instance()
    trucks = [t.to_dict() for t in container.fleet_service.get_all_trucks()]
    return 200, get_network_telemetry(hora=hora, trucks=trucks)


if HAS_FASTAPI:
    @router.get("/tactical-network")
    async def get_tactical_network_endpoint(
        hora: str = "14:00",
        services: ServiceContainer = Depends(get_services),
    ):
        status_code, data = get_tactical_network_controller(hora=hora, services=services)
        return JSONResponse(status_code=status_code, content=data)

    @router.get("/fleet")
    async def get_fleet_endpoint(services: ServiceContainer = Depends(get_services)):
        status_code, data = get_fleet_controller(services=services)
        return JSONResponse(status_code=status_code, content=data)

    @router.get("/fleet/{truck_id}")
    async def get_truck_endpoint(truck_id: str, services: ServiceContainer = Depends(get_services)):
        status_code, data = get_truck_controller(truck_id, services=services)
        if status_code == 404:
            raise HTTPException(status_code=404, detail=data.get("detail", "Not Found"))
        return JSONResponse(status_code=status_code, content=data)

    @router.get("/restrictions")
    async def get_restrictions_endpoint(services: ServiceContainer = Depends(get_services)):
        status_code, data = get_restrictions_controller(services=services)
        return JSONResponse(status_code=status_code, content=data)

    @router.get("/restrictions/{zone}")
    async def get_zone_restriction_endpoint(zone: str, services: ServiceContainer = Depends(get_services)):
        status_code, data = get_zone_restriction_controller(zone, services=services)
        if status_code == 404:
            raise HTTPException(status_code=404, detail=data.get("detail", "Not Found"))
        return JSONResponse(status_code=status_code, content=data)
