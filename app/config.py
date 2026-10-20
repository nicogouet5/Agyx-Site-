"""
app/config.py
Configuration constants, filesystem paths, and token budget thresholds for Agyx.
Automatically uses writable /tmp/agyx_data when deployed on Vercel Serverless.
"""
import os
import shutil
from pathlib import Path

# Base Paths
APP_DIR = Path(__file__).resolve().parent
BASE_DIR = APP_DIR.parent
DATA_DIR = BASE_DIR / "data"

# Read-only seed files (always read from repository data/)
FLEET_CSV_PATH = str(DATA_DIR / "flota_camiones.csv")
FLEET_JSON_PATH = str(DATA_DIR / "flota_camiones.json")
RESTRICTIONS_CSV_PATH = str(DATA_DIR / "restricciones_viales_urbanas.csv")
RESTRICTIONS_JSON_PATH = str(DATA_DIR / "restricciones_viales_urbanas.json")

# Writable state files (use /tmp/agyx_data on Vercel or read-only filesystems)
_is_vercel = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
if _is_vercel or not os.access(str(DATA_DIR), os.W_OK):
    RUNTIME_DATA_DIR = Path("/tmp/agyx_data")
    RUNTIME_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for fname in ("bitacora_memoria_viva.json", "agyx.db"):
        src = DATA_DIR / fname
        dst = RUNTIME_DATA_DIR / fname
        if src.exists() and not dst.exists():
            try:
                shutil.copy2(src, dst)
            except Exception:
                pass
    MEMORY_JSON_PATH = str(RUNTIME_DATA_DIR / "bitacora_memoria_viva.json")
    SQLITE_DB_PATH = str(RUNTIME_DATA_DIR / "agyx.db")
else:
    MEMORY_JSON_PATH = str(DATA_DIR / "bitacora_memoria_viva.json")
    SQLITE_DB_PATH = str(DATA_DIR / "agyx.db")

# Token Optimization Thresholds
MAX_TOOL_TOKENS = 150
MAX_MEMORY_RULE_TOKENS = 80

# Engine Configurations
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

# Governance Defaults
DEFAULT_BASE_FARE_CLP = 65000.0
DEFAULT_KM_FARE_CLP = 1200.0
DEFAULT_SLA_HOURS = 2.5
