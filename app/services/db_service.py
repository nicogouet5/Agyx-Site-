"""
app/services/db_service.py
SQLite database manager and auto-seeder for Agyx.
Ensures tables exist and seeds fleet and restrictions from JSON if empty.
"""
import json
import os
import sqlite3
from typing import Optional
from app.config import (
    SQLITE_DB_PATH,
    FLEET_JSON_PATH,
    RESTRICTIONS_JSON_PATH,
)


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    target_path = db_path or SQLITE_DB_PATH
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Initializes tables and seeds data if not present."""
    target_path = db_path or SQLITE_DB_PATH
    conn = get_db_connection(target_path)
    cur = conn.cursor()

    # Table 1: Flota Camiones
    cur.execute("""
        CREATE TABLE IF NOT EXISTS flota_camiones (
            id_camion TEXT PRIMARY KEY,
            patente TEXT NOT NULL,
            modelo TEXT NOT NULL,
            tipo_vehiculo TEXT NOT NULL,
            capacidad_max_kg REAL NOT NULL,
            volumen_max_m3 REAL NOT NULL,
            estado_operativo TEXT NOT NULL,
            mantenimiento_bloqueo INTEGER NOT NULL DEFAULT 0,
            mantenimiento_detalle TEXT,
            ubicacion_base TEXT NOT NULL,
            proxima_disponibilidad TEXT NOT NULL,
            costo_base_clp REAL NOT NULL DEFAULT 0.0,
            costo_km_clp REAL NOT NULL DEFAULT 0.0
        );
    """)

    # Table 2: Restricciones Urbanas
    cur.execute("""
        CREATE TABLE IF NOT EXISTS restricciones_urbanas (
            id_restriccion TEXT PRIMARY KEY,
            zona_comuna TEXT NOT NULL,
            comunas_cubiertas TEXT NOT NULL,
            nombre_ordenanza TEXT NOT NULL,
            peso_max_diurno_kg REAL NOT NULL,
            hora_inicio_restriccion TEXT NOT NULL,
            hora_fin_restriccion TEXT NOT NULL,
            ventana_permitida_pesados TEXT NOT NULL,
            admite_hazmat INTEGER NOT NULL DEFAULT 0,
            requiere_escolta_o_permiso INTEGER NOT NULL DEFAULT 0,
            accion_mitigacion_sugerida TEXT NOT NULL,
            base_legal TEXT
        );
    """)

    # Table 3: R4R Proposals
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

    # Table 4: Living Memory Rules
    cur.execute("""
        CREATE TABLE IF NOT EXISTS living_memory_rules (
            id TEXT PRIMARY KEY,
            case_id TEXT,
            raw_reason TEXT,
            distilled_rule TEXT,
            zone_affected TEXT,
            mitigation_actions TEXT,
            token_count INTEGER,
            active INTEGER DEFAULT 1,
            supervisor_name TEXT,
            created_at TEXT
        );
    """)

    # Table 5: Feedback History
    cur.execute("""
        CREATE TABLE IF NOT EXISTS feedback_history (
            entry_id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            supervisor_name TEXT NOT NULL,
            action TEXT NOT NULL,
            rejected_reason TEXT NOT NULL,
            distilled_rule TEXT NOT NULL,
            token_count INTEGER NOT NULL DEFAULT 0
        );
    """)

    # Table 6: Audit Log
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action TEXT NOT NULL,
            case_id TEXT NOT NULL,
            details TEXT NOT NULL
        );
    """)

    # Indices
    cur.execute("CREATE INDEX IF NOT EXISTS idx_flota_disp ON flota_camiones (estado_operativo, mantenimiento_bloqueo);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_r4r_status ON r4r_proposals (case_id, status);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mem_active ON living_memory_rules (active, zone_affected);")

    # Seed Fleet if table is empty
    cur.execute("SELECT COUNT(*) FROM flota_camiones")
    if cur.fetchone()[0] == 0 and os.path.exists(FLEET_JSON_PATH):
        try:
            with open(FLEET_JSON_PATH, "r", encoding="utf-8") as f:
                trucks = json.load(f)
            for t in trucks:
                cur.execute("""
                    INSERT OR REPLACE INTO flota_camiones (
                        id_camion, patente, modelo, tipo_vehiculo, capacidad_max_kg,
                        volumen_max_m3, estado_operativo, mantenimiento_bloqueo,
                        mantenimiento_detalle, ubicacion_base, proxima_disponibilidad,
                        costo_base_clp, costo_km_clp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    t["id_camion"],
                    t["patente"],
                    t["modelo"],
                    t["tipo_vehiculo"],
                    float(t["capacidad_max_kg"]),
                    float(t["volumen_max_m3"]),
                    t["estado_operativo"],
                    1 if t.get("mantenimiento_bloqueo") else 0,
                    t.get("mantenimiento_detalle", ""),
                    t["ubicacion_base"],
                    t["proxima_disponibilidad"],
                    float(t.get("costo_base_clp", 0.0)),
                    float(t.get("costo_km_clp", 0.0)),
                ))
        except Exception as e:
            print(f"Warning seeding fleet: {e}")

    # Seed Restrictions if table is empty
    cur.execute("SELECT COUNT(*) FROM restricciones_urbanas")
    if cur.fetchone()[0] == 0 and os.path.exists(RESTRICTIONS_JSON_PATH):
        try:
            with open(RESTRICTIONS_JSON_PATH, "r", encoding="utf-8") as f:
                rsts = json.load(f)
            for r in rsts:
                cur.execute("""
                    INSERT OR REPLACE INTO restricciones_urbanas (
                        id_restriccion, zona_comuna, comunas_cubiertas, nombre_ordenanza,
                        peso_max_diurno_kg, hora_inicio_restriccion, hora_fin_restriccion,
                        ventana_permitida_pesados, admite_hazmat, requiere_escolta_o_permiso,
                        accion_mitigacion_sugerida, base_legal
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    r["id_restriccion"],
                    r["zona_comuna"],
                    json.dumps(r["comunas_cubiertas"], ensure_ascii=False),
                    r["nombre_ordenanza"],
                    float(r["peso_max_diurno_kg"]),
                    r["hora_inicio_restriccion"],
                    r["hora_fin_restriccion"],
                    r["ventana_permitida_pesados"],
                    1 if r.get("admite_hazmat") else 0,
                    1 if r.get("requiere_escolta_o_permiso") else 0,
                    r["accion_mitigacion_sugerida"],
                    r.get("base_legal", ""),
                ))
        except Exception as e:
            print(f"Warning seeding restrictions: {e}")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
