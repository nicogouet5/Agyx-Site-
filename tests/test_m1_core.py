"""
tests/test_m1_core.py
Comprehensive unit test suite for Milestone 1:
- Structured data sources (CSV/JSON/SQLite)
- Zero-dependency data models & strict governance invariants
- Deterministic token optimizer (<150 tokens tools, <80 tokens memory rules)
- Callable tools (consultar_flota, verificar_ruta, generar_propuesta)
- Domain services (Fleet, Restrictions, Memory, R4R)
- Dual Engine (LocalEngine 6 cases + v1->v2 loop, GeminiEngine fallback)

Runs with pure Python standard library:
python3 -m unittest tests/test_m1_core.py
"""
import json
import os
import sqlite3
import unittest
from datetime import datetime

from app.config import (
    FLEET_JSON_PATH,
    RESTRICTIONS_JSON_PATH,
    MEMORY_JSON_PATH,
    SQLITE_DB_PATH,
    MAX_TOOL_TOKENS,
    MAX_MEMORY_RULE_TOKENS,
)
from app.models import (
    Truck,
    FleetQueryRequest,
    FleetQueryResponse,
    UrbanRestriction,
    RouteVerificationRequest,
    RouteVerificationResponse,
    DispatchOrderInput,
    ProposalR4R,
    EvaluationResult,
    ReviewActionRequest,
    ReviewActionResponse,
    InactivitySimulationRequest,
    InactivitySimulationResponse,
    LivingMemoryRule,
    FeedbackLogEntry,
    calculate_token_count,
)
from app.tools.token_optimizer import (
    count_tokens,
    enforce_token_budget,
    distill_rule,
    assert_token_budget,
)
from app.tools.callable_tools import (
    consultar_flota_disponible,
    verificar_factibilidad_ruta_urbana,
    generar_propuesta_r4r,
)
from app.services import (
    init_db,
    FleetService,
    RestrictionService,
    MemoryService,
    R4RService,
)
from app.engine import (
    LocalAgentEngine,
    GeminiAgentEngine,
    get_agent_engine,
)


class TestM1DataLayer(unittest.TestCase):
    """Test structured data sources, CSV, JSON, and SQLite schemas."""

    def test_fleet_dataset_integrity(self):
        """Verify 7 trucks, maintenance lock on CAM-04, and en-route statuses."""
        with open(FLEET_JSON_PATH, "r", encoding="utf-8") as f:
            trucks = json.load(f)
        self.assertEqual(len(trucks), 7, f"Expected 7 trucks, got {len(trucks)}")

        cam4 = next((t for t in trucks if t["id_camion"] == "CAM-04"), None)
        self.assertIsNotNone(cam4)
        self.assertTrue(cam4["mantenimiento_bloqueo"])
        self.assertEqual(cam4["estado_operativo"], "EN_MANTENIMIENTO")
        self.assertIn("frenos", cam4["mantenimiento_detalle"].lower())

        en_ruta = [t for t in trucks if t["estado_operativo"] == "EN_RUTA"]
        self.assertTrue(len(en_ruta) >= 2)
        cam6 = next(t for t in trucks if t["id_camion"] == "CAM-06")
        self.assertEqual(cam6["proxima_disponibilidad"], "2026-10-21T08:00:00")

    def test_restrictions_dataset_integrity(self):
        """Verify 4 zones, Santiago Centro daytime ban (>5t), and HAZMAT rules."""
        with open(RESTRICTIONS_JSON_PATH, "r", encoding="utf-8") as f:
            rsts = json.load(f)
        self.assertEqual(len(rsts), 4)

        stgo = next((r for r in rsts if r["zona_comuna"] == "SANTIAGO_CENTRO"), None)
        self.assertIsNotNone(stgo)
        self.assertEqual(stgo["peso_max_diurno_kg"], 5000.0)
        self.assertEqual(stgo["hora_inicio_restriccion"], "07:30")
        self.assertEqual(stgo["hora_fin_restriccion"], "21:00")

        hazm = next((r for r in rsts if r["zona_comuna"] == "ANILLO_VESPUCIO"), None)
        self.assertIsNotNone(hazm)
        self.assertFalse(hazm["admite_hazmat"])

    def test_sqlite_seeding_and_tables(self):
        """Verify SQLite agyx.db initialization and row counts."""
        init_db(SQLITE_DB_PATH)
        conn = sqlite3.connect(SQLITE_DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM flota_camiones")
        self.assertEqual(cur.fetchone()[0], 7)

        cur.execute("SELECT COUNT(*) FROM restricciones_urbanas")
        self.assertEqual(cur.fetchone()[0], 4)
        conn.close()


class TestM1DataModelsAndInvariants(unittest.TestCase):
    """Test standard library models and strict governance invariants."""

    def test_proposal_r4r_auto_approved_invariant(self):
        """Strict Invariant: ProposalR4R.auto_approved must never be True."""
        prop = ProposalR4R(propuesta_id="PROP-T1", case_id="CASO-1")
        self.assertFalse(prop.auto_approved)
        self.assertTrue(prop.requiere_firma_humana)

        # Attempting to force auto_approved=True must raise ValueError
        with self.assertRaises(ValueError):
            ProposalR4R(propuesta_id="PROP-T2", case_id="CASO-1", auto_approved=True)

    def test_review_action_rejection_reason_mandatory(self):
        """Strict Invariant: Empty or whitespace rejected_reason must be rejected with ValueError."""
        # Valid approve
        appr = ReviewActionRequest(case_id="CASO-1", action="APPROVE", supervisor_name="Carlos")
        self.assertEqual(appr.action, "APPROVE")

        # Valid reject
        rej = ReviewActionRequest(
            case_id="CASO-3", action="REJECT", supervisor_name="Carlos", rejected_reason="Ordenanza municipal >5t"
        )
        self.assertEqual(rej.action, "REJECT")
        self.assertEqual(rej.rejected_reason, "Ordenanza municipal >5t")

        # Invalid reject with empty reason
        with self.assertRaises(ValueError):
            ReviewActionRequest(case_id="CASO-3", action="REJECT", supervisor_name="Carlos", rejected_reason="")

        # Invalid reject with whitespace reason
        with self.assertRaises(ValueError):
            ReviewActionRequest(case_id="CASO-3", action="REJECT", supervisor_name="Carlos", rejected_reason="   \n\t  ")

        # Missing supervisor name
        with self.assertRaises(ValueError):
            ReviewActionRequest(case_id="CASO-3", action="APPROVE", supervisor_name="")

    def test_living_memory_rule_token_budget_enforcement(self):
        """LivingMemoryRule must reject rules exceeding 80 tokens."""
        valid_rule = "[SANTIAGO_CENTRO] >5.000kg prohibido 07:30-21:00. Solución: reprogramar 21:30 hrs o 2x camiones 5t."
        rule_obj = LivingMemoryRule(
            rule_id="RULE-1",
            source_case_id="CASO-3",
            created_at=datetime.utcnow().isoformat(),
            author="Carlos",
            raw_rejection="raw",
            distilled_rule=valid_rule,
            zone="SANTIAGO_CENTRO",
        )
        self.assertLess(rule_obj.token_count, 80)

        # Extremely long rule exceeding 80 tokens
        long_rule = " ".join(["palabra_de_prueba"] * 90)
        with self.assertRaises(ValueError):
            LivingMemoryRule(
                rule_id="RULE-2",
                source_case_id="CASO-3",
                created_at=datetime.utcnow().isoformat(),
                author="Carlos",
                raw_rejection="raw",
                distilled_rule=long_rule,
                zone="SANTIAGO_CENTRO",
            )


class TestM1TokenOptimizer(unittest.TestCase):
    """Test deterministic token counting and payload pruning."""

    def test_token_counter_accuracy(self):
        """count_tokens returns deterministic BPE approximations."""
        self.assertEqual(count_tokens(""), 0)
        self.assertEqual(count_tokens(None), 0)
        tokens = count_tokens("Agyx Logistics Copilot")
        self.assertEqual(tokens, 3)

        payload = {"status": "OK", "id": "CAM-02"}
        t_json = count_tokens(payload)
        self.assertEqual(t_json, 19)

    def test_distill_rule_known_patterns(self):
        """Rule distillation compresses Santiago Centro, Brake, and HAZMAT rejections."""
        stgo_raw = (
            "Ordenanza Santiago Centro prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs. "
            "Reprogramar a ventana nocturna (21:30/06:00) o subdividir en 2 camiones de 5t"
        )
        distilled = distill_rule(stgo_raw)
        self.assertIn("[SANTIAGO_CENTRO]", distilled)
        self.assertLess(count_tokens(distilled), 80)

        brake_raw = "No se puede usar el camión CAM-04 porque tiene falla de frenos en el taller mecánico."
        distilled_brake = distill_rule(brake_raw)
        self.assertIn("frenos", distilled_brake.lower())
        self.assertLess(count_tokens(distilled_brake), 80)

    def test_enforce_token_budget_pruning(self):
        """enforce_token_budget preserves payloads under budget and prunes if over."""
        small = {"status": "OK", "camiones": ["CAM-02"]}
        self.assertEqual(enforce_token_budget(small, max_tokens=150), small)

        # Huge verbose dictionary
        huge = {
            "status": "OK",
            "debug": "x" * 200,
            "raw_query": "y" * 200,
            "candidatos": [{"id": f"CAM-{i}", "desc": "z" * 50} for i in range(10)],
        }
        pruned = enforce_token_budget(huge, max_tokens=150)
        self.assertLessEqual(count_tokens(pruned), 150)
        self.assertNotIn("debug", pruned)


class TestM1CallableTools(unittest.TestCase):
    """Test the 3 verifiable callable tools and their token budgets."""

    def test_tool1_caso1_selection_and_tokens(self):
        """Caso 1: 3,200 kg selects Atego 5t CAM-02 under 150 tokens."""
        res = consultar_flota_disponible(peso_kg=3200, hora_despacho="14:00")
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["candidatos"][0]["id"], "CAM-02")
        assert_token_budget(res, max_tokens=MAX_TOOL_TOKENS, name="Tool1_Caso1")

    def test_tool1_caso2_busy_fleet_reservation(self):
        """Caso 2: 10,000 kg at 15:00 hrs finds next-day slot tomorrow 08:00 hrs."""
        res = consultar_flota_disponible(peso_kg=10000, hora_despacho="15:00")
        self.assertEqual(res["status"], "SIN_DISPONIBILIDAD_HOY")
        self.assertIsNotNone(res["proxima_reserva"])
        self.assertEqual(res["proxima_reserva"]["hora"], "08:00")
        assert_token_budget(res, max_tokens=MAX_TOOL_TOKENS, name="Tool1_Caso2")

    def test_tool1_caso5_brake_failure_lock(self):
        """Caso 5: CAM-04 brake failure triggers BLOQUEO_MANTENIMIENTO."""
        res = consultar_flota_disponible(peso_kg=4000, truck_id_preferido="CAM-04")
        self.assertEqual(res["status"], "BLOQUEO_MANTENIMIENTO")
        self.assertTrue(res["bloqueos_mantenimiento"][0]["bloqueado"])
        self.assertIn("frenos", res["bloqueos_mantenimiento"][0]["motivo"].lower())
        assert_token_budget(res, max_tokens=MAX_TOOL_TOKENS, name="Tool1_Caso5")

    def test_tool2_santiago_centro_v1_vs_v2(self):
        """Caso 3: Santiago Centro daytime ban v1 baseline vs v2 Living Memory."""
        # v1: baseline without living memory
        res_v1 = verificar_factibilidad_ruta_urbana(
            origen="Quilicura", destino_comuna="Santiago Centro",
            peso_kg=9500, hora_solicitada="11:30", living_memory_active=False
        )
        self.assertTrue(res_v1["factible"])
        assert_token_budget(res_v1, max_tokens=MAX_TOOL_TOKENS, name="Tool2_v1")

        # v2: post-iteration with living memory active
        res_v2 = verificar_factibilidad_ruta_urbana(
            origen="Quilicura", destino_comuna="Santiago Centro",
            peso_kg=9500, hora_solicitada="11:30", living_memory_active=True
        )
        self.assertFalse(res_v2["factible"])
        self.assertIsNotNone(res_v2["leccion_memoria_viva"])
        self.assertIn("REPROGRAMAR_NOCTURNO_2130", res_v2["acciones_mitigacion"])
        assert_token_budget(res_v2, max_tokens=MAX_TOOL_TOKENS, name="Tool2_v2")

    def test_tool2_caso6_hazmat_block(self):
        """Caso 6: Hazardous cargo triggers D.S. 298 block."""
        res = verificar_factibilidad_ruta_urbana(
            origen="Quilicura", destino_comuna="Santiago Centro",
            peso_kg=4000, hora_solicitada="14:00", tipo_carga="ACIDO_SULFURICO"
        )
        self.assertFalse(res["factible"])
        self.assertEqual(res["bloqueo_legal"], "CARGA_PELIGROSA_D_S_298")
        assert_token_budget(res, max_tokens=MAX_TOOL_TOKENS, name="Tool2_Caso6")

    def test_tool3_proposal_generation_and_persistence(self):
        """generar_propuesta_r4r creates proposal with auto_approved=False under 150 tokens."""
        res = generar_propuesta_r4r(
            case_id="CASO-PROP-TEST",
            camiones_asignados=["CAM-02"],
            origen="Quilicura",
            destino="Pudahuel",
            fecha_hora_programada="14:00",
            tarifa_base_clp=50000,
            recargo_clp=15000,
            sla_horas=2.5,
        )
        self.assertEqual(res["estado"], "R4R")
        self.assertFalse(res["auto_approved"])
        self.assertTrue(res["requiere_firma_humana"])
        self.assertEqual(res["total_clp"], 65000.0)
        assert_token_budget(res, max_tokens=MAX_TOOL_TOKENS, name="Tool3")


class TestM1ServicesLayer(unittest.TestCase):
    """Test FleetService, RestrictionService, MemoryService, and R4RService."""

    def setUp(self):
        self.mem_service = MemoryService()
        self.mem_service.reset_memory()
        self.r4r_service = R4RService(memory_service=self.mem_service)

    def test_r4r_inactivity_safeguard(self):
        """Simulated inactivity keeps proposal strictly locked in R4R; auto_approved is False."""
        prop = self.r4r_service.create_proposal(
            case_id="CASO-INACTIVITY-TEST",
            camiones_asignados=["CAM-02"],
            origen="Quilicura",
            destino="Pudahuel",
            fecha_hora_programada="14:00",
            tarifa_base_clp=65000,
        )
        self.assertEqual(prop["estado"], "R4R")

        sim = self.r4r_service.simulate_inactivity("CASO-INACTIVITY-TEST", idle_minutes=120)
        self.assertEqual(sim["status"], "R4R")
        self.assertFalse(sim["auto_approved"])

        # Fetch directly from store
        stored = self.r4r_service.get_proposal("CASO-INACTIVITY-TEST")
        self.assertEqual(stored["estado"], "R4R")
        self.assertFalse(stored["auto_approved"])

    def test_review_approval_with_signature(self):
        """Supervisor APPROVE action transitions proposal to APPROVED; auto_approved remains False."""
        self.r4r_service.create_proposal(
            case_id="CASO-APPROVE-TEST",
            camiones_asignados=["CAM-02"],
            origen="Quilicura",
            destino="Pudahuel",
            fecha_hora_programada="14:00",
            tarifa_base_clp=65000,
        )
        rev = self.r4r_service.review_proposal("CASO-APPROVE-TEST", "APPROVE", "Carlos Morales")
        self.assertTrue(rev["success"])
        self.assertEqual(rev["new_status"], "APPROVED")
        self.assertFalse(rev["auto_approved"])
        self.assertEqual(rev["supervisor_name"], "Carlos Morales")

    def test_review_rejection_distills_rule_and_activates(self):
        """Supervisor REJECT action distills rule, stores in memory, and activates it."""
        self.r4r_service.create_proposal(
            case_id="CASO-REJECT-TEST",
            camiones_asignados=["CAM-05"],
            origen="Quilicura",
            destino="Santiago Centro",
            fecha_hora_programada="11:30",
            tarifa_base_clp=120000,
        )
        reason = "Ordenanza Santiago Centro prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs. Reprogramar a ventana nocturna (21:30/06:00) o subdividir en 2 camiones de 5t"
        rev = self.r4r_service.review_proposal("CASO-REJECT-TEST", "REJECT", "Carlos Morales", rejected_reason=reason)
        self.assertTrue(rev["success"])
        self.assertEqual(rev["new_status"], "REJECTED")
        self.assertFalse(rev["auto_approved"])
        self.assertIsNotNone(rev["distilled_rule_created"])

        active_rules = self.mem_service.get_active_rules("SANTIAGO_CENTRO")
        self.assertEqual(len(active_rules), 1)
        self.assertIn("SANTIAGO_CENTRO", active_rules[0]["distilled_rule"])


class TestM1EngineLayerAnd6Cases(unittest.TestCase):
    """Test LocalAgentEngine executing all 6 cases and Case 3 v1->v2 loop."""

    def setUp(self):
        self.mem_service = MemoryService()
        self.mem_service.reset_memory()
        self.engine = LocalAgentEngine(memory_service=self.mem_service)

    def test_caso1_normal_despacho_directo(self):
        """Caso 1: 3,200 kg Quilicura -> Pudahuel at 14:00 hrs assigns CAM-02 in R4R."""
        order = {"case_id": "CASO-1", "peso_kg": 3200, "origen": "Quilicura", "destino": "Pudahuel", "hora": "14:00"}
        res = self.engine.evaluate_order(order)
        self.assertEqual(res["status"], "R4R")
        self.assertFalse(res["auto_approved"])
        self.assertEqual(res["proposal"]["camiones"], ["CAM-02"])

    def test_caso2_reserva_otro_dia(self):
        """Caso 2: 10,000 kg at 15:00 hrs when 12t fleet is busy triggers tomorrow 08:00 hrs."""
        order = {"case_id": "CASO-2", "peso_kg": 10000, "origen": "Quilicura", "destino": "San Bernardo", "hora": "15:00"}
        res = self.engine.evaluate_order(order)
        self.assertEqual(res["status"], "R4R")
        self.assertFalse(res["auto_approved"])
        self.assertIn("08:00", res["proposal"]["fecha_hora_programada"])

    def test_caso3_v1_to_v2_living_memory_iteration(self):
        """Caso 3: v1 naive run -> supervisor reject -> Living Memory distillation -> v2 pass."""
        order = {"case_id": "CASO-3", "peso_kg": 9500, "origen": "Quilicura", "destino": "Santiago Centro", "hora": "11:30"}

        # 1. v1: Naive dispatch assigns CAM-05 at daytime 11:30
        res_v1 = self.engine.evaluate_order(order, v1_mode=True)
        self.assertEqual(res_v1["status"], "R4R")
        self.assertEqual(res_v1["proposal"]["camiones"], ["CAM-05"])
        self.assertEqual(res_v1["proposal"]["fecha_hora_programada"], "11:30")

        # 2. Supervisor rejects with mandatory reason
        reason = "Ordenanza Santiago Centro prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs. Reprogramar a ventana nocturna (21:30/06:00) o subdividir en 2 camiones de 5t"
        rev = self.engine.r4r_service.review_proposal("CASO-3", "REJECT", "Carlos Morales", rejected_reason=reason)
        self.assertEqual(rev["new_status"], "REJECTED")

        # 3. v2: Living Memory active -> adapts to 21:30 hrs or 2x 5t
        res_v2 = self.engine.evaluate_order(order, v1_mode=False)
        self.assertEqual(res_v2["status"], "R4R")
        self.assertFalse(res_v2["auto_approved"])
        self.assertTrue(
            "21:30" in res_v2["proposal"]["fecha_hora_programada"] or
            "Memoria Viva" in res_v2["proposal"]["observaciones"]
        )

    def test_caso4_informacion_incompleta(self):
        """Caso 4: Ambiguous / incomplete order sets R4R_INFO_INCOMPLETA and requests fields."""
        order = {"case_id": "CASO-4", "descripcion": "Necesito mandar unos pallets urgentes al centro ahora en la tarde"}
        res = self.engine.evaluate_order(order)
        self.assertEqual(res["status"], "R4R_INFO_INCOMPLETA")
        self.assertFalse(res["auto_approved"])
        self.assertTrue(len(res["proposal"]["campos_faltantes"]) >= 1)

    def test_caso5_riesgo_camion_falla_frenos(self):
        """Caso 5: Attempting to assign CAM-04 sets BLOQUEADO_RIESGO."""
        order = {"case_id": "CASO-5", "peso_kg": 4000, "origen": "Quilicura", "destino": "Maipú", "truck_id_preferido": "CAM-04"}
        res = self.engine.evaluate_order(order)
        self.assertEqual(res["status"], "BLOQUEADO_RIESGO")
        self.assertFalse(res["auto_approved"])
        self.assertIn("frenos", res["proposal"]["observaciones"].lower())

    def test_caso6_riesgo_carga_peligrosa_hazmat(self):
        """Caso 6: Chemical HAZMAT cargo sets BLOQUEADO_RIESGO under D.S. 298."""
        order = {"case_id": "CASO-6", "peso_kg": 4000, "origen": "Quilicura", "destino": "Santiago Centro", "tipo_carga": "ACIDO_SULFURICO"}
        res = self.engine.evaluate_order(order)
        self.assertEqual(res["status"], "BLOQUEADO_RIESGO")
        self.assertFalse(res["auto_approved"])
        self.assertIn("298", res["proposal"]["observaciones"])

    def test_gemini_engine_fallback_and_pack_export(self):
        """GeminiAgentEngine falls back gracefully to LocalAgentEngine when offline."""
        gem_engine = GeminiAgentEngine(memory_service=self.mem_service)
        res = gem_engine.evaluate_order({
            "case_id": "CASO-GEMINI", "peso_kg": 3200, "origen": "Quilicura", "destino": "Pudahuel", "hora": "14:00"
        })
        self.assertEqual(res["status"], "R4R")
        self.assertIn("local_deterministic_fallback", res.get("engine_used", ""))

        pack = GeminiAgentEngine.export_google_ai_studio_pack()
        self.assertIn("system_instruction", pack)
        self.assertIn("tool_declarations", pack)
        self.assertEqual(len(pack["tool_declarations"]), 3)


if __name__ == "__main__":
    unittest.main()
