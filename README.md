# Agyx — Agente Operativo de IA para Factibilidad de Despacho, Flota y Rutas Pesadas (Grupo 2)

Prototipo funcional desarrollado para el **Certamen 2** del proyecto semestral integrador **"Software Logístico Pymes-Fletes" (Grupo 2)**.

---

## 1. Características Principales y Cumplimiento de Rúbrica (100 pts)

1. **Alineación Directa con los Actos 3 y 4:**
   - Resuelve los dos *Pain Points* principales del proyecto: **(1) Planificación de rutas urbanas para vehículos con carga pesada (camiones en Santiago Centro)** y **(2) Solicitudes cuando la flota clave está en ruta o en mantenimiento crítico (`CAM-04` con falla de frenos)**, activando además la rama *"SI: Reserva de pedido (otro día)"* del Acto 4.
2. **Gobernanza Estricta `R4R` (`Ready for Review`) — Cero Auto-Aprobación:**
   - Toda evaluación del agente se persiste en base de datos (`data/agyx.db`) con `estado = "R4R"` y restricción SQL `CHECK (auto_approved = 0)`.
   - Ante inactividad del supervisor humano, la orden permanece bloqueada en `R4R` indefinidamente y **jamás se aprueba ni despacha sola**.
3. **Rechazo con `rejected_reason` Obligatorio y Bitácora / Memoria Viva (`<80 tokens`):**
   - Si el Coordinador de Tráfico rechaza una propuesta en `R4R`, el sistema exige un `rejected_reason` no vacío (`HTTP 400/422` si se omite o contiene solo espacios).
   - El motivo del rechazo se destila automáticamente en una regla compacta (`<80 tokens`) dentro de `data/bitacora_memoria_viva.json` y retroalimenta al agente en futuras ejecuciones (demostrado en vivo en la iteración del **Caso 3: `v1 ➔ v2`**).
4. **Arquitectura Python + FastAPI + Optimización de Tokens + Adaptación Móvil (PWA):**
   - Herramientas verificables (`consultar_flota_disponible`, `verificar_factibilidad_ruta_urbana`, `generar_propuesta_r4r`) con pre-filtrado determinista en Python (`<150 tokens` por llamada).
   - Motor Dual: **Motor Determinista 0-Tokens** (funciona sin conexión ni claves de API para que el profesor evalúe el proyecto de inmediato) + **Motor Google Gemini 2.5 Flash con Function Calling** (activable opcionalmente con `GEMINI_API_KEY`).
   - Interfaz Web **Mobile-First / PWA** con conmutador en pantalla **"Vista Escritorio / Vista Móvil en Terreno"**.

---

## 2. Ejecución Rápida (Sin Contraseñas ni Claves de API)

### A. Ejecutar la Verificación Automatizada Completa (6 Casos + Iteración `v1 ➔ v2` + 135+ Tests)
```bash
python3 tests/verify_all.py
```

### B. Levantar la Aplicación Web Interactiva (FastAPI / Servidor Integrado)
```bash
python3 -m app.main
```
Luego abrir en el navegador: **`http://localhost:8000`**

*(Opcional: Si tienes `uvicorn` instalado, también puedes correr `uvicorn app.main:app --reload --port 8000`)*.

---

## 3. Estructura de Entregables del Certamen 2 (`entregables/`)

| Entregable | Archivo en el Repositorio | Descripción |
|---|---|---|
| **A. Ficha de Diseño (<= 4 páginas PDF)** | `entregables/ficha_diseno_certamen2.html` y `entregables/ficha_diseno_certamen2.md` | Documento de 4 páginas A4 listo para `Imprimir -> Guardar como PDF` desde cualquier navegador. |
| **B. Matriz de las 6 Pruebas + Iteración** | `entregables/matriz_6_pruebas.csv` y `entregables/matriz_6_pruebas.html` | Matriz con las 7 columnas oficiales de la pauta, los 6 casos distintos (`v1`), la repetición verificada del Caso 3 (`v2`) y las conclusiones. |
| **C. Guion para el Video de Ejecución Real** | `entregables/guion_video_demo.md` | Guion cronometrado (3 min 30 seg) indicando qué clic hacer y qué explicar en cada sección. |
| **D. Pack para Google AI Studio / Dify** | `entregables/google_ai_studio_pack/` | Instrucciones del sistema (`v1` y `v2`), declaraciones OpenAPI de herramientas (`function_declarations.json`) y prompts de los 6 casos. |
