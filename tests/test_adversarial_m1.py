"""
tests/test_adversarial_m1.py
Adversarial Stress-Testing Harness for Milestone 1 Living Memory and Governance Mechanics.
Executed by M1 Challenger 2.

Covers:
1. Living Memory Distillation Budget (500+ character raw rejections, dense token symbols, <80 tokens).
2. v1 -> v2 Iteration Loop (rapid sequential rejections, duplicate rules, memory reset, re-activation).
3. Zero Auto-Approval Invariant (15+ inactivity cycles, immutability, tamper resistance).
4. Mandatory Non-Empty Rejection Reason (empty, whitespace, tabs, newlines, null).
"""
import unittest
import os
import shutil
import tempfile
import time
import sqlite3
from typing import List, Dict, Any

from app.models.review import ReviewActionRequest, ReviewActionResponse
from app.models.dispatch import ProposalR4R, EvaluationResult
from app.models.memory import LivingMemoryRule
from app.models.restrictions import UrbanRestriction
from app.tools.token_optimizer import distill_rule, count_tokens, assert_token_budget, enforce_token_budget
from app.tools.callable_tools import consultar_flota_disponible, verificar_factibilidad_ruta_urbana
from app.services.db_service import init_db
from app.services.memory_service import MemoryService
from app.services.r4r_service import R4RService
from app.engine.local_engine import LocalAgentEngine


class TestLivingMemoryDistillationBudget(unittest.TestCase):
    """Stress tests for Living Memory distillation and token budget enforcement."""

    def test_distillation_budget_realistic_long_rejection(self):
        """Verify that a 500+ character realistic supervisor rejection is distilled to strictly < 80 tokens."""
        raw_500 = (
            "Estimados despachadores y coordinadores de flota: Les informo formalmente que se rechaza la propuesta "
            "para la comuna de Renca debido a que el cliente Wal-Mart exige que todos los camiones que ingresen al Centro "
            "de Distribución El Peñón cuenten con cortina metálica y chofer con certificación de trabajo en altura. "
            "Adicionalmente, no se permiten entregas después de las 16:30 horas los días viernes debido a saturación de "
            "andenes de recepción y cambio de turno del personal de bodega. Favor reprogramar para el día lunes temprano."
        )
        self.assertGreater(len(raw_500), 500)
        distilled = distill_rule(raw_500)
        tokens = count_tokens(distilled)
        self.assertLess(tokens, 80, f"Distilled rule exceeded 80 tokens budget: {tokens} tokens")
        self.assertIn("[REGLA_OPERACIONAL]", distilled)

    def test_distillation_budget_santiago_centro_long_rejection(self):
        """Verify 500+ character Santiago Centro municipal ban rejection distills to < 80 tokens."""
        raw_centro_600 = (
            "Ordenanza Santiago Centro prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs. "
            "Por disposición expresa de la Dirección de Tránsito de la Ilustre Municipalidad "
            "de Santiago, ordenanza N° 45 sobre control de emisiones y congestión vial, se prohíbe terminantemente la "
            "circulación de camiones de carga pesada cuyo peso bruto vehicular o tara de carga supere los 5.000 kg dentro "
            "del perímetro céntrico comprendido por Avenida Bernardo O'Higgins, Vicuña Mackenna, Mapocho y Matucana "
            "en el horario diurno de 07:30 a 21:00 horas. Para dar curso al despacho se debe coordinar ingreso nocturno "
            "a partir de las 21:30 hrs o fraccionar la carga en vehículos livianos tipo Atego 5t."
        )
        self.assertGreater(len(raw_centro_600), 500)
        distilled = distill_rule(raw_centro_600)
        tokens = count_tokens(distilled)
        self.assertLess(tokens, 80, f"Distilled rule exceeded 80 tokens: {tokens}")
        self.assertIn("SANTIAGO_CENTRO", distilled)
        self.assertIn("5.000kg", distilled)

    def test_distillation_budget_1000_char_rambling_text(self):
        """Stress-test distillation against a 1000+ character rambling human supervisor explanation."""
        rambling_1000 = (
            "Atención equipo de despacho: Esta propuesta debe ser completamente desestimada y rechazada. "
            "El motivo es que el cliente nos acaba de notificar telefónicamente que las condiciones del muelle "
            "de descarga en San Bernardo no son aptas para ramplas ni camiones articulados de más de 8 toneladas. "
            + ("Adicionalmente existen faenas viales en el acceso lateral por Camino Lonquén que impiden maniobras. " * 8)
            + "Favor coordinar con el cliente una entrega diferida en camión mediano con plataforma elevadora."
        )
        self.assertGreater(len(rambling_1000), 1000)
        distilled = distill_rule(rambling_1000)
        tokens = count_tokens(distilled)
        self.assertLess(tokens, 80, f"Distilled rule exceeded 80 tokens: {tokens}")

    def test_distillation_budget_adversarial_dense_symbols(self):
        """
        Adversarial stress-test: A 500+ character rejection filled with dense punctuation and symbols.
        Evaluates whether the distillation handles unbroken symbol sequences under the 80 token budget.
        """
        adversarial_symbols = "!@#$%^&*()_+=[]{}|;:,.<>?" * 25  # 650 characters of dense symbols
        self.assertGreater(len(adversarial_symbols), 500)
        distilled = distill_rule(adversarial_symbols)
        tokens = count_tokens(distilled)
        
        # Empirical finding: When input is unspaced punctuation, character truncation to 137
        # yields 146 tokens because each symbol is a token and words.split() cannot split unspaced text.
        print(f"\n[EMPIRICAL VULNERABILITY] Dense symbols raw length={len(adversarial_symbols)}, distilled tokens={tokens}")
        # We record whether the token budget held or overflowed
        is_budget_compliant = (tokens < 80)
        self.assertTrue(is_budget_compliant, f"Dense symbols must strictly comply with < 80 tokens budget: {tokens}")


class TestV1V2IterationLoop(unittest.TestCase):
    """Stress tests for the v1 -> v2 Living Memory feedback loop, duplicate rules, and reset."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_db = os.path.join(self.temp_dir, "test_agyx.db")
        self.temp_json = os.path.join(self.temp_dir, "test_mem.json")
        init_db(self.temp_db)
        self.memory_service = MemoryService(storage_path=self.temp_json, db_path=self.temp_db)
        self.r4r_service = R4RService(memory_service=self.memory_service, db_path=self.temp_db, storage_path=self.temp_json)
        self.engine = LocalAgentEngine(memory_service=self.memory_service, r4r_service=self.r4r_service)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_v1_to_v2_lifecycle_and_reactivation(self):
        """
        End-to-end iteration loop:
        1. Evaluate Case 3 in v1 -> assigns CAM-05 at 11:30 hrs.
        2. Supervisor rejects with mandatory reason -> saved to Living Memory.
        3. Evaluate Case 3 in v2 -> night window 21:30 hrs proposed.
        4. Reset memory -> clears active rules.
        5. Explicit v1 replay remains naive; safe v2 never regresses after memory reset.
        6. Re-reject -> re-activates rule -> v2 compliant proposal.
        """
        order_caso3 = {
            "case_id": "CASO-3-LIFECYCLE",
            "peso_kg": 9500,
            "origen": "Quilicura",
            "destino": "Santiago Centro",
            "hora": "11:30",
        }

        # Step 1: v1 naive baseline
        v1_res = self.engine.evaluate_order(order_caso3, v1_mode=True)
        self.assertEqual(v1_res["status"], "R4R")
        self.assertEqual(v1_res["proposal"]["camiones"], ["CAM-05"])
        self.assertIn("11:30", v1_res["proposal"]["fecha_hora_programada"])

        # Step 2: Supervisor human rejection
        rejection_res = self.r4r_service.review_proposal(
            case_id="CASO-3-LIFECYCLE",
            action="REJECT",
            supervisor_name="Carlos Morales",
            rejected_reason="Ordenanza Santiago Centro prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs. Reprogramar a ventana nocturna 21:30 hrs.",
        )
        self.assertEqual(rejection_res["new_status"], "REJECTED")
        self.assertFalse(rejection_res["auto_approved"])

        # Step 3: v2 compliant post-iteration
        v2_res = self.engine.evaluate_order(order_caso3, v1_mode=False)
        self.assertEqual(v2_res["status"], "R4R")
        self.assertIn("21:30", v2_res["proposal"]["fecha_hora_programada"])
        self.assertIn("Memoria Viva", v2_res["proposal"]["observaciones"])

        # Step 4: Memory reset
        self.memory_service.reset_memory()
        active_after_reset = self.memory_service.get_active_rules("SANTIAGO_CENTRO")
        self.assertEqual(len(active_after_reset), 0)

        # Step 5: Only an explicit historical v1 replay is naive after reset.
        safe_after_reset = self.engine.evaluate_order(order_caso3, v1_mode=False)
        self.assertIn("21:30", safe_after_reset["proposal"]["fecha_hora_programada"])
        v1_again = self.engine.evaluate_order(order_caso3, v1_mode=True)
        self.assertEqual(v1_again["proposal"]["camiones"], ["CAM-05"])
        self.assertIn("11:30", v1_again["proposal"]["fecha_hora_programada"])

        # Step 6: Re-activation after reset
        # Sub-second collision resistance allows immediate save
        self.r4r_service.review_proposal(
            case_id="CASO-3-LIFECYCLE",
            action="REJECT",
            supervisor_name="Carlos Morales",
            rejected_reason="Re-activación: Ordenanza Santiago Centro >5.000 kg horario diurno prohibido.",
        )
        v2_reactivated = self.engine.evaluate_order(order_caso3, v1_mode=False)
        self.assertIn("21:30", v2_reactivated["proposal"]["fecha_hora_programada"])

    def test_rapid_sequential_rejections_primary_key_collision(self):
        """
        Adversarial stress-test: Multiple sequential rejections executed within the same second.
        Tests if timestamp-based ID generation handles rapid sequential rejections without collision.
        """
        r1 = self.memory_service.save_feedback(
            case_id="CASO-SEQ-1",
            action="REJECT",
            supervisor_name="Sup A",
            rejected_reason="Rechazo 1 por ordenanza Santiago Centro > 5000 kg",
        )
        r2 = self.memory_service.save_feedback(
            case_id="CASO-SEQ-2",
            action="REJECT",
            supervisor_name="Sup B",
            rejected_reason="Rechazo 2 por ordenanza Santiago Centro > 5000 kg",
        )
        self.assertIsNotNone(r1["rule_id"])
        self.assertIsNotNone(r2["rule_id"])
        self.assertNotEqual(r1["rule_id"], r2["rule_id"], "Rule IDs must be unique even in same second")
        self.assertNotEqual(r1["entry_id"], r2["entry_id"], "Entry IDs must be unique even in same second")

    def test_duplicate_rules_accumulation_and_prompt_injection(self):
        """
        Test behavior when duplicate rules are added to living memory.
        Checks if active rules and prompt injection handle duplicate rules gracefully.
        """
        for i in range(2):
            self.memory_service.save_feedback(
                case_id=f"CASO-DUP-{i}",
                action="REJECT",
                supervisor_name="Carlos Morales",
                rejected_reason="Ordenanza Santiago Centro prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs.",
            )

        rules_raw = self.memory_service.get_active_rules("SANTIAGO_CENTRO", deduplicate=False)
        self.assertGreaterEqual(len(rules_raw), 2)
        rules_deduped = self.memory_service.get_active_rules("SANTIAGO_CENTRO", deduplicate=True)
        self.assertEqual(len(rules_deduped), 1)
        injection = self.memory_service.format_prompt_injection("SANTIAGO_CENTRO")
        tokens = count_tokens(injection)
        # Verify injection token count remains within tool/memory limits
        self.assertLess(tokens, 80, f"Prompt injection token budget exceeded due to duplicate rules: {tokens}")


class TestZeroAutoApprovalInvariant(unittest.TestCase):
    """Stress tests for the Zero Auto-Approval Invariant across repeated inactivity and polling cycles."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_db = os.path.join(self.temp_dir, "test_agyx.db")
        self.temp_json = os.path.join(self.temp_dir, "test_mem.json")
        init_db(self.temp_db)
        self.r4r_service = R4RService(db_path=self.temp_db, storage_path=self.temp_json)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_15_inactivity_and_polling_cycles(self):
        """
        Simulate 15 consecutive inactivity and polling cycles with increasing idle times
        (from 15 minutes to 7 days). Asserts auto_approved is ALWAYS False and status never changes.
        """
        prop = self.r4r_service.create_proposal(
            case_id="CASO-INACTIVITY-STRESS",
            camiones_asignados=["CAM-02"],
            origen="Quilicura",
            destino="Pudahuel",
            fecha_hora_programada="14:00",
            tarifa_base_clp=50000.0,
            recargo_clp=15000.0,
            sla_horas=2.5,
        )
        self.assertEqual(prop["estado"], "R4R")
        self.assertFalse(prop["auto_approved"])

        idle_durations = [15, 30, 45, 60, 90, 120, 240, 480, 720, 1440, 2880, 4320, 5760, 7200, 10080]
        self.assertEqual(len(idle_durations), 15)

        for cycle_idx, idle_mins in enumerate(idle_durations):
            # 1. Simulate inactivity
            inact_resp = self.r4r_service.simulate_inactivity("CASO-INACTIVITY-STRESS", idle_minutes=idle_mins)
            self.assertFalse(inact_resp["auto_approved"], f"Cycle {cycle_idx}: auto_approved became True in response!")
            self.assertEqual(inact_resp["status"], "R4R", f"Cycle {cycle_idx}: status mutated to {inact_resp['status']}")

            # 2. Poll proposal state directly from storage
            queried = self.r4r_service.get_proposal("CASO-INACTIVITY-STRESS")
            self.assertIsNotNone(queried)
            self.assertFalse(queried["auto_approved"], f"Cycle {cycle_idx}: database auto_approved became True!")
            self.assertEqual(queried["estado"], "R4R", f"Cycle {cycle_idx}: database status changed to {queried['estado']}!")
            self.assertIsNone(queried["human_signature"], f"Cycle {cycle_idx}: signature was unexpectedly set!")
            self.assertIsNone(queried["review_timestamp"], f"Cycle {cycle_idx}: review timestamp was set!")

    def test_direct_tampering_attempts_rejected(self):
        """Attempting to construct proposals or review responses with auto_approved=True raises ValueError."""
        # 1. ProposalR4R model
        with self.assertRaises(ValueError):
            ProposalR4R(
                propuesta_id="PROP-TAMPER",
                case_id="CASO-TAMPER",
                camiones_asignados=["CAM-01"],
                auto_approved=True,  # Tamper attempt
            )

        # 2. ReviewActionResponse model
        with self.assertRaises(ValueError):
            ReviewActionResponse(
                success=True,
                case_id="CASO-TAMPER",
                previous_status="R4R",
                new_status="APPROVED",
                auto_approved=True,  # Tamper attempt
            )

        # 3. EvaluationResult model
        with self.assertRaises(ValueError):
            EvaluationResult(
                case_id="CASO-TAMPER",
                status="R4R",
                auto_approved=True,  # Tamper attempt
            )

    def test_cannot_approve_without_supervisor_signature(self):
        """Approving a proposal without a supervisor_name raises validation error."""
        self.r4r_service.create_proposal(
            case_id="CASO-NO-SIG",
            camiones_asignados=["CAM-01"],
            origen="Quilicura",
            destino="Pudahuel",
            fecha_hora_programada="14:00",
            tarifa_base_clp=50000.0,
        )

        # Attempt review approval with empty supervisor_name
        for empty_sig in ["", "   ", None]:
            with self.assertRaises(ValueError):
                self.r4r_service.review_proposal(
                    case_id="CASO-NO-SIG",
                    action="APPROVE",
                    supervisor_name=empty_sig,
                )

        # Confirm case is still in R4R
        prop = self.r4r_service.get_proposal("CASO-NO-SIG")
        self.assertEqual(prop["estado"], "R4R")
        self.assertFalse(prop["auto_approved"])


class TestMandatoryRejectionReasonValidation(unittest.TestCase):
    """Stress tests for mandatory non-empty rejected_reason validation across all layers."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_db = os.path.join(self.temp_dir, "test_agyx.db")
        self.temp_json = os.path.join(self.temp_dir, "test_mem.json")
        init_db(self.temp_db)
        self.r4r_service = R4RService(db_path=self.temp_db, storage_path=self.temp_json)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_all_empty_and_whitespace_variants_rejected(self):
        """
        Test that empty strings, spaces only, tabs, newlines, and null values
        all raise a ValueError across ReviewActionRequest, review_proposal, and save_feedback.
        """
        self.r4r_service.create_proposal(
            case_id="CASO-REJECT-STRESS",
            camiones_asignados=["CAM-02"],
            origen="Quilicura",
            destino="Santiago Centro",
            fecha_hora_programada="11:30",
            tarifa_base_clp=60000.0,
        )

        invalid_reasons = [
            "",
            " ",
            "   ",
            "\t",
            "\t\t\t",
            "\n",
            "\r\n",
            "  \t \n \r  ",
            None,
        ]

        for invalid_val in invalid_reasons:
            # 1. Model layer validation
            with self.assertRaises(ValueError, msg=f"ReviewActionRequest allowed {invalid_val!r}"):
                ReviewActionRequest(
                    case_id="CASO-REJECT-STRESS",
                    action="REJECT",
                    supervisor_name="Carlos Morales",
                    rejected_reason=invalid_val,
                )

            # 2. Service layer validation
            with self.assertRaises(ValueError, msg=f"review_proposal allowed {invalid_val!r}"):
                self.r4r_service.review_proposal(
                    case_id="CASO-REJECT-STRESS",
                    action="REJECT",
                    supervisor_name="Carlos Morales",
                    rejected_reason=invalid_val,
                )

            # 3. Direct memory service validation
            with self.assertRaises(ValueError, msg=f"save_feedback allowed {invalid_val!r}"):
                self.r4r_service.memory_service.save_feedback(
                    case_id="CASO-REJECT-STRESS",
                    action="REJECT",
                    supervisor_name="Carlos Morales",
                    rejected_reason=invalid_val,
                )

        # Invariant check: Case must remain untouched in R4R
        prop = self.r4r_service.get_proposal("CASO-REJECT-STRESS")
        self.assertEqual(prop["estado"], "R4R")
        self.assertFalse(prop["auto_approved"])
        self.assertIsNone(prop["rejected_reason"])


class TestIteration2Remediation(unittest.TestCase):
    """
    Dedicated test suite validating all 11 fixes specified in M1 Iteration 2:
    Fix 1: Catastrophic 50t overload guard (local_engine.py).
    Fix 2: CAM-04 casing/whitespace/description normalization (callable_tools.py & local_engine.py).
    Fix 3: Spanish accent normalization for HAZMAT (callable_tools.py & local_engine.py).
    Fix 4: Defensive string weight parsing (local_engine.py).
    Fix 5: Token budget recursive pruning (token_optimizer.py).
    Fix 6: Dense unbroken symbol distillation (token_optimizer.py & memory_service.py).
    Fix 7: Sub-second primary key collision (memory_service.py).
    Fix 8: Self-initialization of r4r_proposals (r4r_service.py).
    Fix 9: Active rules deduplication (memory_service.py).
    Fix 10: Single-digit hour time comparison (restrictions.py).
    Fix 11: Off-peak night window orders preservation (local_engine.py).
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_db = os.path.join(self.temp_dir, "test_iter2.db")
        self.temp_json = os.path.join(self.temp_dir, "test_iter2.json")
        init_db(self.temp_db)
        self.memory_service = MemoryService(storage_path=self.temp_json, db_path=self.temp_db)
        self.r4r_service = R4RService(memory_service=self.memory_service, db_path=self.temp_db, storage_path=self.temp_json)
        self.engine = LocalAgentEngine(memory_service=self.memory_service, r4r_service=self.r4r_service)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_fix1_catastrophic_overload_guard(self):
        """Fix 1: Overload >15t blocked with BLOQUEADO_RIESGO and empty trucks."""
        res = self.engine.evaluate_order({
            "case_id": "TEST-F1",
            "peso_kg": 50000,
            "origen": "Quilicura",
            "destino": "San Bernardo",
            "hora": "10:00",
        })
        self.assertEqual(res["status"], "BLOQUEADO_RIESGO")
        self.assertFalse(res["auto_approved"])
        self.assertEqual(res["proposal"]["camiones"], [])
        self.assertIn("sobrepeso crítico", res["proposal"]["observaciones"].lower())

        tool_res = consultar_flota_disponible(peso_kg=50000)
        self.assertEqual(tool_res["status"], "EXCEDE_CAPACIDAD_FLOTA")
        self.assertEqual(tool_res["candidatos"], [])

    def test_fix2_cam04_casing_whitespace_description(self):
        """Fix 2: Normalized detection of CAM-04 across IDs and descriptions."""
        for evasive_truck in ["cam-04", " CAM-04 ", "Cam-04\t", "CAM04", "CAM 04"]:
            res_t = consultar_flota_disponible(peso_kg=4000, truck_id_preferido=evasive_truck)
            self.assertEqual(res_t["status"], "BLOQUEO_MANTENIMIENTO", f"Tool missed {evasive_truck!r}")

            res_e = self.engine.evaluate_order({
                "case_id": "TEST-F2",
                "peso_kg": 4000,
                "origen": "Quilicura",
                "destino": "Maipú",
                "hora": "10:00",
                "truck_id_preferido": evasive_truck,
            })
            self.assertEqual(res_e["status"], "BLOQUEADO_RIESGO", f"Engine missed {evasive_truck!r}")

        # Description detection
        res_desc = self.engine.evaluate_order({
            "case_id": "TEST-F2-DESC",
            "peso_kg": 4000,
            "origen": "Quilicura",
            "destino": "Maipú",
            "hora": "10:00",
            "descripcion": "Asignar por favor camión CAM-04 que está en taller",
        })
        self.assertEqual(res_desc["status"], "BLOQUEADO_RIESGO")

    def test_fix3_spanish_accent_hazmat(self):
        """Fix 3: Spanish accented HAZMAT and D.S. 298 / IMO keywords blocked."""
        hazmat_samples = [
            "Ácido Sulfúrico", "Ácido Nítrico", "Sustancia Química Tóxica",
            "Material Radiactivo", "Gas Cloro", "Carga IMO Peligrosa", "Regulado por D.S. 298"
        ]
        for cargo in hazmat_samples:
            tool_res = verificar_factibilidad_ruta_urbana(
                "Quilicura", "Santiago Centro", 3000, "14:00", tipo_carga=cargo
            )
            self.assertFalse(tool_res["factible"], f"Tool allowed {cargo}")
            self.assertEqual(tool_res["bloqueo_legal"], "CARGA_PELIGROSA_D_S_298")

            eng_res = self.engine.evaluate_order({
                "case_id": "TEST-F3",
                "peso_kg": 3000,
                "origen": "Quilicura",
                "destino": "San Bernardo",
                "hora": "10:00",
                "tipo_carga": cargo,
            })
            self.assertEqual(eng_res["status"], "BLOQUEADO_RIESGO", f"Engine allowed {cargo}")
            self.assertEqual(eng_res["proposal"]["bloqueo_legal"], "CARGA_PELIGROSA_NO_AUTORIZADA")

    def test_fix4_defensive_string_weight_parsing(self):
        """Fix 4: Ambiguous string weights parsed defensively -> R4R_INFO_INCOMPLETA."""
        for invalid_weight in ["no se", "desconocido", "unos pallets", "", None, -100]:
            res = self.engine.evaluate_order({
                "case_id": "TEST-F4",
                "peso_kg": invalid_weight,
                "origen": "Quilicura",
                "destino": "Santiago Centro",
            })
            self.assertEqual(res["status"], "R4R_INFO_INCOMPLETA", f"Failed for {invalid_weight!r}")
            self.assertIn("peso_kg", res["proposal"]["campos_faltantes"])

    def test_fix5_token_budget_recursive_pruning(self):
        """Fix 5: Recursive pruning ensures nested structures are strictly < 150 tokens."""
        heavy_payload = {
            "status": "OK",
            "motivo": "detallado " * 20,
            "propuesta_id": "PROP-NESTED-TEST",
            "candidatos": [
                {"id": "CAM-01", "desc": "cadena larga " * 80, "sub": {"anidado": "x" * 200}},
                {"id": "CAM-02", "desc": "cadena larga " * 80, "sub": {"anidado": "y" * 200}},
            ],
            "metadata": {"debug_trace": "z" * 500},
        }
        pruned = enforce_token_budget(heavy_payload, max_tokens=150)
        tokens = count_tokens(pruned)
        self.assertLess(tokens, 150, f"Token budget exceeded: {tokens} >= 150")
        self.assertIn("status", pruned)

    def test_fix6_dense_unbroken_symbols_distillation(self):
        """Fix 6: Dense unspaced symbols iteratively trimmed to strictly < 80 tokens."""
        symbols = "!@#$%^&*()_+=[]{}|;:,.<>?" * 30  # 780 unbroken symbols
        rule = distill_rule(symbols, max_tokens=80)
        tokens = count_tokens(rule)
        self.assertLess(tokens, 80, f"Distilled symbols exceeded 80 tokens: {tokens}")
        self.assertTrue(rule.startswith("[REGLA_OPERACIONAL]"))

    def test_fix7_sub_second_primary_key_collision(self):
        """Fix 7: Sub-second microsecond + UUID generates distinct rule_id and entry_id."""
        r1 = self.memory_service.save_feedback("C1", "REJECT", "Supervisor A", "Rechazo primera ordenanza")
        r2 = self.memory_service.save_feedback("C2", "REJECT", "Supervisor B", "Rechazo segunda ordenanza")
        self.assertNotEqual(r1["rule_id"], r2["rule_id"])
        self.assertNotEqual(r1["entry_id"], r2["entry_id"])

    def test_fix8_r4r_service_self_initialization(self):
        """Fix 8: R4RService autonomously self-initializes r4r_proposals table."""
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "standalone.db")
            json_path = os.path.join(td, "standalone.json")
            service = R4RService(db_path=db_path, storage_path=json_path)
            queue = service.get_queue()
            self.assertIsInstance(queue, list)

    def test_fix9_active_rules_deduplication(self):
        """Fix 9: get_active_rules deduplicates repeated rejection rules."""
        for i in range(3):
            self.memory_service.save_feedback(
                f"C-DEDUP-{i}", "REJECT", "Carlos",
                "Ordenanza Santiago Centro prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs."
            )
        deduped = self.memory_service.get_active_rules("SANTIAGO_CENTRO", deduplicate=True)
        raw = self.memory_service.get_active_rules("SANTIAGO_CENTRO", deduplicate=False)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(len(raw), 3)

    def test_fix10_single_digit_hour_comparison(self):
        """Fix 10: Single-digit hour strings correctly converted to numeric minutes."""
        restr = UrbanRestriction(
            id_restriccion="R10", zona_comuna="SANTIAGO_CENTRO", comunas_cubiertas=["Santiago"],
            nombre_ordenanza="Ordenanza 5t", peso_max_diurno_kg=5000.0,
            hora_inicio_restriccion="07:30", hora_fin_restriccion="21:00",
            ventana_permitida_pesados="21:30-06:30", admite_hazmat=False,
            requiere_escolta_o_permiso=False, accion_mitigacion_sugerida="reprogramar"
        )
        self.assertTrue(restr.en_horario_restringido("7:30"))
        self.assertTrue(restr.en_horario_restringido("07:30"))
        self.assertTrue(restr.en_horario_restringido("12:00"))
        self.assertTrue(restr.en_horario_restringido("21:00"))
        self.assertFalse(restr.en_horario_restringido("21:01"))
        self.assertFalse(restr.en_horario_restringido("23:00"))
        self.assertFalse(restr.en_horario_restringido("6:30"))

    def test_fix11_off_peak_night_window_preservation(self):
        """Fix 11: Orders placed in legal night window (23:00) preserved without forcing 21:30."""
        # Active memory is present
        self.memory_service.save_feedback(
            "C3", "REJECT", "Carlos Morales",
            "Ordenanza Santiago Centro prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs."
        )
        # Daytime 11:30 adapts to 21:30
        res_day = self.engine.evaluate_order({
            "case_id": "TEST-DAY",
            "peso_kg": 9500,
            "origen": "Quilicura",
            "destino": "Santiago Centro",
            "hora": "11:30"
        }, v1_mode=False)
        self.assertIn("21:30", res_day["proposal"]["fecha_hora_programada"])

        # Night window 23:00 preserves 23:00
        res_night = self.engine.evaluate_order({
            "case_id": "TEST-NIGHT",
            "peso_kg": 9500,
            "origen": "Quilicura",
            "destino": "Santiago Centro",
            "hora": "23:00"
        }, v1_mode=False)
        self.assertIn("23:00", res_night["proposal"]["fecha_hora_programada"])
        self.assertIn("Ventana Nocturna Confirmada", res_night["proposal"]["fecha_hora_programada"])


if __name__ == "__main__":
    unittest.main()
