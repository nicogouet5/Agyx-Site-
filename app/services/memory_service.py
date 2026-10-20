"""
app/services/memory_service.py
Living Memory (Memoria Viva) distillation engine, token budget enforcer, and feedback store.
Synchronizes between SQLite (agyx.db) and JSON (bitacora_memoria_viva.json).
"""
import json
import os
import sqlite3
from datetime import datetime
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from app.config import (
    MEMORY_JSON_PATH,
    SQLITE_DB_PATH,
    MAX_MEMORY_RULE_TOKENS,
)
from app.models.memory import (
    LivingMemoryRule,
    FeedbackLogEntry,
    calculate_token_count,
)
from app.models.review import clean_human_text
from app.tools.token_optimizer import distill_rule, count_tokens


class MemoryService:
    def __init__(
        self,
        storage_path: Optional[str] = None,
        db_path: Optional[str] = None,
    ):
        self.storage_path = Path(storage_path or MEMORY_JSON_PATH)
        self.db_path = Path(db_path or SQLITE_DB_PATH)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_sqlite()
        self._init_json_store()

    def _init_sqlite(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
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
        conn.commit()
        conn.close()

    def _init_json_store(self) -> None:
        if not self.storage_path.exists():
            clean_state = {
                "metadata": {
                    "system": "Agyx Operational AI Agent",
                    "version": "1.0.0",
                    "initialized_at": datetime.utcnow().isoformat() + "Z",
                },
                "active_rules": [],
                "feedback_history": [],
                "proposals_log": [],
                "propuestas_r4r": [],
                "bitacora_feedback": [],
                "living_memory_rules": [],
            }
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(clean_state, f, indent=2, ensure_ascii=False)

    def distill_rejection_reason(
        self,
        raw_reason: str,
        case_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, List[str], str]:
        """
        Compresses supervisor rejection reason into an operational rule (< 80 tokens).
        Returns: (distilled_rule, mitigation_actions, zone_affected)
        """
        cleaned = clean_human_text(raw_reason)
        lower = cleaned.lower()

        if ("santiago centro" in lower or "centro" in lower) and ("5000" in lower or "5.000" in lower or "5t" in lower or "peso" in lower):
            rule = "[SANTIAGO_CENTRO] >5.000kg prohibido 07:30-21:00. Solución: reprogramar 21:30 hrs o 2x camiones 5t."
            mitigations = ["REPROGRAMAR_NOCTURNO_2130", "SUBDIVIDIR_2X_5T"]
            zone = "SANTIAGO_CENTRO"
        elif "freno" in lower or "cam-04" in lower or "mantenimiento" in lower:
            rule = "[SEGURIDAD_FLOTA] CAM-04 bloqueado por falla crítica de frenos de aire. Prohibido asignar."
            mitigations = ["BLOQUEAR_CAMION_EN_MANTENIMIENTO"]
            zone = "FLOTA_MANTENIMIENTO"
        elif "peligrosa" in lower or "hazmat" in lower or "ácido" in lower or "acido" in lower:
            rule = "[CARGA_PELIGROSA] Transporte D.S. 298 no autorizado sin resolución SEREMI y camión ADR."
            mitigations = ["BLOQUEAR_RIESGO_HAZMAT"]
            zone = "CARGA_PELIGROSA"
        else:
            rule = distill_rule(cleaned, max_tokens=MAX_MEMORY_RULE_TOKENS)
            mitigations = ["APLICAR_REGLA_SUPERVISOR"]
            zone = "GENERAL"

        tokens = count_tokens(rule)
        if tokens >= MAX_MEMORY_RULE_TOKENS:
            words = rule.split()
            if len(words) > 35:
                rule = " ".join(words[:35]) + "..."
            while count_tokens(rule) >= MAX_MEMORY_RULE_TOKENS:
                if len(rule) > 24:
                    rule = rule[:-5].strip() + "..."
                else:
                    rule = "[REGLA_OPERACIONAL] ..."
                    break

        return rule, mitigations, zone

    def save_feedback(
        self,
        case_id: str,
        action: str,
        supervisor_name: str,
        rejected_reason: str,
        proposal_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Validates mandatory rejection reason and stores distilled feedback rule.
        Enforces strict validation: rejected_reason cannot be empty or whitespace.
        """
        norm_action = (action or "").strip().upper()
        if norm_action != "REJECT":
            return {}

        clean_rej = clean_human_text(rejected_reason)
        if not clean_rej:
            raise ValueError("Validation Error: rejected_reason cannot be empty or whitespace when rejecting a proposal")

        clean_sup = clean_human_text(supervisor_name)
        if not clean_sup:
            raise ValueError("Validation Error: supervisor_name cannot be empty or whitespace")

        rule_text, mitigations, zone = self.distill_rejection_reason(clean_rej, proposal_data)
        tokens = count_tokens(rule_text)
        if tokens >= MAX_MEMORY_RULE_TOKENS:
            while tokens >= MAX_MEMORY_RULE_TOKENS:
                if len(rule_text) > 24:
                    rule_text = rule_text[:-5].strip() + "..."
                    tokens = count_tokens(rule_text)
                else:
                    rule_text = "[REGLA_OPERACIONAL] ..."
                    tokens = count_tokens(rule_text)
                    break

        now = datetime.utcnow()
        timestamp_str = now.strftime("%Y%m%d%H%M%S%f")
        rand_suffix = uuid.uuid4().hex[:6]
        rule_id = f"RULE-{timestamp_str}-{rand_suffix}"
        entry_id = f"FEEDBACK-{timestamp_str}-{rand_suffix}"
        now_iso = now.isoformat() + "Z"

        # 1. SQLite Persistence
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO living_memory_rules (
                id, case_id, raw_reason, distilled_rule, zone_affected,
                mitigation_actions, token_count, active, supervisor_name, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """, (
            rule_id, case_id, clean_rej, rule_text, zone,
            json.dumps(mitigations, ensure_ascii=False), tokens, clean_sup, now_iso
        ))
        cur.execute("""
            INSERT INTO feedback_history (
                entry_id, case_id, timestamp, supervisor_name, action,
                rejected_reason, distilled_rule, token_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry_id, case_id, now_iso, clean_sup, "REJECT",
            clean_rej, rule_text, tokens
        ))
        conn.commit()
        conn.close()

        # 2. JSON Synchronization
        self._sync_to_json()

        return {
            "rule_id": rule_id,
            "entry_id": entry_id,
            "case_id": case_id,
            "distilled_rule": rule_text,
            "mitigation_actions": mitigations,
            "zone_affected": zone,
            "token_count": tokens,
            "active": True,
        }

    def _sync_to_json(self) -> None:
        """Flushes SQLite living_memory_rules and feedback_history to JSON."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT id, case_id, raw_reason, distilled_rule, zone_affected, mitigation_actions, token_count, active, supervisor_name, created_at FROM living_memory_rules ORDER BY created_at ASC")
        rule_rows = cur.fetchall()

        cur.execute("SELECT entry_id, case_id, timestamp, supervisor_name, action, rejected_reason, distilled_rule, token_count FROM feedback_history ORDER BY timestamp ASC")
        feed_rows = cur.fetchall()
        conn.close()

        rules_list = []
        active_rules_list = []
        for r in rule_rows:
            obj = {
                "id": r[0],
                "case_id": r[1],
                "raw_reason": r[2],
                "distilled_rule": r[3],
                "zone_affected": r[4],
                "mitigation_actions": json.loads(r[5]) if r[5] else [],
                "token_count": r[6],
                "active": bool(r[7]),
                "supervisor_name": r[8],
                "created_at": r[9],
            }
            rules_list.append(obj)
            if obj["active"]:
                active_rules_list.append(obj)

        feedback_list = []
        for f in feed_rows:
            feedback_list.append({
                "entry_id": f[0],
                "case_id": f[1],
                "timestamp": f[2],
                "supervisor_name": f[3],
                "action": f[4],
                "rejected_reason": f[5],
                "distilled_rule": f[6],
                "token_count": f[7],
            })

        # Load existing json to preserve proposals_log
        existing = {}
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as fp:
                    existing = json.load(fp)
            except Exception:
                existing = {}

        existing["active_rules"] = active_rules_list
        existing["living_memory_rules"] = rules_list
        existing["feedback_history"] = feedback_list
        existing["bitacora_feedback"] = feedback_list

        tmp_path = str(self.storage_path) + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as fp:
            json.dump(existing, fp, indent=2, ensure_ascii=False)
        os.replace(tmp_path, self.storage_path)

    def get_active_rules(self, zone: Optional[str] = None, deduplicate: bool = True) -> List[Dict[str, Any]]:
        """Retrieves active living memory rules from SQLite, optionally filtered by zone and deduplicated."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        if zone:
            norm_zone = zone.strip().upper()
            cur.execute("""
                SELECT id, case_id, distilled_rule, zone_affected, mitigation_actions, token_count
                FROM living_memory_rules
                WHERE active = 1 AND (UPPER(zone_affected) = ? OR zone_affected = 'GENERAL')
                ORDER BY created_at DESC
            """, (norm_zone,))
        else:
            cur.execute("""
                SELECT id, case_id, distilled_rule, zone_affected, mitigation_actions, token_count
                FROM living_memory_rules
                WHERE active = 1
                ORDER BY created_at DESC
            """)
        rows = cur.fetchall()
        conn.close()

        raw_rules = [{
            "id": r[0],
            "case_id": r[1],
            "distilled_rule": r[2],
            "zone_affected": r[3],
            "mitigation_actions": json.loads(r[4]) if r[4] else [],
            "token_count": r[5],
        } for r in rows]

        if not deduplicate:
            return raw_rules

        seen_rules = set()
        deduped = []
        for r in raw_rules:
            rule_key = r["distilled_rule"].strip()
            if rule_key not in seen_rules:
                seen_rules.add(rule_key)
                deduped.append(r)
        return deduped

    def format_prompt_injection(self, zone: Optional[str] = None) -> str:
        """Formats active living memory rules into a token-efficient prompt block."""
        rules = self.get_active_rules(zone)
        if not rules:
            return ""
        lines = ["### REGLAS OPERACIONALES ACTIVAS (MEMORIA VIVA - SUPERVISIÓN HUMANA):"]
        for r in rules:
            lines.append(f"- {r['distilled_rule']} (ID: {r['id']})")
        return "\n".join(lines)

    def reset_memory(self) -> None:
        """Clears memory rules for clean test passes and resets."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("DELETE FROM living_memory_rules")
        cur.execute("DELETE FROM feedback_history")
        conn.commit()
        conn.close()
        self._sync_to_json()
