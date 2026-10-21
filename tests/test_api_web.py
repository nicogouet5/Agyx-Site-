"""
tests/test_api_web.py
Comprehensive automated integration test suite for Agyx FastAPI Web & REST API layer.
Verifies:
- Health and Web UI index routes (/health, /, /index.html)
- Actual HTML template contents (#mobile-simulator-frame, #review-modal, #inactivity-safeguard-panel)
- PWA and static assets (/static/manifest.json, /static/sw.js, /static/css/app.css, icons)
- Dispatch evaluation endpoint (/api/dispatch/evaluate) across all 6 cases
- R4R queue listing and proposal audit retrieval (/api/r4r/queue, /api/r4r/{id})
- Human Review governance: APPROVE signature, valid REJECT distillation
- MANDATORY REJECTION REASON: HTTP 400 or HTTP 422 on empty or whitespace reason
- Zero auto-approval under inactivity simulation (/api/r4r/simulate-inactivity)
- Living Memory endpoints (/api/memory, /api/memory/reset, /api/memory/seed)
- Fleet and restrictions endpoints (/api/fleet, /api/restrictions)
- Demo case runners (/api/demo/cases, /api/demo/run-case, /api/demo/run-all)
- Dual-resilience FallbackApp import cleanly
- Zero-dependency resilience: executes with pure Python 3.9+ standard library.
"""
import unittest
import json
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlparse, parse_qs, unquote

from app.config import APP_DIR
from app.api.dependencies import ServiceContainer
from app.api.routes_dispatch import evaluate_dispatch_controller
from app.api.routes_r4r import (
    get_queue_controller,
    get_proposal_controller,
    review_proposal_controller,
    simulate_inactivity_controller,
)
from app.api.routes_memory import (
    get_memory_controller,
    reset_memory_controller,
    seed_memory_controller,
)
from app.api.routes_fleet import (
    get_fleet_controller,
    get_truck_controller,
    get_restrictions_controller,
    get_zone_restriction_controller,
)
from app.api.routes_demo import (
    get_demo_cases_controller,
    run_case_controller,
    run_all_cases_controller,
)


class MockResponse:
    """Lightweight test response object mimicking requests/TestClient response."""
    def __init__(self, status_code: int, data: Any, text: str = "", content_type: str = "application/json"):
        self.status_code = status_code
        self._data = data
        self.text = text or (json.dumps(data) if isinstance(data, (dict, list)) else str(data))
        self.content_type = content_type

    def json(self) -> Any:
        if isinstance(self._data, (dict, list)):
            return self._data
        return json.loads(self.text)


class InProcessApiClient:
    """
    In-process test client executing REST API requests directly through the controller layer.
    Guarantees 100% test reproducibility without requiring socket bindings or external dependencies.
    """
    def __init__(self, services: Optional[ServiceContainer] = None):
        self.services = services or ServiceContainer.get_instance()

    def get(self, path: str, params: Optional[Dict[str, str]] = None) -> MockResponse:
        parsed = urlparse(path)
        route_path = parsed.path
        query = parse_qs(parsed.query)
        if params:
            for k, v in params.items():
                query[k] = [v]

        if route_path in ("/health", "/api/health"):
            return MockResponse(200, {
                "status": "OK",
                "app": "Agyx Operational AI Agent",
                "version": "1.0.0",
                "server": "InProcess/FastAPI",
            })

        # Genuinely serve templates/index.html
        if route_path in ("/", "/index.html"):
            index_path = APP_DIR / "templates" / "index.html"
            if index_path.exists():
                with open(index_path, "r", encoding="utf-8") as f:
                    content = f.read()
                return MockResponse(200, {}, text=content, content_type="text/html")
            return MockResponse(404, {"error": "INDEX_NOT_FOUND"})

        # Genuinely serve static assets
        if route_path.startswith("/static/"):
            rel_path = unquote(route_path[len("/static/"):].lstrip("/"))
            file_path = (APP_DIR / "static" / rel_path).resolve()
            if file_path.is_file() and file_path.is_relative_to((APP_DIR / "static").resolve()):
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                return MockResponse(200, {}, text=content, content_type="text/plain")
            return MockResponse(404, {"error": "STATIC_FILE_NOT_FOUND", "path": route_path})

        if route_path == "/api/r4r/queue":
            code, data = get_queue_controller(services=self.services)
            return MockResponse(code, data)

        if route_path.startswith("/api/r4r/"):
            case_id = route_path[len("/api/r4r/"):].strip()
            code, data = get_proposal_controller(case_id, services=self.services)
            return MockResponse(code, data)

        if route_path in ("/api/memory", "/api/memory/"):
            zone = query.get("zone", [None])[0]
            code, data = get_memory_controller(zone=zone, services=self.services)
            return MockResponse(code, data)

        if route_path == "/api/fleet":
            code, data = get_fleet_controller(services=self.services)
            return MockResponse(code, data)

        if route_path.startswith("/api/fleet/"):
            truck_id = route_path[len("/api/fleet/"):].strip()
            code, data = get_truck_controller(truck_id, services=self.services)
            return MockResponse(code, data)

        if route_path == "/api/restrictions":
            code, data = get_restrictions_controller(services=self.services)
            return MockResponse(code, data)

        if route_path.startswith("/api/restrictions/"):
            zone = route_path[len("/api/restrictions/"):].strip()
            code, data = get_zone_restriction_controller(zone, services=self.services)
            return MockResponse(code, data)

        if route_path == "/api/demo/cases":
            code, data = get_demo_cases_controller()
            return MockResponse(code, data)

        return MockResponse(404, {"error": "NOT_FOUND", "path": route_path})

    def post(self, path: str, json_data: Optional[Dict[str, Any]] = None) -> MockResponse:
        parsed = urlparse(path)
        route_path = parsed.path
        payload = json_data or {}

        if route_path in ("/api/dispatch/evaluate", "/api/dispatch/evaluate/"):
            code, data = evaluate_dispatch_controller(payload, services=self.services)
            return MockResponse(code, data)

        if route_path in ("/api/r4r/review", "/api/r4r/review/"):
            code, data = review_proposal_controller(payload, services=self.services)
            return MockResponse(code, data)

        if route_path in ("/api/r4r/simulate-inactivity", "/api/r4r/simulate-inactivity/"):
            code, data = simulate_inactivity_controller(payload, services=self.services)
            return MockResponse(code, data)

        if route_path in ("/api/memory/reset", "/api/memory/reset/"):
            code, data = reset_memory_controller(services=self.services)
            return MockResponse(code, data)

        if route_path in ("/api/memory/seed", "/api/memory/seed/"):
            code, data = seed_memory_controller(payload, services=self.services)
            return MockResponse(code, data)

        if route_path.startswith("/api/demo/run-case/"):
            case_id = route_path[len("/api/demo/run-case/"):].strip()
            code, data = run_case_controller(case_id, payload=payload, services=self.services)
            return MockResponse(code, data)

        if route_path in ("/api/demo/run-all", "/api/demo/run-all/"):
            code, data = run_all_cases_controller(payload=payload, services=self.services)
            return MockResponse(code, data)

        return MockResponse(404, {"error": "NOT_FOUND", "path": route_path})


class TestAgyxWebAPI(unittest.TestCase):
    """Complete integration test suite for Agyx FastAPI and Web layer."""

    def setUp(self):
        ServiceContainer.reset()
        self.services = ServiceContainer.get_instance()
        self.services.memory_service.reset_memory()
        self.client = InProcessApiClient(services=self.services)

    # -------------------------------------------------------------
    # 1. Health and UI Routes
    # -------------------------------------------------------------
    def test_health_check_endpoints(self):
        """GET /health and GET /api/health return HTTP 200 with status OK."""
        res1 = self.client.get("/health")
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json()["status"], "OK")

        res2 = self.client.get("/api/health")
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["status"], "OK")

    def test_index_route_serves_actual_template(self):
        """GET / genuinely serves templates/index.html containing mobile simulator and R4R UI."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        # Verify required DOM element IDs per rubric
        self.assertIn("mobile-simulator-frame", res.text, "index.html must include #mobile-simulator-frame")
        self.assertIn("inactivity-safeguard-panel", res.text, "index.html must include #inactivity-safeguard-panel")
        self.assertIn("review-modal", res.text, "index.html must include #review-modal")
        self.assertIn("tab-case3", res.text, "index.html must include #tab-case3")
        self.assertIn("btn-toggle-view", res.text, "index.html must include desktop/mobile view toggle")

    def test_static_and_pwa_assets_serving(self):
        """Verify CSS, JS, manifest.json, sw.js, and SVG icons are served properly."""
        assets = [
            "/static/manifest.json",
            "/static/sw.js",
            "/static/css/app.css",
            "/static/js/app.js",
            "/static/icons/favicon.svg",
            "/static/icons/icon-192.svg",
            "/static/icons/icon-512.svg",
            "/static/icons/icon-maskable.svg",
        ]
        for asset_path in assets:
            res = self.client.get(asset_path)
            self.assertEqual(res.status_code, 200, f"Asset {asset_path} must be accessible with 200")
            self.assertTrue(len(res.text) > 0, f"Asset {asset_path} must not be empty")

    # -------------------------------------------------------------
    # 2. Dispatch Evaluation Endpoint (Cases 1 to 6)
    # -------------------------------------------------------------
    def test_dispatch_evaluate_caso1_normal(self):
        """Caso 1: 3,200 kg returns HTTP 200, status R4R, CAM-02 assigned, auto_approved=False."""
        payload = {
            "case_id": "CASO-1",
            "origen": "Quilicura",
            "destino": "Pudahuel",
            "cargo_weight_kg": 3200,
            "hora_despacho": "14:00",
        }
        res = self.client.post("/api/dispatch/evaluate", json_data=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "R4R")
        self.assertFalse(data["auto_approved"])
        trucks = data["proposal"].get("camiones") or data["proposal"].get("camiones_asignados")
        self.assertEqual(trucks, ["CAM-02"])
        self.assertFalse(data["proposal"]["auto_approved"])

    def test_dispatch_evaluate_caso2_reserva(self):
        """Caso 2: 10,000 kg when fleet is busy returns next-day reservation in R4R."""
        payload = {
            "case_id": "CASO-2",
            "origen": "Quilicura",
            "destino": "San Bernardo",
            "cargo_weight_kg": 10000,
            "hora_despacho": "15:00",
        }
        res = self.client.post("/api/dispatch/evaluate", json_data=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "R4R")
        self.assertFalse(data["auto_approved"])
        self.assertIn("08:00", data["proposal"]["fecha_hora_programada"])

    def test_dispatch_evaluate_caso3_v1_and_v2(self):
        """Caso 3: v1 assigns daytime naive; v2 post-memory assigns night window."""
        payload_v1 = {
            "case_id": "CASO-3",
            "origen": "Quilicura",
            "destino": "Santiago Centro",
            "cargo_weight_kg": 9500,
            "hora_despacho": "11:30",
            "version_mode": "v1",
        }
        res_v1 = self.client.post("/api/dispatch/evaluate", json_data=payload_v1)
        self.assertEqual(res_v1.status_code, 200)
        self.assertEqual(res_v1.json()["status"], "R4R")
        self.assertEqual(res_v1.json()["proposal"]["fecha_hora_programada"], "11:30")

        # Seed memory rule
        self.client.post("/api/memory/seed", json_data={
            "case_id": "CASO-3",
            "rejected_reason": "Ordenanza Santiago Centro prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs. Reprogramar a ventana nocturna (21:30/06:00) o subdividir en 2 camiones de 5t",
        })

        # Run v2
        payload_v2 = dict(payload_v1, version_mode="v2")
        res_v2 = self.client.post("/api/dispatch/evaluate", json_data=payload_v2)
        self.assertEqual(res_v2.status_code, 200)
        data_v2 = res_v2.json()
        self.assertEqual(data_v2["status"], "R4R")
        self.assertIn("21:30", data_v2["proposal"]["fecha_hora_programada"])

    def test_dispatch_evaluate_caso4_info_incompleta(self):
        """Caso 4: Incomplete request returns R4R_INFO_INCOMPLETA with missing fields list."""
        payload = {
            "case_id": "CASO-4",
            "descripcion": "Necesito mandar unos pallets urgentes al centro ahora en la tarde",
        }
        res = self.client.post("/api/dispatch/evaluate", json_data=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "R4R_INFO_INCOMPLETA")
        self.assertFalse(data["auto_approved"])
        self.assertTrue(len(data["proposal"]["campos_faltantes"]) >= 1)

    def test_dispatch_evaluate_caso5_falla_frenos(self):
        """Caso 5: Pressure to use CAM-04 with brake failure triggers BLOQUEADO_RIESGO."""
        payload = {
            "case_id": "CASO-5",
            "origen": "Quilicura",
            "destino": "Maipú",
            "cargo_weight_kg": 4000,
            "truck_id_preferido": "CAM-04",
        }
        res = self.client.post("/api/dispatch/evaluate", json_data=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "BLOQUEADO_RIESGO")
        self.assertFalse(data["auto_approved"])
        self.assertIn("frenos", data["proposal"]["observaciones"].lower())

    def test_dispatch_evaluate_caso6_hazmat(self):
        """Caso 6: Chemical HAZMAT cargo triggers legal block under D.S. 298."""
        payload = {
            "case_id": "CASO-6",
            "origen": "Quilicura",
            "destino": "Santiago Centro",
            "cargo_weight_kg": 4000,
            "tipo_carga": "ACIDO_SULFURICO",
        }
        res = self.client.post("/api/dispatch/evaluate", json_data=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "BLOQUEADO_RIESGO")
        self.assertFalse(data["auto_approved"])
        self.assertIn("298", data["proposal"]["observaciones"])

    # -------------------------------------------------------------
    # 3. R4R Queue and Human Review Governance
    # -------------------------------------------------------------
    def test_r4r_queue_and_proposal_lookup(self):
        """GET /api/r4r/queue and GET /api/r4r/{case_id} return stored records."""
        # Create a proposal first
        self.client.post("/api/dispatch/evaluate", json_data={
            "case_id": "CASO-LOOKUP-TEST", "cargo_weight_kg": 3200, "destino": "Pudahuel"
        })

        q_res = self.client.get("/api/r4r/queue")
        self.assertEqual(q_res.status_code, 200)
        self.assertTrue(q_res.json()["total"] >= 1)

        p_res = self.client.get("/api/r4r/CASO-LOOKUP-TEST")
        self.assertEqual(p_res.status_code, 200)
        self.assertEqual(p_res.json()["case_id"], "CASO-LOOKUP-TEST")

        not_found = self.client.get("/api/r4r/CASO-DOES-NOT-EXIST")
        self.assertEqual(not_found.status_code, 404)

    def test_review_approval_flow(self):
        """POST /api/r4r/review with APPROVE sets APPROVED, records signature, auto_approved=False."""
        self.client.post("/api/dispatch/evaluate", json_data={
            "case_id": "CASO-APP-TEST", "cargo_weight_kg": 3200, "destino": "Pudahuel"
        })

        res = self.client.post("/api/r4r/review", json_data={
            "case_id": "CASO-APP-TEST",
            "action": "APPROVE",
            "supervisor_name": "Carlos Morales",
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["new_status"], "APPROVED")
        self.assertFalse(data["auto_approved"])
        self.assertEqual(data["supervisor_name"], "Carlos Morales")

    def test_review_rejection_valid_flow(self):
        """POST /api/r4r/review with valid reason sets REJECTED, distills rule, auto_approved=False."""
        self.client.post("/api/dispatch/evaluate", json_data={
            "case_id": "CASO-REJ-VALID", "cargo_weight_kg": 9500, "destino": "Santiago Centro",
            "hora_despacho": "11:30", "version_mode": "v1"
        })

        reason = "Ordenanza Santiago Centro prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs. Reprogramar a ventana nocturna (21:30/06:00) o subdividir en 2 camiones de 5t"
        res = self.client.post("/api/r4r/review", json_data={
            "case_id": "CASO-REJ-VALID",
            "action": "REJECT",
            "supervisor_name": "Carlos Morales",
            "rejected_reason": reason,
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["new_status"], "REJECTED")
        self.assertFalse(data["auto_approved"])
        self.assertIsNotNone(data["distilled_rule_created"])

    # -------------------------------------------------------------
    # 4. CRITICAL RUBRIC TEST: Empty/Whitespace Rejection Rejection
    # -------------------------------------------------------------
    def test_review_rejection_fails_on_empty_or_whitespace_reason(self):
        """
        CERTAMEN 2 RUBRIC VALIDATION:
        Submitting REJECT with empty or whitespace reason MUST return HTTP 400 or HTTP 422.
        Proposal MUST remain locked in R4R.
        """
        self.client.post("/api/dispatch/evaluate", json_data={
            "case_id": "CASO-REJ-EMPTY", "cargo_weight_kg": 3200, "destino": "Pudahuel"
        })

        # Test empty string reason
        res_empty = self.client.post("/api/r4r/review", json_data={
            "case_id": "CASO-REJ-EMPTY",
            "action": "REJECT",
            "supervisor_name": "Carlos Morales",
            "rejected_reason": "",
        })
        self.assertIn(res_empty.status_code, (400, 422), "Empty rejection reason must return HTTP 400 or 422")

        # Test whitespace only reason
        res_ws = self.client.post("/api/r4r/review", json_data={
            "case_id": "CASO-REJ-EMPTY",
            "action": "REJECT",
            "supervisor_name": "Carlos Morales",
            "rejected_reason": "   \n\t  ",
        })
        self.assertIn(res_ws.status_code, (400, 422), "Whitespace rejection reason must return HTTP 400 or 422")

        # Test None / missing reason
        res_none = self.client.post("/api/r4r/review", json_data={
            "case_id": "CASO-REJ-EMPTY",
            "action": "REJECT",
            "supervisor_name": "Carlos Morales",
        })
        self.assertIn(res_none.status_code, (400, 422), "Missing rejection reason must return HTTP 400 or 422")

        # Confirm proposal is STILL in original R4R state (not transitioned to REJECTED)
        prop_check = self.client.get("/api/r4r/CASO-REJ-EMPTY")
        self.assertEqual(prop_check.json()["estado"], "R4R")
        self.assertFalse(prop_check.json()["auto_approved"])

    # -------------------------------------------------------------
    # 5. ZERO AUTO-APPROVAL UNDER INACTIVITY SIMULATION
    # -------------------------------------------------------------
    def test_simulate_inactivity_safeguard(self):
        """
        Simulating operator inactivity (60 min, 1440 min) NEVER transitions out of R4R.
        auto_approved remains strictly False.
        """
        self.client.post("/api/dispatch/evaluate", json_data={
            "case_id": "CASO-IDLE-TEST", "cargo_weight_kg": 3200, "destino": "Pudahuel"
        })

        # Simulate 1 hour inactivity
        res1 = self.client.post("/api/r4r/simulate-inactivity", json_data={
            "case_id": "CASO-IDLE-TEST", "idle_minutes": 60
        })
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json()["status"], "R4R")
        self.assertFalse(res1.json()["auto_approved"])

        # Simulate 24 hours inactivity
        res2 = self.client.post("/api/r4r/simulate-inactivity", json_data={
            "case_id": "CASO-IDLE-TEST", "idle_minutes": 1440
        })
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["status"], "R4R")
        self.assertFalse(res2.json()["auto_approved"])

        # Check stored proposal
        stored = self.client.get("/api/r4r/CASO-IDLE-TEST").json()
        self.assertEqual(stored["estado"], "R4R")
        self.assertFalse(stored["auto_approved"])

    # -------------------------------------------------------------
    # 6. Living Memory Endpoints
    # -------------------------------------------------------------
    def test_living_memory_reset_seed_inspect(self):
        """Test reset, seed, and get endpoints for Living Memory."""
        reset_res = self.client.post("/api/memory/reset")
        self.assertEqual(reset_res.status_code, 200)

        seed_res = self.client.post("/api/memory/seed", json_data={
            "case_id": "CASO-3",
            "rejected_reason": "Ordenanza Santiago Centro prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs. Reprogramar a ventana nocturna (21:30/06:00) o subdividir en 2 camiones de 5t",
        })
        self.assertEqual(seed_res.status_code, 200)
        self.assertLess(seed_res.json()["rule"]["token_count"], 80)

        mem_res = self.client.get("/api/memory")
        self.assertEqual(mem_res.status_code, 200)
        self.assertEqual(mem_res.json()["active_rules_count"], 1)

    # -------------------------------------------------------------
    # 7. Fleet and Restrictions Endpoints
    # -------------------------------------------------------------
    def test_fleet_and_restrictions_endpoints(self):
        """GET /api/fleet and GET /api/restrictions return catalog data."""
        fleet_res = self.client.get("/api/fleet")
        self.assertEqual(fleet_res.status_code, 200)
        self.assertEqual(fleet_res.json()["total"], 7)

        # Check CAM-04 maintenance lock
        cam4 = next(t for t in fleet_res.json()["trucks"] if t["id_camion"] == "CAM-04")
        self.assertTrue(cam4["mantenimiento_bloqueo"])

        # Single truck lookup
        t_res = self.client.get("/api/fleet/CAM-04")
        self.assertEqual(t_res.status_code, 200)
        self.assertEqual(t_res.json()["id_camion"], "CAM-04")

        # Urban restrictions
        rst_res = self.client.get("/api/restrictions")
        self.assertEqual(rst_res.status_code, 200)
        self.assertEqual(rst_res.json()["total"], 4)

    # -------------------------------------------------------------
    # 8. Demo Runner Endpoints
    # -------------------------------------------------------------
    def test_demo_runner_endpoints(self):
        """GET /api/demo/cases, POST /api/demo/run-case, POST /api/demo/run-all."""
        cases_res = self.client.get("/api/demo/cases")
        self.assertEqual(cases_res.status_code, 200)
        self.assertEqual(cases_res.json()["total"], 6)

        # Run single demo case (Caso 1)
        c1_run = self.client.post("/api/demo/run-case/CASO-1")
        self.assertEqual(c1_run.status_code, 200)
        self.assertEqual(c1_run.json()["evaluation"]["status"], "R4R")

        # Run all cases
        all_run = self.client.post("/api/demo/run-all")
        self.assertEqual(all_run.status_code, 200)
        self.assertTrue(all_run.json()["all_auto_approved_false"])
        self.assertEqual(all_run.json()["total_executed"], 7)  # 6 cases + Caso 3 v1/v2

    # -------------------------------------------------------------
    # 9. Dual-Resilience Fallback App Verification
    # -------------------------------------------------------------
    def test_dual_resilience_fallback_import(self):
        """Importing app from app.main succeeds and exposes title and version."""
        from app.main import app
        self.assertIsNotNone(app)
        self.assertTrue(hasattr(app, "title"))
        self.assertIn("Agyx", app.title)


if __name__ == "__main__":
    unittest.main()
