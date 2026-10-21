"""
app/api/routes_dispatch.py
FastAPI router and controller for dispatch order evaluation.
Executes token-optimized evaluation via LocalAgentEngine (or GeminiAgentEngine),
enforcing the strict R4R state machine invariant: auto_approved == False.
"""
from typing import Dict, Any, Optional, Tuple
from app.api.dependencies import ServiceContainer, get_services
from app.services.geo_service import resolve_destination, calculate_tactical_route

try:
    from fastapi import APIRouter, HTTPException, Depends, Request
    from fastapi.responses import JSONResponse
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    class APIRouter:  # type: ignore
        def __init__(self, *args, **kwargs): pass
        def post(self, *args, **kwargs): return lambda fn: fn
        def get(self, *args, **kwargs): return lambda fn: fn
    def Depends(fn=None): return None  # type: ignore


router = APIRouter(prefix="/api/dispatch", tags=["Dispatch"])


def evaluate_dispatch_controller(
    order_data: Dict[str, Any],
    services: Optional[ServiceContainer] = None,
) -> Tuple[int, Dict[str, Any]]:
    """
    Core framework-agnostic controller evaluating a dispatch order.
    Returns: (status_code, response_dict)
    """
    container = services or ServiceContainer.get_instance()
    if not isinstance(order_data, dict):
        return 400, {"error": "INVALID_PAYLOAD", "detail": "Payload must be a valid JSON object"}

    engine_mode = str(order_data.get("engine_mode", "local")).strip().lower()
    version_mode = str(order_data.get("version_mode", "v2")).strip().lower()
    if version_mode not in ("v1", "v2"):
        return 400, {"error": "INVALID_VERSION", "detail": "version_mode debe ser v1 o v2"}
    v1_mode = (version_mode == "v1")

    # Select operational agent engine
    if engine_mode == "gemini":
        engine = container.gemini_engine
    else:
        engine = container.local_engine

    try:
        eval_result = engine.evaluate_order(order_data, v1_mode=v1_mode)
    except Exception as e:
        return 500, {"error": "EVALUATION_FAILED", "detail": str(e)}

    # Governance Invariant Enforcement
    if eval_result.get("auto_approved") is True:
        eval_result["auto_approved"] = False
    if "proposal" in eval_result and isinstance(eval_result["proposal"], dict):
        eval_result["proposal"]["auto_approved"] = False
        eval_result["proposal"]["requiere_firma_humana"] = True

    destino_raw = order_data.get("destino") or order_data.get("destino_comuna", "")
    location = resolve_destination(destino_raw)
    if location:
        eval_result["mapa"] = location

    prop_dict = eval_result.get("proposal") if isinstance(eval_result.get("proposal"), dict) else {}
    assigned_trucks = prop_dict.get("camiones") or prop_dict.get("camiones_asignados") or []
    peso_raw = order_data.get("cargo_weight_kg") if order_data.get("cargo_weight_kg") is not None else order_data.get("peso_kg")
    try:
        peso_val = float(peso_raw) if peso_raw is not None else 0.0
    except (ValueError, TypeError):
        peso_val = 0.0
    hora_val = str(
        order_data.get("hora_despacho")
        or order_data.get("hora_solicitada")
        or order_data.get("hora")
        or order_data.get("requested_datetime")
        or "14:00"
    )
    eval_result["tactical_map"] = calculate_tactical_route(
        origen=str(order_data.get("origen", "Quilicura")),
        destino=str(destino_raw or "Santiago Centro"),
        hora=hora_val,
        peso_kg=peso_val,
        version_mode=version_mode,
        status=str(eval_result.get("status", "R4R")),
        assigned_trucks=assigned_trucks,
    )

    return 200, eval_result


if HAS_FASTAPI:
    @router.post("/evaluate")
    async def evaluate_dispatch_endpoint(
        request: Request,
        services: ServiceContainer = Depends(get_services),
    ):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body in request")

        status_code, data = evaluate_dispatch_controller(body, services=services)
        if status_code >= 400:
            raise HTTPException(status_code=status_code, detail=data.get("detail", data.get("error", "Error")))
        return JSONResponse(status_code=status_code, content=data)
