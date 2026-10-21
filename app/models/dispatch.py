"""
app/models/dispatch.py
Data models for dispatch orders, R4R proposals, and evaluation results.
Enforces the strict invariant auto_approved == False on all proposals.
Built with pure Python standard library dataclasses for zero-dependency execution.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
import json
import datetime


@dataclass
class DispatchOrderInput:
    case_id: str
    origen: str = "Quilicura"
    destino: str = ""
    cargo_weight_kg: Optional[float] = None
    cargo_volume_m3: Optional[float] = None
    cargo_type: str = "GENERAL"
    requested_datetime: Optional[str] = None
    hora_despacho: Optional[str] = None
    requested_truck_id: Optional[str] = None
    descripcion: str = ""
    version_mode: str = "v2"  # v1 solo para reconstruir el fallo inicial
    engine_mode: str = "local"  # "local" (zero-token deterministic) or "gemini"

    def __post_init__(self):
        if self.cargo_weight_kg is not None:
            self.cargo_weight_kg = float(self.cargo_weight_kg)
        if self.cargo_volume_m3 is not None:
            self.cargo_volume_m3 = float(self.cargo_volume_m3)
        self.version_mode = (self.version_mode or "v2").strip().lower()
        self.engine_mode = (self.engine_mode or "local").strip().lower()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DispatchOrderInput":
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in fields})


@dataclass
class ProposalR4R:
    propuesta_id: str
    case_id: str
    version: int = 1
    created_at: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z")
    origen: str = ""
    destino: str = ""
    camiones_asignados: List[str] = field(default_factory=list)
    estado: str = "R4R"
    auto_approved: bool = False  # STRICT GOVERNANCE INVARIANT: CAN NEVER BE TRUE
    requiere_firma_humana: bool = True
    tarifa_base_clp: float = 0.0
    recargo_clp: float = 0.0
    tarifa_total_clp: float = 0.0
    sla_horas: float = 2.0
    observaciones: str = ""
    campos_faltantes: List[str] = field(default_factory=list)
    opciones_mitigacion: List[str] = field(default_factory=list)
    leccion_memoria_aplicada: Optional[str] = None
    tokens_utilizados: int = 0
    detalles_json: Dict[str, Any] = field(default_factory=dict)
    human_signature: Optional[str] = None
    review_timestamp: Optional[str] = None
    rejected_reason: Optional[str] = None

    def __post_init__(self):
        # Strict state machine invariant check: zero auto-approval under any condition
        if self.auto_approved is True:
            raise ValueError("Governance Violation: auto_approved cannot be True in an R4R proposal")
        self.auto_approved = False
        self.requiere_firma_humana = True
        self.tarifa_base_clp = float(self.tarifa_base_clp)
        self.recargo_clp = float(self.recargo_clp)
        self.tarifa_total_clp = float(self.tarifa_base_clp + self.recargo_clp)
        self.sla_horas = float(self.sla_horas)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProposalR4R":
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in fields})


@dataclass
class EvaluationResult:
    case_id: str
    status: str  # R4R, R4R_INFO_INCOMPLETA, BLOQUEADO_RIESGO
    auto_approved: bool = False
    proposal: Optional[ProposalR4R] = None
    tool_traces: List[Dict[str, Any]] = field(default_factory=list)
    message: str = ""
    tokens_billed: int = 0

    def __post_init__(self):
        if self.auto_approved is True:
            raise ValueError("EvaluationResult invariant violated: auto_approved must be False")
        self.auto_approved = False

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        if self.proposal:
            res["proposal"] = self.proposal.to_dict()
        return res
