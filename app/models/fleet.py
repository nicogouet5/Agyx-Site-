"""
app/models/fleet.py
Data models for fleet vehicles, operational status, and capacity queries.
Built with pure Python standard library dataclasses for zero-dependency execution.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
import json


@dataclass
class Truck:
    id_camion: str
    patente: str
    modelo: str
    tipo_vehiculo: str
    capacidad_max_kg: float
    volumen_max_m3: float
    estado_operativo: str
    mantenimiento_bloqueo: bool
    mantenimiento_detalle: str
    ubicacion_base: str
    proxima_disponibilidad: str
    costo_base_clp: float = 0.0
    costo_km_clp: float = 0.0

    def __post_init__(self):
        self.capacidad_max_kg = float(self.capacidad_max_kg)
        self.volumen_max_m3 = float(self.volumen_max_m3)
        self.costo_base_clp = float(self.costo_base_clp)
        self.costo_km_clp = float(self.costo_km_clp)
        if isinstance(self.mantenimiento_bloqueo, str):
            self.mantenimiento_bloqueo = self.mantenimiento_bloqueo.lower() in ("true", "1", "yes")
        else:
            self.mantenimiento_bloqueo = bool(self.mantenimiento_bloqueo)

    def esta_disponible(self) -> bool:
        return self.estado_operativo.upper() == "DISPONIBLE" and not self.mantenimiento_bloqueo

    def tiene_falla_critica(self) -> bool:
        return self.mantenimiento_bloqueo or "frenos" in self.mantenimiento_detalle.lower()

    def puede_cargar(self, peso_kg: float, volumen_m3: float = 0.0) -> bool:
        return self.capacidad_max_kg >= peso_kg and (volumen_m3 <= 0 or self.volumen_max_m3 >= volumen_m3)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Truck":
        fields = cls.__dataclass_fields__
        filtered = {k: v for k, v in data.items() if k in fields}
        return cls(**filtered)


@dataclass
class FleetQueryRequest:
    peso_kg: float
    volumen_m3: float = 0.0
    fecha_despacho: Optional[str] = None
    hora_despacho: Optional[str] = None
    truck_id_preferido: Optional[str] = None

    def __post_init__(self):
        self.peso_kg = float(self.peso_kg)
        self.volumen_m3 = float(self.volumen_m3)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FleetQueryRequest":
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in fields})


@dataclass
class TruckCandidate:
    id: str
    modelo: str
    cap_kg: float
    disp: str
    costo_base_clp: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MaintenanceLockInfo:
    id: str
    bloqueado: bool
    motivo: str
    severidad: str = "ALTA"
    accion: str = "BLOQUEADO_RIESGO"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FleetQueryResponse:
    status: str
    candidatos: List[Dict[str, Any]] = field(default_factory=list)
    proxima_reserva: Optional[Dict[str, Any]] = None
    bloqueos_mantenimiento: List[Dict[str, Any]] = field(default_factory=list)
    tokens_used: int = 0
    nota: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)
