"""
app/models/restrictions.py
Data models for urban road ordinances, weight/hour restrictions, and HAZMAT rules.
Built with pure Python standard library dataclasses for zero-dependency execution.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
import json


@dataclass
class UrbanRestriction:
    id_restriccion: str
    zona_comuna: str
    comunas_cubiertas: List[str]
    nombre_ordenanza: str
    peso_max_diurno_kg: float
    hora_inicio_restriccion: str
    hora_fin_restriccion: str
    ventana_permitida_pesados: str
    admite_hazmat: bool
    requiere_escolta_o_permiso: bool
    accion_mitigacion_sugerida: str
    base_legal: str = ""

    def __post_init__(self):
        self.peso_max_diurno_kg = float(self.peso_max_diurno_kg)
        if isinstance(self.comunas_cubiertas, str):
            try:
                self.comunas_cubiertas = json.loads(self.comunas_cubiertas)
            except Exception:
                self.comunas_cubiertas = [c.strip() for c in self.comunas_cubiertas.split(",") if c.strip()]
        if isinstance(self.admite_hazmat, str):
            self.admite_hazmat = self.admite_hazmat.lower() in ("true", "1", "yes")
        else:
            self.admite_hazmat = bool(self.admite_hazmat)
        if isinstance(self.requiere_escolta_o_permiso, str):
            self.requiere_escolta_o_permiso = self.requiere_escolta_o_permiso.lower() in ("true", "1", "yes")
        else:
            self.requiere_escolta_o_permiso = bool(self.requiere_escolta_o_permiso)

    def aplica_a_comuna(self, comuna: str) -> bool:
        norm_target = comuna.strip().upper()
        if self.zona_comuna.upper() in norm_target or norm_target in self.zona_comuna.upper():
            return True
        return any(c.strip().upper() in norm_target or norm_target in c.strip().upper() for c in self.comunas_cubiertas)

    @staticmethod
    def _parse_time_to_minutes(hora_str: str) -> Optional[int]:
        """Converts 'H:MM' or 'HH:MM' string to elapsed minutes from midnight [0, 1439]."""
        if not hora_str:
            return None
        clean = hora_str.strip()
        parts = clean.split(":")
        if len(parts) >= 2:
            try:
                h_digits = "".join(c for c in parts[0] if c.isdigit())
                m_digits = "".join(c for c in parts[1][:2] if c.isdigit())
                if not h_digits or not m_digits:
                    return None
                h = int(h_digits)
                m = int(m_digits)
                if 0 <= h <= 23 and 0 <= m <= 59:
                    return h * 60 + m
            except (ValueError, TypeError):
                return None
        return None

    def en_horario_restringido(self, hora_str: str) -> bool:
        """Checks if time in hora_str falls into [hora_inicio_restriccion, hora_fin_restriccion]."""
        m_req = self._parse_time_to_minutes(hora_str)
        m_ini = self._parse_time_to_minutes(self.hora_inicio_restriccion)
        m_fin = self._parse_time_to_minutes(self.hora_fin_restriccion)
        if m_req is None or m_ini is None or m_fin is None:
            return False
        if m_ini <= m_fin:
            return m_ini <= m_req <= m_fin
        else:
            return m_req >= m_ini or m_req <= m_fin

    def viola_peso_diurno(self, peso_kg: float, hora_str: str) -> bool:
        if self.en_horario_restringido(hora_str):
            return peso_kg > self.peso_max_diurno_kg
        return False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UrbanRestriction":
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in fields})


@dataclass
class RouteVerificationRequest:
    origen: str
    destino_comuna: str
    peso_kg: float
    hora_solicitada: str
    tipo_carga: str = "GENERAL"
    living_memory_active: bool = False

    def __post_init__(self):
        self.peso_kg = float(self.peso_kg)
        if isinstance(self.living_memory_active, str):
            self.living_memory_active = self.living_memory_active.lower() in ("true", "1", "yes")
        else:
            self.living_memory_active = bool(self.living_memory_active)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RouteVerificationRequest":
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in fields})


@dataclass
class RouteVerificationResponse:
    factible: bool
    zona: Optional[str] = None
    motivo: Optional[str] = None
    bloqueo_legal: Optional[str] = None
    leccion_memoria_viva: Optional[str] = None
    acciones_mitigacion: List[str] = field(default_factory=list)
    ventana_recomendada: Optional[str] = None
    tokens_used: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)
