"""Generate a reproducible, synthetic-data execution record for Certamen 2."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.api.dependencies import ServiceContainer
from app.api.routes_demo import CANONICAL_CASES, run_case_controller
from app.api.routes_r4r import review_proposal_controller


OUTPUT = Path(__file__).resolve().parent / "evidencia" / "corrida_6_casos.json"
REASON = (
    "Ordenanza Santiago Centro prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs. "
    "Reprogramar a ventana nocturna (21:30/06:00) o subdividir en 2 camiones de 5t"
)


def compact(result: dict) -> dict:
    evaluation = result["evaluation"]
    proposal = evaluation.get("proposal") or {}
    return {
        "status": evaluation["status"],
        "auto_approved": evaluation.get("auto_approved"),
        "camiones": proposal.get("camiones", []),
        "fecha_hora_programada": proposal.get("fecha_hora_programada"),
        "campos_faltantes": proposal.get("campos_faltantes", []),
        "observaciones": proposal.get("observaciones"),
    }


def run() -> dict:
    now = datetime.now(ZoneInfo("America/Santiago"))
    records = []
    with tempfile.TemporaryDirectory() as temp_dir:
        services = ServiceContainer(
            db_path=str(Path(temp_dir) / "agyx.db"),
            memory_path=str(Path(temp_dir) / "memory.json"),
        )
        for case in CANONICAL_CASES:
            case_id = case["case_id"]
            if case_id == "CASO-3":
                _, before = run_case_controller(
                    case_id, {"version_mode": "v2", "case_id": "CASO-3-SIN-MEMORIA"}, services=services
                )
                pre = compact(before)
                records.append({
                    "case_id": "CASO-3-sin-memoria",
                    "tipo": "control previo a la mejora",
                    "entrada": dict(case["order_payload"], version_mode="v2", case_id="CASO-3-SIN-MEMORIA"),
                    "esperado": "Retener sin camión ni alternativa aprendida",
                    "obtenido": pre,
                    "cumple": pre["status"] == "R4R_INFO_INCOMPLETA" and pre["camiones"] == [],
                })
                _, initial = run_case_controller(case_id, {"version_mode": "v1"}, services=services)
                observed = compact(initial)
                records.append({
                    "case_id": "CASO-3-v1",
                    "tipo": "límite, fallo inicial",
                    "entrada": dict(case["order_payload"], version_mode="v1"),
                    "esperado": "No asignar camión pesado a las 11:30 en zona restringida",
                    "obtenido": observed,
                    "cumple": False,
                })
                review_code, review = review_proposal_controller({
                    "case_id": case_id,
                    "action": "REJECT",
                    "supervisor_name": "Carlos Morales (dato sintético de demostración)",
                    "rejected_reason": REASON,
                }, services=services)
                _, repeated = run_case_controller(case_id, {"version_mode": "v2"}, services=services)
                observed = compact(repeated)
                records.append({
                    "case_id": "CASO-3-v2",
                    "tipo": "repetición tras rechazo simulado",
                    "entrada": dict(case["order_payload"], version_mode="v2"),
                    "esperado": "Proponer 21:30, mantener R4R sin autoaprobación",
                    "obtenido": observed,
                    "cumple": (
                        review_code == 200 and observed["status"] == "R4R"
                        and "21:30" in (observed["fecha_hora_programada"] or "")
                        and observed["auto_approved"] is False
                    ),
                    "revision_humana_simulada": {
                        "accion": "REJECT",
                        "resultado": review.get("new_status"),
                        "motivo": REASON,
                        "regla_destilada": review.get("distilled_rule_created"),
                    },
                })
                continue

            _, result = run_case_controller(case_id, services=services)
            observed = compact(result)
            expected = case["resultado_esperado"]
            records.append({
                "case_id": case_id,
                "tipo": case["categoria"].lower(),
                "entrada": case["order_payload"],
                "esperado": expected,
                "obtenido": observed,
                "cumple": (
                    observed["status"] == expected["estado"]
                    and observed["auto_approved"] is False
                    and ("camiones_asignados" not in expected or observed["camiones"] == expected["camiones_asignados"])
                    and ("campos_faltantes" not in expected or all(
                        field in observed["campos_faltantes"] for field in expected["campos_faltantes"]
                    ))
                    and (case_id != "CASO-2" or observed["fecha_hora_programada"] ==
                         f"{(now.date() + timedelta(days=1)).isoformat()} 08:00 hrs")
                ),
            })

    distinct = [r for r in records if r["case_id"] in {f"CASO-{n}" for n in (1, 2, 4, 5, 6)} or r["case_id"] == "CASO-3-v1"]
    return {
        "ejecutado_en": now.isoformat(),
        "entorno": "motor local determinista, datos sintéticos, almacenamiento temporal aislado",
        "revision_humana": "Simulada por llamada al controlador; no autentica a una persona",
        "resumen": {
            "casos_distintos": 6,
            "cumplen_inicialmente": sum(r["cumple"] for r in distinct),
            "cumplen_tras_iteracion": sum(r["cumple"] for r in distinct) + int(next(r for r in records if r["case_id"] == "CASO-3-v2")["cumple"]),
        },
        "registros": records,
    }


if __name__ == "__main__":
    evidence = run()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{OUTPUT}: {evidence['resumen']}")
