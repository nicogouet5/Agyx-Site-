"""Tactical routing, corridor congestion, and location resolution service for Agyx.

Provides:
1. `resolve_destination(destination)` — strict address catalogue resolver (preserves exact
   contract for known street references like Lira 953).
2. `calculate_tactical_route(...)` — computes Dispatch-style tactical route telemetry,
   corridor congestion by time window, SVG path geometry, and mitigation alternatives
   across the Santiago de Chile logistics network.
3. `get_network_telemetry(hora, active_memory)` — returns full network state (nodes,
   corridors, congestion levels, geofence status, and fleet unit coordinates).
"""
import re
import unicodedata
from typing import Any, Dict, List, Optional
from urllib.parse import quote


def _normalize(value: str) -> str:
    plain = unicodedata.normalize("NFKD", str(value or ""))
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", plain).strip().lower()


def _parse_minutes(hora: Optional[str]) -> Optional[int]:
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(hora or ""))
    if not match:
        return None
    h, m = map(int, match.groups())
    return h * 60 + m if h < 24 and m < 60 else None


def resolve_destination(destination: str) -> dict:
    """Resolve the known Lira 953 reference without guessing other addresses."""
    normalized = _normalize(destination)
    lira_953 = bool(re.search(r"\blira\s*(?:n[°ºo.]?\s*)?953\b", normalized))
    if lira_953:
        return {
            "direccion": "Lira 953, Santiago, Chile",
            "zona": "SANTIAGO_CENTRO",
            "fuente": "referencia_de_demostracion",
            "verificacion": "zona_aproximada_sujeta_a_revision_humana",
            "map_url": "https://www.openstreetmap.org/search?query=" + quote("Lira 953, Santiago, Chile"),
        }
    return {}


# ---------------------------------------------------------------------------
# Tactical Map Nodes & Corridors Topology (Santiago RM)
# ---------------------------------------------------------------------------
SANTIAGO_NODES: Dict[str, Dict[str, Any]] = {
    "QUILICURA": {
        "id": "QUILICURA",
        "nombre": "Base Quilicura",
        "comuna": "Quilicura",
        "x": 220,
        "y": 48,
        "tipo": "HUB_BASE",
        "descripcion": "Centro de Distribución Principal Pymes-Fletes (CAM-01, CAM-02, CAM-03, CAM-05, CAM-07)",
    },
    "RENCA": {
        "id": "RENCA",
        "nombre": "Taller Renca",
        "comuna": "Renca",
        "x": 255,
        "y": 102,
        "tipo": "TALLER_MANTENIMIENTO",
        "descripcion": "Taller Mecánico Central — CAM-04 bloqueado por falla crítica de frenos de aire",
    },
    "PUDAHUEL": {
        "id": "PUDAHUEL",
        "nombre": "Bodega Pudahuel",
        "comuna": "Pudahuel",
        "x": 92,
        "y": 138,
        "tipo": "ZONA_INDUSTRIAL",
        "descripcion": "Parque Logístico Pudahuel / ENEA (Zona Industrial 24/7 sin restricción de tonelaje)",
    },
    "MAIPU": {
        "id": "MAIPU",
        "nombre": "Maipú Industrial",
        "comuna": "Maipú",
        "x": 122,
        "y": 228,
        "tipo": "ZONA_INDUSTRIAL",
        "descripcion": "Corredor Camino a Melipilla / Maipú Poniente",
    },
    "SANTIAGO_CENTRO": {
        "id": "SANTIAGO_CENTRO",
        "nombre": "Santiago Centro (Lira 953)",
        "comuna": "Santiago Centro",
        "x": 365,
        "y": 156,
        "tipo": "ZONA_RESTRINGIDA",
        "descripcion": "Anillo Interior Santiago Centro / Lira 953 — Ordenanza N° 84 prohíbe >5.000 kg entre 07:30 y 21:00 hrs",
    },
    "PROVIDENCIA": {
        "id": "PROVIDENCIA",
        "nombre": "Providencia",
        "comuna": "Providencia",
        "x": 515,
        "y": 98,
        "tipo": "ZONA_COMERCIAL",
        "descripcion": "Eje Providencia / Costanera — Restricción >8.000 kg en punta mañana (07:30–10:00 hrs)",
    },
    "SAN_BERNARDO": {
        "id": "SAN_BERNARDO",
        "nombre": "San Bernardo",
        "comuna": "San Bernardo",
        "x": 340,
        "y": 258,
        "tipo": "ZONA_INDUSTRIAL_SUR",
        "descripcion": "Polo Industrial Ruta 5 Sur — Unidad CAM-06 (12t) en ruta hoy, slot reserva mañana 08:00 hrs",
    },
}

SANTIAGO_CORRIDORS: Dict[str, Dict[str, Any]] = {
    "VESPUCIO_NORTE": {
        "id": "VESPUCIO_NORTE",
        "nombre": "Autopista Vespucio Norte",
        "origen": "QUILICURA",
        "destino": "PUDAHUEL",
        "distancia_km": 18.4,
        "svg_path": "M 220,48 Q 120,68 92,138",
        "midpoint": {"x": 142, "y": 84},
    },
    "VESPUCIO_PONIENTE": {
        "id": "VESPUCIO_PONIENTE",
        "nombre": "Vespucio Poniente → Maipú",
        "origen": "QUILICURA",
        "destino": "MAIPU",
        "distancia_km": 24.5,
        "svg_path": "M 220,48 Q 120,68 92,138 L 122,228",
        "midpoint": {"x": 105, "y": 182},
    },
    "AUTOPISTA_CENTRAL_CENTRO": {
        "id": "AUTOPISTA_CENTRAL_CENTRO",
        "nombre": "Autopista Central → Alameda / Lira 953",
        "origen": "QUILICURA",
        "destino": "SANTIAGO_CENTRO",
        "distancia_km": 16.8,
        "svg_path": "M 220,48 L 255,102 L 365,156",
        "split_svg_path": "M 220,48 Q 345,76 365,156",
        "midpoint": {"x": 308, "y": 128},
    },
    "RUTA_5_SUR": {
        "id": "RUTA_5_SUR",
        "nombre": "Autopista Central / Ruta 5 Sur",
        "origen": "QUILICURA",
        "destino": "SAN_BERNARDO",
        "distancia_km": 29.2,
        "svg_path": "M 220,48 L 255,102 L 352,190 L 340,258",
        "midpoint": {"x": 345, "y": 212},
    },
    "COSTANERA_NORTE": {
        "id": "COSTANERA_NORTE",
        "nombre": "Costanera Norte → Eje Oriente",
        "origen": "QUILICURA",
        "destino": "PROVIDENCIA",
        "distancia_km": 19.0,
        "svg_path": "M 220,48 L 255,102 Q 385,78 515,98",
        "midpoint": {"x": 405, "y": 88},
    },
}


def resolve_zone_node(text: str) -> str:
    """Maps a commune name or street address to a canonical tactical node ID."""
    if resolve_destination(text):
        return "SANTIAGO_CENTRO"
    norm = _normalize(text)
    if not norm:
        return "SANTIAGO_CENTRO"
    if "pudahuel" in norm or "enea" in norm:
        return "PUDAHUEL"
    if "bernardo" in norm or "sur" in norm:
        return "SAN_BERNARDO"
    if "maipu" in norm or "melipilla" in norm:
        return "MAIPU"
    if "providencia" in norm or "oriente" in norm or "las condes" in norm:
        return "PROVIDENCIA"
    if "renca" in norm or "taller" in norm:
        return "RENCA"
    if "quilicura" in norm:
        return "QUILICURA"
    if "centro" in norm or "santiago" in norm or "alameda" in norm or "lira" in norm:
        return "SANTIAGO_CENTRO"
    return "SANTIAGO_CENTRO"


def _compute_corridor_congestion(corridor_id: str, minutes: Optional[int], is_daytime_ban_triggered: bool = False) -> Dict[str, Any]:
    """Determines congestion level, speed, and color for a corridor at a given time."""
    mins = minutes if minutes is not None else 14 * 60
    is_rush_hour = (7 * 60 + 30 <= mins <= 10 * 60) or (17 * 60 + 30 <= mins <= 20 * 60)
    is_daytime_centro = (7 * 60 + 30 <= mins <= 21 * 60)
    is_night_window = mins >= 21 * 60 + 1 or mins < 7 * 60 + 30

    if corridor_id == "AUTOPISTA_CENTRAL_CENTRO":
        if is_daytime_ban_triggered:
            return {
                "nivel": "BLOQUEO_ORDENANZA_DIURNA",
                "etiqueta": "RESTRICCIÓN >5t (07:30–21:00)",
                "velocidad_kmh": 0,
                "factor_tiempo": 1.6,
                "color": "#ef4444",
            }
        if is_night_window:
            return {
                "nivel": "VENTANA_NOCTURNA_HABILITADA",
                "etiqueta": "CORREDOR NOCTURNO DESPEJADO",
                "velocidad_kmh": 58,
                "factor_tiempo": 0.9,
                "color": "#10b981",
            }
        if is_daytime_centro:
            return {
                "nivel": "CONGESTION_MEDIA_CONTROL",
                "etiqueta": "CONTROL MUNICIPAL ACTIVO (≤5t OK)",
                "velocidad_kmh": 32,
                "factor_tiempo": 1.25,
                "color": "#f59e0b",
            }

    if is_rush_hour:
        return {
            "nivel": "CONGESTION_ALTA",
            "etiqueta": "HORA PUNTA · TRÁFICO DENSO",
            "velocidad_kmh": 28,
            "factor_tiempo": 1.35,
            "color": "#f59e0b",
        }
    return {
        "nivel": "FLUJO_LIBRE",
        "etiqueta": "FLUJO LIBRE OPERATIVO",
        "velocidad_kmh": 62,
        "factor_tiempo": 1.0,
        "color": "#38bdf8",
    }


def calculate_tactical_route(
    origen: str = "Quilicura",
    destino: str = "Santiago Centro",
    peso_kg: Optional[float] = 0.0,
    hora_solicitada: Optional[str] = None,
    status: str = "R4R",
    camiones: Optional[List[str]] = None,
    v1_mode: bool = False,
    living_memory_active: bool = False,
    fecha_hora_programada: str = "",
    hora: Optional[str] = None,
    version_mode: Optional[str] = None,
    assigned_trucks: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Builds the rich tactical map telemetry payload for a dispatch evaluation."""
    hora_eff = hora_solicitada or hora or "14:00"
    trucks_eff = camiones if camiones is not None else (assigned_trucks or [])
    if version_mode is not None:
        v1_mode = (str(version_mode).lower() == "v1")
        living_memory_active = not v1_mode

    dest_node_id = resolve_zone_node(destino)
    dest_node = SANTIAGO_NODES.get(dest_node_id, SANTIAGO_NODES["SANTIAGO_CENTRO"])
    orig_node = SANTIAGO_NODES["QUILICURA"]

    corridor_map = {
        "PUDAHUEL": "VESPUCIO_NORTE",
        "MAIPU": "VESPUCIO_PONIENTE",
        "SANTIAGO_CENTRO": "AUTOPISTA_CENTRAL_CENTRO",
        "SAN_BERNARDO": "RUTA_5_SUR",
        "PROVIDENCIA": "COSTANERA_NORTE",
    }
    corridor_id = corridor_map.get(dest_node_id, "AUTOPISTA_CENTRAL_CENTRO")
    corridor = SANTIAGO_CORRIDORS[corridor_id]

    mins = _parse_minutes(hora_eff)
    peso = float(peso_kg or 0.0)
    is_centro_heavy_day = (
        dest_node_id == "SANTIAGO_CENTRO"
        and peso > 5000.0
        and mins is not None
        and (7 * 60 + 30 <= mins <= 21 * 60)
    )

    # Determine visual state on the Dispatch tactical board
    effective_minutes = mins
    if "21:30" in str(fecha_hora_programada):
        effective_minutes = 21 * 60 + 30

    congestion = _compute_corridor_congestion(
        corridor_id,
        effective_minutes,
        is_daytime_ban_triggered=(is_centro_heavy_day and "21:30" not in str(fecha_hora_programada)),
    )

    route_color = congestion["color"]
    split_active = False
    truck_badge = f"🚚 {trucks_eff[0]}" if trucks_eff else "⏸ SIN ASIGNAR"
    marker_pos = corridor["midpoint"]

    if status == "BLOQUEADO_RIESGO":
        route_color = "#ef4444"
        congestion["nivel"] = "BLOQUEO_SEGURIDAD"
        congestion["etiqueta"] = "SALIDA DENEGADA · BLOQUEO SEGURIDAD"
        truck_badge = "🛑 BLOQUEADO"
        if dest_node_id == "MAIPU":
            marker_pos = {"x": 255, "y": 78}
    elif status == "R4R_INFO_INCOMPLETA":
        route_color = "#f59e0b"
        congestion["nivel"] = "RETENIDO_REVISION"
        congestion["etiqueta"] = "RETENIDO · DATOS / REGLA PENDIENTE"
        truck_badge = "⚠️ RETENIDO"
    elif "21:30" in str(fecha_hora_programada):
        route_color = "#10b981"
        split_active = True
        truck_badge = f"🌙 {trucks_eff[0] if trucks_eff else 'CAM-05'} (21:30)"
    elif "08:00" in str(fecha_hora_programada):
        route_color = "#a78bfa"
        congestion["nivel"] = "RESERVA_PROGRAMADA"
        congestion["etiqueta"] = "RESERVA DÍA SIGUIENTE (08:00 HRS)"
        truck_badge = f"📅 {trucks_eff[0] if trucks_eff else 'CAM-06'}"
    elif is_centro_heavy_day and v1_mode:
        route_color = "#ef4444"
        truck_badge = "⚠️ CAM-05 (11:30)"

    known_ref = resolve_destination(destino)
    dist_km = float(corridor["distancia_km"])
    speed_kmh = max(float(congestion.get("velocidad_kmh") or 40.0), 20.0)
    eta_mins = int(round((dist_km / speed_kmh) * 60))
    alternatives = (
        ["VENTANA_NOCTURNA_2130", "SUBDIVISION_2X_5T_CAM02_CAM03"]
        if dest_node_id == "SANTIAGO_CENTRO" and peso > 5000
        else (["RESERVA_DIA_SIGUIENTE_0800"] if "08:00" in str(fecha_hora_programada) else ["DESPACHO_DIRECTO_HOY"])
    )

    return {
        "origen_nodo": orig_node["id"],
        "origen_nombre": orig_node["nombre"],
        "destino_nodo": dest_node["id"],
        "destino_nombre": known_ref.get("direccion") or dest_node["nombre"],
        "origin_node": orig_node,
        "destination_node": dest_node,
        "zona": dest_node["id"],
        "corredor_id": corridor["id"],
        "corredor_nombre": corridor["nombre"],
        "distancia_km": dist_km,
        "distance_km": dist_km,
        "eta_minutes": eta_mins,
        "hora_evaluada": hora_eff,
        "version_mode": "v1" if v1_mode else "v2",
        "congestion_nivel": congestion["nivel"],
        "congestion_etiqueta": congestion["etiqueta"],
        "congestion_label": congestion["etiqueta"],
        "congestion_multiplier": congestion.get("factor_tiempo", 1.0),
        "velocidad_estimada_kmh": congestion["velocidad_kmh"],
        "svg_path": corridor["svg_path"],
        "split_svg_path": corridor.get("split_svg_path", ""),
        "split_route_available": split_active,
        "route_color": route_color,
        "truck_badge": truck_badge,
        "truck_marker": marker_pos,
        "geofence_centro_activa": (mins is None) or (7 * 60 + 30 <= mins <= 21 * 60),
        "alternativas_evaluadas": alternatives,
        "alternatives": alternatives,
    }


def get_network_telemetry(
    hora: str = "14:00",
    active_memory: bool = False,
    trucks: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Returns full tactical map state for all corridors and fleet units at a given hour."""
    mins = _parse_minutes(hora)
    if mins is None:
        mins = 14 * 60
        hora = "14:00"

    geofence_active = (7 * 60 + 30) <= mins <= (21 * 60)
    corridors_state = {}
    corridors_list = []
    for cid, cdata in SANTIAGO_CORRIDORS.items():
        cg = _compute_corridor_congestion(cid, mins, is_daytime_ban_triggered=False)
        entry = {
            **cdata,
            "congestion": cg,
            "congestion_level": "ALTA" if cg["factor_tiempo"] >= 1.3 else ("MEDIA" if cg["factor_tiempo"] > 1.0 else "BAJA"),
        }
        corridors_state[cid] = entry
        corridors_list.append(entry)

    fleet_markers = [
        {"id": "CAM-01", "modelo": "Hyundai HD78 3.5t", "capacidad_kg": 3500, "nodo": "QUILICURA", "node_id": "QUILICURA", "x": 310, "y": 54, "estado": "DISPONIBLE", "status": "DISPONIBLE", "blocked": False, "detail": "En Base Quilicura — Disponible (Carga liviana <=3.000 kg)"},
        {"id": "CAM-02", "modelo": "Mercedes Atego 5t", "capacidad_kg": 5000, "nodo": "QUILICURA", "node_id": "QUILICURA", "x": 365, "y": 54, "estado": "DISPONIBLE", "status": "DISPONIBLE", "blocked": False, "detail": "En Base Quilicura — Disponible (Caso 1 / Split 5t)"},
        {"id": "CAM-03", "modelo": "Mercedes Atego 5t", "capacidad_kg": 5000, "nodo": "QUILICURA", "node_id": "QUILICURA", "x": 418, "y": 54, "estado": "DISPONIBLE", "status": "DISPONIBLE", "blocked": False, "detail": "En Base Quilicura — Disponible (Split 2x 5t)"},
        {"id": "CAM-04", "modelo": "VW Delivery 8t", "capacidad_kg": 8000, "nodo": "RENCA", "node_id": "RENCA", "x": 295, "y": 195, "estado": "EN_MANTENIMIENTO", "status": "EN_MANTENIMIENTO", "blocked": True, "alerta": "Falla crítica de frenos de aire", "detail": "BLOQUEADO EN TALLER RENCA: Falla crítica de frenos de aire (Caso 5)"},
        {"id": "CAM-05", "modelo": "Volvo VM 12t", "capacidad_kg": 12000, "nodo": "QUILICURA", "node_id": "QUILICURA", "x": 395, "y": 106, "estado": "DISPONIBLE", "status": "DISPONIBLE", "blocked": False, "detail": "En Base Quilicura — Disponible (12t Caso 3 v1/v2)"},
        {"id": "CAM-06", "modelo": "Scania P250 12t", "capacidad_kg": 12000, "nodo": "SAN_BERNARDO", "node_id": "SAN_BERNARDO", "x": 445, "y": 350, "estado": "EN_RUTA", "status": "EN_RUTA", "blocked": False, "alerta": "Reserva mañana 08:00 hrs", "detail": "En Ruta Sur — Próximo slot mañana 08:00 hrs (Caso 2)"},
        {"id": "CAM-07", "modelo": "Scania G360 15t", "capacidad_kg": 15000, "nodo": "PUDAHUEL", "node_id": "PUDAHUEL", "x": 155, "y": 182, "estado": "EN_RUTA", "status": "EN_RUTA", "blocked": False, "detail": "En Ruta Poniente — Retorno mañana 08:00 hrs"},
    ]

    sample_cg = _compute_corridor_congestion("AUTOPISTA_CENTRAL_CENTRO", mins, is_daytime_ban_triggered=False)

    return {
        "hora": hora,
        "hora_simulada": hora,
        "congestion_label": sample_cg["etiqueta"],
        "congestion_multiplier": sample_cg["factor_tiempo"],
        "santiago_centro_daytime_ban_active": geofence_active,
        "geofence_santiago_centro": {
            "activa": geofence_active,
            "ventana_prohibida": "07:30 - 21:00",
            "peso_max_diurno_kg": 5000,
            "ordenanza": "Ordenanza Municipal N° 84 Santiago Centro",
            "memoria_viva_activa": active_memory,
        },
        "nodos": SANTIAGO_NODES,
        "corredores": corridors_state,
        "corridors": corridors_list,
        "flota_tactica": fleet_markers,
        "fleet_markers": fleet_markers,
    }
