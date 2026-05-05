from enum import Enum

class AgentStatus(str, Enum):
    ACTIVE_MEMBER = "active_member"
    INACTIVE_MEMBER = "inactive_member"       # sanctioned, cannot demand
    ACTIVE_NONMEMBER = "active_nonmember"     # excluded
    INACTIVE_NONMEMBER = "inactive_nonmember" # eliminated