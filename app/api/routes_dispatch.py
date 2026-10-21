"""
app/api/routes_dispatch.py
FastAPI router and controller for dispatch order evaluation and real-time customer portal orders.
Executes token-optimized evaluation via LocalAgentEngine (or GeminiAgentEngine),
enforcing the strict R4R state machine invariant: auto_approved == False.
"""
import random
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from app.api.dependencies import ServiceContainer, get_services
from app.services.geo_service import (
    resolve_destination,
    calculate_tactical_route,
    geocode_santiago_address,
)

try:
    from fastapi import APIRouter, HTTPException, Depends, Request
    from fastapi.responses import JSONResponse
    from app.api.schemas import DispatchEvaluationRequest
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
        fecha_hora_programada=str(prop_dict.get("fecha_hora_programada") or ""),
        orig_lat=order_data.get("orig_lat"),
        orig_lng=order_data.get("orig_lng"),
        dest_lat=order_data.get("dest_lat"),
        dest_lng=order_data.get("dest_lng"),
    )

    # Persist enriched metadata if customer details or coordinates are present
    case_id_val = str(eval_result.get("case_id") or order_data.get("case_id") or "")
    if case_id_val:
        tmap = eval_result["tactical_map"]
        extra_meta: Dict[str, Any] = {
            "origin_coords": tmap.get("origin_coords"),
            "destination_coords": tmap.get("destination_coords"),
            "waypoints": tmap.get("waypoints"),
            "google_maps_url": tmap.get("google_maps_url"),
            "distance_km": tmap.get("distance_km"),
            "eta_minutes": tmap.get("eta_minutes"),
        }
        if order_data.get("cliente_nombre"):
            extra_meta["cliente_nombre"] = str(order_data["cliente_nombre"]).strip()
        if order_data.get("cliente_contacto"):
            extra_meta["cliente_contacto"] = str(order_data["cliente_contacto"]).strip()
        if order_data.get("descripcion_carga"):
            extra_meta["descripcion_carga"] = str(order_data["descripcion_carga"]).strip()
        if order_data.get("is_live_order"):
            extra_meta["is_live_order"] = True
        try:
            container.r4r_service.enrich_proposal_metadata(case_id_val, extra_meta)
        except Exception:
            pass

    return 200, eval_result


def submit_live_order_controller(
    payload: Dict[str, Any],
    services: Optional[ServiceContainer] = None,
) -> Tuple[int, Dict[str, Any]]:
    """
    Processes a real-time customer freight request from /solicitar.
    Geocodes origin/destination in Gran Santiago, runs the AI agent evaluation,
    saves in R4R queue with customer metadata, and returns tracking telemetry.
    """
    container = services or ServiceContainer.get_instance()
    if not isinstance(payload, dict):
        return 400, {"error": "INVALID_PAYLOAD", "detail": "Datos de solicitud inválidos"}

    # Generate unique order ID if not provided
    raw_id = str(payload.get("case_id") or "").strip()
    if not raw_id:
        stamp = datetime.utcnow().strftime("%H%M")
        rand_suffix = random.randint(10, 99)
        raw_id = f"SOL-{stamp}-{rand_suffix}"

    origen_comuna = str(payload.get("origen_comuna") or payload.get("origen") or "Quilicura").strip()
    origen_dir = str(payload.get("origen_direccion") or "").strip()
    origen_full = f"{origen_dir}, {origen_comuna}".strip(", ") if origen_dir else origen_comuna

    destino_comuna = str(payload.get("destino_comuna") or payload.get("destino") or "").strip()
    destino_dir = str(payload.get("destino_direccion") or payload.get("direccion_exacta") or "").strip()
    destino_full = f"{destino_dir}, {destino_comuna}".strip(", ") if destino_dir else destino_comuna

    orig_geo = geocode_santiago_address(
        origen_dir or origen_comuna,
        comuna_hint=origen_comuna,
        custom_lat=payload.get("orig_lat"),
        custom_lng=payload.get("orig_lng"),
    )
    dest_geo = geocode_santiago_address(
        destino_dir or destino_comuna,
        comuna_hint=destino_comuna,
        custom_lat=payload.get("dest_lat"),
        custom_lng=payload.get("dest_lng"),
    )

    # Ensure Living Memory rule for Santiago Centro is seeded if user asks for v2 operational mode
    # so the live agent always protects against the >5.000 kg daytime ordinance out-of-the-box
    active_rules = container.memory_service.get_active_rules(zone="SANTIAGO_CENTRO")
    if not active_rules and payload.get("auto_seed_memory", True):
        try:
            container.memory_service.seed_santiago_centro_rule()
        except Exception:
            pass

    engine_choice = str(payload.get("engine_mode") or ("gemini" if container.gemini_engine.is_available() else "local")).lower()

    peso_val = payload.get("peso_kg") if payload.get("peso_kg") is not None else payload.get("cargo_weight_kg")
    tipo_val = str(payload.get("tipo_carga") or payload.get("cargo_type") or "GENERAL").upper()
    desc_val = str(payload.get("descripcion_carga") or payload.get("descripcion") or "Carga general paletizada").strip()

    order_input: Dict[str, Any] = {
        "case_id": raw_id,
        "origen": orig_geo["nombre"],
        "destino": dest_geo["nombre"],
        "destino_comuna": dest_geo["comuna"],
        "direccion_exacta": destino_dir or dest_geo["nombre"],
        "peso_kg": peso_val,
        "volumen_m3": payload.get("volumen_m3", 12.0),
        "tipo_carga": tipo_val,
        "descripcion_carga": desc_val,
        "fecha_despacho": str(payload.get("fecha_despacho") or "HOY").strip(),
        "hora_despacho": str(payload.get("hora_despacho") or payload.get("hora_solicitada") or "").strip(),
        "hora_exacta": str(payload.get("hora_despacho") or payload.get("hora_solicitada") or "").strip(),
        "truck_id_preferido": payload.get("truck_id_preferido"),
        "cliente_nombre": str(payload.get("cliente_nombre") or "Cliente Empresa").strip(),
        "cliente_contacto": str(payload.get("cliente_contacto") or "").strip(),
        "orig_lat": orig_geo["lat"],
        "orig_lng": orig_geo["lng"],
        "dest_lat": dest_geo["lat"],
        "dest_lng": dest_geo["lng"],
        "engine_mode": engine_choice,
        "version_mode": "v2",
        "is_live_order": True,
    }

    code, eval_res = evaluate_dispatch_controller(order_input, services=container)
    if code >= 400:
        return code, eval_res

    tmap = eval_res.get("tactical_map") or {}
    container.r4r_service.enrich_proposal_metadata(
        raw_id,
        {
            "is_live_order": True,
            "cliente_nombre": order_input["cliente_nombre"],
            "cliente_contacto": order_input["cliente_contacto"],
            "peso_kg": peso_val,
            "origin_coords": [orig_geo["lat"], orig_geo["lng"]],
            "destination_coords": [dest_geo["lat"], dest_geo["lng"]],
            "waypoints": tmap.get("waypoints") or [[orig_geo["lat"], orig_geo["lng"]], [dest_geo["lat"], dest_geo["lng"]]],
            "distance_km": tmap.get("distance_km"),
            "eta_minutes": tmap.get("eta_minutes"),
        },
    )

    # Fetch stored proposal so customer gets full record
    stored_prop = container.r4r_service.get_proposal(raw_id)
    eval_res["stored_proposal"] = stored_prop
    eval_res["cliente_nombre"] = order_input["cliente_nombre"]
    eval_res["cliente_contacto"] = order_input["cliente_contacto"]
    eval_res["descripcion_carga"] = order_input["descripcion_carga"]
    return 200, eval_res


def get_live_sync_controller(
    services: Optional[ServiceContainer] = None,
) -> Tuple[int, Dict[str, Any]]:
    """
    Lightweight real-time synchronization payload polled every 3 seconds by the
    Supervisor Control Center (/) and Client Portal (/solicitar).
    """
    container = services or ServiceContainer.get_instance()
    queue = container.r4r_service.get_queue()
    trucks = container.fleet_service.get_all_trucks_enriched()
    bases = container.fleet_service.get_bases_summary()
    rules = container.memory_service.get_active_rules()

    live_orders = [
        p for p in queue
        if p.get("es_pedido_cliente") or (p.get("proposal_data") or {}).get("is_live_order") or str(p.get("case_id", "")).startswith("SOL-")
    ]
    pending_r4r = [p for p in queue if p.get("estado") == "R4R"]
    pending_live_orders = [p for p in live_orders if p.get("estado") == "R4R"]

    return 200, {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total_queue": len(queue),
        "pending_r4r_count": len(pending_r4r),
        "live_orders_count": len(live_orders),
        "pending_live_count": len(pending_live_orders),
        "latest_order_id": queue[0]["case_id"] if queue else None,
        "latest_order": queue[0] if queue else None,
        "latest_live_order": live_orders[0] if live_orders else None,
        "queue": queue,
        "trucks": trucks,
        "bases": bases,
        "active_rules_count": len(rules),
    }


if HAS_FASTAPI:
    @router.post("/evaluate")
    async def evaluate_dispatch_endpoint(
        payload: DispatchEvaluationRequest,
        services: ServiceContainer = Depends(get_services),
    ):
        status_code, data = evaluate_dispatch_controller(
            payload.model_dump(exclude_none=True), services=services
        )
        if status_code >= 400:
            raise HTTPException(status_code=status_code, detail=data.get("detail", data.get("error", "Error")))
        return JSONResponse(status_code=status_code, content=data)

    @router.post("/live-order")
    async def submit_live_order_endpoint(
        request: Request,
        services: ServiceContainer = Depends(get_services),
    ):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Malformed JSON body")
        status_code, data = submit_live_order_controller(body, services=services)
        if status_code >= 400:
            raise HTTPException(status_code=status_code, detail=data.get("detail", data.get("error", "Error")))
        return JSONResponse(status_code=status_code, content=data)

    @router.get("/live-sync")
    async def get_live_sync_endpoint(
        services: ServiceContainer = Depends(get_services),
    ):
        status_code, data = get_live_sync_controller(services=services)
        return JSONResponse(status_code=status_code, content=data)
