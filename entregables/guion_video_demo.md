# Guion Paso a Paso para el Video de Ejecución Real — Certamen 2 (Agyx · Grupo 2)

- **Duración objetivo:** 3 minutos 30 segundos (breve, directo y enfocado 100% en la rúbrica).
- **Formato recomendado:** Grabación de pantalla (OBS / Loom / QuickTime) con la Web App de **Agyx** corriendo en `http://localhost:8000` (levantada con `python3 -m app.main`). Subir a YouTube como **No listado** o **Público** y verificar que `alonsoastroza@gmail.com` tenga acceso.

---

## Preparación antes de grabar (30 segundos)
1. En una terminal dentro de `/Users/nicolas/Desktop/Agyx`, ejecuta:
   ```bash
   python3 -m app.main
   ```
2. Abre en el navegador `http://localhost:8000`.
3. Ten abiertas en pestañas al lado:
   - `entregables/matriz_6_pruebas.html` (Matriz visual de los 6 casos).
   - `entregables/ficha_diseno_certamen2.html` (Ficha de diseño de 4 páginas).

---

## Estructura Cronometrada del Video (Qué mostrar y qué decir)

### 1. Problema de Negocio y Configuración del Agente (0:00 – 0:45)
- **En pantalla:** Muestra la pantalla principal de **Agyx** (`http://localhost:8000`), la pestaña de **Flota y Restricciones** (`flota_camiones.csv` con `CAM-04` bloqueado por falla de frenos y `restricciones_viales_urbanas.csv` con la ordenanza de Santiago Centro `>5.000 kg` prohibido `07:30–21:00 hrs`) y haz clic en el botón **"Vista Móvil en Terreno (PWA)"** un par de segundos para mostrar que el Coordinador puede operar desde el celular en patio.
- **Qué explicar:**
  > *"Hola, somos el Grupo 2 del proyecto **Software Logístico Pymes-Fletes**. Construimos **Agyx**, un prototipo local en FastAPI que evalúa disponibilidad y mantenimiento de la flota de demostración y aplica reglas viales cargadas en archivos. La implementación demostrada usa un motor determinista con herramientas de consulta y deja las propuestas en **R4R (Ready for Review)**, sin auto-aprobación por inactividad. No consulta flota ni permisos reales."*

### 2. Ejecución de un Caso Normal + Salvaguarda de Inactividad R4R (0:45 – 1:25)
- **En pantalla:**
  1. Selecciona el **Caso 1 (Normal: 3.200 kg Quilicura ➔ Pudahuel a las 14:00 hrs)** (o el **Caso 2: Reserva para otro día** cuando la flota de 12t está en ruta) y haz clic en **Evaluar Orden**.
  2. Muestra la salida: asigna el camión `CAM-02` (5t), calcula `$65.000 CLP` y queda en la **Cola R4R** con `auto_approved = False`.
  3. Haz clic en el botón **"Simular Inactividad (72h)"** en el panel de salvaguarda para demostrar que aunque el humano no haga nada, la orden **nunca se auto-aprueba**. Luego haz clic en **Revisar ➔ Aprobar** ingresando el nombre del supervisor.
- **Qué explicar:**
  > *"En esta ejecución normal de 3.200 kg hacia Pudahuel, Agyx invoca `consultar_flota_disponible` y `generar_propuesta_r4r`, asignando el camión `CAM-02` de 5 toneladas. Observen que el estado queda bloqueado en `R4R`: si simulamos inactividad del operador, el sistema demuestra que `auto_approved` es siempre falso. Solo cuando el Coordinador firma la aprobación pasa a estado aprobado."*

### 3. Caso Límite + Mejora e Iteración Verificada `v1 ➔ v2` con Memoria Viva (1:25 – 2:25)
- **En pantalla:**
  1. Abre la pestaña **"Iteración Caso 3 (v1 ➔ v2)"** (o ejecuta primero el **Caso 4** de datos incompletos para mostrar cómo pide `peso_kg`, `direccion_exacta` y `hora_exacta`, y luego pasa al **Caso 3**).
  2. **Paso 1 (`v1` Pre-Mejora):** Ejecuta el **Caso 3 en modo `v1`** (9.500 kg hacia **Santiago Centro** a las **11:30 hrs**). Muestra cómo en `v1` el agente fallaba al asignar el camión `CAM-05` (12t) a las 11:30 AM ignorando la ordenanza municipal (`>5.000 kg` prohibido `07:30–21:00`).
  3. **Paso 2 (Rechazo Humano con `rejected_reason` obligatorio):** Abre el modal de revisión o ejecuta el Paso 2. Muestra que si intentas rechazar en blanco el sistema lo bloquea (`HTTP 422`), e ingresa el `rejected_reason`: *"Ordenanza Santiago Centro prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs. Reprogramar a ventana nocturna (21:30/06:00) o subdividir en 2 camiones de 5t"*. Muestra cómo aparece inmediatamente la regla destilada (`<80 tokens`) en el panel de **Memoria Viva**.
  4. **Paso 3 (`v2` Post-Mejora):** Re-ejecuta el mismo **Caso 3 en modo `v2`**. Muestra cómo ahora el agente lee la Memoria Viva, evita el horario diurno y propone **Ventana Nocturna (21:30 hrs)** o **Subdivisión en 2 camiones de 5t (`CAM-02 + CAM-03`)**.
- **Qué explicar:**
  > *"Para el caso límite y nuestra iteración documentada, probamos un pedido de 9.500 kg hacia Santiago Centro a las 11:30 AM. En la versión inicial `v1`, el agente fallaba asignando un camión de 12 toneladas al mediodía. Como supervisores humanos, rechazamos la orden R4R: el sistema exige obligatoriamente un `rejected_reason`, lo guarda en nuestra Bitácora de Memoria Viva en menos de 80 tokens y, al volver a ejecutar exactamente el mismo Caso 3 en `v2`, Agyx aplica la regla aprendida y propone reprogramar a ventana nocturna de las 21:30 hrs o dividir la carga en 2 camiones de 5 toneladas."*

### 4. Ejecución de un Caso Riesgoso / Fuera de Alcance (2:25 – 3:00)
- **En pantalla:**
  1. Haz clic en el **Caso 5 (Riesgoso: Forzar camión `CAM-04` con falla crítica de frenos)** y/o en el **Caso 6 (Ácido Sulfúrico — HAZMAT D.S. 298)**.
  2. Muestra el estado rojo **`BLOQUEADO_RIESGO`** con `camiones = []` y la derivación inmediata a Jefe de Taller / Gerencia.
- **Qué explicar:**
  > *"En el caso riesgoso, un operador presiona para despachar con el camión `CAM-04` que está en taller con falla crítica de frenos de aire —o intenta enviar ácido sulfúrico sin certificación D.S. 298—. Agyx bloquea tajantemente la asignación con estado `BLOQUEADO_RIESGO`, asigna cero camiones y escala el incidente a supervisión."*

### 5. Cierre: Qué está Simulado y Qué Limitaciones Siguen Abiertas (3:00 – 3:30)
- **En pantalla:** Muestra brevemente la Matriz de 6 Pruebas (`entregables/matriz_6_pruebas.html`) o la ejecución de `python3 tests/verify_all.py` en la terminal con todo en verde.
- **Qué explicar:**
  > *"En conclusión, pasamos de 5/6 casos cumplidos en `v1` a 6/6 casos (100%) en `v2`. Todo el motor de reglas, persistencia SQLite de la cola R4R y destilación de Memoria Viva funciona realmente; están simulados la telemetría GPS/frenos desde nuestro dataset y el envío externo de WhatsApp al cliente, que quedan como próximos pasos para conectar en producción. ¡Muchas gracias!"*
