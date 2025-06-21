import logging
import collections
from typing import Deque

class InMemoryLogHandler(logging.Handler):
    """
    Un gestionnaire de logs qui conserve les N derniers enregistrements en mémoire.
    """
    def __init__(self, maxlen: int = 100):
        super().__init__()
        # On utilise une deque (double-ended queue) avec une taille maximale.
        # C'est très efficace : quand un nouvel élément est ajouté et que la
        # taille est dépassée, l'élément le plus ancien est automatiquement supprimé.
        self.log_deque: Deque[str] = collections.deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord):
        """
        À chaque fois qu'un log est émis, on l'ajoute à notre deque.
        `self.format(record)` transforme l'enregistrement de log en chaîne de caractères.
        """
        self.log_deque.append(self.format(record))

    def get_logs(self) -> list[str]:
        """
        Retourne la liste des logs stockés.
        """
        return list(self.log_deque)