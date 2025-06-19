from enum import Enum

class AgentOperationalState(str, Enum):
    OFFLINE = "Offline"
    STARTING = "Starting"
    IDLE = "IDLE"
    BUSY = "Busy"
    SLEEPING = "Sleeping"
    ERROR = "Error"