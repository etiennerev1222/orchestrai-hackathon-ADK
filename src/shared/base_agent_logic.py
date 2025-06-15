# src/shared/base_agent_logic.py
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

class BaseAgentLogic(ABC):
    """
    Classe de base abstraite pour la logique métier des agents.
    Chaque agent spécifique devra hériter de cette classe et implémenter la méthode 'process'.
    """
    def __init__(self):
        self.environment_manager = None # Add this attribute
        logger.info(f"Logique d'agent de type '{self.__class__.__name__}' initialisée.")

    def set_environment_manager(self, manager: Any): # Accept Any for now to avoid circular imports
        self.environment_manager = manager
        logger.info(f"EnvironmentManager set for {self.__class__.__name__}.")

    @abstractmethod
    async def process(self, input_data: Any, context_id: str | None = None) -> Any:
        """
        Méthode principale pour traiter les données d'entrée.
        Cette méthode doit être implémentée par les classes filles.

        Args:
            input_data: Les données d'entrée à traiter par l'agent.
                        Le type peut varier en fonction de l'agent (ex: str, dict).
            context_id: Un ID de contexte optionnel pour le suivi.

        Returns:
            Les données résultant du traitement. Le type peut varier.
        """
        pass