"""
app/api/routes_r4r.py
FastAPI router and controller for the R4R (Ready for Review) state machine,
human supervisor review actions, and zero auto-approval inactivity safeguards.
Strictly returns HTTP 400 or HTTP 422 if a rejection is submitted with an empty reason.
"""
from typing import Dict, Any, Optional, Tuple
from app.api.dependencies import ServiceContainer, get_services
from app.models.review import clean_human_text

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


router = APIRouter(prefix="/api/r4r", tags=["R4R & Human Governance"])


def get_queue_controller(
    services: Optional[ServiceContainer] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Retrieves all proposals in the R4R queue."""
    container = services or ServiceContainer.get_instance()
    items = container.r4r_service.get_queue()
    pending = sum(1 for p in items if p.get("estado") in ("R4R", "R4R_INFO_INCOMPLETA", "BLOQUEADO_RIESGO"))
    return 200, {
        "total": len(items),
        "pending_count": pending,
        "items": items,
    }


def get_proposal_controller(
    case_id: str,
    services: Optional[ServiceContainer] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Retrieves a single proposal audit record by case_id or proposal_id."""
    container = services or ServiceContainer.get_instance()
    proposal = container.r4r_service.get_proposal(case_id)
    if not proposal:
        return 404, {"error": "NOT_FOUND", "detail": f"Proposal '{case_id}' not found"}
    return 200, proposal


def review_proposal_controller(
    payload: Dict[str, Any],
    services: Optional[ServiceContainer] = None,
) -> Tuple[int, Dict[str, Any]]:
    """
    Executes supervisor review action (APPROVE or REJECT).
    Enforces Certamen 2 rubric validation:
    - Empty or whitespace rejected_reason on REJECT returns HTTP 422 / 400.
    - Proposal remains in R4R on validation failure.
    - auto_approved is unconditionally False.
    """
    container = services or ServiceContainer.get_instance()
    if not isinstance(payload, dict):
        return 400, {"error": "INVALID_PAYLOAD", "detail": "Request body must be a JSON object"}

    case_id = (payload.get("case_id") or "").strip()
    if not case_id:
        return 400, {"error": "MISSING_CASE_ID", "detail": "case_id is required for review action"}

    action = (payload.get("action") or "").strip().upper()
    if action not in ("APPROVE", "REJECT"):
        return 400, {"error": "INVALID_ACTION", "detail": f"Action '{action}' is invalid. Must be 'APPROVE' or 'REJECT'"}

    supervisor_name = clean_human_text(payload.get("supervisor_name"))
    if not supervisor_name:
        return 400, {"error": "MISSING_SUPERVISOR_NAME", "detail": "supervisor_name is mandatory for human review actions"}

    rejected_reason = payload.get("rejected_reason")
    signature_token = payload.get("signature_token")

    # STRICT RUBRIC VALIDATION: REJECT requires non-empty rejected_reason
    if action == "REJECT":
        clean_reason = clean_human_text(rejected_reason)
        if not clean_reason:
            return 422, {
                "error": "EMPTY_REJECTION_REASON",
                "detail": "Validation Error: rejected_reason cannot be empty or whitespace when rejecting a proposal",
                "case_id": case_id,
                "action": "REJECT",
            }
    else:
        clean_reason = None

    try:
        review_result = container.r4r_service.review_proposal(
            case_id=case_id,
            action=action,
            supervisor_name=supervisor_name,
            rejected_reason=clean_reason,
            signature_token=signature_token,
        )
        return 200, review_result
    except KeyError:
        return 404, {"error": "PROPOSAL_NOT_FOUND", "detail": f"Proposal '{case_id}' not found in R4R store"}
    except ValueError as ve:
        return 422, {"error": "VALIDATION_ERROR", "detail": str(ve)}
    except Exception as e:
        return 500, {"error": "REVIEW_EXECUTION_FAILED", "detail": str(e)}


def simulate_inactivity_controller(
    payload: Dict[str, Any],
    services: Optional[ServiceContainer] = None,
) -> Tuple[int, Dict[str, Any]]:
    """
    Simulates operator inactivity or timeout.
    Proves proposal remains strictly locked in R4R with auto_approved=False.
    """
    container = services or ServiceContainer.get_instance()
    if not isinstance(payload, dict):
        return 400, {"error": "INVALID_PAYLOAD", "detail": "Request body must be a JSON object"}

    case_id = (payload.get("case_id") or "").strip()
    if not case_id:
        return 400, {"error": "MISSING_CASE_ID", "detail": "case_id is required"}

    raw_idle = payload.get("idle_minutes")
    if raw_idle is None:
        if "idle_minutes" in payload:
            return 400, {
                "error": "INVALID_IDLE_MINUTES",
                "detail": "idle_minutes cannot be null; must be a valid integer number of minutes",
            }
        idle_minutes = 60
    else:
        try:
            if isinstance(raw_idle, bool):
                return 400, {
                    "error": "INVALID_IDLE_MINUTES",
                    "detail": "idle_minutes cannot be boolean; must be an integer",
                }
            if isinstance(raw_idle, (int, float)):
                idle_minutes = int(raw_idle)
            elif isinstance(raw_idle, str):
                s_idle = raw_idle.strip()
                if not s_idle:
                    return 400, {
                        "error": "INVALID_IDLE_MINUTES",
                        "detail": "idle_minutes cannot be empty or whitespace",
                    }
                idle_minutes = int(s_idle)
            else:
                return 400, {
                    "error": "INVALID_IDLE_MINUTES",
                    "detail": f"idle_minutes must be an integer, got: {type(raw_idle).__name__}",
                }
        except (ValueError, TypeError, OverflowError):
            return 400, {
                "error": "INVALID_IDLE_MINUTES",
                "detail": f"idle_minutes must be a valid numeric integer, got: {raw_idle!r}",
            }

    try:
        sim_res = container.r4r_service.simulate_inactivity(case_id, idle_minutes=idle_minutes)
        return 200, sim_res
    except KeyError:
        return 404, {"error": "PROPOSAL_NOT_FOUND", "detail": f"Proposal '{case_id}' not found"}
    except Exception as e:
        return 500, {"error": "SIMULATION_FAILED", "detail": str(e)}


if HAS_FASTAPI:
    @router.get("/queue")
    async def get_queue_endpoint(services: ServiceContainer = Depends(get_services)):
        status_code, data = get_queue_controller(services=services)
        return JSONResponse(status_code=status_code, content=data)

    @router.get("/{case_id}")
    async def get_proposal_endpoint(case_id: str, services: ServiceContainer = Depends(get_services)):
        status_code, data = get_proposal_controller(case_id, services=services)
        if status_code == 404:
            raise HTTPException(status_code=404, detail=data.get("detail", "Not Found"))
        return JSONResponse(status_code=status_code, content=data)

    @router.post("/review")
    async def review_proposal_endpoint(request: Request, services: ServiceContainer = Depends(get_services)):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")
        status_code, data = review_proposal_controller(body, services=services)
        if status_code in (400, 404, 422, 500):
            raise HTTPException(status_code=status_code, detail=data.get("detail", data))
        return JSONResponse(status_code=status_code, content=data)

    @router.post("/simulate-inactivity")
    async def simulate_inactivity_endpoint(request: Request, services: ServiceContainer = Depends(get_services)):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")
        status_code, data = simulate_inactivity_controller(body, services=services)
        if status_code != 200:
            raise HTTPException(status_code=status_code, detail=data.get("detail", data))
        return JSONResponse(status_code=status_code, content=data)
