"""Small, offline location catalogue for the demonstration workflow.

An address match is a zone hint, not a calculated road route or legal clearance.
The street reference was supplied for this prototype; no live geocoding is used.
"""
import re
import unicodedata
from urllib.parse import quote


def _normalize(value: str) -> str:
    plain = unicodedata.normalize("NFKD", str(value or ""))
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", plain).strip().lower()


def resolve_destination(destination: str) -> dict:
    """Resolve the known Lira 953 reference without guessing other addresses."""
    normalized = _normalize(destination)
    lira_953 = bool(re.search(r"\blira\s*(?:n[°ºo.]?\s*)?953\b", normalized))
    if lira_953:
        return {
            "direccion": "Lira 953, Santiago, Chile",
            "zona": "SANTIAGO_CENTRO",
            "fuente": "referencia_de_demostracion",
            "verificacion": "zona_aproximada_sujeta_a_revision_humana",
            "map_url": "https://www.openstreetmap.org/search?query=" + quote("Lira 953, Santiago, Chile"),
        }
    return {}
