"""
app/api/routes_memory.py
FastAPI router and controller for Living Memory (Memoria Viva) inspection,
feedback history retrieval, memory reset, and seed rule injection.
Guarantees distilled rules remain strictly within the <80 tokens budget.
"""
from typing import Dict, Any, Optional, Tuple
from app.api.dependencies import ServiceContainer, get_services
from app.security import require_demo_admin

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


router = APIRouter(prefix="/api/memory", tags=["Living Memory"])


def get_memory_controller(
    zone: Optional[str] = None,
    services: Optional[ServiceContainer] = None,
) -> Tuple[int, Dict[str, Any]]:
    """
    Retrieves active Living Memory rules, feedback log history, and token counts.
    """
    container = services or ServiceContainer.get_instance()
    active_rules = container.memory_service.get_active_rules(zone=zone)

    # Fetch feedback history directly from memory service database
    import sqlite3
    conn = sqlite3.connect(container.memory_service.db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT entry_id, case_id, timestamp, supervisor_name, action, rejected_reason, distilled_rule, token_count
        FROM feedback_history
        ORDER BY timestamp DESC
    """)
    rows = cur.fetchall()
    conn.close()

    feedback_history = [{
        "entry_id": r[0],
        "case_id": r[1],
        "timestamp": r[2],
        "supervisor_name": r[3],
        "action": r[4],
        "rejected_reason": r[5],
        "distilled_rule": r[6],
        "token_count": r[7],
    } for r in rows]

    total_tokens = sum(r.get("token_count", 0) for r in active_rules)

    return 200, {
        "active_rules": active_rules,
        "active_rules_count": len(active_rules),
        "feedback_history": feedback_history,
        "total_tokens": total_tokens,
    }


def reset_memory_controller(
    services: Optional[ServiceContainer] = None,
    admin_token: Optional[str] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Resets memory, only when the local demo mode or demo-admin token permits it."""
    allowed, error = require_demo_admin(admin_token)
    if not allowed:
        return 403, error
    container = services or ServiceContainer.get_instance()
    container.memory_service.reset_memory()
    return 200, {
        "status": "OK",
        "message": "Memoria Viva reseteada a estado limpio sin reglas previas.",
        "active_rules_count": 0,
    }


def seed_memory_controller(
    payload: Optional[Dict[str, Any]] = None,
    services: Optional[ServiceContainer] = None,
    admin_token: Optional[str] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Seeds the academic rule only in authorized demo administration mode."""
    allowed, error = require_demo_admin(admin_token)
    if not allowed:
        return 403, error
    container = services or ServiceContainer.get_instance()
    data = payload or {}

    case_id = data.get("case_id", "CASO-3")
    supervisor = data.get("supervisor_name", "Carlos Morales (Jefe de Operaciones)")
    reason = data.get(
        "rejected_reason",
        "Ordenanza Santiago Centro prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs. "
        "Reprogramar a ventana nocturna (21:30/06:00) o subdividir en 2 camiones de 5t",
    )

    try:
        feedback_res = container.memory_service.save_feedback(
            case_id=case_id,
            action="REJECT",
            supervisor_name=supervisor,
            rejected_reason=reason,
        )
        return 200, {
            "status": "OK",
            "message": "Regla de aprendizaje sembrada exitosamente en Memoria Viva.",
            "rule": feedback_res,
        }
    except Exception as e:
        return 500, {"error": "SEED_FAILED", "detail": str(e)}


if HAS_FASTAPI:
    @router.get("")
    @router.get("/")
    async def get_memory_endpoint(
        zone: Optional[str] = None,
        services: ServiceContainer = Depends(get_services),
    ):
        status_code, data = get_memory_controller(zone=zone, services=services)
        return JSONResponse(status_code=status_code, content=data)

    @router.post("/reset")
    async def reset_memory_endpoint(request: Request, services: ServiceContainer = Depends(get_services)):
        status_code, data = reset_memory_controller(
            services=services, admin_token=request.headers.get("X-Agyx-Demo-Token")
        )
        return JSONResponse(status_code=status_code, content=data)

    @router.post("/seed")
    async def seed_memory_endpoint(
        request: Request,
        services: ServiceContainer = Depends(get_services),
    ):
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass
        status_code, data = seed_memory_controller(
            payload=body,
            services=services,
            admin_token=request.headers.get("X-Agyx-Demo-Token"),
        )
        if status_code != 200:
            raise HTTPException(status_code=status_code, detail=data.get("detail", "Error"))
        return JSONResponse(status_code=status_code, content=data)
