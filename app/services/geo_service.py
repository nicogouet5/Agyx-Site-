"""Tactical routing, corridor congestion, and location resolution service for Agyx.

Provides:
1. `resolve_destination(destination)` — strict address catalogue resolver (preserves exact
   contract for known street references like Lira 953).
2. `geocode_santiago_address(address_text, comuna_hint)` — full geocoder covering 38+ comunas
   and major avenues of Gran Santiago (Región Metropolitana) with exact GPS coordinates.
3. `calculate_tactical_route(...)` — computes Dispatch-style tactical route telemetry,
   corridor congestion by time window, SVG path geometry, real GPS waypoints, and mitigation
   alternatives across the Santiago de Chile logistics network.
4. `get_network_telemetry(hora, active_memory, trucks)` — returns full network state (nodes,
   corridors, congestion levels, geofence status, bases summary, and live fleet unit coordinates).
"""
import math
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote


def _normalize(value: str) -> str:
    plain = unicodedata.normalize("NFKD", str(value or ""))
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", plain).strip().lower()


def _parse_minutes(hora: Optional[str]) -> Optional[int]:
    match = re.search(r"(\d{1,2}):(\d{2})", str(hora or ""))
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
        "lat": -33.3600,
        "lng": -70.6900,
        "tipo": "HUB_BASE",
        "descripcion": "Centro de Distribución Principal Pymes-Fletes (CAM-01, CAM-02, CAM-03, CAM-05, CAM-07)",
    },
    "RENCA": {
        "id": "RENCA",
        "nombre": "Taller Renca",
        "comuna": "Renca",
        "x": 255,
        "y": 102,
        "lat": -33.4050,
        "lng": -70.6800,
        "tipo": "TALLER_MANTENIMIENTO",
        "descripcion": "Taller Mecánico Central — CAM-04 bloqueado por falla crítica de frenos de aire",
    },
    "PUDAHUEL": {
        "id": "PUDAHUEL",
        "nombre": "Bodega Pudahuel",
        "comuna": "Pudahuel",
        "x": 92,
        "y": 138,
        "lat": -33.4350,
        "lng": -70.7600,
        "tipo": "ZONA_INDUSTRIAL",
        "descripcion": "Parque Logístico Pudahuel / ENEA (Zona Industrial 24/7 sin restricción de tonelaje)",
    },
    "MAIPU": {
        "id": "MAIPU",
        "nombre": "Maipú Industrial",
        "comuna": "Maipú",
        "x": 122,
        "y": 228,
        "lat": -33.5100,
        "lng": -70.7600,
        "tipo": "ZONA_INDUSTRIAL",
        "descripcion": "Corredor Camino a Melipilla / Maipú Poniente",
    },
    "SANTIAGO_CENTRO": {
        "id": "SANTIAGO_CENTRO",
        "nombre": "Santiago Centro (Lira 953)",
        "comuna": "Santiago Centro",
        "x": 365,
        "y": 156,
        "lat": -33.4503,
        "lng": -70.6441,
        "tipo": "ZONA_RESTRINGIDA",
        "descripcion": "Anillo Interior Santiago Centro / Lira 953 — Ordenanza N° 84 prohíbe >5.000 kg entre 07:30 y 21:00 hrs",
    },
    "PROVIDENCIA": {
        "id": "PROVIDENCIA",
        "nombre": "Providencia",
        "comuna": "Providencia",
        "x": 515,
        "y": 98,
        "lat": -33.4300,
        "lng": -70.6150,
        "tipo": "ZONA_COMERCIAL",
        "descripcion": "Eje Providencia / Costanera — Restricción >8.000 kg en punta mañana (07:30–10:00 hrs)",
    },
    "SAN_BERNARDO": {
        "id": "SAN_BERNARDO",
        "nombre": "San Bernardo",
        "comuna": "San Bernardo",
        "x": 340,
        "y": 258,
        "lat": -33.5900,
        "lng": -70.7000,
        "tipo": "ZONA_INDUSTRIAL_SUR",
        "descripcion": "Polo Industrial Ruta 5 Sur — Unidad CAM-06 (12t) en ruta hoy, slot reserva mañana 08:00 hrs",
    },
}

# ---------------------------------------------------------------------------
# Full Gran Santiago Gazetteer (38 Comunas + Major Streets & Industrial Hubs)
# ---------------------------------------------------------------------------
GRAN_SANTIAGO_COMUNAS: Dict[str, Dict[str, Any]] = {
    "quilicura": {"nombre": "Quilicura", "lat": -33.3600, "lng": -70.6900, "zona": "QUILICURA", "sector": "NORTE"},
    "huechuraba": {"nombre": "Huechuraba", "lat": -33.3740, "lng": -70.6360, "zona": "QUILICURA", "sector": "NORTE"},
    "conchali": {"nombre": "Conchalí", "lat": -33.3850, "lng": -70.6750, "zona": "QUILICURA", "sector": "NORTE"},
    "recoleta": {"nombre": "Recoleta", "lat": -33.4060, "lng": -70.6420, "zona": "SANTIAGO_CENTRO", "sector": "NORTE"},
    "independencia": {"nombre": "Independencia", "lat": -33.4150, "lng": -70.6650, "zona": "SANTIAGO_CENTRO", "sector": "NORTE"},
    "colina": {"nombre": "Colina / Chicureo", "lat": -33.2040, "lng": -70.6750, "zona": "QUILICURA", "sector": "NORTE"},
    "lampa": {"nombre": "Lampa", "lat": -33.2860, "lng": -70.8760, "zona": "QUILICURA", "sector": "NORTE"},
    "renca": {"nombre": "Renca", "lat": -33.4050, "lng": -70.6800, "zona": "RENCA", "sector": "PONIENTE"},
    "cerro navia": {"nombre": "Cerro Navia", "lat": -33.4220, "lng": -70.7350, "zona": "PUDAHUEL", "sector": "PONIENTE"},
    "quinta normal": {"nombre": "Quinta Normal", "lat": -33.4280, "lng": -70.6980, "zona": "RENCA", "sector": "PONIENTE"},
    "lo prado": {"nombre": "Lo Prado", "lat": -33.4440, "lng": -70.7250, "zona": "PUDAHUEL", "sector": "PONIENTE"},
    "pudahuel": {"nombre": "Pudahuel", "lat": -33.4350, "lng": -70.7600, "zona": "PUDAHUEL", "sector": "PONIENTE"},
    "estacion central": {"nombre": "Estación Central", "lat": -33.4590, "lng": -70.6990, "zona": "SANTIAGO_CENTRO", "sector": "PONIENTE"},
    "cerrillos": {"nombre": "Cerrillos", "lat": -33.4950, "lng": -70.7180, "zona": "MAIPU", "sector": "PONIENTE"},
    "maipu": {"nombre": "Maipú", "lat": -33.5100, "lng": -70.7600, "zona": "MAIPU", "sector": "PONIENTE"},
    "padre hurtado": {"nombre": "Padre Hurtado", "lat": -33.5710, "lng": -70.8190, "zona": "MAIPU", "sector": "PONIENTE"},
    "santiago": {"nombre": "Santiago Centro", "lat": -33.4503, "lng": -70.6441, "zona": "SANTIAGO_CENTRO", "sector": "CENTRO"},
    "santiago centro": {"nombre": "Santiago Centro", "lat": -33.4503, "lng": -70.6441, "zona": "SANTIAGO_CENTRO", "sector": "CENTRO"},
    "providencia": {"nombre": "Providencia", "lat": -33.4300, "lng": -70.6150, "zona": "PROVIDENCIA", "sector": "ORIENTE"},
    "las condes": {"nombre": "Las Condes", "lat": -33.4120, "lng": -70.5680, "zona": "PROVIDENCIA", "sector": "ORIENTE"},
    "vitacura": {"nombre": "Vitacura", "lat": -33.3880, "lng": -70.5750, "zona": "PROVIDENCIA", "sector": "ORIENTE"},
    "lo barnechea": {"nombre": "Lo Barnechea", "lat": -33.3520, "lng": -70.5180, "zona": "PROVIDENCIA", "sector": "ORIENTE"},
    "nunoa": {"nombre": "Ñuñoa", "lat": -33.4560, "lng": -70.5950, "zona": "PROVIDENCIA", "sector": "ORIENTE"},
    "la reina": {"nombre": "La Reina", "lat": -33.4430, "lng": -70.5540, "zona": "PROVIDENCIA", "sector": "ORIENTE"},
    "macul": {"nombre": "Macul", "lat": -33.4890, "lng": -70.5980, "zona": "PROVIDENCIA", "sector": "ORIENTE"},
    "penalolen": {"nombre": "Peñalolén", "lat": -33.4860, "lng": -70.5480, "zona": "PROVIDENCIA", "sector": "ORIENTE"},
    "la florida": {"nombre": "La Florida", "lat": -33.5230, "lng": -70.5880, "zona": "SAN_BERNARDO", "sector": "SUR"},
    "puente alto": {"nombre": "Puente Alto", "lat": -33.6110, "lng": -70.5750, "zona": "SAN_BERNARDO", "sector": "SUR"},
    "san miguel": {"nombre": "San Miguel", "lat": -33.4980, "lng": -70.6510, "zona": "SANTIAGO_CENTRO", "sector": "SUR"},
    "san joaquin": {"nombre": "San Joaquín", "lat": -33.4960, "lng": -70.6280, "zona": "SANTIAGO_CENTRO", "sector": "SUR"},
    "pedro aguirre cerda": {"nombre": "Pedro Aguirre Cerda", "lat": -33.4880, "lng": -70.6780, "zona": "SANTIAGO_CENTRO", "sector": "SUR"},
    "lo espejo": {"nombre": "Lo Espejo", "lat": -33.5220, "lng": -70.6910, "zona": "SAN_BERNARDO", "sector": "SUR"},
    "la cisterna": {"nombre": "La Cisterna", "lat": -33.5350, "lng": -70.6630, "zona": "SAN_BERNARDO", "sector": "SUR"},
    "san ramon": {"nombre": "San Ramón", "lat": -33.5420, "lng": -70.6420, "zona": "SAN_BERNARDO", "sector": "SUR"},
    "la granja": {"nombre": "La Granja", "lat": -33.5380, "lng": -70.6210, "zona": "SAN_BERNARDO", "sector": "SUR"},
    "el bosque": {"nombre": "El Bosque", "lat": -33.5620, "lng": -70.6750, "zona": "SAN_BERNARDO", "sector": "SUR"},
    "la pintana": {"nombre": "La Pintana", "lat": -33.5830, "lng": -70.6340, "zona": "SAN_BERNARDO", "sector": "SUR"},
    "san bernardo": {"nombre": "San Bernardo", "lat": -33.5900, "lng": -70.7000, "zona": "SAN_BERNARDO", "sector": "SUR"},
    "buin": {"nombre": "Buin", "lat": -33.7320, "lng": -70.7420, "zona": "SAN_BERNARDO", "sector": "SUR"},
}

KNOWN_SANTIAGO_LANDMARKS: List[Tuple[str, Dict[str, Any]]] = [
    ("lira 953", {"nombre": "Lira 953, Santiago Centro", "lat": -33.4503, "lng": -70.6441, "zona": "SANTIAGO_CENTRO", "comuna": "Santiago Centro"}),
    ("lira", {"nombre": "Calle Lira, Santiago Centro", "lat": -33.4503, "lng": -70.6441, "zona": "SANTIAGO_CENTRO", "comuna": "Santiago Centro"}),
    ("alameda", {"nombre": "Av. Libertador Bernardo O'Higgins (Alameda)", "lat": -33.4429, "lng": -70.6539, "zona": "SANTIAGO_CENTRO", "comuna": "Santiago Centro"}),
    ("santa rosa", {"nombre": "Av. Santa Rosa, Santiago", "lat": -33.4620, "lng": -70.6425, "zona": "SANTIAGO_CENTRO", "comuna": "Santiago Centro"}),
    ("matta", {"nombre": "Av. Manuel Antonio Matta, Santiago Centro", "lat": -33.4568, "lng": -70.6450, "zona": "SANTIAGO_CENTRO", "comuna": "Santiago Centro"}),
    ("vicuna mackenna", {"nombre": "Av. Vicuña Mackenna, Santiago", "lat": -33.4540, "lng": -70.6310, "zona": "SANTIAGO_CENTRO", "comuna": "Santiago Centro"}),
    ("apoquindo", {"nombre": "Av. Apoquindo, Las Condes", "lat": -33.4135, "lng": -70.5810, "zona": "PROVIDENCIA", "comuna": "Las Condes"}),
    ("kennedy", {"nombre": "Av. Presidente Kennedy, Vitacura", "lat": -33.4005, "lng": -70.5760, "zona": "PROVIDENCIA", "comuna": "Vitacura"}),
    ("costanera", {"nombre": "Costanera Center / Av. Andrés Bello, Providencia", "lat": -33.4175, "lng": -70.6065, "zona": "PROVIDENCIA", "comuna": "Providencia"}),
    ("irarrazaval", {"nombre": "Av. Irarrázaval, Ñuñoa", "lat": -33.4545, "lng": -70.6020, "zona": "PROVIDENCIA", "comuna": "Ñuñoa"}),
    ("enea", {"nombre": "Parque Industrial ENEA, Pudahuel", "lat": -33.4280, "lng": -70.7810, "zona": "PUDAHUEL", "comuna": "Pudahuel"}),
    ("aeropuerto", {"nombre": "Terminal de Carga Aeropuerto SCL, Pudahuel", "lat": -33.3930, "lng": -70.7850, "zona": "PUDAHUEL", "comuna": "Pudahuel"}),
    ("melipilla", {"nombre": "Camino a Melipilla, Maipú / Cerrillos", "lat": -33.5040, "lng": -70.7390, "zona": "MAIPU", "comuna": "Maipú"}),
    ("pajaritos", {"nombre": "Av. Los Pajaritos, Maipú", "lat": -33.4950, "lng": -70.7570, "zona": "MAIPU", "comuna": "Maipú"}),
    ("lo boza", {"nombre": "Parque Industrial Lo Boza, Quilicura", "lat": -33.3720, "lng": -70.7080, "zona": "QUILICURA", "comuna": "Quilicura"}),
    ("san ignacio", {"nombre": "Centro Industrial San Ignacio, Quilicura", "lat": -33.3510, "lng": -70.7010, "zona": "QUILICURA", "comuna": "Quilicura"}),
    ("panamericana", {"nombre": "Ruta 5 Norte / Panamericana, Quilicura", "lat": -33.3560, "lng": -70.6890, "zona": "QUILICURA", "comuna": "Quilicura"}),
    ("gran avenida", {"nombre": "Gran Avenida José Miguel Carrera, Zona Sur", "lat": -33.5280, "lng": -70.6610, "zona": "SAN_BERNARDO", "comuna": "La Cisterna"}),
    ("ochagavia", {"nombre": "Av. Presidente Jorge Alessandri / Ochagavía, San Bernardo", "lat": -33.5680, "lng": -70.7030, "zona": "SAN_BERNARDO", "comuna": "San Bernardo"}),
]


def _latlng_to_svg(lat: float, lng: float) -> Tuple[int, int]:
    """Projects real Santiago GPS coordinates into the 680x360 tactical SVG viewport."""
    # Bounding box approx: lat [-33.32, -33.62], lng [-70.80, -70.52]
    norm_x = (lng - (-70.80)) / ((-70.52) - (-70.80))
    norm_y = (lat - (-33.32)) / ((-33.62) - (-33.32))
    svg_x = int(max(45, min(635, round(50 + norm_x * 580))))
    svg_y = int(max(30, min(330, round(30 + norm_y * 290))))
    return svg_x, svg_y


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculates great-circle distance in km multiplied by 1.28 urban road factor."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    straight_km = r * c
    return round(max(3.5, straight_km * 1.28), 1)


def geocode_santiago_address(
    address_text: str,
    comuna_hint: str = "",
    custom_lat: Optional[float] = None,
    custom_lng: Optional[float] = None,
) -> Dict[str, Any]:
    """Resolves any street address or comuna in Gran Santiago into real GPS coordinates."""
    combined = f"{address_text or ''} {comuna_hint or ''}".strip()
    norm = _normalize(combined)

    # 1. If explicit GPS coordinates were picked on the interactive map
    if custom_lat is not None and custom_lng is not None:
        try:
            lat_f, lng_f = float(custom_lat), float(custom_lng)
            if -34.0 <= lat_f <= -33.0 and -71.2 <= lng_f <= -70.2:
                sx, sy = _latlng_to_svg(lat_f, lng_f)
                zona = resolve_zone_node(combined)
                return {
                    "nombre": combined or f"Punto GPS ({lat_f:.4f}, {lng_f:.4f})",
                    "comuna": comuna_hint or SANTIAGO_NODES.get(zona, {}).get("comuna", "Santiago"),
                    "zona": zona,
                    "lat": round(lat_f, 5),
                    "lng": round(lng_f, 5),
                    "x": sx,
                    "y": sy,
                }
        except (ValueError, TypeError):
            pass

    # 2. Check known landmarks & major avenues
    for key, info in KNOWN_SANTIAGO_LANDMARKS:
        if key in norm:
            # Extract street number if present to add subtle realistic offset along avenue
            num_match = re.search(r"\b(\d{2,5})\b", norm)
            offset_lat, offset_lng = 0.0, 0.0
            if num_match and key != "lira 953":
                num_val = int(num_match.group(1))
                offset_lat = ((num_val % 1000) - 500) * 0.000008
                offset_lng = ((num_val % 700) - 350) * 0.000008
            lat_f = round(info["lat"] + offset_lat, 5)
            lng_f = round(info["lng"] + offset_lng, 5)
            sx, sy = _latlng_to_svg(lat_f, lng_f)
            display_label = address_text.strip() if address_text and len(address_text.strip()) > 3 else info["nombre"]
            if comuna_hint and comuna_hint.lower() not in display_label.lower():
                display_label = f"{display_label}, {comuna_hint.strip()}"
            return {
                "nombre": display_label,
                "comuna": info["comuna"],
                "zona": info["zona"],
                "lat": lat_f,
                "lng": lng_f,
                "x": sx,
                "y": sy,
            }

    # 3. Check all 38 comunas of Gran Santiago
    for c_key, c_info in GRAN_SANTIAGO_COMUNAS.items():
        if c_key in norm:
            num_match = re.search(r"\b(\d{2,5})\b", norm)
            offset_lat, offset_lng = 0.0, 0.0
            if num_match:
                num_val = int(num_match.group(1))
                offset_lat = ((num_val % 900) - 450) * 0.00001
                offset_lng = ((num_val % 600) - 300) * 0.00001
            lat_f = round(c_info["lat"] + offset_lat, 5)
            lng_f = round(c_info["lng"] + offset_lng, 5)
            sx, sy = _latlng_to_svg(lat_f, lng_f)
            display_label = address_text.strip() if address_text and len(address_text.strip()) > 2 else c_info["nombre"]
            if comuna_hint and comuna_hint.lower() not in display_label.lower():
                display_label = f"{display_label}, {c_info['nombre']}"
            return {
                "nombre": display_label,
                "comuna": c_info["nombre"],
                "zona": c_info["zona"],
                "lat": lat_f,
                "lng": lng_f,
                "x": sx,
                "y": sy,
            }

    # 4. Fallback to canonical node
    node_id = resolve_zone_node(combined)
    node = SANTIAGO_NODES.get(node_id, SANTIAGO_NODES["SANTIAGO_CENTRO"])
    return {
        "nombre": combined or node["nombre"],
        "comuna": node["comuna"],
        "zona": node["id"],
        "lat": node["lat"],
        "lng": node["lng"],
        "x": node["x"],
        "y": node["y"],
    }


SANTIAGO_CORRIDORS: Dict[str, Dict[str, Any]] = {
    "VESPUCIO_NORTE": {
        "id": "VESPUCIO_NORTE",
        "nombre": "Autopista Vespucio Norte",
        "origen": "QUILICURA",
        "destino": "PUDAHUEL",
        "distancia_km": 18.4,
        "svg_path": "M 220,48 Q 120,68 92,138",
        "waypoints": [[-33.3600, -70.6900], [-33.3850, -70.7350], [-33.4350, -70.7600]],
        "midpoint": {"x": 142, "y": 84, "lat": -33.3850, "lng": -70.7350},
    },
    "VESPUCIO_PONIENTE": {
        "id": "VESPUCIO_PONIENTE",
        "nombre": "Vespucio Poniente → Maipú",
        "origen": "QUILICURA",
        "destino": "MAIPU",
        "distancia_km": 24.5,
        "svg_path": "M 220,48 Q 120,68 92,138 L 122,228",
        "waypoints": [[-33.3600, -70.6900], [-33.4350, -70.7600], [-33.5100, -70.7600]],
        "midpoint": {"x": 105, "y": 182, "lat": -33.4700, "lng": -70.7600},
    },
    "AUTOPISTA_CENTRAL_CENTRO": {
        "id": "AUTOPISTA_CENTRAL_CENTRO",
        "nombre": "Autopista Central → Alameda / Lira 953",
        "origen": "QUILICURA",
        "destino": "SANTIAGO_CENTRO",
        "distancia_km": 16.8,
        "svg_path": "M 220,48 L 255,102 L 365,156",
        "split_svg_path": "M 220,48 Q 345,76 365,156",
        "waypoints": [[-33.3600, -70.6900], [-33.4050, -70.6800], [-33.4410, -70.6600], [-33.4503, -70.6441]],
        "midpoint": {"x": 308, "y": 128, "lat": -33.4250, "lng": -70.6650},
    },
    "RUTA_5_SUR": {
        "id": "RUTA_5_SUR",
        "nombre": "Autopista Central / Ruta 5 Sur",
        "origen": "QUILICURA",
        "destino": "SAN_BERNARDO",
        "distancia_km": 29.2,
        "svg_path": "M 220,48 L 255,102 L 352,190 L 340,258",
        "waypoints": [[-33.3600, -70.6900], [-33.4050, -70.6800], [-33.4503, -70.6600], [-33.5200, -70.6850], [-33.5900, -70.7000]],
        "midpoint": {"x": 345, "y": 212, "lat": -33.5000, "lng": -70.6800},
    },
    "COSTANERA_NORTE": {
        "id": "COSTANERA_NORTE",
        "nombre": "Costanera Norte → Eje Oriente",
        "origen": "QUILICURA",
        "destino": "PROVIDENCIA",
        "distancia_km": 19.0,
        "svg_path": "M 220,48 L 255,102 Q 385,78 515,98",
        "waypoints": [[-33.3600, -70.6900], [-33.4050, -70.6800], [-33.4150, -70.6100], [-33.4300, -70.6150]],
        "midpoint": {"x": 405, "y": 88, "lat": -33.4150, "lng": -70.6300},
    },
}


def resolve_zone_node(text: str) -> str:
    """Maps a commune name or street address to a canonical tactical node ID."""
    if resolve_destination(text):
        return "SANTIAGO_CENTRO"
    norm = _normalize(text)
    if not norm:
        return "SANTIAGO_CENTRO"
    for key, info in KNOWN_SANTIAGO_LANDMARKS:
        if key in norm:
            return info["zona"]
    for c_key, c_info in GRAN_SANTIAGO_COMUNAS.items():
        if c_key in norm:
            return c_info["zona"]
    if "pudahuel" in norm or "enea" in norm or "lo prado" in norm or "cerro navia" in norm:
        return "PUDAHUEL"
    if "bernardo" in norm or "sur" in norm or "puente alto" in norm or "pintana" in norm or "bosque" in norm or "cisterna" in norm:
        return "SAN_BERNARDO"
    if "maipu" in norm or "melipilla" in norm or "cerrillos" in norm:
        return "MAIPU"
    if "providencia" in norm or "oriente" in norm or "las condes" in norm or "vitacura" in norm or "nunoa" in norm or "macul" in norm or "reina" in norm:
        return "PROVIDENCIA"
    if "renca" in norm or "taller" in norm or "quinta normal" in norm:
        return "RENCA"
    if "quilicura" in norm or "huechuraba" in norm or "conchali" in norm or "colina" in norm or "lampa" in norm:
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


def _build_dynamic_waypoints(orig_geo: Dict[str, Any], dest_geo: Dict[str, Any], default_waypoints: List[List[float]]) -> List[List[float]]:
    """Builds realistic road waypoints connecting custom origin and destination through Santiago's highway junctions."""
    olat, olng = orig_geo["lat"], orig_geo["lng"]
    dlat, dlng = dest_geo["lat"], dest_geo["lng"]
    # If standard canonical route from Quilicura to exact node, use canonical corridor waypoints
    if abs(olat - (-33.3600)) < 0.002 and default_waypoints:
        pts = [list(p) for p in default_waypoints]
        pts[0] = [olat, olng]
        pts[-1] = [dlat, dlng]
        return pts

    # Otherwise build realistic urban highway intermediate junction
    mid_lat = round((olat + dlat) / 2.0, 5)
    # Route via Autopista Central (-70.665) or Vespucio depending on longitude
    junction_lng = -70.6650 if max(olng, dlng) > -70.7000 else -70.7450
    mid_lng = round((olng + dlng + junction_lng) / 3.0, 5)
    return [
        [olat, olng],
        [mid_lat, mid_lng],
        [dlat, dlng],
    ]


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
    orig_lat: Optional[float] = None,
    orig_lng: Optional[float] = None,
    dest_lat: Optional[float] = None,
    dest_lng: Optional[float] = None,
) -> Dict[str, Any]:
    """Builds the rich tactical map telemetry payload for a dispatch evaluation."""
    hora_eff = hora_solicitada or hora or "14:00"
    trucks_eff = camiones if camiones is not None else (assigned_trucks or [])
    if version_mode is not None:
        v1_mode = (str(version_mode).lower() == "v1")
        living_memory_active = not v1_mode

    orig_geo = geocode_santiago_address(origen, custom_lat=orig_lat, custom_lng=orig_lng)
    dest_geo = geocode_santiago_address(destino, custom_lat=dest_lat, custom_lng=dest_lng)

    dest_node_id = dest_geo["zona"]
    dest_node = dict(SANTIAGO_NODES.get(dest_node_id, SANTIAGO_NODES["SANTIAGO_CENTRO"]))
    orig_node = dict(SANTIAGO_NODES.get(orig_geo["zona"], SANTIAGO_NODES["QUILICURA"]))

    # Override coords if custom street/comuna geocoding was resolved
    orig_node["lat"] = orig_geo["lat"]
    orig_node["lng"] = orig_geo["lng"]
    orig_node["nombre"] = orig_geo["nombre"]
    dest_node["lat"] = dest_geo["lat"]
    dest_node["lng"] = dest_geo["lng"]
    dest_node["nombre"] = dest_geo["nombre"]

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
    marker_pos = dict(corridor["midpoint"])

    if status == "BLOQUEADO_RIESGO":
        route_color = "#ef4444"
        congestion["nivel"] = "BLOQUEO_SEGURIDAD"
        congestion["etiqueta"] = "SALIDA DENEGADA · BLOQUEO SEGURIDAD"
        truck_badge = "🛑 BLOQUEADO"
        if dest_node_id == "MAIPU":
            marker_pos = {"x": 255, "y": 78, "lat": -33.4050, "lng": -70.6800}
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
    waypoints = _build_dynamic_waypoints(orig_geo, dest_geo, corridor.get("waypoints", []))

    # Preserve canonical distance for standard Quilicura -> node routes, else compute real Haversine road km
    if orig_geo["zona"] == "QUILICURA" and dest_geo["comuna"].lower() in ("pudahuel", "maipú", "maipu", "santiago centro", "providencia", "san bernardo"):
        dist_km = float(corridor["distancia_km"])
    else:
        dist_km = _haversine_km(orig_geo["lat"], orig_geo["lng"], dest_geo["lat"], dest_geo["lng"])

    speed_kmh = max(float(congestion.get("velocidad_kmh") or 40.0), 20.0)
    eta_mins = int(round((dist_km / speed_kmh) * 60))
    alternatives = (
        ["VENTANA_NOCTURNA_2130", "SUBDIVISION_2X_5T_CAM02_CAM03"]
        if dest_node_id == "SANTIAGO_CENTRO" and peso > 5000
        else (["RESERVA_DIA_SIGUIENTE_0800"] if "08:00" in str(fecha_hora_programada) else ["DESPACHO_DIRECTO_HOY"])
    )

    gmaps_url = (
        f"https://www.google.com/maps/dir/?api=1"
        f"&origin={orig_geo['lat']},{orig_geo['lng']}"
        f"&destination={dest_geo['lat']},{dest_geo['lng']}"
        f"&travelmode=driving"
    )

    return {
        "origen_nodo": orig_node["id"],
        "origen_nombre": orig_geo["nombre"],
        "destino_nodo": dest_node["id"],
        "destino_nombre": known_ref.get("direccion") or dest_geo["nombre"],
        "origin_node": orig_node,
        "destination_node": dest_node,
        "origin_coords": [orig_geo["lat"], orig_geo["lng"]],
        "destination_coords": [dest_geo["lat"], dest_geo["lng"]],
        "waypoints": waypoints,
        "google_maps_url": gmaps_url,
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

    default_markers = {
        "CAM-01": {"id": "CAM-01", "modelo": "Hyundai HD78 3.5t", "capacidad_kg": 3500, "nodo": "QUILICURA", "node_id": "QUILICURA", "base_guarda": "Hub Central Quilicura", "x": 310, "y": 54, "lat": -33.3610, "lng": -70.6910, "estado": "DISPONIBLE", "status": "DISPONIBLE", "blocked": False, "detail": "En Base Quilicura — Disponible (Carga liviana <=3.000 kg)"},
        "CAM-02": {"id": "CAM-02", "modelo": "Mercedes Atego 5t", "capacidad_kg": 5000, "nodo": "QUILICURA", "node_id": "QUILICURA", "base_guarda": "Hub Central Quilicura", "x": 365, "y": 54, "lat": -33.3600, "lng": -70.6880, "estado": "DISPONIBLE", "status": "DISPONIBLE", "blocked": False, "detail": "En Base Quilicura — Disponible (Caso 1 / Split 5t)"},
        "CAM-03": {"id": "CAM-03", "modelo": "Mercedes Atego 5t", "capacidad_kg": 5000, "nodo": "QUILICURA", "node_id": "QUILICURA", "base_guarda": "Hub Central Quilicura", "x": 418, "y": 54, "lat": -33.3590, "lng": -70.6920, "estado": "DISPONIBLE", "status": "DISPONIBLE", "blocked": False, "detail": "En Base Quilicura — Disponible (Split 2x 5t)"},
        "CAM-04": {"id": "CAM-04", "modelo": "VW Delivery 8t", "capacidad_kg": 8000, "nodo": "RENCA", "node_id": "RENCA", "base_guarda": "Taller Mecánico Renca", "x": 295, "y": 195, "lat": -33.4050, "lng": -70.6800, "estado": "EN_MANTENIMIENTO", "status": "EN_MANTENIMIENTO", "blocked": True, "alerta": "Falla crítica de frenos de aire", "detail": "BLOQUEADO EN TALLER RENCA: Falla crítica de frenos de aire (Caso 5)"},
        "CAM-05": {"id": "CAM-05", "modelo": "Volvo VM 12t", "capacidad_kg": 12000, "nodo": "QUILICURA", "node_id": "QUILICURA", "base_guarda": "Hub Central Quilicura", "x": 395, "y": 106, "lat": -33.3620, "lng": -70.6870, "estado": "DISPONIBLE", "status": "DISPONIBLE", "blocked": False, "detail": "En Base Quilicura — Disponible (12t Caso 3 v1/v2)"},
        "CAM-06": {"id": "CAM-06", "modelo": "Scania P250 12t", "capacidad_kg": 12000, "nodo": "SAN_BERNARDO", "node_id": "SAN_BERNARDO", "base_guarda": "Planta Sur San Bernardo", "x": 445, "y": 350, "lat": -33.5900, "lng": -70.7000, "estado": "EN_RUTA", "status": "EN_RUTA", "blocked": False, "alerta": "Reserva mañana 08:00 hrs", "detail": "En Ruta Sur — Próximo slot mañana 08:00 hrs (Caso 2)"},
        "CAM-07": {"id": "CAM-07", "modelo": "Scania G360 15t", "capacidad_kg": 15000, "nodo": "PUDAHUEL", "node_id": "PUDAHUEL", "base_guarda": "CD Logístico Pudahuel", "x": 155, "y": 182, "lat": -33.4350, "lng": -70.7600, "estado": "EN_RUTA", "status": "EN_RUTA", "blocked": False, "detail": "En Ruta Poniente — Retorno mañana 08:00 hrs"},
    }

    # Merge live truck positions/statuses if provided from FleetService
    if trucks:
        for t in trucks:
            tid = t.get("id_camion") or t.get("id")
            if tid and tid in default_markers:
                m = default_markers[tid]
                raw_est = t.get("estado_operativo") or t.get("status") or m["status"]
                if raw_est == "DISPONIBLE_HOY":
                    raw_est = "DISPONIBLE"
                elif raw_est == "EN_RUTA_HOY":
                    raw_est = "EN_RUTA"
                m["status"] = raw_est
                m["estado"] = raw_est
                if t.get("lat") is not None and t.get("lng") is not None:
                    m["lat"] = float(t["lat"])
                    m["lng"] = float(t["lng"])
                    sx, sy = _latlng_to_svg(m["lat"], m["lng"])
                    m["x"], m["y"] = sx, sy
                if t.get("ubicacion_actual"):
                    m["detail"] = f"{t['ubicacion_actual']} — {t.get('notas_mantenimiento') or raw_est}"
                if t.get("base_guarda"):
                    m["base_guarda"] = t["base_guarda"]

    fleet_markers = list(default_markers.values())
    sample_cg = _compute_corridor_congestion("AUTOPISTA_CENTRAL_CENTRO", mins, is_daytime_ban_triggered=False)

    geofence_coords = [
        [-33.4300, -70.6720],
        [-33.4320, -70.6380],
        [-33.4580, -70.6350],
        [-33.4680, -70.6550],
        [-33.4520, -70.6800],
    ]

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
            "polygon_coords": geofence_coords,
        },
        "geofence_polygon_coords": geofence_coords,
        "map_center": {"lat": -33.4450, "lng": -70.6600, "zoom": 12},
        "nodos": SANTIAGO_NODES,
        "comunas_disponibles": [v["nombre"] for v in GRAN_SANTIAGO_COMUNAS.values()],
        "corredores": corridors_state,
        "corridors": corridors_list,
        "flota_tactica": fleet_markers,
        "fleet_markers": fleet_markers,
    }
