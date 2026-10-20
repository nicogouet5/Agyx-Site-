"""
app/services/fleet_service.py
Service layer for fleet queries, maintenance safety checks, and reservation slots.
"""
import json
import os
from typing import Dict, Any, List, Optional

from app.config import FLEET_JSON_PATH
from app.models.fleet import Truck
from app.tools.callable_tools import consultar_flota_disponible


class FleetService:
    def __init__(self, fleet_path: Optional[str] = None):
        self.fleet_path = fleet_path or FLEET_JSON_PATH

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
