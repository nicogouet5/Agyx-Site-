# Auditoría técnica — Framework y evolución de Agyx

**Fecha:** 21 de octubre de 2026  
**Alcance:** código en `app/`, `api/`, configuración Vercel, dependencias, pruebas y despliegue público. No se realizó una auditoría legal de las ordenanzas ni una prueba de carga contra producción.

## Dictamen ejecutivo

**FastAPI es una elección correcta para el prototipo académico y para el núcleo de reglas de Agyx.** Es ligero, permite exponer una API Python, documentar contratos OpenAPI y conserva muy bien la lógica determinista de flota, restricciones y R4R. No hay una razón técnica para reescribir el backend ahora.

Sin embargo, el producto mezcla dos objetivos distintos:

1. **Demo/certamen reproducible:** el stack actual los cumple bien: `145/145` pruebas pasan con `python3 tests/verify_all.py` y el despliegue responde `200` en `/api/health`.
2. **Software operativo que autoriza despachos y guarda auditoría:** el stack actual **no está listo**. El riesgo principal no es FastAPI, sino ejecutar estado crítico en SQLite/JSON dentro de Vercel Serverless, sin autenticación ni autorización.

**Recomendación:** mantener FastAPI y evolucionar alrededor de él. Antes de conectar datos reales o permitir decisiones reales, resolver persistencia, identidad, control de acceso, validación tipada y operación segura.

---

## Requerimientos identificados y nivel de cumplimiento

Los requerimientos se infirieron de `README.md` y `PROJECT.md`: evaluación de factibilidad, bloqueo de riesgo, R4R sin autoaprobación, rechazo con motivo, memoria viva, UI/PWA, API y ejecución reproducible.

| Requerimiento | Evidencia | Estado para demo | Estado operativo |
|---|---|---:|---:|
| Motor de reglas de flota/ruta y bloqueos | `app/engine/local_engine.py`, servicios y herramientas | Cumple | Parcial: reglas y datos son estáticos/de demostración |
| R4R: sin aprobación automática | guardas en modelos, servicio y `CHECK (auto_approved = 0)` | Cumple | Parcial: cualquiera puede invocar la aprobación |
| Rechazo con razón no vacía | `routes_r4r.py`, `models/review.py` | Cumple | Parcial: falta identidad verificable y trazabilidad inmutable |
| Memoria persistente y auditabilidad | SQLite + JSON | Cumple localmente | No cumple en Vercel Serverless: `/tmp` no es persistencia durable |
| API web y frontend responsivo/PWA | FastAPI + HTML/JS/CSS + SW | Cumple | Parcial: frontend monolítico y dependiente de CDNs |
| IA Gemini con function calling | `engine/gemini_engine.py` | Parcial | No verificable: `google-genai` no está en `requirements.txt`; además no existe ciclo agente-herramienta-respuesta |
| Seguridad para uso real | CORS abierto, API pública | No aplica al certamen | No cumple |
| Calidad automatizada | `tests/verify_all.py` | Cumple (145 pruebas) | Parcial: no cubre auth, concurrencia, persistencia serverless, E2E real ni carga |

---

## Lo que está bien del framework actual

### Backend: FastAPI + Python

- **Adecuado al dominio:** las reglas de factibilidad, R4R y procesamiento de datos son deterministas y están en Python; FastAPI evita incorporar complejidad innecesaria.
- **Separación razonable para un prototipo:** rutas, servicios, herramientas, modelos y motores están en carpetas separadas (`app/api`, `services`, `tools`, `engine`, `models`).
- **Controlador reutilizable:** los controladores retornan `(status_code, data)`, por lo que existe una ruta alternativa de stdlib además de FastAPI. Es útil para el contexto académico/offline.
- **Invariantes valiosos:** la prohibición de `auto_approved=True` aparece tanto en modelos como en SQLite y en la capa de rutas.
- **Despliegue simple:** `api/index.py` y `vercel.json` permiten publicar sin administrar servidores.

### Frontend/PWA

- La interfaz satisface bien el objetivo de demo: visualiza flota, cola R4R, mapa y los casos de prueba.
- El service worker es *network-first*, una decisión más segura que cache-first para no presentar datos operativos obsoletos como actuales.
- El frontend ya usa `escapeHtml` en varios valores procedentes de API al construir tarjetas, una buena base de seguridad de presentación.

---

## Pain points y riesgos priorizados

### P0 — bloquear antes de uso operativo

#### 1. La persistencia de auditoría no es durable en Vercel

**Evidencia:** `app/config.py` copia `agyx.db` y `bitacora_memoria_viva.json` a `/tmp/agyx_data` cuando detecta Vercel. El filesystem de una función serverless es efímero y no se comparte de forma garantizada entre instancias o despliegues.

**Impacto:** una aprobación, rechazo o regla de memoria puede desaparecer, divergir entre instancias o volver al estado semilla. Esto invalida la promesa de “Memoria Viva” y la bitácora si se usa operativamente.

**Mejora:** sustituir SQLite/JSON runtime por PostgreSQL gestionado (Neon, Supabase, RDS, etc.). Usar migraciones (Alembic), transacciones y una tabla de eventos de auditoría *append-only*. Conservar SQLite únicamente para demo local/offline.

#### 2. No existe autenticación, autorización ni identidad real

**Evidencia:** `app/main.py` permite CORS para todos los orígenes y las rutas `/api/r4r/review`, `/api/memory/reset` y `/api/memory/seed` son públicas. El propio README describe la firma como nombre declarado.

**Impacto:** cualquier visitante puede aprobar/rechazar una propuesta, resetear memoria o sembrar reglas. R4R no es una salvaguarda efectiva mientras el aprobador no sea verificable.

**Mejora:** integrar OIDC (Auth0, Clerk, Supabase Auth, Azure AD/Google Workspace según organización), RBAC (`dispatcher`, `supervisor`, `admin`, `viewer`) y auditoría con `user_id`, rol, IP/metadatos y correlación de solicitud. Deshabilitar endpoints de demo/reset en producción y restringir CORS a dominios propios.

#### 3. Datos de ruta, congestión y regulación son simulados/estáticos

**Evidencia:** `app/services/geo_service.py` declara nodos, coordenadas y congestión en código; `resolve_destination` resuelve explícitamente la referencia de demostración Lira 953. Los CSV/JSON son datasets locales.

**Impacto:** el mapa puede dar una apariencia de decisión en tiempo real que no posee. Un despacho real basado en estos datos puede incumplir restricciones o SLA.

**Mejora:** etiquetar explícitamente la UI como “simulación” hasta integrar fuentes versionadas y con fecha de vigencia: geocodificación, telemática/estado de flota, tráfico/ruteo y fuente legal validada. Agregar `source`, `fetched_at`, `valid_until`, nivel de confianza y regla de bloqueo cuando una fuente crítica esté vencida.

### P1 — alta prioridad para robustez y fluidez

#### 4. Contratos HTTP sin validación Pydantic efectiva

**Evidencia:** aunque `pydantic` está en `requirements.txt`, los endpoints reciben `Request` y ejecutan `await request.json()`; luego validan manualmente diccionarios. Los modelos de `app/models/` son dataclasses. En el ambiente auditado FastAPI no estaba instalado, por lo que las pruebas pasan por la capa independiente del framework.

**Impacto:** OpenAPI pierde esquemas de entrada/salida útiles; hay validación dispersa, errores inconsistentes y menor calidad de SDK/documentación.

**Mejora:** definir `BaseModel` Pydantic por comando y respuesta (`EvaluateDispatchRequest`, `ReviewProposalRequest`, etc.), declararlos en las firmas de FastAPI y responder modelos tipados. Mantener los servicios sin dependencia de HTTP. Esto reduce código repetido y hace la API más predecible.

#### 5. El “motor Gemini” no es un ciclo de function calling completo

**Evidencia:** `app/engine/gemini_engine.py` realiza una generación, ejecuta localmente los `function_calls` que hayan llegado y después evalúa siempre con `LocalAgentEngine`; no envía los resultados de herramientas de regreso a Gemini para una respuesta final. Tampoco `google-genai` está declarado en `requirements.txt`.

**Impacto:** con una clave configurada, el producto puede anunciar Gemini pero caer a fallback o gastar tokens sin afectar la decisión. El comportamiento no está probado con el proveedor real.

**Mejora:** decidir uno de estos diseños y hacerlo explícito:

- **Recomendado para decisiones críticas:** motor determinista como autoridad; LLM sólo explica, resume o propone alternativas sin capacidad de aprobar/persistir. No llamar Gemini si no añade valor.
- **Asistido por LLM:** agregar `google-genai` como dependencia opcional/versionada, timeout/retry/circuit breaker, límites de costo y un bucle de tool calling con máximo de iteraciones. Validar todas las salidas del LLM contra los mismos esquemas y reglas deterministas antes de persistir.

#### 6. SQLite y acceso síncrono dentro de endpoints `async`

**Evidencia:** rutas `async` llaman servicios que abren conexiones `sqlite3` sincrónicas. Hay además creación de schema duplicada en `db_service.py` y `r4r_service.py`.

**Impacto:** bajo concurrencia, el event loop puede bloquearse y SQLite puede devolver bloqueos. La duplicación incrementa el riesgo de drift del schema.

**Mejora:** con PostgreSQL usar SQLAlchemy 2 async o psycopg con pool y una única capa de repositorios/migraciones. Si se mantiene SQLite para demo, ejecutar I/O en threadpool, habilitar pruebas de concurrencia y centralizar el DDL en migraciones.

#### 7. Frontend difícil de mantener

**Evidencia:** `app/static/js/app.js` tiene ~2.028 líneas y `index.html` ~1.116. Estado, fetch, renderizado, mapa y flujo de revisión coexisten en archivos grandes.

**Impacto:** cambios pequeños tienen alto riesgo de regresión, pruebas unitarias del cliente son difíciles y la UX se vuelve menos fluida al crecer.

**Mejora gradual (sin reescritura inmediata):** separar en módulos ES: `api-client`, `store`, `r4r-view`, `map-view`, `memory-view`, `demo`. Luego evaluar React/Vue/Svelte sólo si se suman usuarios, vistas y flujos complejos. Para la UI actual, JavaScript modular es suficiente y tiene menor costo de migración.

#### 8. Dependencia de CDN y experiencia offline incompleta

**Evidencia:** `index.html` carga Tailwind Play CDN y Leaflet desde `unpkg`. La PWA cachea el shell, pero no esas dependencias ni los tiles de mapa. El fallback offline de `/api/*` devuelve HTTP 200 con un objeto de error.

**Impacto:** un usuario offline puede recibir una interfaz parcial y el cliente puede interpretar una falla como respuesta exitosa. Tailwind Play CDN tampoco es la recomendación para producción.

**Mejora:** compilar Tailwind en CSS local, empaquetar Leaflet o usar import map/bundler, definir una página offline clara y devolver `503`/un contrato `{ offline: true }` que el cliente trate como error. Para operaciones offline reales, usar una cola local explícita y sincronización idempotente; nunca simular que una aprobación se guardó cuando no ocurrió.

### P2 — calidad, seguridad y operación

- **Observabilidad insuficiente:** los `except Exception` frecuentemente devuelven `str(e)` al cliente o silencian la falla. Agregar logging estructurado, `request_id`, Sentry/OpenTelemetry, métricas de latencia/error y alertas. Nunca exponer detalles internos en producción.
- **Sin límites de abuso:** agregar rate limiting, tamaño máximo de body, timeouts, encabezados de seguridad y protección CSRF si se utiliza autenticación por cookie.
- **Artefactos runtime en Git:** `data/agyx.db` está versionado. Es razonable como fixture académico, pero separar seed/demo de datos runtime y evitar que contenga datos personales o de operación.
- **Pruebas sesgadas a la rúbrica:** los 145 tests son una buena base, pero no prueban persistencia multiinstancia, recuperación ante caída, autorización por rol, XSS E2E, proveedor Gemini, migraciones ni carga.
- **Mantenibilidad de la documentación:** `PROJECT.md` declara hitos “IN_PROGRESS/PLANNED” mientras README comunica entregables completos. Unificar fuente de verdad, estado y arquitectura real.

---

## Arquitectura objetivo recomendada

```text
Navegador / PWA
  └─ Frontend modular (Tailwind compilado, cliente API tipado)
       └─ HTTPS / API FastAPI
            ├─ OIDC + RBAC + rate limit + audit context
            ├─ Pydantic request/response contracts
            ├─ Motor determinista de elegibilidad (autoridad)
            ├─ Servicio LLM opcional: explicación/propuesta, nunca autoridad
            ├─ Integraciones: tráfico, geocoding, telemática, normativa
            └─ Repository / Unit of Work
                 └─ PostgreSQL gestionado
                      ├─ propuestas + transiciones R4R
                      ├─ audit_events append-only
                      ├─ memoria viva versionada
                      └─ datos fuente con vigencia/procedencia
```

**Principio clave:** el LLM nunca debe cambiar directamente el estado de despacho. Sólo el flujo de estado del backend, autorizado y transaccional, puede pasar `R4R → APPROVED/REJECTED`.

---

## Plan de mejora priorizado

### Fase 0 — 1 a 2 días: honestidad y protección mínima

1. Mostrar una etiqueta inequívoca **“Entorno demo / datos simulados”** mientras no existan integraciones reales.
2. Proteger o despublicar `/api/memory/reset`, `/api/memory/seed` y la ejecución de demos en producción.
3. Restringir CORS a la URL de producción/desarrollo; no usar `*` en un producto autenticado.
4. Fijar versiones de dependencias y añadir `google-genai` sólo si Gemini será parte del producto. Añadir `uvicorn` como dependencia de desarrollo/ejecución local.
5. Configurar logs seguros y no devolver excepciones internas.

**Resultado:** reduce la posibilidad de presentar o alterar la demo como sistema operativo real.

### Fase 1 — 1 a 2 semanas: hacer el backend confiable

1. Migrar estado persistente a PostgreSQL gestionado; modelar transiciones y auditoría append-only.
2. Implementar autenticación y RBAC; registrar identidad verificable de la revisión.
3. Reemplazar bodies manuales por Pydantic y publicar OpenAPI con contratos completos.
4. Implementar migraciones, health/readiness checks y configuración por ambiente.
5. Añadir pruebas de integración contra Postgres efímero: doble aprobación simultánea, permisos, rollback, idempotencia y reinicios.

**Criterio de salida:** una revisión no puede ser ejecutada por un visitante anónimo y sobrevive a un cold start/redeploy.

### Fase 2 — 2 a 4 semanas: datos operativos y UX fluida

1. Integrar fuentes reales por adaptadores; exponer procedencia/frescura y fallback seguro.
2. Modularizar el frontend sin forzar un cambio de framework. Añadir pruebas de UI para R4R y errores de red.
3. Compilar/assets locales para Tailwind y Leaflet; definir offline realista.
4. Agregar observabilidad, rate limits, SLOs y backup/retención de auditoría.

### Fase 3 — posterior: IA controlada

1. Medir si el LLM aporta valor frente a reglas deterministas.
2. Si se conserva Gemini, instrumentar costo/latencia/calidad, tool calling multi-turn limitado y evaluación con casos adversariales.
3. Aplicar guardrails: datos mínimos, redacción de PII, validación estructural y aprobación humana obligatoria.

---

## Decisión de framework

| Decisión | Recomendación | Motivo |
|---|---|---|
| Backend | **Mantener FastAPI** | Encaja con Python, reglas, APIs, tipado futuro y despliegue serverless/contenedor. El problema actual no es el framework. |
| Persistencia | **Cambiar SQLite/JSON runtime por Postgres** | Necesario para concurrencia, durabilidad, auditoría y escalamiento. |
| Frontend | **Modularizar vanilla JS primero; migrar a React/Next sólo si crece** | Evita una reescritura costosa; el pain point actual es tamaño/acoplamiento, no la ausencia de React. |
| Hosting | **Vercel puede quedar para frontend/API liviana; evaluar contenedor para workers/integraciones** | Las operaciones persistentes/asíncronas y conectores suelen ser más predecibles en Cloud Run, Render, Fly.io o una API desplegada como contenedor. |
| LLM | **No usarlo como autoridad operacional** | Las reglas y el estado R4R deben ser deterministas, auditables y reproducibles. |

---

## Verificaciones realizadas

- `python3 tests/verify_all.py`: **145 tests, OK**.
- `https://agyx-fletes.vercel.app/api/health`: respondió **HTTP 200** durante la auditoría.
- Revisión estática de rutas, configuración, motores, persistencia, PWA y dependencias.

Estas verificaciones confirman que la demo funciona y que su suite cubre los casos declarados; no certifican seguridad, cumplimiento legal, disponibilidad, exactitud de tráfico o preparación productiva.
