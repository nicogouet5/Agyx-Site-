"""Small, dependency-free safeguards for destructive demo endpoints.

Agyx remains frictionless in local/academic mode.  In production-like deployments,
resetting or seeding the learning memory and running the destructive full demo needs a
server-side token.  This is deliberately not a substitute for real authentication;
it prevents accidental public mutation while keeping the prototype easy to run.
"""
import hmac
from typing import Any, Dict, Optional, Tuple

from app.config import demo_admin_actions_enabled, DEMO_ADMIN_TOKEN


def require_demo_admin(provided_token: Optional[str]) -> Tuple[bool, Dict[str, Any]]:
    """Authorize a destructive demo action, returning an API-safe error on failure."""
    if demo_admin_actions_enabled():
        return True, {}

    if DEMO_ADMIN_TOKEN and provided_token and hmac.compare_digest(
        str(provided_token), DEMO_ADMIN_TOKEN
    ):
        return True, {}

    return False, {
        "error": "DEMO_ADMIN_AUTH_REQUIRED",
        "detail": (
            "Esta acción modifica el estado de demostración y está deshabilitada en "
            "producción. Configure DEMO_ADMIN_TOKEN y envíelo en X-Agyx-Demo-Token."
        ),
    }
