"""
app/services/r4r_service.py
Service layer for the R4R (Ready for Review) state machine, human approval/rejection governance,
and inactivity safeguard enforcement.
Strict invariant: auto_approved == False unconditionally.
"""
import json
import os
import sqlite3
from datetime import datetime
from typing import Dict, Any, List, Optional

from app.config import MEMORY_JSON_PATH, SQLITE_DB_PATH
from app.models.review import (
    ReviewActionRequest,
    ReviewActionResponse,
    InactivitySimulationResponse,
)
from app.services.memory_service import MemoryService
from app.tools.callable_tools import generar_propuesta_r4r


class R4RService:
    def __init__(
        self,
        memory_service: Optional[MemoryService] = None,
        db_path: Optional[str] = None,
        storage_path: Optional[str] = None,
    ):
        self.db_path = db_path or SQLITE_DB_PATH
        self.storage_path = storage_path or MEMORY_JSON_PATH
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_sqlite()
        self.memory_service = memory_service or MemoryService(
            storage_path=self.storage_path, db_path=self.db_path
        )

    def _init_sqlite(self) -> None:
        """Ensures r4r_proposals table exists in SQLite database."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS r4r_proposals (
                proposal_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                cargo_weight_kg REAL NOT NULL DEFAULT 0.0,
                cargo_volume_m3 REAL DEFAULT 0.0,
                cargo_type TEXT NOT NULL DEFAULT 'GENERAL',
                requested_datetime TEXT NOT NULL DEFAULT '',
                assigned_trucks TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL,
                auto_approved INTEGER NOT NULL DEFAULT 0 CHECK (auto_approved = 0),
                human_signature TEXT,
                review_timestamp TEXT,
                rejected_reason TEXT,
                tarifa_total_clp REAL NOT NULL DEFAULT 0.0,
                sla_horas REAL NOT NULL DEFAULT 2.0,
                proposal_data TEXT NOT NULL DEFAULT '{}',
                tokens_used INTEGER NOT NULL DEFAULT 0
            );
        """)
        conn.commit()
        conn.close()

    def create_proposal(
        self,
        case_id: str,
        camiones_asignados: List[str],
        origen: str,
        destino: str,
        fecha_hora_programada: str,
        tarifa_base_clp: float,
        recargo_clp: float = 0.0,
        sla_horas: float = 2.0,
        estado_caso: str = "R4R",
        observaciones: str = "",
        campos_faltantes: Optional[List[str]] = None,
        bloqueo_legal: Optional[str] = None,
        bloqueos_mantenimiento: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Creates an R4R proposal and persists it atomically.
        Invariant: auto_approved is False unconditionally.
        """
        return generar_propuesta_r4r(
            case_id=case_id,
            camiones_asignados=camiones_asignados,
            origen=origen,
            destino=destino,
            fecha_hora_programada=fecha_hora_programada,
            tarifa_base_clp=tarifa_base_clp,
            recargo_clp=recargo_clp,
            sla_horas=sla_horas,
            estado_caso=estado_caso,
            observaciones=observaciones,
            campos_faltantes=campos_faltantes,
            bloqueo_legal=bloqueo_legal,
            bloqueos_mantenimiento=bloqueos_mantenimiento,
            memory_file=self.storage_path,
            sqlite_db=self.db_path,
        )

    def get_queue(self) -> List[Dict[str, Any]]:
        """Returns all proposals currently pending in R4R (or info incompleta / bloqueado)."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            SELECT proposal_id, case_id, created_at, origin, destination, assigned_trucks,
                   tarifa_total_clp, sla_horas, status, auto_approved, human_signature,
                   review_timestamp, rejected_reason, proposal_data
            FROM r4r_proposals
            ORDER BY created_at DESC
        """)
        rows = cur.fetchall()
        conn.close()

        results = []
        for r in rows:
            pdata = json.loads(r[13]) if r[13] else {}
            results.append({
                "proposal_id": r[0],
                "propuesta_id": r[0],
                "case_id": r[1],
                "created_at": r[2],
                "origen": r[3],
                "destino": r[4],
                "camiones": json.loads(r[5]) if r[5] else [],
                "total_clp": r[6],
                "sla_horas": r[7],
                "estado": r[8],
                "auto_approved": bool(r[9]),  # always False
                "human_signature": r[10],
                "review_timestamp": r[11],
                "rejected_reason": r[12],
                "proposal_data": pdata,
                "cliente_nombre": pdata.get("cliente_nombre"),
                "cliente_contacto": pdata.get("cliente_contacto"),
                "es_pedido_cliente": bool(pdata.get("is_live_order") or str(r[1]).startswith("SOL-") or str(r[1]).startswith("PED-")),
                "peso_kg": pdata.get("peso_kg") or pdata.get("cargo_weight_kg"),
                "fecha_hora_programada": pdata.get("fecha_hora_programada"),
                "observaciones": pdata.get("observaciones"),
                "origin_coords": pdata.get("origin_coords"),
                "destination_coords": pdata.get("destination_coords"),
                "waypoints": pdata.get("waypoints"),
                "distance_km": pdata.get("distance_km"),
                "eta_minutes": pdata.get("eta_minutes"),
            })
        return results

    def get_proposal(self, case_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single proposal by case_id or proposal_id."""
        clean_id = (case_id or "").strip()
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            SELECT proposal_id, case_id, created_at, origin, destination, assigned_trucks,
                   tarifa_total_clp, sla_horas, status, auto_approved, human_signature,
                   review_timestamp, rejected_reason, proposal_data
            FROM r4r_proposals
            WHERE UPPER(case_id) = UPPER(?) OR UPPER(proposal_id) = UPPER(?)
            ORDER BY created_at DESC LIMIT 1
        """, (clean_id, clean_id))
        row = cur.fetchone()
        conn.close()

        if not row:
            return None

        pdata = json.loads(row[13]) if row[13] else {}
        return {
            "propuesta_id": row[0],
            "proposal_id": row[0],
            "case_id": row[1],
            "created_at": row[2],
            "origen": row[3],
            "destino": row[4],
            "camiones": json.loads(row[5]) if row[5] else [],
            "total_clp": row[6],
            "sla_horas": row[7],
            "estado": row[8],
            "auto_approved": bool(row[9]),  # False
            "human_signature": row[10],
            "review_timestamp": row[11],
            "rejected_reason": row[12],
            "proposal_data": pdata,
            "cliente_nombre": pdata.get("cliente_nombre"),
            "cliente_contacto": pdata.get("cliente_contacto"),
            "es_pedido_cliente": bool(pdata.get("is_live_order") or str(row[1]).startswith("SOL-") or str(row[1]).startswith("PED-")),
            "peso_kg": pdata.get("peso_kg") or pdata.get("cargo_weight_kg"),
            "fecha_hora_programada": pdata.get("fecha_hora_programada"),
            "observaciones": pdata.get("observaciones"),
            "origin_coords": pdata.get("origin_coords"),
            "destination_coords": pdata.get("destination_coords"),
            "waypoints": pdata.get("waypoints"),
            "distance_km": pdata.get("distance_km"),
            "eta_minutes": pdata.get("eta_minutes"),
        }

    def enrich_proposal_metadata(self, case_id: str, extra_data: Dict[str, Any]) -> None:
        """Persists extended live customer metadata and tactical route coords into proposal_data."""
        proposal = self.get_proposal(case_id)
        if not proposal:
            return
        merged = dict(proposal.get("proposal_data") or {})
        merged.update(extra_data)
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "UPDATE r4r_proposals SET proposal_data = ? WHERE proposal_id = ?",
            (json.dumps(merged, ensure_ascii=False), proposal["propuesta_id"]),
        )
        conn.commit()
        conn.close()

    def review_proposal(
        self,
        case_id: str,
        action: str,
        supervisor_name: str,
        rejected_reason: Optional[str] = None,
        signature_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes supervisor review action (APPROVE or REJECT).
        Validates that rejected_reason is mandatory and non-empty on REJECT.
        Auto_approved remains False unconditionally.
        """
        # Validate via domain model ReviewActionRequest
        req = ReviewActionRequest(
            case_id=case_id,
            action=action,
            supervisor_name=supervisor_name,
            rejected_reason=rejected_reason,
            signature_token=signature_token,
        )

        proposal = self.get_proposal(case_id)
        if not proposal:
            raise KeyError(f"Proposal with case_id '{case_id}' not found in R4R store")

        previous_status = proposal["estado"]
        if previous_status != "R4R":
            raise ValueError(
                f"La propuesta en estado {previous_status} no puede aprobarse ni rechazarse; "
                "solo una propuesta R4R puede pasar por revisión humana."
            )
        now_iso = datetime.utcnow().isoformat() + "Z"
        distilled_created = None

        if req.action == "APPROVE":
            new_status = "APPROVED"
            human_sig = req.supervisor_name.strip()
            final_reason = None
            msg = f"Propuesta aprobada exitosamente por {human_sig}. Despacho autorizado y camión en ruta."
            try:
                from app.services.fleet_service import FleetService
                from app.services.geo_service import geocode_santiago_address
                pdata = proposal.get("proposal_data") or {}
                dest_coords = pdata.get("destination_coords")
                if isinstance(dest_coords, list) and len(dest_coords) == 2:
                    d_lat, d_lng = float(dest_coords[0]), float(dest_coords[1])
                else:
                    g = geocode_santiago_address(proposal.get("destino", "Santiago"))
                    d_lat, d_lng = g["lat"], g["lng"]
                FleetService(db_path=self.db_path).dispatch_trucks_for_order(
                    truck_ids=proposal.get("camiones", []),
                    case_id=proposal["case_id"],
                    destino=proposal.get("destino", "Santiago"),
                    dest_lat=d_lat,
                    dest_lng=d_lng,
                )
            except Exception:
                pass
        else:
            new_status = "REJECTED"
            human_sig = req.supervisor_name.strip()
            final_reason = req.rejected_reason
            # Distill rule and persist in living memory
            feedback_res = self.memory_service.save_feedback(
                case_id=proposal["case_id"],
                action="REJECT",
                supervisor_name=human_sig,
                rejected_reason=final_reason,
                proposal_data=proposal,
            )
            distilled_created = feedback_res.get("distilled_rule")
            msg = f"Propuesta rechazada por {human_sig}. Razón registrada en Memoria Viva: '{distilled_created}'"

        # Update SQLite
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            UPDATE r4r_proposals
            SET status = ?,
                auto_approved = 0,
                human_signature = ?,
                review_timestamp = ?,
                rejected_reason = ?
            WHERE proposal_id = ? AND status = 'R4R'
        """, (new_status, human_sig, now_iso, final_reason, proposal["propuesta_id"]))
        if cur.rowcount != 1:
            conn.rollback()
            conn.close()
            raise ValueError("La propuesta cambió de estado durante la revisión; vuelva a cargarla.")
        conn.commit()
        conn.close()

        # Update JSON file
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                for p in data.get("propuestas_r4r", []):
                    if p.get("propuesta_id") == proposal["propuesta_id"]:
                        p["estado"] = new_status
                        p["human_signature"] = human_sig
                        p["review_timestamp"] = now_iso
                        p["rejected_reason"] = final_reason
                        p["auto_approved"] = False
                for p in data.get("proposals_log", []):
                    if p.get("propuesta_id") == proposal["propuesta_id"]:
                        p["estado"] = new_status
                        p["human_signature"] = human_sig
                        p["review_timestamp"] = now_iso
                        p["rejected_reason"] = final_reason
                        p["auto_approved"] = False
                tmp = str(self.storage_path) + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fp:
                    json.dump(data, fp, indent=2, ensure_ascii=False)
                os.replace(tmp, self.storage_path)
            except Exception:
                pass

        resp = ReviewActionResponse(
            success=True,
            case_id=proposal["case_id"],
            previous_status=previous_status,
            new_status=new_status,
            auto_approved=False,
            supervisor_name=human_sig,
            review_timestamp=now_iso,
            rejected_reason=final_reason,
            distilled_rule_created=distilled_created,
            message=msg,
        )
        return resp.to_dict()

    def simulate_inactivity(self, case_id: str, idle_minutes: int = 60) -> Dict[str, Any]:
        """
        Simulates human supervisor inactivity / timeout.
        Guarantees: proposal remains strictly in R4R (or original status).
        auto_approved is NEVER True.
        """
        prop = self.get_proposal(case_id)
        if not prop:
            raise KeyError(f"Proposal with case_id '{case_id}' not found")

        current_status = prop["estado"]
        # Inactivity must NEVER change status or auto-approve
        resp = InactivitySimulationResponse(
            case_id=prop["case_id"],
            status=current_status,
            auto_approved=False,
            idle_minutes_simulated=idle_minutes,
            message=f"Order '{case_id}' remains strictly locked in {current_status} after {idle_minutes} minutes of inactivity. Zero auto-approval guaranteed.",
        )
        return resp.to_dict()
