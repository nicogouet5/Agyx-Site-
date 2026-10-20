"""
app/services/restriction_service.py
Service layer for municipal road ordinances, daytime bans, and HAZMAT legal checks.
"""
import json
import os
from typing import Dict, Any, List, Optional

from app.config import RESTRICTIONS_JSON_PATH
from app.models.restrictions import UrbanRestriction
from app.tools.callable_tools import verificar_factibilidad_ruta_urbana


class RestrictionService:
    def __init__(self, restrictions_path: Optional[str] = None):
        self.restrictions_path = restrictions_path or RESTRICTIONS_JSON_PATH

    def get_all_restrictions(self) -> List[UrbanRestriction]:
        """Loads all urban restrictions as domain UrbanRestriction instances."""
        if not os.path.exists(self.restrictions_path):
            return []
        try:
            with open(self.restrictions_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [UrbanRestriction.from_dict(r) for r in data]
        except Exception:
            return []

    def get_restriction_for_zone(self, zone_or_comuna: str) -> Optional[UrbanRestriction]:
        """Finds matching restriction for a given zone or comuna name."""
        for r in self.get_all_restrictions():
            if r.aplica_a_comuna(zone_or_comuna):
                return r
        return None

    def check_route_feasibility(
        self,
        origen: str,
        destino_comuna: str,
        peso_kg: float,
        hora_solicitada: str,
        tipo_carga: str = "GENERAL",
        living_memory_active: bool = False,
    ) -> Dict[str, Any]:
        """
        Validates municipal compliance, HAZMAT D.S. 298 block, and Living Memory rules.
        Guarantees token budget <150 tokens.
        """
        return verificar_factibilidad_ruta_urbana(
            origen=origen,
            destino_comuna=destino_comuna,
            peso_kg=peso_kg,
            hora_solicitada=hora_solicitada,
            tipo_carga=tipo_carga,
            living_memory_active=living_memory_active,
        )
