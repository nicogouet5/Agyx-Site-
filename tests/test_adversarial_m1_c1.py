"""
tests/test_adversarial_m1_c1.py
Adversarial Stress-Testing Suite for Milestone 1.
Executed by M1 Challenger 1.

Covers:
1. Extreme boundary weights (0 kg, -500 kg, 3500 kg, 5000 kg, 12000 kg, 50000 kg overload).
2. Timestamp edge cases (07:30, 21:00, 21:01, 00:00, single-digit 7:30, invalid strings).
3. Safety lock bypass: CAM-04 brake failure (case-sensitivity, whitespace, descriptions).
4. Ambiguous inputs with partial fields (missing fields vs unhandled type errors).
5. Token budget stress (payload pruning, <=150 token budget, nested dict token leak).
6. HAZMAT cargo classification (accented Spanish string bypass: Ácido Sulfúrico).
"""
import unittest
import os
import json
import sqlite3
import tempfile
import shutil

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
from app.models.restrictions import UrbanRestriction
from app.services.memory_service import MemoryService
from app.services.r4r_service import R4RService
from app.services.db_service import init_db
from app.engine.local_engine import LocalAgentEngine


class TestExtremeBoundaryWeights(unittest.TestCase):
    """Stress testing weight boundaries in tool 1 and engine."""

    def test_weight_zero_and_negative(self):
        """0 kg and negative weights must be caught by validation."""
        for w in [0, -1, -500, -99999]:
            res = consultar_flota_disponible(peso_kg=w)
            self.assertEqual(res["status"], "ERROR_VALIDACION")
            self.assertEqual(len(res["candidatos"]), 0)
            self.assertIn("inválido", res.get("motivo", "").lower())
            assert_token_budget(res, max_tokens=150, name=f"Weight_{w}")

    def test_weight_3500kg_tres_cuartos_boundary(self):
        """
        3500 kg is the nominal capacity of CAM-01 (HD78 3.5t PBV).
        Under Chilean standards, effective payload is 3000 kg.
        Therefore, 3500 kg must select CAM-02 (5t Atego).
        """
        res = consultar_flota_disponible(peso_kg=3500, hora_despacho="12:00")
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["candidatos"][0]["id"], "CAM-02")
        assert_token_budget(res, max_tokens=150, name="Weight_3500")

    def test_weight_5000kg_exact_boundary(self):
        """5000 kg exact boundary matches CAM-02 (5t Atego)."""
        res = consultar_flota_disponible(peso_kg=5000, hora_despacho="12:00")
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["candidatos"][0]["id"], "CAM-02")
        assert_token_budget(res, max_tokens=150, name="Weight_5000")

    def test_weight_12000kg_exact_boundary(self):
        """12000 kg exact boundary matches CAM-05 (12t Volvo) when departing before 15:00."""
        res = consultar_flota_disponible(peso_kg=12000, hora_despacho="11:00")
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["candidatos"][0]["id"], "CAM-05")
        assert_token_budget(res, max_tokens=150, name="Weight_12000")

    def test_weight_50000kg_catastrophic_overload_vulnerability(self):
        """
        Adversarial test: 50,000 kg (50 tons) massively exceeds entire fleet.
        Tool returns EXCEDE_CAPACIDAD_FLOTA with empty candidates.
        LocalAgentEngine blocks dispatch with BLOQUEADO_RIESGO and empty trucks.
        """
        # 1. Tool behavior
        res_tool = consultar_flota_disponible(peso_kg=50000)
        self.assertEqual(res_tool["status"], "EXCEDE_CAPACIDAD_FLOTA")
        self.assertEqual(len(res_tool["candidatos"]), 0)

        # 2. Engine behavior
        engine = LocalAgentEngine()
        order = {
            "case_id": "CASO-OVERLOAD-50T",
            "peso_kg": 50000,
            "origen": "Quilicura",
            "destino": "San Bernardo",
            "hora": "10:00",
        }
        res_engine = engine.evaluate_order(order)
        self.assertEqual(res_engine["status"], "BLOQUEADO_RIESGO")
        self.assertFalse(res_engine["auto_approved"])
        assigned_trucks = res_engine.get("proposal", {}).get("camiones", [])
        self.assertEqual(assigned_trucks, [], "Confirmed: 50,000 kg overload is blocked with empty truck assignments")


class TestTimestampEdgeCases(unittest.TestCase):
    """Stress testing time window evaluations in tool 2 and restriction models."""

    def test_boundary_timestamps_santiago_centro(self):
        """
        Daytime ban applies 07:30 to 21:00 inclusive.
        07:30 -> In ban (factible: False)
        21:00 -> In ban (factible: False)
        21:01 -> Compliant night window (factible: True)
        00:00 -> Compliant night window (factible: True)
        """
        # 07:30: Ban applies
        r_0730 = verificar_factibilidad_ruta_urbana(
            "Quilicura", "Santiago Centro", 9500, "07:30", living_memory_active=True
        )
        self.assertFalse(r_0730["factible"])

        # 21:00: Ban applies
        r_2100 = verificar_factibilidad_ruta_urbana(
            "Quilicura", "Santiago Centro", 9500, "21:00", living_memory_active=True
        )
        self.assertFalse(r_2100["factible"])

        # 21:01: Ban expires -> Night window
        r_2101 = verificar_factibilidad_ruta_urbana(
            "Quilicura", "Santiago Centro", 9500, "21:01", living_memory_active=True
        )
        self.assertTrue(r_2101["factible"])
        self.assertIn("VENTANA_CONFIRMADA", r_2101["acciones_mitigacion"])

        # 00:00: Night window
        r_0000 = verificar_factibilidad_ruta_urbana(
            "Quilicura", "Santiago Centro", 9500, "00:00", living_memory_active=True
        )
        self.assertTrue(r_0000["factible"])

    def test_timestamp_single_digit_hour_ascii_bug_in_urban_restriction(self):
        """
        Adversarial test: '7:30' instead of '07:30'.
        UrbanRestriction.en_horario_restringido performs numeric minute comparison.
        Both '07:30' and '7:30' must evaluate to True (restricted).
        """
        restr = UrbanRestriction(
            id_restriccion="REST-01",
            zona_comuna="SANTIAGO_CENTRO",
            comunas_cubiertas=["Santiago"],
            nombre_ordenanza="Ordenanza 5t",
            peso_max_diurno_kg=5000.0,
            hora_inicio_restriccion="07:30",
            hora_fin_restriccion="21:00",
            ventana_permitida_pesados="21:30-06:30",
            admite_hazmat=False,
            requiere_escolta_o_permiso=False,
            accion_mitigacion_sugerida="reprogramar",
        )
        # '07:30' correctly detected
        self.assertTrue(restr.en_horario_restringido("07:30"))
        # '7:30' correctly detected with numeric minutes
        is_restricted = restr.en_horario_restringido("7:30")
        self.assertTrue(is_restricted, "Confirmed: Numeric minute comparison correctly detects '7:30' ban")

    def test_invalid_and_out_of_range_timestamp_strings(self):
        """
        Adversarial test: invalid time strings.
        '' and 'invalid' fallback to 12:00 (caught by ban).
        '25:99' parses to 1599 minutes > 1260, incorrectly passing as 'night window'!
        """
        # Invalid strings fallback to 12:00
        r_empty = verificar_factibilidad_ruta_urbana("Quilicura", "Santiago Centro", 9500, "", living_memory_active=True)
        self.assertFalse(r_empty["factible"])

        # 25:99 is not a valid 24h clock time but passes as night window
        r_2599 = verificar_factibilidad_ruta_urbana("Quilicura", "Santiago Centro", 9500, "25:99", living_memory_active=True)
        print(f"\n[EMPIRICAL VULNERABILITY] Invalid time '25:99' factible: {r_2599['factible']}")
        self.assertFalse(r_2599["factible"], "Invalid 25:99 must be rejected")


class TestCAM04BrakeFailureBypass(unittest.TestCase):
    """Stress testing safety locks and evasion attempts for CAM-04 brake failure."""

    def test_cam04_canonical_uppercase_blocked(self):
        """Canonical 'CAM-04' is strictly blocked."""
        res_tool = consultar_flota_disponible(peso_kg=4000, truck_id_preferido="CAM-04")
        self.assertEqual(res_tool["status"], "BLOQUEO_MANTENIMIENTO")
        self.assertTrue(res_tool["bloqueos_mantenimiento"][0]["bloqueado"])

        engine = LocalAgentEngine()
        res_engine = engine.evaluate_order({
            "case_id": "CASO-5-CANONICAL",
            "peso_kg": 4000,
            "origen": "Quilicura",
            "destino": "Maipú",
            "truck_id_preferido": "CAM-04",
        })
        self.assertEqual(res_engine["status"], "BLOQUEADO_RIESGO")
        self.assertFalse(res_engine["auto_approved"])

    def test_cam04_lowercase_and_whitespace_bypass_vulnerability(self):
        """
        Adversarial test: Passing 'cam-04', ' CAM-04 ', or 'Cam-04'.
        Normalized casing and whitespace checks ensure:
        - consultar_flota_disponible returns status: 'BLOQUEO_MANTENIMIENTO'.
        - LocalAgentEngine returns status: 'BLOQUEADO_RIESGO'.
        """
        evasion_attempts = ["cam-04", " CAM-04 ", "Cam-04", "cam-04\n"]
        engine = LocalAgentEngine()

        for evasive_id in evasion_attempts:
            # 1. Tool check
            r_tool = consultar_flota_disponible(peso_kg=4000, truck_id_preferido=evasive_id)
            self.assertEqual(r_tool["status"], "BLOQUEO_MANTENIMIENTO", f"Tool must block evasive ID {evasive_id!r}")
            self.assertTrue(r_tool["bloqueos_mantenimiento"][0]["bloqueado"])

            # 2. Engine check
            r_engine = engine.evaluate_order({
                "case_id": "CASO-5-EVASIVE",
                "peso_kg": 4000,
                "origen": "Quilicura",
                "destino": "Maipú",
                "truck_id_preferido": evasive_id,
            })
            self.assertEqual(r_engine["status"], "BLOQUEADO_RIESGO", f"Engine must flag BLOQUEADO_RIESGO for {evasive_id!r}")
            self.assertFalse(r_engine["auto_approved"])

    def test_cam04_requested_in_free_text_description_bypassed(self):
        """
        Adversarial test: Operator requests CAM-04 inside order description.
        Engine normalizes and scans description for CAM-04 / brake failure.
        """
        engine = LocalAgentEngine()
        order = {
            "case_id": "CASO-5-DESC",
            "peso_kg": 4000,
            "origen": "Quilicura",
            "destino": "Maipú",
            "descripcion": "Por favor asignar expresamente el camión CAM-04 para este flete urgente",
        }
        res = engine.evaluate_order(order)
        self.assertEqual(res["status"], "BLOQUEADO_RIESGO")
        self.assertFalse(res["auto_approved"])


class TestAmbiguousInputsAndPartialFields(unittest.TestCase):
    """Stress testing ambiguous orders and field validation."""

    def test_missing_fields_cleanly_flagged_in_r4r_info_incompleta(self):
        """Canonical ambiguous order stops in R4R_INFO_INCOMPLETA."""
        engine = LocalAgentEngine()
        order = {
            "case_id": "CASO-4",
            "descripcion": "Necesito mandar unos pallets urgentes al centro ahora en la tarde",
        }
        res = engine.evaluate_order(order)
        self.assertEqual(res["status"], "R4R_INFO_INCOMPLETA")
        self.assertFalse(res["auto_approved"])
        self.assertIn("peso_kg", res["proposal"]["campos_faltantes"])

    def test_non_numeric_weight_string_unhandled_crash_vulnerability(self):
        """
        Adversarial test: User submits text in peso_kg ('no se', 'desconocido').
        In evaluate_order:
        Defensive parsing catches invalid string weight, adds 'peso_kg' to missing_fields,
        and cleanly returns R4R_INFO_INCOMPLETA without crashing.
        """
        engine = LocalAgentEngine()
        order = {
            "case_id": "CASO-CRASH",
            "peso_kg": "no se",
            "origen": "Quilicura",
            "destino": "Santiago Centro",
        }
        crashed = False
        res = None
        try:
            res = engine.evaluate_order(order)
        except Exception:
            crashed = True

        self.assertFalse(crashed, "Engine must not crash on non-numeric string weight")
        self.assertIsNotNone(res)
        self.assertEqual(res["status"], "R4R_INFO_INCOMPLETA")
        self.assertIn("peso_kg", res["proposal"]["campos_faltantes"])


class TestTokenBudgetStress(unittest.TestCase):
    """Stress testing token budgets and payload pruning."""

    def test_callable_tools_always_under_150_tokens(self):
        """All 3 tools must produce compact outputs <= 150 tokens."""
        # Tool 1
        r1 = consultar_flota_disponible(peso_kg=3200, hora_despacho="14:00")
        self.assertLess(count_tokens(r1), 150)

        # Tool 2
        r2 = verificar_factibilidad_ruta_urbana("Quilicura", "Santiago Centro", 9500, "11:30", living_memory_active=True)
        self.assertLess(count_tokens(r2), 150)

        # Tool 3
        r3 = generar_propuesta_r4r(
            case_id="CASO-1",
            camiones_asignados=["CAM-02"],
            origen="Quilicura",
            destino="Pudahuel",
            fecha_hora_programada="14:00",
            tarifa_base_clp=50000,
        )
        self.assertLess(count_tokens(r3), 150)

    def test_nested_dict_token_leak_vulnerability(self):
        """
        Adversarial test: enforce_token_budget only truncates top-level strings.
        When candidates list contains dictionaries with long fields, nested strings
        are never truncated, and candidates is kept in essential_keys.
        Final token count exceeds 150 tokens (measured 279 tokens).
        """
        adversarial_payload = {
            "status": "OK",
            "motivo": "palabra " * 15,
            "propuesta_id": "prop_id",
            "candidatos": [
                {"id": "CAM-01", "desc": "palabra " * 100},
                {"id": "CAM-02", "desc": "palabra " * 100},
            ],
        }
        pruned = enforce_token_budget(adversarial_payload, max_tokens=150)
        toks = count_tokens(pruned)
        self.assertLess(toks, 150, f"Token budget strictly enforced for nested structures: {toks} < 150")
        self.assertTrue(len(pruned["candidatos"]) > 0, "Candidates preserved after pruning")


class TestHazmatSpanishAccentsBypass(unittest.TestCase):
    """Stress testing HAZMAT D.S. 298 classification with real-world Spanish accents."""

    def test_hazmat_accented_spanish_bypass_vulnerability(self):
        """
        Adversarial test: Dangerous cargo spelled with accents:
        'Ácido Sulfúrico', 'Ácido Nítrico', 'Sustancia Química'.
        Unicode NFKD diacritic normalization ensures all accented strings trigger legal block!
        """
        accented_cargos = [
            "Ácido Sulfúrico",
            "Ácido Nítrico",
            "Sustancia Química Tóxica",
            "Material Radiactivo",
            "Gas Cloro",
        ]
        engine = LocalAgentEngine()

        for cargo in accented_cargos:
            # 1. Tool check
            r_tool = verificar_factibilidad_ruta_urbana(
                origen="Quilicura",
                destino_comuna="Santiago Centro",
                peso_kg=3000,
                hora_solicitada="14:00",
                tipo_carga=cargo,
            )
            # 2. Engine check
            order = {
                "case_id": "CASO-6-ACCENT",
                "peso_kg": 3000,
                "origen": "Quilicura",
                "destino": "Santiago Centro",
                "tipo_carga": cargo,
            }
            r_engine = engine.evaluate_order(order)

            self.assertFalse(r_tool["factible"], f"Tool must block hazardous cargo {cargo!r}")
            self.assertEqual(r_engine["status"], "BLOQUEADO_RIESGO", f"Engine must block hazardous cargo {cargo!r}")
            self.assertFalse(r_engine["auto_approved"])


if __name__ == "__main__":
    unittest.main()
