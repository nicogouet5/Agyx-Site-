"""
app/models/__init__.py
Unified models re-export package.
Enforces clean imports across the application.
"""
from app.models.fleet import (
    Truck,
    FleetQueryRequest,
    FleetQueryResponse,
    TruckCandidate,
    MaintenanceLockInfo,
)
from app.models.restrictions import (
    UrbanRestriction,
    RouteVerificationRequest,
    RouteVerificationResponse,
)
from app.models.dispatch import (
    DispatchOrderInput,
    ProposalR4R,
    EvaluationResult,
)
from app.models.review import (
    ReviewActionRequest,
    ReviewActionResponse,
    InactivitySimulationRequest,
    InactivitySimulationResponse,
)
from app.models.memory import (
    LivingMemoryRule,
    FeedbackLogEntry,
    LivingMemoryState,
    calculate_token_count,
)

__all__ = [
    "Truck",
    "FleetQueryRequest",
    "FleetQueryResponse",
    "TruckCandidate",
    "MaintenanceLockInfo",
    "UrbanRestriction",
    "RouteVerificationRequest",
    "RouteVerificationResponse",
    "DispatchOrderInput",
    "ProposalR4R",
    "EvaluationResult",
    "ReviewActionRequest",
    "ReviewActionResponse",
    "InactivitySimulationRequest",
    "InactivitySimulationResponse",
    "LivingMemoryRule",
    "FeedbackLogEntry",
    "LivingMemoryState",
    "calculate_token_count",
]
