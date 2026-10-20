"""
app/engine/__init__.py
Agent engine package initialization and engine factory.
"""
from typing import Optional
from app.engine.base import BaseAgentEngine
from app.engine.local_engine import LocalAgentEngine
from app.engine.gemini_engine import GeminiAgentEngine


def get_agent_engine(
    engine_type: Optional[str] = None,
    api_key: Optional[str] = None,
) -> BaseAgentEngine:
    """
    Engine factory returning the requested engine or the default zero-token local engine.
    """
    mode = (engine_type or "local").strip().lower()
    if mode == "gemini":
        engine = GeminiAgentEngine(api_key=api_key)
        return engine
    return LocalAgentEngine()


__all__ = [
    "BaseAgentEngine",
    "LocalAgentEngine",
    "GeminiAgentEngine",
    "get_agent_engine",
]
