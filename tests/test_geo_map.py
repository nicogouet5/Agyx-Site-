"""The Lira 953 address hint must affect the actual dispatch decision."""
import tempfile
import unittest
from pathlib import Path

from app.api.dependencies import ServiceContainer
from app.api.routes_dispatch import evaluate_dispatch_controller
from app.services.geo_service import resolve_destination
from app.tools.callable_tools import verificar_factibilidad_ruta_urbana


class TestMapReference(unittest.TestCase):
    def test_known_address_resolves_to_centro(self):
        self.assertEqual(resolve_destination("Lira 953, Santiago")["zona"], "SANTIAGO_CENTRO")
        self.assertEqual(resolve_destination("Av. Lira N° 953")["zona"], "SANTIAGO_CENTRO")
        self.assertEqual(resolve_destination("Pudahuel"), {})
        self.assertEqual(resolve_destination("Lira 9530"), {})

    def test_heavy_daytime_address_requires_human_review_without_memory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            services = ServiceContainer(db_path=str(Path(temp_dir) / "demo.db"), memory_path=str(Path(temp_dir) / "memory.json"))
            status, result = evaluate_dispatch_controller({
            "case_id": "TEST-LIRA-953",
            "origen": "Quilicura",
            "destino": "Lira 953, Santiago",
            "cargo_weight_kg": 9500,
            "hora_despacho": "11:30",
            "version_mode": "v2",
            }, services=services)
        self.assertEqual(status, 200)
        self.assertEqual(result["mapa"]["zona"], "SANTIAGO_CENTRO")
        self.assertEqual(result["status"], "R4R_INFO_INCOMPLETA")
        self.assertFalse(result["auto_approved"])
        self.assertEqual(result["proposal"]["camiones"], [])
        self.assertEqual(result["mapa"]["direccion"], "Lira 953, Santiago, Chile")
        self.assertIn("regla_operativa_validada", result["proposal"]["campos_faltantes"])

    def test_route_tool_blocks_daytime_even_without_memory(self):
        result = verificar_factibilidad_ruta_urbana(
            "Quilicura", "Lira 953", 9500, "11:30", living_memory_active=False
        )
        self.assertFalse(result["factible"])
        self.assertEqual(result["zona"], "SANTIAGO_CENTRO")


if __name__ == "__main__":
    unittest.main()
