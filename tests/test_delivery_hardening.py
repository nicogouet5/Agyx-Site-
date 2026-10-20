"""Regression checks for the Certamen 2 demo safety boundary."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.api.routes_dispatch import evaluate_dispatch_controller
from app.services.r4r_service import R4RService
from app.tools.callable_tools import consultar_flota_disponible, verificar_factibilidad_ruta_urbana


class DeliveryHardeningTests(unittest.TestCase):
    def test_blocked_case_cannot_be_approved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = R4RService(db_path=str(Path(temp_dir) / "demo.db"), storage_path=str(Path(temp_dir) / "memory.json"))
            service.create_proposal("BLOCKED", [], "Quilicura", "Maipú", "10:00", 0, estado_caso="BLOQUEADO_RIESGO")
            with self.assertRaises(ValueError):
                service.review_proposal("BLOCKED", "APPROVE", "Nombre declarado")
            self.assertEqual(service.get_proposal("BLOCKED")["estado"], "BLOQUEADO_RIESGO")

    def test_incomplete_case_cannot_be_approved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = R4RService(db_path=str(Path(temp_dir) / "demo.db"), storage_path=str(Path(temp_dir) / "memory.json"))
            service.create_proposal("INCOMPLETE", [], "Quilicura", "", "", 0, campos_faltantes=["peso_kg"])
            with self.assertRaises(ValueError):
                service.review_proposal("INCOMPLETE", "APPROVE", "Nombre declarado")

    def test_default_version_is_safe(self):
        code, result = evaluate_dispatch_controller({"case_id": "DEFAULT-V2", "destino": "Santiago Centro", "cargo_weight_kg": 9500, "hora_despacho": "11:30"})
        self.assertEqual(code, 200)
        self.assertIn("21:30", result["proposal"]["fecha_hora_programada"])

    def test_invalid_hour_is_not_factible(self):
        result = verificar_factibilidad_ruta_urbana("Quilicura", "Santiago Centro", 9500, "25:99")
        self.assertFalse(result["factible"])
        self.assertIn("SOLICITAR_HORA_VALIDA", result["acciones_mitigacion"])
        code, evaluated = evaluate_dispatch_controller({"case_id": "INVALID-HOUR", "destino": "Santiago Centro", "cargo_weight_kg": 9500, "hora_despacho": "25:99"})
        self.assertEqual(code, 200)
        self.assertEqual(evaluated["status"], "R4R_INFO_INCOMPLETA")

    def test_reservation_date_follows_requested_day(self):
        requested_day = datetime.now(ZoneInfo("America/Santiago")).date() + timedelta(days=7)
        result = consultar_flota_disponible(10000, fecha_despacho=requested_day.isoformat(), hora_despacho="15:00")
        self.assertEqual(result["proxima_reserva"]["fecha"], (requested_day + timedelta(days=1)).isoformat())


if __name__ == "__main__":
    unittest.main()
