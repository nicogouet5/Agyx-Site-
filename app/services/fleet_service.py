"""
app/services/fleet_service.py
Service layer for fleet queries, maintenance safety checks, physical depot bases
("lugares donde se guardan"), and real-time operational truck state updates.
"""
import json
import os
import sqlite3
from datetime import datetime
from typing import Dict, Any, List, Optional

from app.config import FLEET_JSON_PATH, SQLITE_DB_PATH
from app.models.fleet import Truck
from app.tools.callable_tools import consultar_flota_disponible


BASES_OPERATIVAS: Dict[str, Dict[str, Any]] = {
    "HUB_QUILICURA": {
        "id": "HUB_QUILICURA",
        "nombre": "Hub Central Quilicura",
        "comuna": "Quilicura",
        "direccion": "Panamericana Norte Km 16.5, Quilicura",
        "tipo": "PATIO_CENTRAL",
        "capacidad_andenes": 6,
        "lat": -33.3600,
        "lng": -70.6900,
        "camiones_base": ["CAM-01", "CAM-02", "CAM-03", "CAM-05"],
        "descripcion": "Base operativa principal donde se guardan y despachan las unidades livianas, medianas y pesadas.",
    },
    "TALLER_RENCA": {
        "id": "TALLER_RENCA",
        "nombre": "Taller Mecánico Renca",
        "comuna": "Renca",
        "direccion": "Av. Domingo Santa María 3800, Renca",
        "tipo": "MAESTRANZA_SEGURIDAD",
        "capacidad_andenes": 3,
        "lat": -33.4050,
        "lng": -70.6800,
        "camiones_base": ["CAM-04"],
        "descripcion": "Recinto de mantenimiento y bloqueo físico/electrónico de unidades con fallas mecánicas.",
    },
    "CD_PUDAHUEL": {
        "id": "CD_PUDAHUEL",
        "nombre": "CD Logístico Pudahuel (ENEA)",
        "comuna": "Pudahuel",
        "direccion": "Parque Industrial ENEA, Pudahuel",
        "tipo": "BASE_PONIENTE",
        "capacidad_andenes": 4,
        "lat": -33.4350,
        "lng": -70.7600,
        "camiones_base": ["CAM-07"],
        "descripcion": "Base secundaria poniente para camiones pesados de 15t y conexión aeroportuaria.",
    },
    "PLANTA_SAN_BERNARDO": {
        "id": "PLANTA_SAN_BERNARDO",
        "nombre": "Patio Sur San Bernardo",
        "comuna": "San Bernardo",
        "direccion": "Av. Jorge Alessandri 11500, San Bernardo",
        "tipo": "BASE_SUR",
        "capacidad_andenes": 4,
        "lat": -33.5900,
        "lng": -70.7000,
        "camiones_base": ["CAM-06"],
        "descripcion": "Patio de guarda zona sur para operaciones industriales de alto tonelaje.",
    },
}

TRUCK_HOME_BASE_MAP: Dict[str, str] = {
    "CAM-01": "HUB_QUILICURA",
    "CAM-02": "HUB_QUILICURA",
    "CAM-03": "HUB_QUILICURA",
    "CAM-04": "TALLER_RENCA",
    "CAM-05": "HUB_QUILICURA",
    "CAM-06": "PLANTA_SAN_BERNARDO",
    "CAM-07": "CD_PUDAHUEL",
}

DEFAULT_TRUCK_COORDS: Dict[str, Dict[str, float]] = {
    "CAM-01": {"lat": -33.3610, "lng": -70.6910},
    "CAM-02": {"lat": -33.3600, "lng": -70.6880},
    "CAM-03": {"lat": -33.3590, "lng": -70.6920},
    "CAM-04": {"lat": -33.4050, "lng": -70.6800},
    "CAM-05": {"lat": -33.3620, "lng": -70.6870},
    "CAM-06": {"lat": -33.5900, "lng": -70.7000},
    "CAM-07": {"lat": -33.4350, "lng": -70.7600},
}


class FleetService:
    def __init__(self, fleet_path: Optional[str] = None, db_path: Optional[str] = None):
        self.fleet_path = fleet_path or FLEET_JSON_PATH
        self.db_path = db_path or SQLITE_DB_PATH
        self._init_live_table()

    def _init_live_table(self) -> None:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fleet_live_state (
                    truck_id TEXT PRIMARY KEY,
                    estado_operativo TEXT NOT NULL,
                    ubicacion_actual TEXT NOT NULL,
                    base_id TEXT NOT NULL,
                    lat REAL NOT NULL,
                    lng REAL NOT NULL,
                    active_order_id TEXT,
                    destino_actual TEXT,
                    updated_at TEXT NOT NULL
                );
            """)
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _get_live_overrides(self) -> Dict[str, Dict[str, Any]]:
        overrides: Dict[str, Dict[str, Any]] = {}
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("""
                SELECT truck_id, estado_operativo, ubicacion_actual, base_id,
                       lat, lng, active_order_id, destino_actual, updated_at
                FROM fleet_live_state
            """)
            for row in cur.fetchall():
                overrides[row[0]] = {
                    "truck_id": row[0],
                    "estado_operativo": row[1],
                    "ubicacion_actual": row[2],
                    "base_id": row[3],
                    "lat": row[4],
                    "lng": row[5],
                    "active_order_id": row[6],
                    "destino_actual": row[7],
                    "updated_at": row[8],
                }
            conn.close()
        except Exception:
            pass
        return overrides

    def get_all_trucks(self) -> List[Truck]:
        """Loads all trucks as domain Truck instances."""
        if not os.path.exists(self.fleet_path):
            return []
        try:
            with open(self.fleet_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [Truck.from_dict(t) for t in data]
        except Exception:
            return []

    def get_all_trucks_enriched(self) -> List[Dict[str, Any]]:
        """Returns all trucks enriched with their home base ('lugar de guarda'), live GPS coords, and active mission."""
        trucks = self.get_all_trucks()
        overrides = self._get_live_overrides()
        result = []
        for t in trucks:
            d = t.to_dict()
            tid = d["id_camion"]
            base_id = TRUCK_HOME_BASE_MAP.get(tid, "HUB_QUILICURA")
            base_info = BASES_OPERATIVAS.get(base_id, BASES_OPERATIVAS["HUB_QUILICURA"])
            coords = DEFAULT_TRUCK_COORDS.get(tid, {"lat": base_info["lat"], "lng": base_info["lng"]})

            d["base_id"] = base_id
            d["base_guarda"] = base_info["nombre"]
            d["base_direccion"] = base_info["direccion"]
            d["lat"] = coords["lat"]
            d["lng"] = coords["lng"]
            d["ubicacion_actual"] = d["ubicacion_base"]
            d["active_order_id"] = None
            d["destino_actual"] = None

            if tid in overrides and tid != "CAM-04":
                ov = overrides[tid]
                d["estado_operativo"] = ov["estado_operativo"]
                d["ubicacion_actual"] = ov["ubicacion_actual"]
                d["lat"] = ov["lat"]
                d["lng"] = ov["lng"]
                d["active_order_id"] = ov["active_order_id"]
                d["destino_actual"] = ov["destino_actual"]
                d["updated_at"] = ov["updated_at"]

            result.append(d)
        return result

    def get_bases_summary(self) -> List[Dict[str, Any]]:
        """Returns the 4 physical storage/maintenance bases ('lugares donde se guardan') with parked vs en-route units."""
        enriched = self.get_all_trucks_enriched()
        bases_list = []
        for bid, binfo in BASES_OPERATIVAS.items():
            assigned = [t for t in enriched if t.get("base_id") == bid]
            en_guarda = [t for t in assigned if t.get("estado_operativo") in ("DISPONIBLE", "EN_MANTENIMIENTO")]
            en_ruta = [t for t in assigned if t.get("estado_operativo") == "EN_RUTA"]
            bases_list.append({
                **binfo,
                "unidades_asignadas": len(assigned),
                "unidades_en_guarda": len(en_guarda),
                "unidades_en_ruta": len(en_ruta),
                "camiones": assigned,
            })
        return bases_list

    def update_truck_live_status(
        self,
        truck_id: str,
        estado_operativo: str,
        ubicacion_actual: Optional[str] = None,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        active_order_id: Optional[str] = None,
        destino_actual: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates a truck's live operational status and GPS position (blocks CAM-04 from leaving Renca)."""
        clean_id = (truck_id or "").strip().upper()
        truck = self.get_truck_by_id(clean_id)
        if not truck:
            raise KeyError(f"Camión '{clean_id}' no encontrado")

        if clean_id == "CAM-04" and estado_operativo.upper() != "EN_MANTENIMIENTO":
            raise ValueError(
                "BLOQUEO DE SEGURIDAD ACTIVO: CAM-04 tiene falla crítica en sistema de frenos de aire "
                "y no puede salir de Taller Renca."
            )

        base_id = TRUCK_HOME_BASE_MAP.get(clean_id, "HUB_QUILICURA")
        base_info = BASES_OPERATIVAS.get(base_id, BASES_OPERATIVAS["HUB_QUILICURA"])
        default_c = DEFAULT_TRUCK_COORDS.get(clean_id, {"lat": base_info["lat"], "lng": base_info["lng"]})

        new_est = estado_operativo.strip().upper()
        if new_est == "DISPONIBLE":
            # Returning truck to its home depot base
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("DELETE FROM fleet_live_state WHERE truck_id = ?", (clean_id,))
            conn.commit()
            conn.close()
            return {
                "truck_id": clean_id,
                "estado_operativo": "DISPONIBLE",
                "ubicacion_actual": base_info["nombre"],
                "base_guarda": base_info["nombre"],
                "lat": default_c["lat"],
                "lng": default_c["lng"],
                "active_order_id": None,
                "message": f"Unidad {clean_id} retornada y guardada en {base_info['nombre']}.",
            }

        final_lat = float(lat) if lat is not None else default_c["lat"]
        final_lng = float(lng) if lng is not None else default_c["lng"]
        final_ubic = ubicacion_actual or (f"En Ruta → {destino_actual}" if destino_actual else base_info["nombre"])
        now_iso = datetime.utcnow().isoformat() + "Z"

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO fleet_live_state (
                truck_id, estado_operativo, ubicacion_actual, base_id,
                lat, lng, active_order_id, destino_actual, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(truck_id) DO UPDATE SET
                estado_operativo = excluded.estado_operativo,
                ubicacion_actual = excluded.ubicacion_actual,
                lat = excluded.lat,
                lng = excluded.lng,
                active_order_id = excluded.active_order_id,
                destino_actual = excluded.destino_actual,
                updated_at = excluded.updated_at
        """, (clean_id, new_est, final_ubic, base_id, final_lat, final_lng, active_order_id, destino_actual, now_iso))
        conn.commit()
        conn.close()

        return {
            "truck_id": clean_id,
            "estado_operativo": new_est,
            "ubicacion_actual": final_ubic,
            "base_guarda": base_info["nombre"],
            "lat": final_lat,
            "lng": final_lng,
            "active_order_id": active_order_id,
            "destino_actual": destino_actual,
            "message": f"Estado de {clean_id} actualizado a {new_est} ({final_ubic}).",
        }

    def dispatch_trucks_for_order(
        self,
        truck_ids: List[str],
        case_id: str,
        destino: str,
        dest_lat: Optional[float] = None,
        dest_lng: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Marks assigned trucks as EN_RUTA toward the approved order's destination."""
        dispatched = []
        for idx, tid in enumerate(truck_ids or []):
            if tid.upper() == "CAM-04":
                continue
            try:
                # Position truck along route / destination with slight offset if multiple trucks
                lat_val = (float(dest_lat) + idx * 0.0025) if dest_lat is not None else None
                lng_val = (float(dest_lng) + idx * 0.0025) if dest_lng is not None else None
                res = self.update_truck_live_status(
                    truck_id=tid,
                    estado_operativo="EN_RUTA",
                    ubicacion_actual=f"En Ruta ({case_id}) → {destino}",
                    lat=lat_val,
                    lng=lng_val,
                    active_order_id=case_id,
                    destino_actual=destino,
                )
                dispatched.append(res)
            except Exception:
                pass
        return dispatched

    def reset_live_fleet(self) -> None:
        """Clears live truck overrides so all units return to their canonical initial state."""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("DELETE FROM fleet_live_state")
            conn.commit()
            conn.close()
        except Exception:
            pass

    def get_truck_by_id(self, truck_id: str) -> Optional[Truck]:
        """Returns single truck by ID."""
        clean_id = (truck_id or "").strip().upper()
        for t in self.get_all_trucks():
            if t.id_camion.upper() == clean_id:
                return t
        return None

    def filter_available_trucks(
        self,
        peso_kg: float,
        volumen_m3: float = 0.0,
        fecha: Optional[str] = None,
        hora: Optional[str] = None,
        truck_id_preferido: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes capacity filtering, maintenance checks, and next-day reservations.
        Guarantees token budget <150 tokens.
        """
        return consultar_flota_disponible(
            peso_kg=peso_kg,
            volumen_m3=volumen_m3,
            fecha_despacho=fecha,
            hora_despacho=hora,
            truck_id_preferido=truck_id_preferido,
            fleet_file=self.fleet_path,
        )
