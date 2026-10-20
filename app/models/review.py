"""
app/models/review.py
Data models for human supervisor actions (APPROVE, REJECT) and inactivity safeguards.
Enforces non-empty rejected_reason on rejection and zero auto-approval on timeout.
Built with pure Python standard library dataclasses for zero-dependency execution.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
import json
import datetime


import unicodedata


def clean_human_text(text: Any) -> str:
    """
    Sanitizes human-entered text (supervisor signatures, rejection reasons) by:
    1. Eliminating invisible formatting, zero-width codes, surrogates, and unassigned characters
       (Unicode category 'Cf' e.g. \\u200B ZWSP, \\u200C ZWNJ, \\u200D ZWJ, \\uFEFF BOM; 'Cs'; 'Co'; 'Cn').
    2. Filtering out unprintable control characters (category 'Cc' except standard intra-text whitespace).
    3. Stripping all leading and trailing whitespace, Unicode separators (category 'Z'),
       and control/format characters (category 'C').
    Returns an empty string '' if no substantive human text remains.
    """
    if text is None:
        return ""
    raw = str(text)
    if not raw:
        return ""

    # Remove invisible formatting, zero-width characters, surrogates, and unassigned characters
    cleaned_chars = []
    for ch in raw:
        cat = unicodedata.category(ch)
        if cat in ("Cf", "Cs", "Co", "Cn"):
            continue
        if cat == "Cc" and ch not in ("\n", "\r", "\t", " "):
            continue
        cleaned_chars.append(ch)

    s = "".join(cleaned_chars)

    # Strip leading and trailing whitespace, Unicode category Z (separators) and category C
    start = 0
    end = len(s)
    while start < end:
        ch = s[start]
        cat = unicodedata.category(ch)
        if ch.isspace() or cat.startswith("Z") or cat.startswith("C"):
            start += 1
        else:
            break

    while end > start:
        ch = s[end - 1]
        cat = unicodedata.category(ch)
        if ch.isspace() or cat.startswith("Z") or cat.startswith("C"):
            end -= 1
        else:
            break

    return s[start:end]


@dataclass
class ReviewActionRequest:
    case_id: str
    action: str
    supervisor_name: str
    rejected_reason: Optional[str] = None
    signature_token: Optional[str] = None

    def __post_init__(self):
        self.action = (self.action or "").strip().upper()
        if self.action not in ("APPROVE", "REJECT"):
            raise ValueError(f"Invalid review action: '{self.action}'. Must be 'APPROVE' or 'REJECT'")
        clean_sup = clean_human_text(self.supervisor_name)
        if not clean_sup:
            raise ValueError("supervisor_name is mandatory for supervisor review actions")
        self.supervisor_name = clean_sup
        if self.action == "REJECT":
            clean_rej = clean_human_text(self.rejected_reason)
            if not clean_rej:
                raise ValueError("Validation Error: rejected_reason cannot be empty or whitespace when rejecting a proposal")
            self.rejected_reason = clean_rej
        else:
            self.rejected_reason = clean_human_text(self.rejected_reason) if self.rejected_reason else None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewActionRequest":
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in fields})


@dataclass
class ReviewActionResponse:
    success: bool
    case_id: str
    previous_status: str
    new_status: str  # APPROVED, REJECTED
    auto_approved: bool = False  # NEVER True
    supervisor_name: str = ""
    review_timestamp: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z")
    rejected_reason: Optional[str] = None
    distilled_rule_created: Optional[str] = None
    tokens_used: int = 0
    message: str = ""

    def __post_init__(self):
        if self.auto_approved is True:
            raise ValueError("Zero auto-approval invariant: auto_approved cannot be True")
        self.auto_approved = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class InactivitySimulationRequest:
    case_id: str
    idle_minutes: int = 60

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class InactivitySimulationResponse:
    case_id: str
    status: str = "R4R"
    auto_approved: bool = False  # STRICT GOVERNANCE: Always False
    idle_minutes_simulated: int = 60
    message: str = "Order remains strictly locked in R4R upon operator inactivity; zero auto-approval guaranteed."

    def __post_init__(self):
        self.auto_approved = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
