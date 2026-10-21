"""Generate the Spanish hand-in PDFs from the reviewed Agyx deliverables.

Requires reportlab. The visual system follows the supplied one-page hand-in:
A4 paper, numbered section label, right-aligned SimpleTech logo, dark bands,
tabular content and a restrained accent colour (teal instead of magenta).
"""
from __future__ import annotations

import csv
import os
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent
LOGO = ROOT / "assets" / "simpletech-logo-000.png"
TEAM = "Nicolas Inostrosa · Felipe Gatica · Tomas Perez · Daniel Brambilla"
INK = colors.HexColor("#14222B")
TEAL = colors.HexColor("#087F8C")
PALE = colors.HexColor("#E8F4F4")
GRAY = colors.HexColor("#52616A")
LIGHT = colors.HexColor("#F2F5F6")

FONT_DIR = Path(os.environ.get("AGYX_FONT_DIR", "/usr/share/fonts/truetype/dejavu"))
if (FONT_DIR / "DejaVuSans.ttf").exists():
    pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
elif Path("/System/Library/Fonts/Supplemental/Arial.ttf").exists():
    pdfmetrics.registerFont(TTFont("DejaVu", "/System/Library/Fonts/Supplemental/Arial.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"))
pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold")

ST = {
    "body": ParagraphStyle("body", fontName="DejaVu", fontSize=8.6, leading=12.8, textColor=INK, spaceAfter=6),
    "small": ParagraphStyle("small", fontName="DejaVu", fontSize=7.5, leading=11, textColor=INK, spaceAfter=4),
    "muted": ParagraphStyle("muted", fontName="DejaVu", fontSize=7.3, leading=10.5, textColor=GRAY, spaceAfter=5),
    "h": ParagraphStyle("h", fontName="DejaVu-Bold", fontSize=10.8, leading=14.2, textColor=TEAL, spaceBefore=13, spaceAfter=7),
    "cardtitle": ParagraphStyle("cardtitle", fontName="DejaVu-Bold", fontSize=8.5, leading=12.3, textColor=INK, spaceAfter=5),
    "white": ParagraphStyle("white", fontName="DejaVu-Bold", fontSize=8.4, leading=12, textColor=colors.white),
}


def p(text: str, kind="body") -> Paragraph:
    return Paragraph(text, ST[kind])


def bullet(text: str) -> Paragraph:
    return p("<font color='#087F8C'>■</font>  " + text)


def title_page(canvas, doc, label: str, title: str, subtitle: str):
    canvas.saveState()
    w, h = A4
    canvas.setFillColor(TEAL)
    canvas.rect(0, h - 7, w, 7, fill=1, stroke=0)
    canvas.setFont("DejaVu-Bold", 7)
    canvas.setFillColor(TEAL)
    canvas.drawString(44, h - 45, label.upper())
    canvas.setFillColor(INK)
    canvas.setFont("DejaVu-Bold", 17)
    canvas.drawString(44, h - 74, title)
    canvas.setFont("DejaVu", 8.7)
    canvas.setFillColor(GRAY)
    canvas.drawString(44, h - 92, subtitle)
    if LOGO.exists():
        canvas.drawImage(str(LOGO), w - 112, h - 99, width=61, height=68, mask="auto", preserveAspectRatio=True)
    canvas.setStrokeColor(TEAL)
    canvas.setLineWidth(1.5)
    canvas.line(44, 44, w - 44, 44)
    canvas.setFont("DejaVu", 6.9)
    canvas.setFillColor(GRAY)
    canvas.drawString(44, 30, "AGYX / SOFTWARE LOGÍSTICO PYMES-FLETES / CERTAMEN 2")
    canvas.drawRightString(w - 44, 30, str(doc.page))
    canvas.restoreState()


def build(name: str, label: str, title: str, subtitle: str, story: list, landscape=False):
    page_size = A4
    doc = SimpleDocTemplate(
        str(ROOT / name), pagesize=page_size,
        leftMargin=44, rightMargin=44, topMargin=116, bottomMargin=57,
        title=title, author=TEAM,
    )
    doc.build(story, onFirstPage=lambda c, d: title_page(c, d, label, title, subtitle),
              onLaterPages=lambda c, d: title_page(c, d, label, title, subtitle))


def section(label: str):
    return p(label.upper(), "h")


def band(label: str, content: str):
    table = Table([[p(label, "white"), p(content, "small")]], colWidths=[151, 356])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), INK),
        ("BACKGROUND", (1, 0), (1, 0), PALE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def matrix_row(label: str, content: str):
    table = Table([[p(label, "cardtitle"), p(content, "small")]], colWidths=[133, 374])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), LIGHT),
        ("LINEBELOW", (0, 0), (-1, -1), 0.35, colors.HexColor("#D0DADC")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


class WorkflowComparison(Flowable):
    """Two comparable, page-width workflow lanes for the design sheet."""

    def __init__(self):
        super().__init__()
        self.width = 507
        self.height = 146

    def draw(self):
        c = self.canv
        gap = 11
        box_width = (self.width - 3 * gap) / 4
        lanes = [
            ("ANTES / COORDINACIÓN MANUAL", 80, LIGHT, GRAY, [
                "Pedido por WhatsApp / planilla",
                "Coordinador revisa datos dispersos",
                "Asigna camión y horario manualmente",
                "Riesgo de restricción, espera o falla",
            ]),
            ("AHORA / CON AGYX", 9, PALE, TEAL, [
                "Pedido en formulario / API",
                "Valida datos, flota, zona y reglas",
                "Propone directo, reserva o bloqueo en R4R",
                "Persona aprueba o rechaza; aprende del rechazo",
            ]),
        ]
        card_style = ParagraphStyle(
            "workflow-card", fontName="DejaVu", fontSize=7.2, leading=10,
            textColor=INK, alignment=1,
        )
        for heading, y, fill, accent, labels in lanes:
            c.setFillColor(accent)
            c.setFont("DejaVu-Bold", 8)
            c.drawString(0, y + 57, heading)
            for index, label in enumerate(labels):
                x = index * (box_width + gap)
                c.setFillColor(fill)
                c.setStrokeColor(accent)
                c.roundRect(x, y, box_width, 49, 5, fill=1, stroke=1)
                para = Paragraph(label, card_style)
                _, text_height = para.wrap(box_width - 10, 43)
                para.drawOn(c, x + 5, y + (49 - text_height) / 2)
                if index < 3:
                    arrow_x = x + box_width + 2
                    c.setStrokeColor(accent)
                    c.setLineWidth(1)
                    c.line(arrow_x, y + 24.5, arrow_x + 7, y + 24.5)
                    c.line(arrow_x + 5, y + 27, arrow_x + 7, y + 24.5)
                    c.line(arrow_x + 5, y + 22, arrow_x + 7, y + 24.5)
        c.setFillColor(GRAY)
        c.setFont("DejaVu", 6.8)
        c.drawString(0, 0, "R4R = espera aprobación humana; el rechazo alimenta Memoria Viva para la próxima evaluación.")


def ficha():
    story = [
        band("PROPÓSITO", "Preparar propuestas de despacho para el Coordinador de Tráfico, con consulta de flota, radar táctico de rutas y restricciones urbanas y revisión humana obligatoria."),
        section("01 / Problema, usuario y alcance"),
        matrix_row("PROBLEMA", "Las pymes de fletes coordinan pedidos con información dispersa. Una carga pesada puede ser asignada a una zona restringida; además, la flota clave puede estar en ruta o en mantenimiento."),
        matrix_row("USUARIO", "Coordinador de Tráfico o Jefe de Operaciones, desde consola de comando o simulador móvil en terreno."),
        matrix_row("OBJETIVO", "Evaluar el pedido, recomendar despacho o reserva, pedir datos faltantes o bloquear riesgos. La propuesta permanece en R4R hasta una decisión humana."),
        section("02 / Workflow: antes y con Agyx"),
        WorkflowComparison(),
        section("03 / Qué funciona y qué se simula"),
        band("OPERATIVO", "Motor dual (Local determinista 0-tokens + Gemini Function Calling), 3 herramientas Python con presupuesto <150 tokens, API REST (/api/dispatch, /api/r4r, /api/tactical-network), Radar Táctico SVG y Memoria Viva."),
        Spacer(1, 6),
        band("SIMULADO", "Telemetría GPS/taller y perfiles de congestión horaria calculados sobre catálogo local demostrativo (Quilicura, Pudahuel, Maipú, Renca, Santiago Centro / Lira 953, Providencia, San Bernardo), sin sensores IoT en vivo."),
        Spacer(1, 10),
        p("<b>Equipo:</b> " + TEAM, "muted"),
        PageBreak(),
        section("04 / Instrucciones, datos y herramientas"),
        matrix_row("INSTRUCCIONES", "La tarea y las reglas están en el motor local y en el paquete de instrucciones v1/v2. La salida debe ser una propuesta R4R o una detención justificada; nunca un despacho automático."),
        matrix_row("DATOS", "<b>flota_camiones.csv/json:</b> 7 vehículos, incluido CAM-04 en taller. <b>restricciones_viales_urbanas.csv/json:</b> límites por zona. <b>SQLite y bitácora:</b> propuestas y rechazo humano."),
        matrix_row("HERRAMIENTAS", "consultar_flota_disponible, verificar_factibilidad_ruta_urbana y generar_propuesta_r4r. Todas cumplen presupuesto <150 tokens (69, 86 y 88 tokens medidos)."),
        matrix_row("RADAR TÁCTICO", "Centro de Comando inspirado en 'Dispatch' con red vial RM, congestión por franja horaria, bloqueo en Taller Renca (CAM-04) y polígono Santiago Centro (Lira 953: >5.000 kg prohibido 07:30–21:00)."),
        section("05 / Controles de seguridad"),
        bullet("CAM-04 con falla de frenos: <b>BLOQUEADO_RIESGO</b>; no se asigna vehículo ni sale de Taller Renca."),
        bullet("Ácido sulfúrico y otras cargas peligrosas (D.S. 298): <b>BLOQUEADO_RIESGO</b> y derivación."),
        bullet("Pedido sin peso/dirección/hora suficiente: <b>R4R_INFO_INCOMPLETA</b>."),
        bullet("La base exige auto_approved = 0; solo R4R permite aprobar o rechazar, y el rechazo exige motivo (HTTP 422 si vacío). El nombre declarado no autentica identidad."),
        section("06 / Configuración que puede revisarse"),
        p("Código y datos: <b>app/</b> y <b>data/</b>. Instrucciones reutilizables: <b>entregables/google_ai_studio_pack/</b>. Pruebas: <b>tests/verify_all.py</b>. El motor local garantiza reproducibilidad offline y el motor Gemini ejecuta Function Calling real si se provee GEMINI_API_KEY."),
        p("<b>Capturas de ejecución verificada:</b> caso normal evaluado en R4R y caso riesgoso detenido. Los datos son de demostración; estas capturas acompañan al repositorio y al prototipo desplegado.", "muted"),
        Image(str(ROOT / "evidencia" / "01_caso_normal_r4r.png"), width=400, height=120),
        p("Caso normal: CAM-02 en espera de revisión humana.", "muted"),
        Image(str(ROOT / "evidencia" / "02_caso_riesgoso_bloqueado.png"), width=400, height=92),
        p("Caso riesgoso: CAM-04 bloqueado, sin flota asignada.", "muted"),
        PageBreak(),
        section("07 / Seis casos y mejora"),
        matrix_row("1 · NORMAL", "3.200 kg Quilicura → Pudahuel. CAM-02, $65.000 CLP, R4R. Cumple."),
        matrix_row("2 · NORMAL", "10.000 kg con flota pesada en ruta. Reserva siguiente día a las 08:00, CAM-06, R4R. Cumple."),
        matrix_row("3 · LÍMITE", "9.500 kg hacia Santiago Centro a las 11:30. En v1 se propuso CAM-05 durante horario restringido: no cumple. Tras rechazo humano y regla de Memoria Viva, v2 propone 21:30 o split 2x 5t: cumple."),
        matrix_row("4 · LÍMITE", "Pedido sin peso, dirección exacta ni hora. R4R_INFO_INCOMPLETA y solicitud de datos. Cumple."),
        matrix_row("5 · RIESGO", "Forzar CAM-04 con falla crítica de frenos. BLOQUEADO_RIESGO, sin camiones. Cumple."),
        matrix_row("6 · RIESGO", "Ácido sulfúrico no autorizado (D.S. 298). BLOQUEADO_RIESGO, sin camiones. Cumple."),
        section("08 / Evidencia y conclusión"),
        band("RESULTADO", "5/6 casos cumplieron en v1 (83,3%); 6/6 tras la iteración del Caso 3 (100%). La suite integrada verificó 14/14 criterios y 145/145 pruebas automatizadas."),
        Spacer(1, 8),
        p("El principal fallo fue la asignación diurna de un camión de 12 t hacia Santiago Centro. Sin memoria, v2 retiene el pedido sin asignación. El rechazo humano registra una regla destilada (<80 tokens); solo entonces la repetición v2 propone ventana nocturna (21:30) o subdivisión 2x 5t. La matriz CSV conserva entrada, esperado, obtenido, cumplimiento, evidencia y ajuste."),
        p("<b>Comprobación cartográfica y táctica:</b> Lira 953 con 9.500 kg a las 11:30 se resuelve dentro del nodo SANTIAGO_CENTRO en el Radar Táctico. Sin memoria se retiene; tras rechazo y regla activa, traza ruta nocturna (21:30) o corredor dual 2x 5t en R4R."),
        PageBreak(),
        section("09 / Riesgos y límites abiertos"),
        matrix_row("DATOS", "La flota y restricciones son datos de demostración. No hay sensores IoT de frenos ni telemetría GPS satelital en vivo."),
        matrix_row("MAPA", "El Radar Táctico simula corredores viales y congestión horaria sobre una topología local de Santiago. El Coordinador debe contrastar permisos reales antes de aprobar."),
        matrix_row("GEMINI", "El repositorio opera por defecto con el motor determinista local (0 tokens) para garantizar 100% de reproducibilidad offline, e incluye soporte opcional para Gemini 2.5 Flash con Function Calling."),
        matrix_row("DESPACHO", "La revisión con nombre declarado cambia el estado en SQLite, sin autenticar identidad criptográfica ni disparar órdenes físicas o mensajes externos."),
        section("10 / Acceso y materiales de revisión"),
        bullet("Repositorio GitHub: <b>https://github.com/nicogouet5/Agyx-Site-</b>. Instalar <b>pip install -r requirements.txt</b>; iniciar <b>python3 -m app.main</b>; abrir http://localhost:8000."),
        bullet("Verificación automatizada: <b>python3 tests/verify_all.py</b> (14/14 criterios y 145/145 tests OK). Matriz: <b>matriz_6_pruebas.pdf/csv</b>. Evidencia JSON: <b>evidencia/corrida_6_casos.json</b>."),
        bullet("Despliegue público interactivo (Vercel): <b>https://agyx-fletes.vercel.app</b> (incluye Radar Táctico Dispatch, simulador móvil y acceso directo a los 3 PDFs en la barra superior)."),
        bullet("Guion y evidencia audiovisual: estructura minuto a minuto en <b>entregables/guion_video_demo.md</b> para contraste con la ejecución en vivo."),
        Spacer(1, 12),
        band("ENTREGA", "Subir PDF de esta ficha (4 páginas), matriz de 6 pruebas, guía README y enlaces de acceso reproducible a Canvas."),
        Spacer(1, 9),
        p("<b>Integrantes:</b> " + TEAM, "muted"),
    ]
    build("ficha_diseno_certamen2.pdf", "01 / Entregable requerido", "Ficha de diseño · Agyx", "Agente operativo para factibilidad de despacho / Grupo 2", story)


def matriz():
    with (ROOT / "matriz_6_pruebas.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    story = [band("COBERTURA", "6 casos distintos: 2 normales, 2 límite y 2 riesgosos. El Caso 3 se repite tras la mejora v1 → v2."), Spacer(1, 9)]
    keys = ["Entrada", "Resultado esperado", "Resultado obtenido", "Cumple / no cumple", "Evidencia", "Ajuste o pendiente"]
    labels = ["ENTRADA", "ESPERADO", "OBTENIDO", "CUMPLE", "EVIDENCIA", "AJUSTE"]
    for index, row in enumerate(rows):
        if index and index % 2 == 0:
            story.append(PageBreak())
        story.append(section(f"{index+1:02d} / {escape(row['Caso y tipo'])}"))
        for label, key in zip(labels, keys):
            story.append(matrix_row(label, escape(row[key])))
        story.append(Spacer(1, 8))
    build("matriz_6_pruebas.pdf", "02 / Entregable requerido", "Matriz de pruebas · Agyx", "Resultados esperados, observados y ajuste / Grupo 2", story)


def guia():
    story = [
        band("PROTOTIPO", "Agyx evalúa solicitudes de flete para pymes de Santiago con Radar Táctico interactivo y prepara propuestas con revisión humana obligatoria (R4R)."),
        section("01 / Capacidades"),
        bullet("Consulta flota de 7 vehículos y estado de mantenimiento; bloquea CAM-04 en Taller Renca por falla crítica de frenos."),
        bullet("Radar Táctico estilo 'Dispatch' con red vial de Santiago, congestión horaria en vivo y polígono de restricción en Santiago Centro (>5.000 kg 07:30–21:00)."),
        bullet("Clasifica pedidos incompletos (Caso 4) o peligrosos D.S. 298 (Caso 6) y guarda propuestas R4R en SQLite con auto_approved = False."),
        bullet("Registra rechazos humanos con motivo obligatorio y destila reglas (<80 tokens) en Memoria Viva para adaptar v1 → v2."),
        bullet("Reconoce Lira 953, Santiago dentro de la zona Santiago Centro y calcula rutas alternativas (ventana nocturna 21:30 o split 2x 5t)."),
        section("02 / Instalar y ejecutar"),
        band("REQUISITOS", "Python 3.9 o posterior. Desde la raíz del repositorio: python3 -m venv .venv; .venv/bin/python -m pip install -r requirements.txt."),
        Spacer(1, 6),
        band("INICIAR", "Ejecutar .venv/bin/python -m app.main. Abrir http://localhost:8000 (o visitar https://agyx-fletes.vercel.app). Si Uvicorn no está instalado, inicia el servidor HTTP integrado."),
        Spacer(1, 6),
        band("VALIDAR", "Ejecutar .venv/bin/python tests/verify_all.py (verifica los 14 criterios de aceptación y las 145 pruebas automatizadas)."),
        section("03 / Radar Táctico y Ejemplo Lira 953"),
        p("En el Centro de Comando superior o en el formulario, seleccionar cualquiera de las misiones (Casos 1–6 o <b>Lira 953 Centro</b>) y cambiar el selector de hora/tráfico (08:00, 11:30, 14:00, 15:00, 21:30). Con memoria limpia, Lira 953 (9.500 kg a las 11:30) se retiene sin camión; tras registrar el rechazo humano del Caso 3 y activar la regla, v2 traza la ruta nocturna (21:30) en R4R."),
        section("04 / Archivos y entrega"),
        p("<b>app/</b>: motor dual, servicio geoespacial, API y consola web. <b>data/</b>: flota, restricciones y bitácora. <b>tests/</b>: suite de 145 tests. <b>entregables/</b>: ficha PDF (4 págs), matriz PDF/CSV/HTML, pack de AI Studio y guion de video."),
        p("Repositorio público: https://github.com/nicogouet5/Agyx-Site- · Deploy interactivo: https://agyx-fletes.vercel.app.", "muted"),
        Spacer(1, 9),
        p("<b>Integrantes:</b> " + TEAM, "muted"),
    ]
    build("guia_readme.pdf", "03 / Material de revisión", "Guía de uso · Agyx", "Resumen del README en español / Grupo 2", story)


if __name__ == "__main__":
    ficha()
    matriz()
    guia()
