"""
app/models/memory.py
Data models for the Living Memory (Memoria Viva) and human feedback log.
Enforces distilled rule compactness (< 80 tokens) and dynamic rule injection.
Built with pure Python standard library dataclasses for zero-dependency execution.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
import json
import re


def calculate_token_count(text: str) -> int:
    """Exact token counter using regex pattern \\w+|[^\\w\\s]."""
    if not text:
        return 0
    return len(re.findall(r"\w+|[^\w\s]", text))


@dataclass
class LivingMemoryRule:
    rule_id: str
    source_case_id: str
    created_at: str
    author: str
    raw_rejection: str
    distilled_rule: str
    zone: str
    threshold_weight_kg: float = 5000.0
    is_active: bool = True
    applied_count: int = 0
    token_count: int = 0

    def __post_init__(self):
        self.threshold_weight_kg = float(self.threshold_weight_kg)
        if isinstance(self.is_active, str):
            self.is_active = self.is_active.lower() in ("true", "1", "yes")
        else:
            self.is_active = bool(self.is_active)
        self.token_count = calculate_token_count(self.distilled_rule)
        # Token budget verification: must be < 80 tokens
        if self.token_count >= 80:
            raise ValueError(f"Living memory distilled rule exceeds 80 tokens budget: {self.token_count} tokens")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LivingMemoryRule":
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in fields})


@dataclass
class FeedbackLogEntry:
    entry_id: str
    case_id: str
    timestamp: str
    supervisor_name: str
    action: str
    rejected_reason: str
    distilled_rule: str
    token_count: int = 0

    def __post_init__(self):
        self.token_count = calculate_token_count(self.distilled_rule)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FeedbackLogEntry":
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in fields})


@dataclass
class LivingMemoryState:
    rules: List[LivingMemoryRule] = field(default_factory=list)
    feedback_history: List[FeedbackLogEntry] = field(default_factory=list)
    active_rules_count: int = 0
    total_tokens: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rules": [r.to_dict() for r in self.rules],
            "feedback_history": [f.to_dict() for f in self.feedback_history],
            "active_rules_count": self.active_rules_count,
            "total_tokens": self.total_tokens,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)
