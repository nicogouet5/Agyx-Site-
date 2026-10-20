"""
app/engine/base.py
Base abstract interface for Agyx operational AI agent engines.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseAgentEngine(ABC):
    @abstractmethod
    def evaluate_order(self, order: Dict[str, Any], v1_mode: bool = False) -> Dict[str, Any]:
        """
        Evaluates a dispatch order against fleet, urban restrictions, and living memory.
        Returns evaluation result dictionary with proposal in R4R state.
        """
        pass
