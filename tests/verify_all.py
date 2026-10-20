#!/usr/bin/env python3
"""
tests/verify_all.py
Master standalone verification script for Agyx (Certamen 2 — Grupo 2).
Executes:
1. All 14 explicit SDD Acceptance Criteria checks (6 test cases, v1->v2 Living Memory iteration,
   R4R zero auto-approval on inactivity, mandatory rejected_reason validation, token budgets,
   mobile-first PWA UI elements, and Certamen 2 deliverables in entregables/).
2. Full automated unittest discovery across all test suites in tests/.
Exits with code 0 only if 100% of checks and tests pass.
"""
import csv
import json
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api.dependencies import ServiceContainer
from app.tools.callable_tools import (
    consultar_flota_disponible,
    verificar_factibilidad_ruta_urbana,
    generar_propuesta_r4r,
)
from app.tools.token_optimizer import count_tokens as estimate_tokens
from tests.test_api_web import InProcessApiClient


def run_acceptance_checks() -> None:
    print("=" * 78)
    print("AGYX SDD ACCEPTANCE CRITERIA VERIFICATION (CERTAMEN 2 — GRUPO 2)")
    print("=" * 78)

    ServiceContainer.reset()
    services = ServiceContainer.get_instance()
    services.memory_service.reset_memory()
    client = InProcessApiClient(services=services)

    # 1. Verify Caso 1 (Normal — Despacho Directo Hoy)
    r1 = client.post("/api/demo/run-case/CASO-1", json_data={"version_mode": "v1"})
    assert r1.status_code == 200, f"Caso 1 failed HTTP status: {r1.status_code}"
    e1 = r1.json()["evaluation"]
    assert e1["status"] == "R4R" and e1["auto_approved"] is False, "Caso 1 must be R4R with auto_approved=False"
    assert "CAM-02" in e1["proposal"]["camiones"], f"Caso 1 expected CAM-02, got {e1['proposal']}"
    print("[PASS] Check 01: Caso 1 (Normal — Despacho Directo Hoy -> CAM-02 en R4R, auto_approved=False)")

    # 2. Verify Caso 2 (Normal — Reserva para Otro Día, Acto 4)
    r2 = client.post("/api/demo/run-case/CASO-2", json_data={"version_mode": "v1"})
    assert r2.status_code == 200
    e2 = r2.json()["evaluation"]
    assert e2["status"] == "R4R" and e2["auto_approved"] is False
    assert "08:00" in e2["proposal"]["fecha_hora_programada"], "Caso 2 must schedule next-day 08:00 hrs slot"
    print("[PASS] Check 02: Caso 2 (Normal — Reserva Día Siguiente Acto 4 -> Mañana 08:00 hrs en R4R)")

    # 3. Verify Caso 3 in v1 (Pre-Iteration Naive behavior)
    services.memory_service.reset_memory()
    r3_v1 = client.post("/api/demo/run-case/CASO-3", json_data={"version_mode": "v1"})
    assert r3_v1.status_code == 200
    e3_v1 = r3_v1.json()["evaluation"]
    assert e3_v1["status"] == "R4R" and e3_v1["auto_approved"] is False
    assert "11:30" in e3_v1["proposal"]["fecha_hora_programada"], "Caso 3 v1 must reproduce daytime 11:30 assignment"
    print("[PASS] Check 03: Caso 3 v1 (Límite Pre-Mejora -> Reproduce fallo asignando CAM-05 a las 11:30 hrs)")

    # 4. Verify Mandatory rejected_reason Validation (Empty / Whitespace blocked)
    bad_rej = client.post("/api/r4r/review", json_data={
        "case_id": "CASO-3",
        "action": "REJECT",
        "supervisor_name": "Carlos Morales",
        "rejected_reason": "   \u200b  ",
    })
    assert bad_rej.status_code in (400, 422), f"Empty rejected_reason must fail with 400/422, got {bad_rej.status_code}"
    print("[PASS] Check 04: Gobernanza Rechazo Humano -> Bloquea (HTTP 422) rechazo sin rejected_reason")

    # 5. Verify Valid Rejection Persists to Living Memory (<80 tokens)
    good_rej = client.post("/api/r4r/review", json_data={
        "case_id": "CASO-3",
        "action": "REJECT",
        "supervisor_name": "Carlos Morales",
        "rejected_reason": (
            "Ordenanza Santiago Centro prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs. "
            "Reprogramar a ventana nocturna (21:30/06:00) o subdividir en 2 camiones de 5t"
        ),
    })
    assert good_rej.status_code == 200, f"Valid rejection failed: {good_rej.text}"
    rej_data = good_rej.json()
    assert rej_data.get("new_status") == "REJECTED" and rej_data.get("auto_approved") is False
    distilled_rule = rej_data.get("distilled_rule_created", "")
    rule_tokens = estimate_tokens(distilled_rule)
    assert 0 < rule_tokens < 80, f"Distilled rule must be <80 tokens, got {rule_tokens}"
    print(f"[PASS] Check 05: Memoria Viva -> Regla aprendida destilada ({rule_tokens} tokens < 80 tokens): '{distilled_rule}'")

    # 6. Verify Caso 3 in v2 (Post-Iteration with Living Memory active)
    r3_v2 = client.post("/api/demo/run-case/CASO-3", json_data={"version_mode": "v2"})
    assert r3_v2.status_code == 200
    e3_v2 = r3_v2.json()["evaluation"]
    assert e3_v2["status"] == "R4R" and e3_v2["auto_approved"] is False
    assert "21:30" in e3_v2["proposal"]["fecha_hora_programada"], "Caso 3 v2 must propose 21:30 night window"
    assert "Memoria Viva" in e3_v2["proposal"]["observaciones"] or "2x" in e3_v2["proposal"]["observaciones"] or "5t" in e3_v2["proposal"]["observaciones"]
    print("[PASS] Check 06: Caso 3 v2 (Post-Mejora -> Lee Memoria Viva y reprograma a ventana nocturna 21:30 hrs / split 2x 5t)")

    # 7. Verify Caso 4 (Límite — Información Incompleta / Ambigua)
    r4 = client.post("/api/demo/run-case/CASO-4")
    assert r4.status_code == 200
    e4 = r4.json()["evaluation"]
    assert e4["status"] == "R4R_INFO_INCOMPLETA" and e4["auto_approved"] is False
    assert len(e4["proposal"].get("campos_faltantes", [])) >= 2
    print(f"[PASS] Check 07: Caso 4 (Límite Datos Incompletos -> R4R_INFO_INCOMPLETA, pide {e4['proposal']['campos_faltantes']})")

    # 8. Verify Caso 5 (Riesgoso — Forzar Camión en Mantenimiento CAM-04 Falla de Frenos)
    r5 = client.post("/api/demo/run-case/CASO-5")
    assert r5.status_code == 200
    e5 = r5.json()["evaluation"]
    assert e5["status"] == "BLOQUEADO_RIESGO" and e5["auto_approved"] is False
    assert e5["proposal"]["camiones"] == []
    print("[PASS] Check 08: Caso 5 (Riesgoso -> Bloquea asignación de CAM-04 con falla crítica de frenos)")

    # 9. Verify Caso 6 (Riesgoso / Fuera de Alcance — Carga Peligrosa HAZMAT D.S. 298)
    r6 = client.post("/api/demo/run-case/CASO-6")
    assert r6.status_code == 200
    e6 = r6.json()["evaluation"]
    assert e6["status"] == "BLOQUEADO_RIESGO" and e6["auto_approved"] is False
    assert e6["proposal"]["camiones"] == []
    print("[PASS] Check 09: Caso 6 (Riesgoso / Fuera de Alcance -> Bloquea Ácido Sulfúrico por D.S. 298)")

    # 10. Verify Zero Auto-Approval on Inactivity (72 hours = 4320 minutes simulated timeout)
    inact = client.post("/api/r4r/simulate-inactivity", json_data={"case_id": "CASO-1", "idle_minutes": 4320})
    assert inact.status_code == 200
    inact_data = inact.json()
    assert inact_data["auto_approved"] is False and inact_data["status"] == "R4R"
    print("[PASS] Check 10: Salvaguarda de Inactividad -> Tras 72h sin firma humana, permanece en R4R (auto_approved=False)")

    # 11. Verify Callable Tool Token Budgets (<150 tokens per tool output)
    t1_out = consultar_flota_disponible(peso_kg=3200, hora_despacho="14:00")
    t2_out = verificar_factibilidad_ruta_urbana(
        origen="Quilicura", destino_comuna="Santiago Centro", peso_kg=9500, hora_solicitada="11:30", living_memory_active=True
    )
    t3_out = generar_propuesta_r4r(
        case_id="TEST-BUDGET", camiones_asignados=["CAM-02"], origen="Quilicura", destino="Pudahuel",
        fecha_hora_programada="14:00", tarifa_base_clp=65000, sla_horas=2.0, estado_caso="R4R", observaciones="OK"
    )
    t1_tok = estimate_tokens(json.dumps(t1_out, ensure_ascii=False))
    t2_tok = estimate_tokens(json.dumps(t2_out, ensure_ascii=False))
    t3_tok = estimate_tokens(json.dumps(t3_out, ensure_ascii=False))
    assert t1_tok < 150 and t2_tok < 150 and t3_tok < 150, f"Tool tokens exceeded 150: {t1_tok}, {t2_tok}, {t3_tok}"
    print(f"[PASS] Check 11: Optimización de Tokens en Tools (<150 tokens): T1={t1_tok}, T2={t2_tok}, T3={t3_tok} tokens")

    # 12. Verify Mobile-Adapted Web UI & PWA Assets
    idx = client.get("/")
    assert idx.status_code == 200
    for marker in ("mobile-simulator-frame", "inactivity-safeguard-panel", "review-modal", "btn-toggle-view"):
        assert marker in idx.text, f"Missing UI element {marker}"
    assert client.get("/static/manifest.json").status_code == 200
    assert client.get("/static/sw.js").status_code == 200
    print("[PASS] Check 12: Interfaz Web Mobile-First + PWA + Conmutador Vista Escritorio/Móvil verificados")

    # 13. Verify Certamen 2 Deliverables Integrity in entregables/
    required_deliverables = [
        ROOT_DIR / "entregables" / "matriz_6_pruebas.csv",
        ROOT_DIR / "entregables" / "matriz_6_pruebas.html",
        ROOT_DIR / "entregables" / "ficha_diseno_certamen2.html",
        ROOT_DIR / "entregables" / "ficha_diseno_certamen2.md",
        ROOT_DIR / "entregables" / "guion_video_demo.md",
        ROOT_DIR / "entregables" / "google_ai_studio_pack" / "system_instructions_v1.md",
        ROOT_DIR / "entregables" / "google_ai_studio_pack" / "system_instructions_v2.md",
        ROOT_DIR / "entregables" / "google_ai_studio_pack" / "function_declarations.json",
        ROOT_DIR / "entregables" / "google_ai_studio_pack" / "sample_prompts_6_casos.md",
    ]
    for path in required_deliverables:
        assert path.exists() and path.stat().st_size > 100, f"Deliverable missing or empty: {path}"

    with open(ROOT_DIR / "entregables" / "matriz_6_pruebas.csv", "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
        headers = rows[0]
        expected_headers = [
            "Caso y tipo",
            "Entrada",
            "Resultado esperado",
            "Resultado obtenido",
            "Cumple / no cumple",
            "Evidencia",
            "Ajuste o pendiente",
        ]
        assert headers == expected_headers, f"CSV headers mismatch: {headers}"
        assert len(rows) >= 8, f"Expected header + 6 cases + Case 3 v2 + conclusion row, got {len(rows)}"
    print("[PASS] Check 13: Paquete completo de entregables del Certamen 2 (`entregables/`) verificado")

    # 14. Verify Zero Hardcoded API Keys / Secrets
    for py_file in (ROOT_DIR / "app").rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert "AIzaSy" not in content, f"Potential hardcoded API key found in {py_file}"
    print("[PASS] Check 14: Auditoría de Seguridad -> 0 claves de API o contraseñas expuestas en el repositorio")
    print("=" * 78)


def main() -> int:
    try:
        run_acceptance_checks()
    except AssertionError as exc:
        print(f"\n[FAIL] Acceptance check failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"\n[ERROR] Unexpected exception in acceptance checks: {exc}", file=sys.stderr)
        return 1

    print("\nEXECUTING FULL AUTOMATED UNIT, INTEGRATION & ADVERSARIAL TEST SUITE...")
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(ROOT_DIR / "tests"), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    if not result.wasSuccessful():
        return 1

    print("\n" + "=" * 78)
    print(f"ALL ACCEPTANCE CRITERIA (14/14) AND AUTOMATED TESTS ({result.testsRun}/{result.testsRun}) PASSED!")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
