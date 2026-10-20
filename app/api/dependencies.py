"""
app/api/dependencies.py
Unified service container and dependency injection provider for Agyx.
Provides shared singleton instances of FleetService, RestrictionService,
MemoryService, R4RService, LocalAgentEngine, and GeminiAgentEngine.
Supports both FastAPI Depends() and direct Python stdlib invocation.
"""
from typing import Optional
from app.services.db_service import init_db
from app.services.fleet_service import FleetService
from app.services.restriction_service import RestrictionService
from app.services.memory_service import MemoryService
from app.services.r4r_service import R4RService
from app.engine.local_engine import LocalAgentEngine
from app.engine.gemini_engine import GeminiAgentEngine
from app.config import SQLITE_DB_PATH, MEMORY_JSON_PATH


class ServiceContainer:
    _instance: Optional["ServiceContainer"] = None

    def __init__(
        self,
        db_path: Optional[str] = None,
        memory_path: Optional[str] = None,
    ):
        self.db_path = db_path or SQLITE_DB_PATH
        self.memory_path = memory_path or MEMORY_JSON_PATH
        # Ensure database tables exist
        init_db(self.db_path)

        # Domain Services
        self.fleet_service = FleetService()
        self.restriction_service = RestrictionService()
        self.memory_service = MemoryService(
            storage_path=self.memory_path,
            db_path=self.db_path,
        )
        self.r4r_service = R4RService(
            memory_service=self.memory_service,
            db_path=self.db_path,
            storage_path=self.memory_path,
        )

        # Operational Agent Engines
        self.local_engine = LocalAgentEngine(
            fleet_service=self.fleet_service,
            restriction_service=self.restriction_service,
            memory_service=self.memory_service,
            r4r_service=self.r4r_service,
        )
        self.gemini_engine = GeminiAgentEngine(
            memory_service=self.memory_service,
            fleet_service=self.fleet_service,
            restriction_service=self.restriction_service,
            r4r_service=self.r4r_service,
        )

    @classmethod
    def get_instance(cls) -> "ServiceContainer":
        """Returns the shared application service container singleton."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Resets the singleton for clean isolated testing."""
        cls._instance = None


def get_services() -> ServiceContainer:
    """FastAPI dependency provider."""
    return ServiceContainer.get_instance()
