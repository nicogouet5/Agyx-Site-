"""HTTP contracts for FastAPI routes.

Domain services intentionally continue accepting plain dictionaries so the offline
stdlib runner and unit tests stay dependency-light. These schemas make the FastAPI
surface documented and validated when FastAPI/Pydantic are installed.
"""
from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DispatchEvaluationRequest(APIModel):
    case_id: str = Field(min_length=1, max_length=80)
    origen: Optional[str] = Field(default=None, max_length=200)
    destino: Optional[str] = Field(default=None, max_length=200)
    destino_comuna: Optional[str] = Field(default=None, max_length=200)
    cargo_weight_kg: Optional[float] = Field(default=None, ge=0, le=100_000)
    peso_kg: Optional[float] = Field(default=None, ge=0, le=100_000)
    cargo_volume_m3: Optional[float] = Field(default=None, ge=0, le=500)
    tipo_carga: Optional[str] = Field(default=None, max_length=80)
    cargo_type: Optional[str] = Field(default=None, max_length=80)
    hora_despacho: Optional[str] = Field(default=None, max_length=40)
    hora_solicitada: Optional[str] = Field(default=None, max_length=40)
    requested_datetime: Optional[str] = Field(default=None, max_length=80)
    truck_id_preferido: Optional[str] = Field(default=None, max_length=40)
    requested_truck_id: Optional[str] = Field(default=None, max_length=40)
    descripcion: Optional[str] = Field(default=None, max_length=2_000)
    version_mode: Literal["v1", "v2"] = "v2"
    engine_mode: Literal["local", "gemini"] = "local"


class ReviewProposalRequest(APIModel):
    case_id: str = Field(min_length=1, max_length=100)
    action: Literal["APPROVE", "REJECT"]
    supervisor_name: str = Field(min_length=1, max_length=160)
    rejected_reason: Optional[str] = Field(default=None, max_length=2_000)
    signature_token: Optional[str] = Field(default=None, max_length=512)


class InactivityRequest(APIModel):
    case_id: str = Field(min_length=1, max_length=100)
    idle_minutes: int = Field(default=60, ge=0, le=525_600)


class DemoSeedRequest(APIModel):
    case_id: str = Field(default="CASO-3", min_length=1, max_length=80)
    supervisor_name: str = Field(default="Carlos Morales (Jefe de Operaciones)", min_length=1, max_length=160)
    rejected_reason: str = Field(
        default="Ordenanza Santiago Centro prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs.",
        min_length=1,
        max_length=2_000,
    )


class GenericPayload(APIModel):
    """Reserved for optional demo overrides without allowing arbitrary request bodies."""
    overrides: Dict[str, Any] = Field(default_factory=dict)
