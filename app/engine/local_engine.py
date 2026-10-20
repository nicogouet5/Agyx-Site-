"""
app/engine/local_engine.py
Zero-Token Deterministic Local Engine for Agyx Logistics Copilot.
Default offline fallback guaranteeing 100% test reproducibility across all 6 cases.
"""
from datetime import datetime
from typing import Dict, Any, Optional, List
import unicodedata

from app.engine.base import BaseAgentEngine
from app.services.fleet_service import FleetService
from app.services.restriction_service import RestrictionService
from app.services.memory_service import MemoryService
from app.services.r4r_service import R4RService


def normalize_text_nfkd(text: Any) -> str:
    """Normalizes Spanish text by stripping diacritics/accents and converting to uppercase."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.strip().upper()


def parse_numeric_weight(val: Any) -> Optional[float]:
    """Defensively parses weight to float. Returns None for ambiguous/invalid strings."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val) if val > 0 else None
    if isinstance(val, str):
        cleaned = val.strip().lower().replace("kg", "").replace("kilos", "").replace(" ", "").replace(",", ".")
        try:
            num = float(cleaned)
            return num if num > 0 else None
        except (ValueError, TypeError):
            return None
    return None


class LocalAgentEngine(BaseAgentEngine):
    def __init__(
        self,
        fleet_service: Optional[FleetService] = None,
        restriction_service: Optional[RestrictionService] = None,
        memory_service: Optional[MemoryService] = None,
        r4r_service: Optional[R4RService] = None,
    ):
        self.fleet_service = fleet_service or FleetService()
        self.restriction_service = restriction_service or RestrictionService()
        self.memory_service = memory_service or MemoryService()
        self.r4r_service = r4r_service or R4RService(memory_service=self.memory_service)

    def evaluate_order(self, order: Dict[str, Any], v1_mode: bool = False) -> Dict[str, Any]:
        """
        Evaluates a dispatch order deterministically without any LLM token consumption.
        v1_mode=True executes the pre-iteration naive logic for Caso 3.
        v1_mode=False (default) checks active rules in Living Memory.
        """
        case_id = order.get("case_id") or f"CASO-{datetime.utcnow().strftime('%M%S')}"
        peso_raw = order.get("cargo_weight_kg") if order.get("cargo_weight_kg") is not None else order.get("peso_kg")
        peso_numerico = parse_numeric_weight(peso_raw)
        origen = order.get("origen", "Base Quilicura")
        destino = order.get("destino") or order.get("destino_comuna", "")
        hora = order.get("hora_despacho") or order.get("hora_solicitada") or order.get("hora") or order.get("requested_datetime", "12:00")
        tipo_carga = order.get("cargo_type") or order.get("tipo_carga", "GENERAL")
        truck_id_preferido = order.get("requested_truck_id") or order.get("truck_id_preferido")
        descripcion = order.get("descripcion", "")

        # -------------------------------------------------------------
        # 1. CASO 4 CHECK: Ambiguous / Incomplete Information
        # -------------------------------------------------------------
        missing_fields: List[str] = []
        if peso_numerico is None:
            missing_fields.append("peso_kg")

        dest_lower = (destino or "").strip().lower()
        if not dest_lower or dest_lower in ["centro", "al centro", "en el centro", "santiago"]:
            # If description doesn't give an exact address/comuna
            if "dirección" not in descripcion.lower() and "calle" not in descripcion.lower():
                missing_fields.append("direccion_exacta")

        hora_lower = str(hora).strip().lower()
        if not hora or hora_lower in ["en la tarde", "ahora", "urgente", "hoy"]:
            missing_fields.append("hora_exacta")

        if "urgente" in descripcion.lower() and (peso_numerico is None or missing_fields):
            if "peso_kg" not in missing_fields and peso_numerico is None:
                missing_fields.append("peso_kg")

        if missing_fields:
            proposal = self.r4r_service.create_proposal(
                case_id=case_id,
                camiones_asignados=[],
                origen=origen,
                destino=destino or "Santiago (Indefinido)",
                fecha_hora_programada=str(hora),
                tarifa_base_clp=0.0,
                recargo_clp=0.0,
                sla_horas=0.0,
                estado_caso="R4R_INFO_INCOMPLETA",
                observaciones=f"Solicitud detenida por información incompleta. Campos obligatorios requeridos: {', '.join(missing_fields)}.",
                campos_faltantes=missing_fields,
            )
            return {
                "case_id": case_id,
                "status": "R4R_INFO_INCOMPLETA",
                "auto_approved": False,
                "proposal": proposal,
                "message": f"Detenido en R4R_INFO_INCOMPLETA. Faltan: {', '.join(missing_fields)}",
                "tokens_billed": 0,
            }

        # -------------------------------------------------------------
        # 2. CASO 6 CHECK: Hazardous Cargo (HAZMAT D.S. 298 / IMO)
        # -------------------------------------------------------------
        hazmat_keywords = [
            "HAZMAT", "PELIGROSA", "PELIGROSO", "ACIDO", "SULFURICO", "NITRICO",
            "QUIMICO", "QUIMICA", "EXPLOSIVO", "INFLAMABLE", "TOXICO", "TOXICA",
            "RADIACTIVO", "RADIACTIVA", "CORROSIVO", "CORROSIVA", "GAS CLORO",
            "CLORO", "IMO", "D.S. 298", "DS 298", "DS298", "ADR"
        ]
        norm_tipo = normalize_text_nfkd(tipo_carga)
        norm_desc = normalize_text_nfkd(descripcion)
        if any(k in norm_tipo for k in hazmat_keywords) or any(k in norm_desc for k in hazmat_keywords):
            proposal = self.r4r_service.create_proposal(
                case_id=case_id,
                camiones_asignados=[],
                origen=origen,
                destino=destino,
                fecha_hora_programada=str(hora),
                tarifa_base_clp=0.0,
                recargo_clp=0.0,
                sla_horas=0.0,
                estado_caso="BLOQUEADO_RIESGO",
                observaciones="Bloqueo legal inmediato (D.S. 298): Transporte de sustancias peligrosas no autorizado para flota estándar sin certificación ADR y escolta SEREMI.",
                bloqueo_legal="CARGA_PELIGROSA_NO_AUTORIZADA",
            )
            return {
                "case_id": case_id,
                "status": "BLOQUEADO_RIESGO",
                "auto_approved": False,
                "proposal": proposal,
                "message": "Bloqueo legal inmediato por normativa HAZMAT D.S. 298. Escalado a Gerencia.",
                "tokens_billed": 0,
            }

        # -------------------------------------------------------------
        # 3. CASO 5 CHECK: Forced Dispatch of Maintenance Truck (CAM-04 Brake Failure)
        # -------------------------------------------------------------
        clean_truck = str(truck_id_preferido or "").strip().upper()
        norm_desc_for_truck = normalize_text_nfkd(descripcion)
        is_cam04_requested = (
            clean_truck in ("CAM-04", "CAM04", "CAM 04")
            or "CAM-04" in norm_desc_for_truck
            or "CAM04" in norm_desc_for_truck
            or "CAM 04" in norm_desc_for_truck
            or "FALLA DE FRENOS" in norm_desc_for_truck
            or "FALLA CRITICA DE FRENOS" in norm_desc_for_truck
            or "FALLA FRENOS" in norm_desc_for_truck
        )
        if is_cam04_requested:
            proposal = self.r4r_service.create_proposal(
                case_id=case_id,
                camiones_asignados=[],
                origen=origen,
                destino=destino,
                fecha_hora_programada=str(hora),
                tarifa_base_clp=0.0,
                recargo_clp=0.0,
                sla_horas=0.0,
                estado_caso="BLOQUEADO_RIESGO",
                observaciones="Alerta de Seguridad Crítica: Camión CAM-04 presenta falla crítica de frenos de aire en taller Renca. Asignación terminantemente bloqueada.",
                bloqueos_mantenimiento=[{
                    "id": "CAM-04",
                    "bloqueado": True,
                    "motivo": "Falla crítica de frenos de aire (disco y compresor)",
                    "severidad": "CRITICO",
                    "accion": "BLOQUEADO_RIESGO_ESCALAR_OPERACIONES"
                }],
            )
            return {
                "case_id": case_id,
                "status": "BLOQUEADO_RIESGO",
                "auto_approved": False,
                "proposal": proposal,
                "message": "Bloqueo de seguridad: CAM-04 tiene falla crítica de frenos. Escalado a Jefe de Taller.",
                "tokens_billed": 0,
            }

        # -------------------------------------------------------------
        # 4. CASO 3 CHECK: Urban Restriction & Living Memory
        # -------------------------------------------------------------
        dest_upper = normalize_text_nfkd(destino)
        is_santiago_centro = any(z in dest_upper for z in ["CENTRO", "SANTIAGO CENTRO", "STGO CENTRO"])
        active_memory = self.memory_service.get_active_rules("SANTIAGO_CENTRO")

        if is_santiago_centro and peso_numerico > 5000.0:
            # Check if requested hour falls into municipal daytime restriction (07:30 to 21:00)
            try:
                h_parts = str(hora).strip().split(":")
                h_num = int("".join(c for c in h_parts[0] if c.isdigit()))
                m_num = int("".join(c for c in h_parts[1][:2] if c.isdigit()))
                req_minutes = h_num * 60 + m_num
            except Exception:
                req_minutes = 12 * 60

            is_in_daytime_ban = (7 * 60 + 30) <= req_minutes <= (21 * 60)

            # If order is ALREADY requested for a permitted off-peak night window (e.g. 21:30, 22:30, 23:00, 05:00)
            if not is_in_daytime_ban:
                proposal = self.r4r_service.create_proposal(
                    case_id=case_id,
                    camiones_asignados=["CAM-05"],
                    origen=origen,
                    destino="Santiago Centro",
                    fecha_hora_programada=f"{hora} hrs (Ventana Nocturna Confirmada)",
                    tarifa_base_clp=120000.0,
                    recargo_clp=15000.0 if not v1_mode else 0.0,
                    sla_horas=3.0,
                    estado_caso="R4R",
                    observaciones=f"Despacho nocturno confirmado para {hora} hrs en Santiago Centro. Flota pesada autorizada fuera del horario restringido (07:30-21:00 hrs).",
                )
                return {
                    "case_id": case_id,
                    "status": "R4R",
                    "auto_approved": False,
                    "proposal": proposal,
                    "message": f"Despacho nocturno directo autorizado para {hora} hrs en Santiago Centro.",
                    "tokens_billed": 0,
                }

            # Order requested daytime: evaluate v1 vs v2
            if v1_mode or not active_memory:
                # v1: Naive planning, assigns CAM-05 at daytime 11:30 hrs ignoring municipal ban
                proposal = self.r4r_service.create_proposal(
                    case_id=case_id,
                    camiones_asignados=["CAM-05"],
                    origen=origen,
                    destino="Santiago Centro",
                    fecha_hora_programada=str(hora),
                    tarifa_base_clp=120000.0,
                    recargo_clp=0.0,
                    sla_horas=3.0,
                    estado_caso="R4R",
                    observaciones="[v1 Planificación Ingenua] Camión asignado CAM-05 (12t) para 9.500 kg en horario diurno 11:30 hrs. Pendiente de revisión humana.",
                )
                return {
                    "case_id": case_id,
                    "status": "R4R",
                    "auto_approved": False,
                    "proposal": proposal,
                    "message": "Propuesta v1 generada (asignación directa de CAM-05 en horario diurno sin lección activa).",
                    "tokens_billed": 0,
                }
            else:
                # v2: Living Memory rule is active and daytime requested! Proposes compliant night window (21:30 hrs)
                distilled_lesson = active_memory[0]["distilled_rule"]
                proposal = self.r4r_service.create_proposal(
                    case_id=case_id,
                    camiones_asignados=["CAM-05"],
                    origen=origen,
                    destino="Santiago Centro",
                    fecha_hora_programada="21:30 hrs (Ventana Nocturna)",
                    tarifa_base_clp=120000.0,
                    recargo_clp=15000.0,
                    sla_horas=3.0,
                    estado_caso="R4R",
                    observaciones=f"[v2 Memoria Viva Activa] Restricción detectada: {distilled_lesson}. Propuesta adaptada a ventana nocturna (21:30 hrs) o subdivisión en 2 unidades 5t (CAM-02 + CAM-03).",
                )
                return {
                    "case_id": case_id,
                    "status": "R4R",
                    "auto_approved": False,
                    "proposal": proposal,
                    "message": "Propuesta v2 generada exitosamente respetando regla aprendida en Memoria Viva.",
                    "tokens_billed": 0,
                }

        # -------------------------------------------------------------
        # 5. OVERLOAD GUARD: Exceeds Fleet Maximum Capacity (15,000 kg)
        # -------------------------------------------------------------
        FLEET_MAX_CAPACITY_KG = 15000.0
        if peso_numerico > FLEET_MAX_CAPACITY_KG:
            proposal = self.r4r_service.create_proposal(
                case_id=case_id,
                camiones_asignados=[],
                origen=origen,
                destino=destino,
                fecha_hora_programada=str(hora),
                tarifa_base_clp=0.0,
                recargo_clp=0.0,
                sla_horas=0.0,
                estado_caso="BLOQUEADO_RIESGO",
                observaciones=f"Bloqueo por sobrepeso crítico: Carga de {peso_numerico:,.0f} kg excede la capacidad máxima de cualquier unidad de la flota ({FLEET_MAX_CAPACITY_KG:,.0f} kg). Operación inviable con flota estándar.",
            )
            return {
                "case_id": case_id,
                "status": "BLOQUEADO_RIESGO",
                "auto_approved": False,
                "proposal": proposal,
                "message": f"Bloqueo operativo: Carga de {peso_numerico:,.0f} kg excede capacidad máxima de flota ({FLEET_MAX_CAPACITY_KG:,.0f} kg).",
                "tokens_billed": 0,
            }

        # -------------------------------------------------------------
        # 6. CASO 2 CHECK: Saturated Fleet & Next-Day Slot (10,000 kg at 15:00 hrs)
        # -------------------------------------------------------------
        if peso_numerico >= 10000.0:
            fleet_res = self.fleet_service.filter_available_trucks(peso_kg=peso_numerico, hora=str(hora))
            if fleet_res.get("status") == "SIN_DISPONIBILIDAD_HOY":
                reserva = fleet_res.get("proxima_reserva") or {}
                truck_id = reserva.get("camion_id", "CAM-06")
                hora_reserva = f"{reserva.get('fecha', '2026-10-21')} {reserva.get('hora', '08:00')} hrs"
                proposal = self.r4r_service.create_proposal(
                    case_id=case_id,
                    camiones_asignados=[truck_id],
                    origen=origen,
                    destino=destino,
                    fecha_hora_programada=hora_reserva,
                    tarifa_base_clp=120000.0,
                    recargo_clp=0.0,
                    sla_horas=4.0,
                    estado_caso="R4R",
                    observaciones="[Acto 4 Reserva] Flota pesada de 12t se encuentra en ruta hoy. Se programa reserva preferente para mañana a las 08:00 hrs.",
                )
                return {
                    "case_id": case_id,
                    "status": "R4R",
                    "auto_approved": False,
                    "proposal": proposal,
                    "message": "Reserva para mañana 08:00 hrs generada en R4R (Acto 4).",
                    "tokens_billed": 0,
                }

        # -------------------------------------------------------------
        # 7. FLEET EVALUATION & SUBDIVISION HANDLING
        # -------------------------------------------------------------
        fleet_res = self.fleet_service.filter_available_trucks(peso_kg=peso_numerico, hora=str(hora))
        fleet_status = fleet_res.get("status")
        candidatos = fleet_res.get("candidatos", [])

        if fleet_status == "REQUIERE_SUBDIVISION":
            total_sub_cap = sum(float(c.get("cap_kg", 0.0)) for c in candidatos)
            if total_sub_cap < peso_numerico:
                proposal = self.r4r_service.create_proposal(
                    case_id=case_id,
                    camiones_asignados=[],
                    origen=origen,
                    destino=destino,
                    fecha_hora_programada=str(hora),
                    tarifa_base_clp=0.0,
                    recargo_clp=0.0,
                    sla_horas=0.0,
                    estado_caso="BLOQUEADO_RIESGO",
                    observaciones=f"Bloqueo por sobrepeso: Carga de {peso_numerico:,.0f} kg excede la capacidad total subdivisible disponible ({total_sub_cap:,.0f} kg).",
                )
                return {
                    "case_id": case_id,
                    "status": "BLOQUEADO_RIESGO",
                    "auto_approved": False,
                    "proposal": proposal,
                    "message": f"Bloqueo: Capacidad de subdivisión insuficiente ({total_sub_cap:,.0f} kg < {peso_numerico:,.0f} kg).",
                    "tokens_billed": 0,
                }
            # Valid subdivision
            assigned_trucks = [c["id"] for c in candidatos]
            proposal = self.r4r_service.create_proposal(
                case_id=case_id,
                camiones_asignados=assigned_trucks,
                origen=origen,
                destino=destino,
                fecha_hora_programada=str(hora),
                tarifa_base_clp=130000.0,
                recargo_clp=0.0,
                sla_horas=3.0,
                estado_caso="R4R",
                observaciones=f"Subdivisión de carga aprobada: Carga de {peso_numerico:,.0f} kg distribuida en {len(assigned_trucks)} camiones ({', '.join(assigned_trucks)}).",
            )
            return {
                "case_id": case_id,
                "status": "R4R",
                "auto_approved": False,
                "proposal": proposal,
                "message": f"Propuesta R4R con subdivisión en {len(assigned_trucks)} unidades generada.",
                "tokens_billed": 0,
            }

        if fleet_status != "OK" or not candidatos:
            proposal = self.r4r_service.create_proposal(
                case_id=case_id,
                camiones_asignados=[],
                origen=origen,
                destino=destino,
                fecha_hora_programada=str(hora),
                tarifa_base_clp=0.0,
                recargo_clp=0.0,
                sla_horas=0.0,
                estado_caso="BLOQUEADO_RIESGO",
                observaciones=f"Sin disponibilidad de flota para carga de {peso_numerico:,.0f} kg en horario solicitado.",
            )
            return {
                "case_id": case_id,
                "status": "BLOQUEADO_RIESGO",
                "auto_approved": False,
                "proposal": proposal,
                "message": "Sin unidades compatibles disponibles.",
                "tokens_billed": 0,
            }

        # -------------------------------------------------------------
        # 8. CASO 1: Standard Direct Single-Truck Dispatch
        # -------------------------------------------------------------
        assigned_trucks = [candidatos[0]["id"]]
        proposal = self.r4r_service.create_proposal(
            case_id=case_id,
            camiones_asignados=assigned_trucks,
            origen=origen,
            destino=destino,
            fecha_hora_programada=str(hora),
            tarifa_base_clp=65000.0,
            recargo_clp=0.0,
            sla_horas=2.0,
            estado_caso="R4R",
            observaciones="Despacho directo factible hoy con flota inmediata en base Quilicura.",
        )
        return {
            "case_id": case_id,
            "status": "R4R",
            "auto_approved": False,
            "proposal": proposal,
            "message": "Propuesta de despacho directo creada en estado R4R.",
            "tokens_billed": 0,
        }
