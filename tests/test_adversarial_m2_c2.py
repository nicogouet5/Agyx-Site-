"""
tests/test_adversarial_m2_c2.py
Adversarial Stress-Testing Suite for Milestone 2:
Inactivity Safeguard, State Machine Consistency, Web/PWA Assets, and Case 3 Iteration Loop.
Executed by M2 Challenger 2 (Empirical Challenger).

Sections:
1. TestInactivitySafeguardAdversarial:
   - Repeated sequential cycles (60+ calls to POST /api/r4r/simulate-inactivity).
   - Invariant: auto_approved is unconditionally False, status remains R4R.
   - Massive elapsed times (10k, 100k, 1M minutes, 0 min, negative -1, -60, -99k min).
   - Inactivity across non-R4R statuses (R4R_INFO_INCOMPLETA, BLOQUEADO_RIESGO, APPROVED, REJECTED).
   - Relational database level invariant: SQLite CHECK (auto_approved = 0) constraint.
   - Vulnerability exposure: uncaught TypeError/ValueError when idle_minutes is None or non-numeric.

2. TestStateConsistencyAndIdempotency:
   - Queue listings idempotency (100 consecutive calls).
   - Proposal lookup consistency, casing (CASO-1, caso-1, CaSo-1, whitespace), and proposal_id vs case_id.
   - Review state machine transitions: rejection without reason (HTTP 422), rejection with whitespace (HTTP 422),
     valid rejection with distilled rule, approval with digital signature.

3. TestStaticAssetsAndPWAServing:
   - Physical existence and content integrity of index.html, app.css, app.js, manifest.json, sw.js, and 4 SVG icons.
   - Route serving via InProcessApiClient and MIME type verification.
   - Security challenge: directory traversal behavior in fallback static handler.

4. TestCase3IterationLoopDemoEndpoints:
   - Full Case 3 v1 -> v2 iteration cycle through demo runner endpoints.
   - Invariant: auto_approved == False on every step.
   - Rejection validation and distilled rule (<80 tokens) integration in v2.
   - POST /api/demo/run-all consolidated execution.
   - Observation: key mismatch in run_all_cases_controller ('camiones' vs 'camiones_asignados').
"""
import unittest
import json
import os
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

from app.config import APP_DIR, BASE_DIR, DATA_DIR, SQLITE_DB_PATH, MEMORY_JSON_PATH
from app.api.dependencies import ServiceContainer
from app.api.routes_dispatch import evaluate_dispatch_controller
from app.api.routes_r4r import (
    get_queue_controller,
    get_proposal_controller,
    review_proposal_controller,
    simulate_inactivity_controller,
)
from app.api.routes_demo import (
    get_demo_cases_controller,
    run_case_controller,
    run_all_cases_controller,
)
from app.api.routes_memory import reset_memory_controller
from tests.test_api_web import InProcessApiClient


class TestInactivitySafeguardAdversarial(unittest.TestCase):
    """Stress tests on the zero auto-approval inactivity safeguard."""

    @classmethod
    def setUpClass(cls):
        cls.services = ServiceContainer.get_instance()
        # Ensure CASO-1 exists in R4R
        evaluate_dispatch_controller({
            "case_id": "CASO-1",
            "origen": "Quilicura",
            "destino": "Pudahuel",
            "cargo_weight_kg": 3200,
            "hora_despacho": "14:00",
        }, services=cls.services)

    def test_repeated_sequential_inactivity_cycles_60(self):
        """
        Adversarially challenge: 60 sequential cycles of inactivity simulation.
        Assert that after every single cycle:
        - auto_approved is strictly False
        - status in response is 'R4R'
        - status in database remains 'R4R'
        - auto_approved in database remains 0
        """
        for cycle in range(1, 61):
            idle = cycle * 15
            code, res = simulate_inactivity_controller({
                "case_id": "CASO-1",
                "idle_minutes": idle,
            }, services=self.services)

            self.assertEqual(code, 200, f"Cycle {cycle} failed with code {code}")
            self.assertFalse(res["auto_approved"], f"Cycle {cycle}: auto_approved became True!")
            self.assertEqual(res["status"], "R4R", f"Cycle {cycle}: status transitioned out of R4R")

            # Check database persistence
            p_code, prop = get_proposal_controller("CASO-1", services=self.services)
            self.assertEqual(p_code, 200)
            self.assertFalse(prop["auto_approved"])
            self.assertEqual(prop["estado"], "R4R")

    def test_massive_and_extreme_elapsed_times(self):
        """
        Adversarially test massive elapsed times and negative boundary minutes:
        - 10,000 minutes (~7 days)
        - 100,000 minutes (~69 days)
        - 1,000,000 minutes (~1.9 years)
        - 0 minutes
        - Negative minutes: -1, -60, -99,999
        In all cases, proposal must remain strictly R4R with auto_approved=False.
        """
        extreme_minutes = [10000, 100000, 1000000, 0, -1, -60, -99999]
        for m in extreme_minutes:
            code, res = simulate_inactivity_controller({
                "case_id": "CASO-1",
                "idle_minutes": m,
            }, services=self.services)

            self.assertEqual(code, 200, f"Failed for idle_minutes={m}")
            self.assertFalse(res["auto_approved"], f"idle_minutes={m}: auto_approved became True!")
            self.assertEqual(res["status"], "R4R", f"idle_minutes={m}: status altered!")

    def test_inactivity_on_non_r4r_statuses(self):
        """
        Inactivity simulation on edge states (R4R_INFO_INCOMPLETA, BLOQUEADO_RIESGO)
        must never alter status or auto-approve.
        """
        # Case 4: Info Incompleta
        evaluate_dispatch_controller({
            "case_id": "CASO-4",
            "descripcion": "Unos pallets al centro",
        }, services=self.services)

        code4, res4 = simulate_inactivity_controller({
            "case_id": "CASO-4",
            "idle_minutes": 5000,
        }, services=self.services)
        self.assertEqual(code4, 200)
        self.assertEqual(res4["status"], "R4R_INFO_INCOMPLETA")
        self.assertFalse(res4["auto_approved"])

        # Case 5: Bloqueado Riesgo
        evaluate_dispatch_controller({
            "case_id": "CASO-5",
            "origen": "Quilicura",
            "destino": "Maipú",
            "cargo_weight_kg": 4000,
            "truck_id_preferido": "CAM-04",
        }, services=self.services)

        code5, res5 = simulate_inactivity_controller({
            "case_id": "CASO-5",
            "idle_minutes": 5000,
        }, services=self.services)
        self.assertEqual(code5, 200)
        self.assertEqual(res5["status"], "BLOQUEADO_RIESGO")
        self.assertFalse(res5["auto_approved"])

    def test_sqlite_relational_constraint_prevents_auto_approval(self):
        """
        Verify that the SQLite database table r4r_proposals enforces
        CHECK (auto_approved = 0) at the storage engine level.
        """
        conn = sqlite3.connect(SQLITE_DB_PATH)
        cur = conn.cursor()
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                cur.execute("UPDATE r4r_proposals SET auto_approved = 1 WHERE case_id = 'CASO-1'")
                conn.commit()
        finally:
            conn.rollback()
            conn.close()

    def test_vulnerability_unhandled_non_integer_idle_minutes(self):
        """
        VULNERABILITY FINDING:
        In routes_r4r.py line 128:
            idle_minutes = int(payload.get("idle_minutes", 60))
        evaluated before the try/except block.
        When idle_minutes is None or an invalid string like 'abc',
        it raises uncaught TypeError or ValueError instead of returning HTTP 400/422.
        """
        code1, res1 = simulate_inactivity_controller({
            "case_id": "CASO-1",
            "idle_minutes": None,
        }, services=self.services)
        self.assertEqual(code1, 400)
        self.assertEqual(res1.get("error"), "INVALID_IDLE_MINUTES")

        code2, res2 = simulate_inactivity_controller({
            "case_id": "CASO-1",
            "idle_minutes": "not_a_number",
        }, services=self.services)
        self.assertEqual(code2, 400)
        self.assertEqual(res2.get("error"), "INVALID_IDLE_MINUTES")


class TestStateConsistencyAndIdempotency(unittest.TestCase):
    """Stress tests on queue listings, proposal lookups, and state machine consistency."""

    @classmethod
    def setUpClass(cls):
        cls.services = ServiceContainer.get_instance()

    def test_queue_listing_idempotency_100_calls(self):
        """100 sequential calls to get_queue_controller return deterministic and identical results."""
        code0, q0 = get_queue_controller(services=self.services)
        self.assertEqual(code0, 200)
        total0 = q0["total"]
        pending0 = q0["pending_count"]

        for i in range(100):
            code, q = get_queue_controller(services=self.services)
            self.assertEqual(code, 200)
            self.assertEqual(q["total"], total0)
            self.assertEqual(q["pending_count"], pending0)
            self.assertEqual(len(q["items"]), len(q0["items"]))

    def test_proposal_lookup_case_insensitivity_and_whitespace(self):
        """
        Lookups for case_id must succeed regardless of casing or whitespace:
        'CASO-1', 'caso-1', 'CaSo-1', '  CASO-1  '.
        """
        for variant in ["CASO-1", "caso-1", "CaSo-1", "  CASO-1  "]:
            code, prop = get_proposal_controller(variant, services=self.services)
            self.assertEqual(code, 200, f"Lookup failed for variant '{variant}'")
            self.assertEqual(prop["case_id"], "CASO-1")

    def test_proposal_lookup_by_proposal_id(self):
        """Lookup by proposal_id ('PROP-...') works interchangeably with case_id."""
        code_q, q = get_queue_controller(services=self.services)
        self.assertEqual(code_q, 200)
        self.assertTrue(len(q["items"]) > 0)
        sample_prop_id = q["items"][0]["proposal_id"]

        code, prop = get_proposal_controller(sample_prop_id, services=self.services)
        self.assertEqual(code, 200)
        self.assertEqual(prop["propuesta_id"], sample_prop_id)

    def test_proposal_lookup_nonexistent_returns_404(self):
        """Non-existent proposal lookup returns 404 with standard error body."""
        code, res = get_proposal_controller("NONEXISTENT-CASE-XYZ", services=self.services)
        self.assertEqual(code, 404)
        self.assertEqual(res["error"], "NOT_FOUND")

    def test_review_rejection_mandatory_reason_validation(self):
        """
        Strict rubric enforcement:
        - action='REJECT' with None reason -> HTTP 422
        - action='REJECT' with empty string reason -> HTTP 422
        - action='REJECT' with whitespace reason -> HTTP 422
        - In all failure modes, proposal state is NOT altered.
        """
        for invalid_reason in [None, "", "   ", "\t\n  \r\n"]:
            code, res = review_proposal_controller({
                "case_id": "CASO-1",
                "action": "REJECT",
                "supervisor_name": "Supervisor Test",
                "rejected_reason": invalid_reason,
            }, services=self.services)

            self.assertIn(code, (400, 422), f"Expected 400/422 for reason '{invalid_reason}', got {code}")
            # Ensure case remains in R4R
            p_code, prop = get_proposal_controller("CASO-1", services=self.services)
            self.assertEqual(p_code, 200)
            self.assertEqual(prop["estado"], "R4R")

    def test_review_approval_signature_and_invariant(self):
        """
        Review with APPROVE sets status to APPROVED, records supervisor signature,
        and unconditionally preserves auto_approved=False.
        """
        # Create dedicated case for approval
        evaluate_dispatch_controller({
            "case_id": "CASO-APPROVE-TEST",
            "origen": "Quilicura",
            "destino": "Pudahuel",
            "cargo_weight_kg": 3000,
            "hora_despacho": "14:00",
        }, services=self.services)

        code, res = review_proposal_controller({
            "case_id": "CASO-APPROVE-TEST",
            "action": "APPROVE",
            "supervisor_name": "Carlos Morales",
        }, services=self.services)

        self.assertEqual(code, 200)
        self.assertEqual(res["new_status"], "APPROVED")
        self.assertFalse(res["auto_approved"])
        self.assertEqual(res["supervisor_name"], "Carlos Morales")

        # Verify DB
        p_code, prop = get_proposal_controller("CASO-APPROVE-TEST", services=self.services)
        self.assertEqual(prop["estado"], "APPROVED")
        self.assertFalse(prop["auto_approved"])
        self.assertEqual(prop["human_signature"], "Carlos Morales")


class TestStaticAssetsAndPWAServing(unittest.TestCase):
    """Stress tests on static asset existence, readability, syntax, and HTTP serving."""

    def setUp(self):
        self.client = InProcessApiClient()

    def test_static_files_physical_existence_and_readability(self):
        """All required static assets must exist on disk and be readable."""
        required_files = [
            APP_DIR / "templates" / "index.html",
            APP_DIR / "static" / "css" / "app.css",
            APP_DIR / "static" / "js" / "app.js",
            APP_DIR / "static" / "manifest.json",
            APP_DIR / "static" / "sw.js",
            APP_DIR / "static" / "icons" / "icon-192.svg",
            APP_DIR / "static" / "icons" / "icon-512.svg",
            APP_DIR / "static" / "icons" / "icon-maskable.svg",
            APP_DIR / "static" / "icons" / "favicon.svg",
        ]
        for f in required_files:
            self.assertTrue(f.exists(), f"Missing required file: {f}")
            self.assertTrue(f.is_file(), f"Not a file: {f}")
            self.assertGreater(f.stat().st_size, 0, f"File is empty: {f}")

    def test_index_html_contains_critical_rubric_elements(self):
        """index.html must contain all rubric DOM IDs and viewport/PWA tags."""
        index_file = APP_DIR / "templates" / "index.html"
        with open(index_file, "r", encoding="utf-8") as f:
            html = f.read()

        essential_elements = [
            "id=\"mobile-simulator-frame\"",
            "id=\"btn-toggle-view\"",
            "id=\"review-modal\"",
            "id=\"modal-rejected-reason\"",
            "id=\"modal-supervisor-name\"",
            "id=\"btn-modal-approve\"",
            "id=\"btn-modal-reject\"",
            "<meta name=\"viewport\"",
            "<link rel=\"manifest\"",
            "/static/css/app.css",
            "/static/js/app.js",
        ]
        for el in essential_elements:
            self.assertIn(el, html, f"index.html missing essential element: {el}")

    def test_manifest_json_validity(self):
        """manifest.json must be valid JSON with standalone PWA properties."""
        manifest_path = APP_DIR / "static" / "manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        self.assertIn("name", manifest)
        self.assertIn("short_name", manifest)
        self.assertEqual(manifest.get("display"), "standalone")
        self.assertIn("icons", manifest)
        self.assertGreaterEqual(len(manifest["icons"]), 3)

    def test_svg_icons_valid_xml_syntax(self):
        """All SVG icons must parse cleanly as XML elements."""
        icon_dir = APP_DIR / "static" / "icons"
        for svg_file in icon_dir.glob("*.svg"):
            try:
                tree = ET.parse(svg_file)
                root = tree.getroot()
                self.assertTrue(root.tag.endswith("svg"), f"{svg_file} root tag is not svg")
            except Exception as e:
                self.fail(f"Invalid SVG syntax in {svg_file}: {e}")

    def test_static_asset_serving_routes(self):
        """HTTP GET on all static assets returns 200 with appropriate content."""
        routes = [
            ("/", 200),
            ("/index.html", 200),
            ("/static/css/app.css", 200),
            ("/static/js/app.js", 200),
            ("/static/manifest.json", 200),
            ("/static/sw.js", 200),
            ("/static/icons/icon-192.svg", 200),
            ("/static/icons/icon-512.svg", 200),
            ("/static/icons/icon-maskable.svg", 200),
            ("/static/icons/favicon.svg", 200),
            ("/static/icons/nonexistent.svg", 404),
        ]
        for path, expected_code in routes:
            res = self.client.get(path)
            self.assertEqual(res.status_code, expected_code, f"Route {path} returned {res.status_code}")
            if expected_code == 200:
                self.assertGreater(len(res.text), 0, f"Route {path} returned empty body")

    def test_vulnerability_directory_traversal_in_fallback_static_handler(self):
        """
        Verify that directory traversal breakout attempts via /static/
        are strictly blocked, returning HTTP 404 without leaking files.
        """
        res = self.client.get("/static/../../PROJECT.md")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json().get("error"), "STATIC_FILE_NOT_FOUND")
        self.assertNotIn("# Project: Agyx", res.text)

        res2 = self.client.get("/static/../main.py")
        self.assertEqual(res2.status_code, 404)
        self.assertEqual(res2.json().get("error"), "STATIC_FILE_NOT_FOUND")
        self.assertNotIn("AgyxFallbackHTTPHandler", res2.text)

        res3 = self.client.get("/static/%2e%2e/%2e%2e/PROJECT.md")
        self.assertEqual(res3.status_code, 404)
        self.assertEqual(res3.json().get("error"), "STATIC_FILE_NOT_FOUND")


class TestCase3IterationLoopDemoEndpoints(unittest.TestCase):
    """Stress tests on the Case 3 v1 -> v2 iteration loop through demo endpoints."""

    def setUp(self):
        self.services = ServiceContainer.get_instance()
        reset_memory_controller(services=self.services)

    def test_case3_complete_iteration_flow(self):
        """
        Adversarially verify the full lifecycle of Case 3:
        1. Run Case 3 v1 -> Naive daytime dispatch (CAM-05 at 11:30 hrs).
        2. Attempt review rejection with empty reason -> HTTP 422 rejected.
        3. Human supervisor review rejection with valid reason -> sets REJECTED,
           distills rule to <80 tokens, stores in Living Memory.
        4. Run Case 3 v2 -> reads Living Memory, schedules night window (21:30 hrs).
        5. Invariant: auto_approved is False in every single step.
        """
        # Before feedback, v2 detects the restriction but cannot invent a remedy.
        c_before, before = run_case_controller(
            "CASO-3", {"version_mode": "v2", "case_id": "CASO-3-BEFORE"}, services=self.services
        )
        self.assertEqual(c_before, 200)
        self.assertEqual(before["evaluation"]["status"], "R4R_INFO_INCOMPLETA")
        self.assertEqual(before["evaluation"]["proposal"]["camiones"], [])
        self.assertEqual(self.services.memory_service.get_active_rules("SANTIAGO_CENTRO"), [])

        # Step 1: Run v1
        c1, v1_res = run_case_controller("CASO-3", {"version_mode": "v1"}, services=self.services)
        self.assertEqual(c1, 200)
        eval_v1 = v1_res["evaluation"]
        self.assertEqual(eval_v1["status"], "R4R")
        self.assertFalse(eval_v1["auto_approved"])
        self.assertIn("CAM-05", eval_v1["proposal"]["camiones"])
        self.assertIn("11:30", eval_v1["proposal"]["fecha_hora_programada"])

        # Step 2: Inactivity simulation during v1 review
        c_sim, sim_res = simulate_inactivity_controller({
            "case_id": "CASO-3",
            "idle_minutes": 2880,  # 48 hours
        }, services=self.services)
        self.assertEqual(c_sim, 200)
        self.assertEqual(sim_res["status"], "R4R")
        self.assertFalse(sim_res["auto_approved"])

        # Step 3: Rejection with empty reason fails
        c_empty, err = review_proposal_controller({
            "case_id": "CASO-3",
            "action": "REJECT",
            "supervisor_name": "Carlos Morales",
            "rejected_reason": "   ",
        }, services=self.services)
        self.assertEqual(c_empty, 422)

        # Step 4: Rejection with valid reason succeeds and distills
        rejection_reason = (
            "Ordenanza Santiago Centro prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs. "
            "Reprogramar a ventana nocturna (21:30/06:00) o subdividir en 2 camiones de 5t"
        )
        c_valid, rej = review_proposal_controller({
            "case_id": "CASO-3",
            "action": "REJECT",
            "supervisor_name": "Carlos Morales (Operaciones)",
            "rejected_reason": rejection_reason,
        }, services=self.services)
        self.assertEqual(c_valid, 200)
        self.assertEqual(rej["new_status"], "REJECTED")
        self.assertFalse(rej["auto_approved"])
        self.assertIsNotNone(rej["distilled_rule_created"])

        # Step 5: Run v2
        c2, v2_res = run_case_controller("CASO-3", {"version_mode": "v2"}, services=self.services)
        self.assertEqual(c2, 200)
        eval_v2 = v2_res["evaluation"]
        self.assertEqual(eval_v2["status"], "R4R")
        self.assertFalse(eval_v2["auto_approved"])
        self.assertIn("21:30", eval_v2["proposal"]["fecha_hora_programada"])

    def test_run_all_cases_controller_and_key_mismatch_finding(self):
        """
        Verify POST /api/demo/run-all:
        - Executes all 6 cases + v1/v2 comparison (7 records).
        - Invariant: all records have auto_approved == False.
        - FINDING: Observes that 'camiones' in results summary is empty list []
          due to querying 'camiones_asignados' instead of 'camiones'.
        """
        code, all_res = run_all_cases_controller(services=self.services)
        self.assertEqual(code, 200)
        self.assertEqual(all_res["total_executed"], 7)
        self.assertTrue(all_res["all_auto_approved_false"])
        outcomes = {row["case_id"]: row["passed"] for row in all_res["results"]}
        self.assertFalse(outcomes["CASO-3-v1"])
        self.assertTrue(outcomes["CASO-3-v2"])

        for r in all_res["results"]:
            self.assertFalse(r["auto_approved"], f"Result {r['case_id']} had auto_approved=True!")

        # Verify assigned trucks are properly mapped from 'camiones'
        caso1_result = next(r for r in all_res["results"] if r["case_id"] == "CASO-1")
        self.assertEqual(
            caso1_result["camiones"],
            ["CAM-02"],
            "Verifies routes_demo.py correctly maps assigned trucks ['CAM-02']",
        )
        caso2_result = next(r for r in all_res["results"] if r["case_id"] == "CASO-2")
        self.assertEqual(
            caso2_result["camiones"],
            ["CAM-06"],
            "Verifies routes_demo.py correctly maps assigned trucks ['CAM-06']",
        )


if __name__ == "__main__":
    unittest.main()
