from enum import Enum

class AgentOperationalState(str, Enum):
    OFFLINE = "Offline"
    STARTING = "Starting"
    IDLE = "IDLE"
    BUSY = "Busy"
    WORKING = "Working"
    TOOLSCALL = "Toolscall"
    TASKCOMPLETED = "TaskCompleted"
    TASKFAILED = "TaskFailed"
    SLEEPING = "Sleeping"
    ERROR = "Error"