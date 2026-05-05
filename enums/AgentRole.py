from enum import Enum

class AgentRole(str, Enum):
    MEMBER      = "member"
    HEAD        = "head"
    MONITOR     = "monitor"
    GATEKEEPER  = "gatekeeper"