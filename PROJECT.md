# Project: Agyx — Token-Optimized Operational AI Agent (Pymes-Fletes Grupo 2)

## Architecture
Agyx is a token-optimized operational AI Agent prototype for SME freight and logistics companies in Santiago de Chile. It evaluates dispatch orders, verifies fleet availability and maintenance status, validates municipal heavy-vehicle urban restrictions (such as Santiago Centro daytime bans), enforces a strict R4R (Ready for Review) human-in-the-loop state machine with zero auto-approval on inactivity, and records mandatory human rejection reasons into a Living Memory (`Memoria Viva`) that feeds back into future runs.

### Three-Layer Architecture
1. **Frontend Layer (Web UI & PWA)**:
   - Mobile-first responsive UI built with Tailwind CSS.
   - PWA support (`manifest.json`, `sw.js` for offline shell).
   - Interactive "Vista Escritorio / Vista Móvil en Terreno" toggle with mobile device frame simulator.
   - R4R Queue with countdown/inactivity safeguard demonstrating zero auto-approval.
   - Human Review Modal (approval signature / mandatory non-empty `rejected_reason`).
   - Living Memory Inspector with interactive v1 ➔ v2 step-by-step demonstration controller.
2. **Backend & Agent Engine Layer (FastAPI & Python stdlib)**:
   - FastAPI REST API + standalone Python stdlib resilience for offline sandboxes.
   - Deterministic pre-filtering in Python keeping callable tool outputs `<150 tokens`.
   - Living Memory distillation engine keeping distilled operational rules `<80 tokens`.
   - Dual Engine: Zero-Token Deterministic Local Engine (default fallback, 100% offline reproducible) + Google Gemini 2.5 Flash Function Calling.
3. **Data & Persistence Layer (`data/`)**:
   - `flota_camiones.csv` & `.json`: 7 fleet vehicles, maintenance locks (CAM-04 brake failure), locations, and slots.
   - `restricciones_viales_urbanas.csv` & `.json`: Municipal ordinances, daytime bans (Santiago Centro >5,000 kg 07:30–21:00), port slot rules, HAZMAT prohibitions.
   - `bitacora_memoria_viva.json` & SQLite `agyx.db`: Persistent store for R4R proposals, supervisor audit trails, and distilled feedback rules.

---

## Feature Inventory
Every feature from the Survey phase appears here with its assigned milestone:
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Data Sources & Datasets | Structured CSV & JSON datasets for fleet, urban restrictions, and living memory | M1 | ORIGINAL_REQUEST §R1.2 |
| 2 | Token Optimization Core | Deterministic pre-filtering and token counting utilities (<150 tokens tools, <80 tokens memory) | M1 | ORIGINAL_REQUEST §R1.1 |
| 3 | Callable Tool: `consultar_flota_disponible` | Pre-filters trucks by weight/volume, flags CAM-04 brake failure, checks next-day slots | M2 | ORIGINAL_REQUEST §R1.3 |
| 4 | Callable Tool: `verificar_factibilidad_ruta_urbana` | Validates zone, weight, time window, HAZMAT rules, and active living memory lessons | M2 | ORIGINAL_REQUEST §R1.3 |
| 5 | Callable Tool: `generar_propuesta_r4r` | Calculates cost and SLA, persists proposal strictly in `R4R` with `auto_approved=False` | M2 | ORIGINAL_REQUEST §R1.3 |
| 6 | Zero-Token Deterministic Local Engine | Fully deterministic offline execution of the 6 test cases with 0 billed tokens | M2 | ORIGINAL_REQUEST §R1.1 |
| 7 | Gemini 2.5 Flash Function Calling Engine | Integration declarations and function calling handler for Google Gemini API | M2 | ORIGINAL_REQUEST §R1.1 |
| 8 | Living Memory Distillation & Injection | Distills supervisor rejections to <80 tokens and injects into prompt and route checks | M2 | ORIGINAL_REQUEST §R1.1, R2 |
| 9 | R4R State Machine & Zero Auto-Approval | Enforces `R4R` state lock indefinitely upon operator inactivity (`auto_approved=False`) | M3 | ORIGINAL_REQUEST §R1.1, R2 |
| 10 | Human Review API with Mandatory Reason | Supervisor approve (signature/timestamp) and reject (mandatory non-empty reason) | M3 | ORIGINAL_REQUEST §R2 |
| 11 | FastAPI Application & REST Endpoints | Complete REST endpoints for dispatch, R4R queue, review, memory, fleet, demo | M3 | ORIGINAL_REQUEST §R1, R2 |
| 12 | Mobile-First UI with Desktop/Mobile Toggle | Tailwind CSS UI with phone frame simulator for video demo presentation | M4 | ORIGINAL_REQUEST §R2 |
| 13 | R4R Queue & Live Inactivity Safeguard | Visual queue with countdown timer proving zero auto-approval on inactivity | M4 | ORIGINAL_REQUEST §R2 |
| 14 | Human Review Modal & Living Memory Inspector | Review modal with rejection validation and live inspector of learned rules | M4 | ORIGINAL_REQUEST §R2 |
| 15 | 6 Test Cases Matrix (Cases 1–6) | Implementation and verification of the 6 cases including Case 3 v1->v2 iteration | M5 | ORIGINAL_REQUEST §R3 |
| 16 | Automated Test Suite (`verify_all.py` / `pytest`) | 10 automated test suites exiting with code 0 without external network dependencies | M5 | ORIGINAL_REQUEST §R3 |
| 17 | Deliverable: `matriz_6_pruebas.csv` & `.html` | Full 7-column test matrix with Case 3 v1/v2 comparison and operational metrics | M6 | ORIGINAL_REQUEST §R3 |
| 18 | Deliverable: `ficha_diseno_certamen2.html` & `.md` | Academic design document strictly formatted for <= 4 printed pages PDF export | M6 | ORIGINAL_REQUEST §R3 |
| 19 | Deliverable: `google_ai_studio_pack/` | System instruction, OpenAPI tool declarations, sample prompts, and few-shot examples | M6 | ORIGINAL_REQUEST §R3 |
| 20 | Deliverable: `guion_video_demo.md` | Minute-by-minute script (3–5 min) covering all rubric requirements and demo actions | M6 | ORIGINAL_REQUEST §R3 |
| 21 | Full E2E Verification & Forensic Audit Pass | End-to-end integration pass and clean forensic integrity audit | Final | Workflow Protocol |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| **M1** | Data Sources, Tools & Dual Engine | Structured data in `data/`, callable tools (`consultar_flota`, `verificar_ruta`, `generar_propuesta`), token budgets, Living Memory distillation, Local Engine & Gemini engine | none | DONE |
| **M2** | FastAPI Backend, R4R State Machine & Mobile Web UI | REST API endpoints, zero auto-approval guard, rejection validation, Tailwind CSS PWA, desktop/mobile toggle, countdown indicator, review modal, Living Memory inspector | M1 | IN_PROGRESS |
| **M3** | 6 Test Cases Suite & Certamen 2 Deliverables | Automated test suites in `tests/`, `verify_all.py` standalone runner (exit code 0), `entregables/` (`matriz_6_pruebas.csv/.html`, `ficha_diseno_certamen2.html/.md` <=4 pages, `google_ai_studio_pack/`, `guion_video_demo.md`) | M1, M2 | PLANNED |
| **Final** | Full E2E Verification & Forensic Integrity Audit | 100% test pass on all 6 cases (v1 and v2), adversarial coverage hardening, forensic integrity audit check | M1, M2, M3 | PLANNED |

---

## Interface Contracts

### 1. `consultar_flota_disponible`
- **Inputs**: `peso_kg: float`, `volumen_m3: float = 0.0`, `fecha_despacho: Optional[str] = None`, `hora_despacho: Optional[str] = None`, `truck_id_preferido: Optional[str] = None`
- **Output**:
  ```json
  {
    "status": "OK",
    "candidatos": [{"id": "CAM-02", "modelo": "Atego 5t", "cap_kg": 5000, "disp": "INMEDIATA"}],
    "proxima_reserva": null,
    "bloqueos_mantenimiento": [{"id": "CAM-04", "bloqueado": true, "motivo": "Falla frenos"}]
  }
  ```
- **Error Handling**: When `truck_id_preferido == "CAM-04"`, flags critical brake failure lock.

### 2. `verificar_factibilidad_ruta_urbana`
- **Inputs**: `origen: str`, `destino_comuna: str`, `peso_kg: float`, `hora_solicitada: str`, `tipo_carga: str = "GENERAL"`, `living_memory_active: bool = False`
- **Output**:
  ```json
  {
    "factible": false,
    "zona": "SANTIAGO_CENTRO",
    "motivo": "Excede 5.000 kg en horario 07:30-21:00",
    "leccion_memoria_viva": "[SANTIAGO_CENTRO] >5t prohibido 07:30-21:00. Solución: 21:30+ o split 2x5t",
    "acciones_mitigacion": ["REPROGRAMAR_NOCTURNO_2130", "SUBDIVIDIR_2X_5T"]
  }
  ```
- **Error Handling**: Blocks HAZMAT loads with `bloqueo_legal: "CARGA_PELIGROSA_NO_AUTORIZADA"`.

### 3. `generar_propuesta_r4r`
- **Inputs**: `case_id: str`, `camiones_asignados: List[str]`, `origen: str`, `destino: str`, `fecha_hora_programada: str`, `tarifa_base_clp: float`, `recargo_clp: float = 0.0`, `sla_horas: float = 2.0`, `estado_caso: str = "R4R"`, `observaciones: str = ""`, `campos_faltantes: Optional[List[str]] = None`
- **Output**:
  ```json
  {
    "propuesta_id": "PROP-20261020-CASO1",
    "estado": "R4R",
    "auto_approved": false,
    "camiones": ["CAM-02"],
    "total_clp": 65000,
    "sla_horas": 2.5,
    "requiere_firma_humana": true
  }
  ```
- **Invariant**: `auto_approved` is unconditionally `False`.

### 4. `POST /api/r4r/review`
- **Payload**:
  ```json
  {
    "case_id": "CASO-3",
    "action": "REJECT",
    "supervisor_name": "Carlos Morales",
    "rejected_reason": "Ordenanza Santiago Centro prohíbe camiones >5.000 kg..."
  }
  ```
- **Validation**:
  - If `action == "REJECT"` and `rejected_reason` is empty or whitespace: returns HTTP 400/422 Bad Request. Case remains in `R4R`.
  - If valid rejection: transitions case to `REJECTED`, distills rule, stores in `bitacora_memoria_viva.json` / SQLite.

---

## Code Layout
```
/Users/nicolas/Desktop/Agyx/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application, static files mount, API router
│   ├── config.py                   # Configuration constants and file paths
│   ├── models/                     # Data schemas (dispatch, review, fleet, restrictions, memory)
│   ├── services/                   # Business logic (fleet_service, restriction_service, memory_service, r4r_service)
│   ├── tools/                      # Callable tools (callable_tools.py, token_optimizer.py)
│   ├── engine/                     # Dual engines (local_engine.py, gemini_engine.py)
│   ├── api/                        # REST API route handlers
│   ├── templates/                  # Jinja2 / HTML5 templates (index.html)
│   └── static/                     # Tailwind CSS fallback, JS controller, PWA icons & manifest
├── data/                           # CSV and JSON datasets, SQLite database
│   ├── flota_camiones.csv & .json
│   ├── restricciones_viales_urbanas.csv & .json
│   ├── bitacora_memoria_viva.json
│   └── agyx.db
├── tests/                          # Automated test suite
│   ├── test_cases.py
│   ├── test_governance.py
│   ├── test_token_budgets.py
│   └── verify_all.py               # Standalone runner with exit code 0
├── entregables/                    # Certamen 2 deliverables
│   ├── matriz_6_pruebas.csv & .html
│   ├── ficha_diseno_certamen2.html & .md
│   ├── google_ai_studio_pack/
│   └── guion_video_demo.md
├── requirements.txt
└── README.md
```
