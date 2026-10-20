"""
app/api/routes_dispatch.py
FastAPI router and controller for dispatch order evaluation.
Executes token-optimized evaluation via LocalAgentEngine (or GeminiAgentEngine),
enforcing the strict R4R state machine invariant: auto_approved == False.
"""
from typing import Dict, Any, Optional, Tuple
from app.api.dependencies import ServiceContainer, get_services
from app.services.geo_service import resolve_destination

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
    version_mode = str(order_data.get("version_mode", "v1")).strip().lower()
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

    location = resolve_destination(order_data.get("destino") or order_data.get("destino_comuna", ""))
    if location:
        eval_result["mapa"] = location

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
