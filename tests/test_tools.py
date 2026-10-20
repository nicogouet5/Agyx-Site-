"""
tests/test_tools.py
Automated verification for the 3 Callable Tools and Token Optimizer.
Runs with zero external dependencies (pytest or python3 -m unittest).
"""
import unittest
from app.tools.callable_tools import (
    consultar_flota_disponible,
    verificar_factibilidad_ruta_urbana,
    generar_propuesta_r4r,
)
from app.tools.token_optimizer import (
    count_tokens,
    enforce_token_budget,
    distill_rule,
    assert_token_budget,
)


class TestCallableToolsAndTokenOptimizer(unittest.TestCase):

    def test_tool1_caso1_normal_fleet_match(self):
        """Caso 1: 3,200 kg load selects Atego 5t CAM-02 under budget."""
        res = consultar_flota_disponible(peso_kg=3200, hora_despacho="14:00")
        self.assertEqual(res["status"], "OK")
        self.assertTrue(len(res["candidatos"]) >= 1)
        self.assertEqual(res["candidatos"][0]["id"], "CAM-02")
        assert_token_budget(res, max_tokens=150, name="Tool1_Caso1")

    def test_tool1_caso2_busy_fleet_next_day_slot(self):
        """Caso 2: 10,000 kg load when 12t fleet is busy finds slot tomorrow 08:00."""
        res = consultar_flota_disponible(peso_kg=10000, hora_despacho="15:00")
        self.assertEqual(res["status"], "SIN_DISPONIBILIDAD_HOY")
        self.assertIsNotNone(res["proxima_reserva"])
        self.assertEqual(res["proxima_reserva"]["hora"], "08:00")
        assert_token_budget(res, max_tokens=150, name="Tool1_Caso2")

    def test_tool1_caso5_brake_failure_safety_lock(self):
        """Caso 5: Pressure to use CAM-04 with brake failure triggers critical lock."""
        res = consultar_flota_disponible(peso_kg=4000, truck_id_preferido="CAM-04")
        self.assertEqual(res["status"], "BLOQUEO_MANTENIMIENTO")
        self.assertEqual(len(res["bloqueos_mantenimiento"]), 1)
        self.assertTrue(res["bloqueos_mantenimiento"][0]["bloqueado"])
        self.assertIn("frenos", res["bloqueos_mantenimiento"][0]["motivo"].lower())
        assert_token_budget(res, max_tokens=150, name="Tool1_Caso5")

    def test_tool2_santiago_centro_v1_vs_v2(self):
        """Caso 3: Santiago Centro daytime ban v1 baseline vs v2 Living Memory."""
        # v1: baseline without living memory
        res_v1 = verificar_factibilidad_ruta_urbana(
            origen="Quilicura", destino_comuna="Santiago Centro",
            peso_kg=9500, hora_solicitada="11:30", living_memory_active=False
        )
        self.assertTrue(res_v1["factible"])
        assert_token_budget(res_v1, max_tokens=150, name="Tool2_v1")

        # v2: post-iteration with living memory active
        res_v2 = verificar_factibilidad_ruta_urbana(
            origen="Quilicura", destino_comuna="Santiago Centro",
            peso_kg=9500, hora_solicitada="11:30", living_memory_active=True
        )
        self.assertFalse(res_v2["factible"])
        self.assertIsNotNone(res_v2["leccion_memoria_viva"])
        self.assertIn("REPROGRAMAR_NOCTURNO_2130", res_v2["acciones_mitigacion"])
        assert_token_budget(res_v2, max_tokens=150, name="Tool2_v2")

    def test_tool2_caso6_hazmat_ds298_block(self):
        """Caso 6: Hazardous cargo triggers immediate D.S. 298 block."""
        res = verificar_factibilidad_ruta_urbana(
            origen="Quilicura", destino_comuna="Santiago Centro",
            peso_kg=4000, hora_solicitada="14:00", tipo_carga="ACIDO_SULFURICO"
        )
        self.assertFalse(res["factible"])
        self.assertEqual(res["bloqueo_legal"], "CARGA_PELIGROSA_D_S_298")
        assert_token_budget(res, max_tokens=150, name="Tool2_Caso6")

    def test_tool3_auto_approved_invariant_false(self):
        """Invariant: auto_approved is strictly False and requires human review."""
        res = generar_propuesta_r4r(
            case_id="CASO-1",
            camiones_asignados=["CAM-02"],
            origen="Quilicura",
            destino="Pudahuel",
            fecha_hora_programada="2026-10-20 14:00",
            tarifa_base_clp=50000,
            recargo_clp=15000,
            sla_horas=2.5,
        )
        self.assertEqual(res["estado"], "R4R")
        self.assertFalse(res["auto_approved"])
        self.assertTrue(res["requiere_firma_humana"])
        self.assertEqual(res["total_clp"], 65000)
        assert_token_budget(res, max_tokens=150, name="Tool3_Caso1")

    def test_living_memory_distillation_budget(self):
        """Living Memory distillation must produce lessons < 80 tokens."""
        raw = ("Ordenanza Santiago Centro prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs. "
               "Reprogramar a ventana nocturna (21:30/06:00) o subdividir en 2 camiones de 5t")
        distilled = distill_rule(raw)
        self.assertTrue(len(distilled) > 0)
        tokens = count_tokens(distilled)
        self.assertLess(tokens, 80)


if __name__ == "__main__":
    unittest.main()
